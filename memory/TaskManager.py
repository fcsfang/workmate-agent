import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskManager:
    VALID_STATUSES = {"inbox", "planned", "active", "blocked", "done", "abandoned"}

    def __init__(
        self,
        tasks_path: Optional[str] = None,
        events_path: Optional[str] = None,
        llm_client: Optional[Any] = None,
    ):
        memory_dir = Path(__file__).resolve().parent
        self.tasks_path = Path(tasks_path) if tasks_path else memory_dir / "tasks.json"
        self.events_path = Path(events_path) if events_path else memory_dir / "task_events.json"
        self.llm_client = llm_client
        self.tasks_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def load_tasks(self) -> List[Dict[str, Any]]:
        return self._load_list(self.tasks_path)

    def save_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        self._save_list(self.tasks_path, tasks)

    def load_events(self) -> List[Dict[str, Any]]:
        return self._load_list(self.events_path)

    def save_events(self, events: List[Dict[str, Any]]) -> None:
        self._save_list(self.events_path, events)

    def update(
        self,
        extracted: Dict[str, Any],
        user_input: str,
        assistant_output: str,
    ) -> Dict[str, Any]:
        tasks = self.load_tasks()
        now = datetime.now()
        now_text = now.isoformat(timespec="seconds")

        task_title = self._compact(extracted.get("task", ""), 160)
        progress = self._compact(extracted.get("progress", ""), 180)
        blockers = self._list(extracted.get("blockers"))
        next_actions = self._list(extracted.get("next_actions"))
        user_commitments = self._list(extracted.get("user_commitments"))
        subtasks = self._subtasks(extracted.get("subtasks"))

        task = self._select_task(tasks, task_title)
        if not task and task_title:
            task = self._new_task(task_title, now_text)
            tasks.append(task)
            self._append_event("created", task, now_text, {"title": task_title})

        if task:
            previous_status = task.get("status", "inbox")
            lifecycle_decision = self._interpret_lifecycle_with_llm(
                task,
                extracted,
                user_input,
                assistant_output,
            )
            self._apply_turn(
                task,
                extracted,
                progress,
                blockers,
                next_actions,
                user_commitments,
                subtasks,
                now,
                lifecycle_decision,
            )
            if task.get("status") != previous_status:
                self._append_event(
                    "status_changed",
                    task,
                    now_text,
                    {"from": previous_status, "to": task.get("status")},
                )
            self._append_event(
                "turn_updated",
                task,
                now_text,
                {
                    "progress": progress,
                    "blockers": blockers,
                    "next_actions": next_actions[:3],
                    "user_commitments": user_commitments[:3],
                    "subtasks": [subtask["title"] for subtask in subtasks[:5]],
                },
            )
            self.save_tasks(self._sort_tasks(tasks))
            return task

        self.save_tasks(self._sort_tasks(tasks))
        return self.default_task()

    def get_current_task(self) -> Dict[str, Any]:
        tasks = self.load_tasks()
        for status in ["active", "blocked", "planned", "inbox"]:
            candidates = [task for task in tasks if task.get("status") == status]
            if candidates:
                return sorted(candidates, key=lambda task: task.get("updated_at", ""), reverse=True)[0]
        return self.default_task()

    def get_task_view(self, limit: int = 8) -> Dict[str, Any]:
        tasks = self.load_tasks()
        active = [task for task in tasks if task.get("status") in {"active", "blocked", "planned", "inbox"}]
        completed = [task for task in tasks if task.get("status") in {"done", "abandoned"}]
        return {
            "current": self.get_current_task(),
            "active": self._sort_tasks(active)[:limit],
            "recent_completed": self._sort_tasks(completed)[:limit],
            "counts": self._counts(tasks),
        }

    def format_for_context(self) -> str:
        view = self.get_task_view(limit=5)
        current = view["current"]
        if not current.get("id"):
            return "暂无明确任务生命周期记录。"

        lines = [
            "以下是 v0.4.2 任务生命周期记录。请用它记住当前主线、用户明确提出的子任务和任务状态；必要时只给一句轻量提醒。",
            f"当前任务: {current.get('title') or '暂无'}",
            f"状态: {current.get('status') or 'inbox'}",
        ]
        if current.get("progress"):
            lines.append("进展: " + "；".join(current["progress"][-4:]))
        if current.get("subtasks"):
            formatted_subtasks = [
                f"{subtask.get('title')}({subtask.get('status', 'inbox')})"
                for subtask in current["subtasks"][:6]
            ]
            lines.append("子任务: " + "；".join(formatted_subtasks))
        if current.get("blockers"):
            lines.append("阻塞/风险: " + "、".join(current["blockers"][-4:]))
        if current.get("next_actions"):
            lines.append("下一步: " + "；".join(current["next_actions"][:4]))
        if view["active"][1:]:
            related = [f"{task.get('title')}({task.get('status')})" for task in view["active"][1:4]]
            lines.append("其他未关闭任务: " + "；".join(related))
        return "\n".join(lines)

    def default_task(self) -> Dict[str, Any]:
        return {
            "id": "",
            "title": "",
            "status": "inbox",
            "priority": "normal",
            "created_at": "",
            "updated_at": "",
            "started_at": "",
            "completed_at": "",
            "abandoned_at": "",
            "due_at": "",
            "last_user_update_at": "",
            "next_check_at": "",
            "progress": [],
            "subtasks": [],
            "blockers": [],
            "next_actions": [],
            "user_commitments": [],
            "related_record_ids": [],
        }

    def _select_task(self, tasks: List[Dict[str, Any]], task_title: str) -> Optional[Dict[str, Any]]:
        open_tasks = [task for task in tasks if task.get("status") not in {"done", "abandoned"}]
        if task_title:
            for task in open_tasks:
                if self._same_task(task.get("title", ""), task_title):
                    return task
            active = [task for task in open_tasks if task.get("status") in {"active", "blocked"}]
            if active and self._shares_keywords(active[0].get("title", ""), task_title):
                return active[0]
            return None
        if open_tasks:
            return self.get_current_task()
        return None

    def _new_task(self, title: str, now_text: str) -> Dict[str, Any]:
        task = self.default_task()
        task.update({
            "id": self._make_id(now_text, title),
            "title": title,
            "status": "inbox",
            "created_at": now_text,
            "updated_at": now_text,
        })
        return task

    def _apply_turn(
        self,
        task: Dict[str, Any],
        extracted: Dict[str, Any],
        progress: str,
        blockers: List[str],
        next_actions: List[str],
        user_commitments: List[str],
        subtasks: List[Dict[str, str]],
        now: datetime,
        lifecycle_decision: Optional[Dict[str, Any]] = None,
    ) -> None:
        now_text = now.isoformat(timespec="seconds")
        lifecycle_decision = lifecycle_decision or {}
        if extracted.get("task") and not task.get("title"):
            task["title"] = self._compact(extracted["task"], 160)
        if progress:
            task["progress"] = self._merge_unique(task.get("progress", []), [progress], 12)
            task["last_user_update_at"] = now_text
        llm_subtasks = self._subtasks(lifecycle_decision.get("subtask_updates", []))
        if llm_subtasks:
            subtasks = self._merge_subtask_updates(subtasks, llm_subtasks)
        if subtasks:
            task["subtasks"] = self._merge_subtasks(task.get("subtasks", []), subtasks, now_text)
        if blockers:
            task["blockers"] = self._merge_unique(task.get("blockers", []), blockers, 10)
            self._mark_related_subtasks(task, blockers, "blocked", now_text)
        if next_actions:
            task["next_actions"] = self._merge_unique(next_actions, task.get("next_actions", []), 10)
        if user_commitments:
            task["user_commitments"] = self._merge_unique(task.get("user_commitments", []), user_commitments, 10)

        status = self._decision_status(lifecycle_decision.get("task_status", "")) if lifecycle_decision else ""
        status = status or self._infer_status(extracted, task)
        if status == "active" and not task.get("started_at"):
            task["started_at"] = now_text
        if status == "done":
            task["completed_at"] = task.get("completed_at") or now_text
            self._mark_all_open_subtasks(task, "done", now_text)
        if status == "abandoned":
            task["abandoned_at"] = task.get("abandoned_at") or now_text
            self._mark_all_open_subtasks(task, "abandoned", now_text)

        task["status"] = status
        task["updated_at"] = now_text
        task["next_check_at"] = self._next_check_at(status, now)

    def _interpret_lifecycle_with_llm(
        self,
        task: Dict[str, Any],
        extracted: Dict[str, Any],
        user_input: str,
        assistant_output: str,
    ) -> Dict[str, Any]:
        if not self.llm_client:
            return {}
        schema = {
            "task_status": "inbox|planned|active|blocked|done|abandoned",
            "subtask_updates": [
                {
                    "title": "子任务标题，只能使用已有子任务或用户当前明确提出的子任务",
                    "status": "inbox|planned|active|blocked|done|abandoned",
                }
            ],
            "reason": "一句话说明",
            "confidence": 0.0,
        }
        payload = {
            "current_task": task,
            "extracted": extracted,
            "user_input": user_input,
            "assistant_output": assistant_output,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的任务生命周期解释器。"
                    "只根据用户当前输入和结构化提取结果判断任务状态，不要制定技术路线。"
                    "只输出合法 JSON，不要 Markdown，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "要求：\n"
                    "1. 不要因为助手建议而把任务判为完成。\n"
                    "2. 用户明确说完成/放弃/卡住时才更新到 done/abandoned/blocked。\n"
                    "3. 用户只是提出计划时用 planned 或 active，不要夸大进展。\n"
                    "4. subtask_updates 只能包含已有子任务或用户当前明确提出的子任务。\n"
                    "5. 输出字段必须符合 schema。\n\n"
                    f"schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                    f"payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
                ),
            },
        ]
        try:
            raw = self.llm_client.invoke_raw(messages) if hasattr(self.llm_client, "invoke_raw") else self.llm_client.invoke(messages=messages)
            parsed = self._parse_json_object(raw)
            return {
                "task_status": self._decision_status(parsed.get("task_status", "")),
                "subtask_updates": self._subtasks(parsed.get("subtask_updates", [])),
                "reason": self._compact(parsed.get("reason", ""), 180),
                "confidence": self._float(parsed.get("confidence", 0.7)),
            }
        except Exception:
            return {}

    def _infer_status(self, extracted: Dict[str, Any], task: Dict[str, Any]) -> str:
        text = " ".join([
            str(extracted.get("progress", "")),
            " ".join(extracted.get("signals") or []),
            " ".join(extracted.get("categories") or []),
        ])
        if any(keyword in text for keyword in ["放弃", "不做了", "取消", "abandoned"]):
            return "abandoned"
        if any(keyword in text for keyword in ["全部完成", "任务完成", "整体完成", "已经结束", "彻底做完", "done"]):
            return "done"
        if extracted.get("blockers"):
            return "blocked"
        if extracted.get("progress") or extracted.get("next_actions") or task.get("started_at"):
            return "active"
        return task.get("status") if task.get("status") in self.VALID_STATUSES else "inbox"

    def _next_check_at(self, status: str, now: datetime) -> str:
        if status == "blocked":
            return (now + timedelta(minutes=30)).isoformat(timespec="seconds")
        if status == "active":
            return (now + timedelta(minutes=60)).isoformat(timespec="seconds")
        if status == "planned":
            return (now + timedelta(hours=3)).isoformat(timespec="seconds")
        return ""

    def _append_event(self, event_type: str, task: Dict[str, Any], now_text: str, payload: Dict[str, Any]) -> None:
        events = self.load_events()
        events.append({
            "time": now_text,
            "type": event_type,
            "task_id": task.get("id", ""),
            "task_title": task.get("title", ""),
            "payload": payload,
        })
        self.save_events(events[-300:])

    def _load_list(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _save_list(self, path: Path, items: List[Dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(items, file, ensure_ascii=False, indent=2)

    def _sort_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(tasks, key=lambda task: task.get("updated_at", ""), reverse=True)

    def _counts(self, tasks: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {status: 0 for status in sorted(self.VALID_STATUSES)}
        for task in tasks:
            status = task.get("status", "inbox")
            counts[status if status in counts else "inbox"] += 1
        return counts

    def _same_task(self, left: str, right: str) -> bool:
        left = self._compact(left, 160)
        right = self._compact(right, 160)
        return bool(left and right and (left == right or left in right or right in left))

    def _shares_keywords(self, left: str, right: str) -> bool:
        left_terms = set(self._terms(left))
        right_terms = set(self._terms(right))
        return bool(left_terms and right_terms and left_terms.intersection(right_terms))

    def _terms(self, text: str) -> List[str]:
        separators = " \n\t\r，。！？、；;:：/\\|+-_*()（）[]【】{}<>\"'"
        normalized = str(text).lower()
        for separator in separators:
            normalized = normalized.replace(separator, " ")
        return [part for part in normalized.split() if len(part) >= 2]

    def _list(self, value: Any) -> List[str]:
        if isinstance(value, str):
            value = [value] if value else []
        if not isinstance(value, list):
            return []
        return [self._compact(item, 160) for item in value if self._compact(item, 160)]

    def _subtasks(self, value: Any) -> List[Dict[str, str]]:
        if isinstance(value, str):
            value = [value] if value else []
        if not isinstance(value, list):
            return []

        result = []
        for item in value:
            if isinstance(item, dict):
                title = self._compact(item.get("title", ""), 140)
                status = self._status(item.get("status", "planned"))
            else:
                title = self._compact(item, 140)
                status = "planned"
            if title and title not in [subtask["title"] for subtask in result]:
                result.append({"title": title, "status": status})
        return result[:12]

    def _merge_unique(self, first: List[str], second: List[str], limit: int) -> List[str]:
        merged = []
        for item in [*first, *second]:
            item = self._compact(item, 180)
            if item and item not in merged:
                merged.append(item)
        return merged[:limit]

    def _merge_subtasks(
        self,
        existing: List[Dict[str, Any]],
        incoming: List[Dict[str, str]],
        now_text: str,
    ) -> List[Dict[str, Any]]:
        merged = []
        for item in existing:
            if isinstance(item, dict) and item.get("title"):
                normalized = self._normalize_subtask(item, now_text)
                if normalized["title"] not in [subtask["title"] for subtask in merged]:
                    merged.append(normalized)

        for item in incoming:
            title = self._compact(item.get("title", ""), 140)
            if not title:
                continue
            match = self._find_subtask(merged, title)
            if match:
                new_status = self._status(item.get("status", match.get("status", "planned")))
                if self._status_rank(new_status) >= self._status_rank(match.get("status", "planned")):
                    match["status"] = new_status
                match["updated_at"] = now_text
            else:
                merged.append({
                    "id": self._make_id(now_text, title).replace("task-", "subtask-"),
                    "title": title,
                    "status": self._status(item.get("status", "planned")),
                    "created_at": now_text,
                    "updated_at": now_text,
                    "completed_at": now_text if item.get("status") == "done" else "",
                    "blockers": [],
                })
        return merged[:20]

    def _merge_subtask_updates(
        self,
        first: List[Dict[str, str]],
        second: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        merged = list(first)
        for item in second:
            title = item.get("title", "")
            if not title:
                continue
            match = self._find_subtask(merged, title)
            if match:
                new_status = self._status(item.get("status", match.get("status", "planned")))
                if self._status_rank(new_status) >= self._status_rank(match.get("status", "planned")):
                    match["status"] = new_status
            else:
                merged.append({"title": title, "status": self._status(item.get("status", "planned"))})
        return merged[:12]

    def _normalize_subtask(self, item: Dict[str, Any], now_text: str) -> Dict[str, Any]:
        title = self._compact(item.get("title", ""), 140)
        status = self._status(item.get("status", "planned"))
        return {
            "id": item.get("id") or self._make_id(now_text, title).replace("task-", "subtask-"),
            "title": title,
            "status": status,
            "created_at": item.get("created_at", now_text),
            "updated_at": item.get("updated_at", now_text),
            "completed_at": item.get("completed_at", ""),
            "blockers": self._list(item.get("blockers", [])),
        }

    def _mark_related_subtasks(
        self,
        task: Dict[str, Any],
        texts: List[str],
        status: str,
        now_text: str,
    ) -> None:
        for subtask in task.get("subtasks", []):
            if any(self._shares_keywords(subtask.get("title", ""), text) for text in texts):
                subtask["status"] = status
                subtask["updated_at"] = now_text
                subtask["blockers"] = self._merge_unique(subtask.get("blockers", []), texts, 5)

    def _mark_all_open_subtasks(self, task: Dict[str, Any], status: str, now_text: str) -> None:
        for subtask in task.get("subtasks", []):
            if subtask.get("status") not in {"done", "abandoned"}:
                subtask["status"] = status
                subtask["updated_at"] = now_text
                if status == "done":
                    subtask["completed_at"] = now_text

    def _find_subtask(self, subtasks: List[Dict[str, Any]], title: str) -> Optional[Dict[str, Any]]:
        for subtask in subtasks:
            if self._same_task(subtask.get("title", ""), title) or self._shares_keywords(subtask.get("title", ""), title):
                return subtask
        return None

    def _status(self, status: Any) -> str:
        status = str(status or "planned").strip().lower()
        if status in self.VALID_STATUSES:
            return status
        return "planned"

    def _decision_status(self, status: Any) -> str:
        status = str(status or "").strip().lower()
        return status if status in self.VALID_STATUSES else ""

    def _status_rank(self, status: str) -> int:
        order = {
            "inbox": 0,
            "planned": 1,
            "active": 2,
            "blocked": 3,
            "done": 4,
            "abandoned": 4,
        }
        return order.get(status, 0)

    def _make_id(self, now: str, title: str) -> str:
        safe_time = now.replace("-", "").replace(":", "").replace("T", "-")
        return f"task-{safe_time}-{abs(hash(title)) % 10000:04d}"

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("task lifecycle output is not a JSON object")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("task lifecycle output JSON is not object")
        return parsed

    def _float(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.7

    def _compact(self, text: Any, max_length: int = 140) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
