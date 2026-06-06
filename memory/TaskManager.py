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
    ):
        memory_dir = Path(__file__).resolve().parent
        self.tasks_path = Path(tasks_path) if tasks_path else memory_dir / "tasks.json"
        self.events_path = Path(events_path) if events_path else memory_dir / "task_events.json"
        self.tasks_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)

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

        task = self._select_task(tasks, task_title)
        if not task and task_title:
            task = self._new_task(task_title, now_text)
            tasks.append(task)
            self._append_event("created", task, now_text, {"title": task_title})

        if task:
            previous_status = task.get("status", "inbox")
            self._apply_turn(task, extracted, progress, blockers, next_actions, user_commitments, now)
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
            "以下是 v0.4 任务生命周期记录。请用它判断当前主线、任务状态和下一步监督方式。",
            f"当前任务: {current.get('title') or '暂无'}",
            f"状态: {current.get('status') or 'inbox'}",
        ]
        if current.get("progress"):
            lines.append("进展: " + "；".join(current["progress"][-4:]))
        if current.get("blockers"):
            lines.append("阻塞/风险: " + "、".join(current["blockers"][-4:]))
        if current.get("next_actions"):
            lines.append("下一步: " + "；".join(current["next_actions"][:4]))
        if current.get("next_check_at"):
            lines.append(f"建议下次检查时间: {current['next_check_at']}")
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
        now: datetime,
    ) -> None:
        now_text = now.isoformat(timespec="seconds")
        if extracted.get("task") and not task.get("title"):
            task["title"] = self._compact(extracted["task"], 160)
        if progress:
            task["progress"] = self._merge_unique(task.get("progress", []), [progress], 12)
            task["last_user_update_at"] = now_text
        if blockers:
            task["blockers"] = self._merge_unique(task.get("blockers", []), blockers, 10)
        if next_actions:
            task["next_actions"] = self._merge_unique(next_actions, task.get("next_actions", []), 10)
        if user_commitments:
            task["user_commitments"] = self._merge_unique(task.get("user_commitments", []), user_commitments, 10)

        status = self._infer_status(extracted, task)
        if status == "active" and not task.get("started_at"):
            task["started_at"] = now_text
        if status == "done":
            task["completed_at"] = task.get("completed_at") or now_text
        if status == "abandoned":
            task["abandoned_at"] = task.get("abandoned_at") or now_text

        task["status"] = status
        task["updated_at"] = now_text
        task["next_check_at"] = self._next_check_at(status, now)

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

    def _merge_unique(self, first: List[str], second: List[str], limit: int) -> List[str]:
        merged = []
        for item in [*first, *second]:
            item = self._compact(item, 180)
            if item and item not in merged:
                merged.append(item)
        return merged[:limit]

    def _make_id(self, now: str, title: str) -> str:
        safe_time = now.replace("-", "").replace(":", "").replace("T", "-")
        return f"task-{safe_time}-{abs(hash(title)) % 10000:04d}"

    def _compact(self, text: Any, max_length: int = 140) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
