import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path


class FocusSessionManager:
    ACTIVE_STATUSES = {"active", "expired"}
    FINAL_STATUSES = {"completed", "abandoned"}

    def __init__(self, sessions_path: Optional[str] = None):
        self.sessions_path = Path(sessions_path) if sessions_path else memory_data_path("focus_sessions.json")
        self.sessions_path.parent.mkdir(parents=True, exist_ok=True)

    def load_sessions(self) -> List[Dict[str, Any]]:
        if not self.sessions_path.exists() or self.sessions_path.stat().st_size == 0:
            return []
        try:
            with self.sessions_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [session for session in (self._normalize_session(item) for item in data) if session]

    def save_sessions(self, sessions: List[Dict[str, Any]]) -> None:
        with self.sessions_path.open("w", encoding="utf-8") as file:
            json.dump(sessions[-300:], file, ensure_ascii=False, indent=2)

    def start_session(
        self,
        goal: str,
        duration_minutes: int = 45,
        task_id: str = "",
        task_title: str = "",
    ) -> Dict[str, Any]:
        goal = self._compact(goal, 180)
        if not goal:
            raise ValueError("focus session goal is required")
        duration_minutes = self._bounded_int(duration_minutes, 5, 240)
        sessions = self._expire_sessions(self.load_sessions())
        now = datetime.now()
        now_text = now.isoformat(timespec="seconds")
        for session in sessions:
            if session.get("status") in self.ACTIVE_STATUSES:
                session["status"] = "abandoned"
                session["ended_at"] = now_text
                session["outcome"] = "开始新的专注会话，自动收束上一段。"
                session["updated_at"] = now_text
        session = {
            "id": self._make_id(now_text, goal),
            "goal": goal,
            "task_id": task_id or "",
            "task_title": self._compact(task_title, 160),
            "status": "active",
            "duration_minutes": duration_minutes,
            "started_at": now_text,
            "expected_end_at": (now + timedelta(minutes=duration_minutes)).isoformat(timespec="seconds"),
            "ended_at": "",
            "elapsed_minutes": 0,
            "outcome": "",
            "created_at": now_text,
            "updated_at": now_text,
        }
        sessions.append(session)
        self.save_sessions(sessions)
        return session

    def complete_current(self, outcome: str = "") -> Dict[str, Any]:
        return self._finish_current("completed", outcome or "用户标记完成。")

    def abandon_current(self, outcome: str = "") -> Dict[str, Any]:
        return self._finish_current("abandoned", outcome or "用户标记放弃或中断。")

    def current_session(self) -> Dict[str, Any]:
        sessions = self._expire_sessions(self.load_sessions())
        self.save_sessions(sessions)
        for session in reversed(sessions):
            if session.get("status") in self.ACTIVE_STATUSES:
                return self._with_elapsed(session)
        return {}

    def get_recent_sessions(self, limit: int = 8) -> List[Dict[str, Any]]:
        sessions = self._expire_sessions(self.load_sessions())
        self.save_sessions(sessions)
        return [self._with_elapsed(session) for session in reversed(sessions[-limit:])]

    def build_state(self) -> Dict[str, Any]:
        sessions = self._expire_sessions(self.load_sessions())
        self.save_sessions(sessions)
        current = {}
        for session in reversed(sessions):
            if session.get("status") in self.ACTIVE_STATUSES:
                current = self._with_elapsed(session)
                break
        recent = [self._with_elapsed(session) for session in reversed(sessions[-8:])]
        completed = [session for session in sessions if session.get("status") == "completed"]
        return {
            "current": current,
            "recent": recent,
            "count": len(sessions),
            "completed_count": len(completed),
            "total_completed_minutes": sum(int(item.get("elapsed_minutes", 0)) for item in completed),
            "last_gap_minutes": self._last_gap_minutes(sessions),
        }

    def format_for_context(self) -> str:
        state = self.build_state()
        current = state.get("current") or {}
        lines = [
            "以下是专注会话状态。它用于理解用户离开对话后的执行片段，不要把它当作强制考核。",
        ]
        if current:
            lines.extend([
                f"当前专注: {current.get('goal', '')}",
                f"状态: {current.get('status', '')}",
                f"已进行: {current.get('elapsed_minutes', 0)} 分钟 / 计划 {current.get('duration_minutes', 0)} 分钟",
            ])
            if current.get("status") == "expired":
                lines.append("这段专注已经超过预设时长；用户回来时可以温和帮他收束，不要催促。")
        else:
            lines.append("当前没有进行中的专注会话。")
        if state.get("last_gap_minutes") is not None:
            lines.append(f"最近两次会话间隔约 {state['last_gap_minutes']} 分钟。")
        recent = state.get("recent") or []
        if recent:
            summaries = [
                f"{item.get('goal', '')}({item.get('status', '')}, {item.get('elapsed_minutes', 0)}m)"
                for item in recent[:4]
            ]
            lines.append("最近专注片段: " + "；".join(summaries))
        return "\n".join(lines)

    def _finish_current(self, status: str, outcome: str) -> Dict[str, Any]:
        sessions = self._expire_sessions(self.load_sessions())
        now_text = datetime.now().isoformat(timespec="seconds")
        for session in reversed(sessions):
            if session.get("status") in self.ACTIVE_STATUSES:
                session["status"] = status
                session["ended_at"] = now_text
                session["outcome"] = self._compact(outcome, 220)
                session["updated_at"] = now_text
                session["elapsed_minutes"] = self._elapsed_minutes(session)
                self.save_sessions(sessions)
                return self._with_elapsed(session)
        raise ValueError("no active focus session")

    def _expire_sessions(self, sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = datetime.now()
        now_text = now.isoformat(timespec="seconds")
        for session in sessions:
            if session.get("status") != "active":
                continue
            expected_end = self._parse_time(session.get("expected_end_at", ""))
            if expected_end and now > expected_end:
                session["status"] = "expired"
                session["updated_at"] = now_text
            session["elapsed_minutes"] = self._elapsed_minutes(session)
        return sessions

    def _normalize_session(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        goal = self._compact(item.get("goal", ""), 180)
        if not goal:
            return {}
        status = str(item.get("status", "active")).strip().lower()
        if status not in {"active", "expired", "completed", "abandoned"}:
            status = "active"
        return {
            "id": item.get("id", ""),
            "goal": goal,
            "task_id": item.get("task_id", ""),
            "task_title": self._compact(item.get("task_title", ""), 160),
            "status": status,
            "duration_minutes": self._bounded_int(item.get("duration_minutes", 45), 5, 240),
            "started_at": item.get("started_at", ""),
            "expected_end_at": item.get("expected_end_at", ""),
            "ended_at": item.get("ended_at", ""),
            "elapsed_minutes": int(item.get("elapsed_minutes", 0) or 0),
            "outcome": self._compact(item.get("outcome", ""), 220),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def _with_elapsed(self, session: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(session)
        result["elapsed_minutes"] = self._elapsed_minutes(session)
        return result

    def _elapsed_minutes(self, session: Dict[str, Any]) -> int:
        started_at = self._parse_time(session.get("started_at", ""))
        if not started_at:
            return 0
        ended_at = self._parse_time(session.get("ended_at", "")) or datetime.now()
        return max(0, int((ended_at - started_at).total_seconds() // 60))

    def _last_gap_minutes(self, sessions: List[Dict[str, Any]]) -> Optional[int]:
        if len(sessions) < 2:
            return None
        previous = self._parse_time(sessions[-2].get("ended_at") or sessions[-2].get("updated_at") or sessions[-2].get("started_at"))
        current = self._parse_time(sessions[-1].get("started_at"))
        if not previous or not current:
            return None
        return max(0, int((current - previous).total_seconds() // 60))

    def _parse_time(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _make_id(self, now: str, goal: str) -> str:
        safe_time = now.replace("-", "").replace(":", "").replace("T", "-")
        digest = hashlib.sha256(str(goal or "").encode("utf-8")).hexdigest()[:10]
        return f"focus-{safe_time}-{digest}"

    def _bounded_int(self, value: Any, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = minimum
        return max(minimum, min(maximum, number))

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
