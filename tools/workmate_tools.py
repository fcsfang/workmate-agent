import hashlib
from datetime import datetime
from typing import Any, Dict, List

from .registry import ToolRegistry


VALID_TASK_STATUSES = {"inbox", "planned", "active", "blocked", "done", "abandoned"}


def build_workmate_tool_registry(memory_manager: Any) -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        "get_current_task",
        "读取当前最相关的任务。只读，不修改状态。",
        {"type": "object", "properties": {}, "required": []},
        lambda args: {"current_task": memory_manager.get_task_view().get("current", {})},
    )

    registry.register(
        "list_open_tasks",
        "列出未关闭任务。只读，不修改状态。",
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 12}
            },
            "required": [],
        },
        lambda args: _list_open_tasks(memory_manager, args),
    )

    registry.register(
        "update_task_status",
        "更新已有任务状态。只能在用户明确完成、开始、阻塞或放弃时调用；不能创建新任务。",
        {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {"type": "string", "enum": sorted(VALID_TASK_STATUSES)},
                "reason": {"type": "string"},
            },
            "required": ["task_id", "status", "reason"],
        },
        lambda args: _update_task_status(memory_manager, args),
    )

    registry.register(
        "list_open_commitments",
        "列出未关闭承诺。只读，不修改状态。",
        {"type": "object", "properties": {}, "required": []},
        lambda args: {"open_commitments": memory_manager.get_open_commitments()},
    )

    registry.register(
        "search_memory",
        "检索 Workmate Agent 的长期记忆。只读，不修改状态。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["query"],
        },
        lambda args: _search_memory(memory_manager, args),
    )

    registry.register(
        "add_memory_note",
        "写入一条内部备注。只用于用户明确要求记录稳定事实或补充记忆时。",
        {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "category": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["content"],
        },
        lambda args: _add_memory_note(memory_manager, args),
    )

    registry.register(
        "start_focus_session",
        (
            "开始一段专注会话。"
            "只在用户明确表示接下来要去做某件具体的事（如'我去写代码了'/'开始专注45分钟'）时调用。"
            "普通聊天、计划讨论、模糊意图时不调用。"
        ),
        {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "这段专注时间要做的事"},
                "duration_minutes": {"type": "integer", "minimum": 5, "maximum": 240, "description": "计划专注时长（分钟），默认45"},
            },
            "required": ["goal"],
        },
        lambda args: _start_focus_session(memory_manager, args),
    )

    registry.register(
        "complete_focus_session",
        (
            "标记当前专注会话为完成。"
            "只在用户回来汇报刚才的任务完成了时调用。"
            "如果用户只是回来聊天或没有进行中的专注会话，不调用。"
        ),
        {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "description": "完成了什么，可选"},
            },
            "required": [],
        },
        lambda args: _complete_focus_session(memory_manager, args),
    )

    registry.register(
        "abandon_focus_session",
        (
            "放弃或中断当前专注会话。"
            "只在用户明确说被打断、放弃或没做成时调用。"
            "如果没有进行中的专注会话，不调用。"
        ),
        {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "description": "发生了什么，可选"},
            },
            "required": [],
        },
        lambda args: _abandon_focus_session(memory_manager, args),
    )

    return registry


def _list_open_tasks(memory_manager: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    limit = _bounded_int(args.get("limit", 8), 1, 12)
    view = memory_manager.get_task_view(limit=limit)
    tasks = view.get("active", [])
    return {
        "open_tasks": tasks[:limit],
        "counts": view.get("counts", {}),
    }


def _update_task_status(memory_manager: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()
    status = str(args.get("status", "")).strip().lower()
    reason = _compact(args.get("reason", ""), 220)
    if not task_id:
        raise ValueError("task_id is required")
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"invalid status: {status}")
    if not reason:
        raise ValueError("reason is required")

    task_manager = memory_manager.task_state.task_manager
    tasks = task_manager.load_tasks()
    task = next((item for item in tasks if item.get("id") == task_id), None)
    if not task:
        raise ValueError(f"task not found: {task_id}")

    now = datetime.now().isoformat(timespec="seconds")
    previous = task.get("status", "inbox")
    task["status"] = status
    task["updated_at"] = now
    if status == "active" and not task.get("started_at"):
        task["started_at"] = now
    if status == "done":
        task["completed_at"] = task.get("completed_at") or now
    if status == "abandoned":
        task["abandoned_at"] = task.get("abandoned_at") or now
    if reason:
        progress = task.get("progress", [])
        if isinstance(progress, list) and reason not in progress:
            task["progress"] = [*progress, reason][-12:]

    task_manager.save_tasks(task_manager._sort_tasks(tasks))
    task_manager._append_event(
        "tool_status_updated",
        task,
        now,
        {"from": previous, "to": status, "reason": reason},
    )
    _sync_current_state(memory_manager, task)
    return {
        "task_id": task_id,
        "title": task.get("title", ""),
        "previous_status": previous,
        "status": status,
        "reason": reason,
    }


def _sync_current_state(memory_manager: Any, task: Dict[str, Any]) -> None:
    state_manager = memory_manager.task_state.task_state_manager
    state = state_manager.load_state()
    if task.get("id") and (
        state.get("task_id") == task.get("id") or task.get("status") in {"active", "blocked", "planned", "inbox"}
    ):
        state["task_id"] = task.get("id", "")
        state["active_task"] = task.get("title", "")
        state["status"] = task.get("status", "")
        state["current_progress"] = "；".join((task.get("progress") or [])[-2:])
        state["next_action"] = "；".join((task.get("next_actions") or [])[:2])
        state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        state_manager.save_state(state)


def _search_memory(memory_manager: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    query = _compact(args.get("query", ""), 160)
    if not query:
        raise ValueError("query is required")
    limit = _bounded_int(args.get("limit", 5), 1, 8)
    return {
        "query": query,
        "results": memory_manager.search_related_memories(query, limit=limit),
    }


def _add_memory_note(memory_manager: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    content = _compact(args.get("content", ""), 320)
    if not content:
        raise ValueError("content is required")
    category = _compact(args.get("category", "general"), 80) or "general"
    reason = _compact(args.get("reason", ""), 180)
    now = datetime.now().isoformat(timespec="seconds")
    item = {
        "id": _note_id(now, content),
        "type": "note",
        "category": category,
        "content": content,
        "task_id": "",
        "source_record_ids": [],
        "confidence": 0.75,
        "salience": 0.55,
        "status": "active",
        "metadata": {"reason": reason, "source": "tool:add_memory_note"},
        "dedupe_key": "tool_note|" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
        "task_title": "",
        "created_at": now,
        "updated_at": now,
        "last_accessed_at": "",
        "usage_count": 0,
    }
    items = memory_manager.memory_item_manager.load_items()
    if not any(existing.get("dedupe_key") == item["dedupe_key"] for existing in items):
        items.append(item)
        memory_manager.memory_item_manager.save_items(items)
        memory_manager.memory_category_manager.rebuild_from_items(items)
        memory_manager.refresh_search_index(memory_items=items)
        created = True
    else:
        created = False
    return {
        "created": created,
        "note": item,
    }


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def _note_id(now: str, content: str) -> str:
    safe_time = now.replace("-", "").replace(":", "").replace("T", "-")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    return f"note-{safe_time}-{digest}"


def _start_focus_session(memory_manager: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    goal = _compact(args.get("goal", ""), 180)
    if not goal:
        raise ValueError("goal is required")
    duration_minutes = _bounded_int(args.get("duration_minutes", 45), 5, 240)
    session = memory_manager.start_focus_session(goal, duration_minutes=duration_minutes)
    return {
        "started": True,
        "goal": session.get("goal", ""),
        "duration_minutes": session.get("duration_minutes", 0),
        "started_at": session.get("started_at", ""),
        "expected_end_at": session.get("expected_end_at", ""),
    }


def _complete_focus_session(memory_manager: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    outcome = _compact(args.get("outcome", ""), 220)
    try:
        session = memory_manager.complete_focus_session(outcome=outcome)
        return {
            "completed": True,
            "goal": session.get("goal", ""),
            "elapsed_minutes": session.get("elapsed_minutes", 0),
            "outcome": session.get("outcome", ""),
        }
    except ValueError as exc:
        return {"completed": False, "reason": str(exc)}


def _abandon_focus_session(memory_manager: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    outcome = _compact(args.get("outcome", ""), 220)
    try:
        session = memory_manager.abandon_focus_session(outcome=outcome)
        return {
            "abandoned": True,
            "goal": session.get("goal", ""),
            "elapsed_minutes": session.get("elapsed_minutes", 0),
            "outcome": session.get("outcome", ""),
        }
    except ValueError as exc:
        return {"abandoned": False, "reason": str(exc)}


def _compact(text: Any, max_length: int = 160) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."

