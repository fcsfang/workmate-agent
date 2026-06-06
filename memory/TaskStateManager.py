import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class TaskStateManager:
    def __init__(self, state_path: Optional[str] = None):
        memory_dir = Path(__file__).resolve().parent
        self.state_path = Path(state_path) if state_path else memory_dir / "task_state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists() or self.state_path.stat().st_size == 0:
            return self.default_state()

        try:
            with self.state_path.open("r", encoding="utf-8") as file:
                state = json.load(file)
        except json.JSONDecodeError:
            return self.default_state()

        if not isinstance(state, dict):
            return self.default_state()
        return self._sanitize_state({**self.default_state(), **state})

    def save_state(self, state: Dict[str, Any]) -> None:
        with self.state_path.open("w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)

    def update(
        self,
        extracted: Dict[str, Any],
        user_input: str,
        assistant_output: str,
        task_lifecycle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = self.load_state()
        now = datetime.now().isoformat(timespec="seconds")
        task_lifecycle = task_lifecycle or {}

        task = task_lifecycle.get("title") or extracted.get("task")
        if task:
            state["active_task"] = task
            state["task_id"] = task_lifecycle.get("id", state.get("task_id", ""))
            if task_lifecycle.get("status"):
                state["status"] = self._state_status(task_lifecycle["status"])
            elif state.get("status") == "idle":
                state["status"] = "in_progress"
            if not state.get("started_at"):
                state["started_at"] = now

        progress = extracted.get("progress") or self._last_item(task_lifecycle.get("progress"))
        if progress:
            state["current_progress"] = progress
            state["status"] = self._state_status(task_lifecycle.get("status")) or self._status_from_progress(progress)

        blockers = task_lifecycle.get("blockers") or extracted.get("blockers") or []
        if blockers:
            state["blockers"] = self._merge_unique(state.get("blockers", []), blockers, limit=8)

        subtasks = task_lifecycle.get("subtasks") or extracted.get("subtasks") or []
        state["subtasks"] = self._subtasks(subtasks)

        next_actions = task_lifecycle.get("next_actions") or extracted.get("next_actions") or []
        if next_actions:
            state["next_action"] = next_actions[0]
            state["next_actions"] = self._merge_unique(next_actions, state.get("next_actions", []), limit=8)

        state["updated_at"] = now
        state["last_user_input"] = self._compact(user_input)
        state["last_agent_response"] = self._compact(assistant_output)
        state["events"] = self._append_event(state.get("events", []), now, extracted)
        state.pop("evidence_required", None)
        self.save_state(state)
        return state

    def format_for_context(self) -> str:
        state = self.load_state()
        lines = [
            "以下是当前任务状态。请优先用它判断用户是否偏离主线、是否完成了承诺、下一步该做什么。",
            f"状态: {state.get('status') or 'idle'}",
            f"当前任务: {state.get('active_task') or '暂无'}",
            f"当前进度: {state.get('current_progress') or '暂无'}",
            f"下一步: {state.get('next_action') or '暂无'}",
        ]

        if state.get("blockers"):
            lines.append("阻塞/风险: " + "、".join(state["blockers"][:5]))
        if state.get("subtasks"):
            formatted = [
                f"{item.get('title')}({item.get('status', 'planned')})"
                for item in state["subtasks"][:5]
            ]
            lines.append("子任务: " + "；".join(formatted))
        if state.get("updated_at"):
            lines.append(f"更新时间: {state['updated_at']}")
        return "\n".join(lines)

    def default_state(self) -> Dict[str, Any]:
        return {
            "status": "idle",
            "task_id": "",
            "active_task": "",
            "started_at": "",
            "updated_at": "",
            "current_progress": "",
            "next_action": "",
            "next_actions": [],
            "subtasks": [],
            "blockers": [],
            "last_user_input": "",
            "last_agent_response": "",
            "events": [],
        }

    def _status_from_progress(self, progress: str) -> str:
        if any(keyword in progress for keyword in ["完成了", "做完了", "全部", "结束"]):
            return "in_progress"
        return "in_progress"

    def _state_status(self, lifecycle_status: Optional[str]) -> str:
        mapping = {
            "inbox": "idle",
            "planned": "planned",
            "active": "in_progress",
            "blocked": "blocked",
            "done": "done",
            "abandoned": "abandoned",
        }
        return mapping.get(lifecycle_status or "", "")

    def _append_event(self, events, time_text: str, extracted: Dict[str, Any]):
        event = {
            "time": time_text,
            "categories": extracted.get("categories", []),
            "task": extracted.get("task", ""),
            "progress": extracted.get("progress", ""),
            "blockers": extracted.get("blockers", []),
        }
        return [*events, event][-20:]

    def _last_item(self, items) -> str:
        if isinstance(items, list) and items:
            return items[-1]
        return ""

    def _subtasks(self, value) -> list:
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            if isinstance(item, dict):
                title = self._compact(item.get("title", ""), 140)
                status = item.get("status", "planned")
            else:
                title = self._compact(item, 140)
                status = "planned"
            if title:
                result.append({"title": title, "status": status})
        return result[:10]

    def _merge_unique(self, first, second, limit: int):
        merged = []
        for item in [*first, *second]:
            if item and item not in merged:
                merged.append(item)
        return merged[:limit]

    def _sanitize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state.pop("evidence_required", None)
        for key in ["blockers", "next_actions"]:
            values = state.get(key, [])
            if isinstance(values, list):
                state[key] = [value for value in values if not self._looks_like_forced_proof(value)]
        events = []
        for event in state.get("events", []):
            if not isinstance(event, dict):
                continue
            event = dict(event)
            blockers = event.get("blockers", [])
            if isinstance(blockers, list):
                event["blockers"] = [value for value in blockers if not self._looks_like_forced_proof(value)]
            events.append(event)
        state["events"] = events[-20:]
        return state

    def _looks_like_forced_proof(self, text: str) -> bool:
        return any(keyword in str(text) for keyword in ["证据", "截图", "截屏", "拒绝验证", "验证证据", "合格证据"])

    def _compact(self, text: str, max_length: int = 180) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
