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
        return {**self.default_state(), **state}

    def save_state(self, state: Dict[str, Any]) -> None:
        with self.state_path.open("w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)

    def update(self, extracted: Dict[str, Any], user_input: str, assistant_output: str) -> Dict[str, Any]:
        state = self.load_state()
        now = datetime.now().isoformat(timespec="seconds")

        task = extracted.get("task")
        if task:
            state["active_task"] = task
            if state.get("status") == "idle":
                state["status"] = "in_progress"
            if not state.get("started_at"):
                state["started_at"] = now

        progress = extracted.get("progress")
        if progress:
            state["current_progress"] = progress
            state["status"] = self._status_from_progress(progress)

        blockers = extracted.get("blockers") or []
        if blockers:
            state["blockers"] = self._merge_unique(state.get("blockers", []), blockers, limit=8)

        next_actions = extracted.get("next_actions") or []
        if next_actions:
            state["next_action"] = next_actions[0]
            state["next_actions"] = self._merge_unique(next_actions, state.get("next_actions", []), limit=8)

        evidence_required = extracted.get("evidence_required") or []
        if evidence_required:
            state["evidence_required"] = self._merge_unique(evidence_required, state.get("evidence_required", []), limit=6)

        state["updated_at"] = now
        state["last_user_input"] = self._compact(user_input)
        state["last_agent_response"] = self._compact(assistant_output)
        state["events"] = self._append_event(state.get("events", []), now, extracted)
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
        if state.get("evidence_required"):
            lines.append("待验证证据: " + "；".join(state["evidence_required"][:3]))
        if state.get("updated_at"):
            lines.append(f"更新时间: {state['updated_at']}")
        return "\n".join(lines)

    def default_state(self) -> Dict[str, Any]:
        return {
            "status": "idle",
            "active_task": "",
            "started_at": "",
            "updated_at": "",
            "current_progress": "",
            "next_action": "",
            "next_actions": [],
            "blockers": [],
            "evidence_required": [],
            "last_user_input": "",
            "last_agent_response": "",
            "events": [],
        }

    def _status_from_progress(self, progress: str) -> str:
        if any(keyword in progress for keyword in ["完成了", "做完了", "全部", "结束"]):
            return "in_progress"
        return "in_progress"

    def _append_event(self, events, time_text: str, extracted: Dict[str, Any]):
        event = {
            "time": time_text,
            "categories": extracted.get("categories", []),
            "task": extracted.get("task", ""),
            "progress": extracted.get("progress", ""),
            "blockers": extracted.get("blockers", []),
        }
        return [*events, event][-20:]

    def _merge_unique(self, first, second, limit: int):
        merged = []
        for item in [*first, *second]:
            if item and item not in merged:
                merged.append(item)
        return merged[:limit]

    def _compact(self, text: str, max_length: int = 180) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
