import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path


class SupervisionEventManager:
    ACTIVE_STATUSES = {"detected", "notified", "acknowledged"}
    PAUSED_STATUSES = {"snoozed", "muted"}
    FINAL_STATUSES = {"resolved"}
    VALID_STATUSES = ACTIVE_STATUSES | PAUSED_STATUSES | FINAL_STATUSES

    def __init__(self, events_path: Optional[str] = None, preferences_path: Optional[str] = None):
        self.events_path = Path(events_path) if events_path else memory_data_path("supervision_events.json")
        self.preferences_path = (
            Path(preferences_path) if preferences_path else memory_data_path("supervision_preferences.json")
        )
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)

    def load_events(self) -> List[Dict[str, Any]]:
        if not self.events_path.exists() or self.events_path.stat().st_size == 0:
            return []
        try:
            with self.events_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [event for event in (self._normalize_event(item) for item in data) if event]

    def load_preferences(self) -> Dict[str, Any]:
        defaults = self.default_preferences()
        if not self.preferences_path.exists() or self.preferences_path.stat().st_size == 0:
            return defaults
        try:
            with self.preferences_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return defaults
        if not isinstance(data, dict):
            return defaults
        return self._normalize_preferences({**defaults, **data})

    def save_preferences(self, preferences: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_preferences({**self.default_preferences(), **preferences})
        with self.preferences_path.open("w", encoding="utf-8") as file:
            json.dump(normalized, file, ensure_ascii=False, indent=2)
        return normalized

    def update_preferences(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        preferences = self.load_preferences()
        preferences.update({key: value for key, value in (updates or {}).items() if key in preferences})
        return self.save_preferences(preferences)

    def default_preferences(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "reminder_strength": "gentle",
            "min_severity": "low",
            "push_min_severity": "medium",
            "default_snooze_minutes": 60,
            "default_mute_hours": 24,
            "quiet_hours_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "07:00",
            "notify_focus": True,
            "notify_commitments": True,
            "notify_tasks": True,
        }

    def save_events(self, events: List[Dict[str, Any]]) -> None:
        with self.events_path.open("w", encoding="utf-8") as file:
            json.dump(events[-500:], file, ensure_ascii=False, indent=2)

    def get_event(self, event_id: str) -> Dict[str, Any]:
        for event in self.load_events():
            if event.get("id") == event_id:
                return event
        raise ValueError(f"supervision event not found: {event_id}")

    def detect_events(
        self,
        focus_state: Dict[str, Any],
        commitments: List[Dict[str, Any]],
        task_view: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        events = self.load_events()
        now = datetime.now()
        self._reactivate_paused_events(events, now)
        candidates = []
        focus_candidate = self._focus_expired_candidate(focus_state, now)
        if focus_candidate:
            candidates.append(focus_candidate)
        candidates.extend(self._commitment_deadline_candidates(commitments, now))
        stale_candidate = self._stale_task_candidate(task_view, now)
        if stale_candidate:
            candidates.append(stale_candidate)

        for candidate in candidates:
            events = self._upsert_candidate(events, candidate, now)

        self._auto_resolve_missing_events(events, candidates, now)
        self.save_events(events)
        return self.build_state(events=events)["active"]

    def build_state(self, events: Optional[List[Dict[str, Any]]] = None, limit: int = 12) -> Dict[str, Any]:
        events = events if events is not None else self.load_events()
        self._reactivate_paused_events(events, datetime.now())
        active = [
            event for event in events
            if event.get("status") in self.ACTIVE_STATUSES
        ]
        snoozed = [event for event in events if self._is_snoozed_now(event)]
        muted = [event for event in events if self._is_muted_now(event)]
        recent = sorted(events, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit]
        active_sorted = sorted(active, key=lambda item: (self._severity_rank(item), item.get("updated_at", "")), reverse=True)
        return {
            "active": active_sorted[:limit],
            "snoozed": sorted(snoozed, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit],
            "muted": sorted(muted, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit],
            "recent": recent,
            "preferences": self.load_preferences(),
            "feedback_stats": self._feedback_stats(events),
            "counts": {
                "active": len(active),
                "snoozed": len(snoozed),
                "muted": len(muted),
                "resolved": len([event for event in events if event.get("status") == "resolved"]),
                "total": len(events),
            },
        }

    def mark_notified(self, event_id: str) -> Dict[str, Any]:
        return self._transition(event_id, "notified", {"notified_at": datetime.now().isoformat(timespec="seconds")})

    def acknowledge(self, event_id: str) -> Dict[str, Any]:
        return self._transition(event_id, "acknowledged", {"acknowledged_at": datetime.now().isoformat(timespec="seconds")})

    def snooze(self, event_id: str, minutes: int = 60) -> Dict[str, Any]:
        minutes = self._bounded_int(minutes, 5, 1440)
        now = datetime.now()
        return self._transition(
            event_id,
            "snoozed",
            {
                "snoozed_at": now.isoformat(timespec="seconds"),
                "snoozed_until": (now + timedelta(minutes=minutes)).isoformat(timespec="seconds"),
            },
        )

    def resolve(self, event_id: str, linked_updates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        fields = {"resolved_at": datetime.now().isoformat(timespec="seconds")}
        if linked_updates is not None:
            fields["linked_updates"] = linked_updates
        return self._transition(event_id, "resolved", fields)

    def mute(self, event_id: str, hours: int = 24) -> Dict[str, Any]:
        hours = self._bounded_int(hours, 1, 168)
        now = datetime.now()
        return self._transition(
            event_id,
            "muted",
            {
                "muted_at": now.isoformat(timespec="seconds"),
                "muted_until": (now + timedelta(hours=hours)).isoformat(timespec="seconds"),
            },
        )

    def should_notify(self, event: Dict[str, Any], now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        preferences = self.load_preferences()
        if not preferences.get("enabled", True):
            return False
        if event.get("status") != "detected":
            return False
        push_min_severity = preferences.get("push_min_severity") or preferences.get("min_severity", "low")
        if self._severity_rank(event) < self._severity_rank({"severity": push_min_severity}):
            return False
        if preferences.get("quiet_hours_enabled") and self._in_quiet_hours(now, preferences):
            return False
        event_type = event.get("type", "")
        if event_type == "focus_expired" and not preferences.get("notify_focus", True):
            return False
        if event_type in {"commitment_due_today", "commitment_overdue"} and not preferences.get("notify_commitments", True):
            return False
        if event_type == "task_stale" and not preferences.get("notify_tasks", True):
            return False
        return True

    def format_for_context(self, state: Optional[Dict[str, Any]] = None) -> str:
        state = state or self.build_state()
        active = state.get("active") or []
        if not active:
            return "暂无未处理的监督事件。"
        lines = [
            "以下是可追踪的监督事件。请把它们当作低压力提醒，不要反复催促，不要要求证明。",
        ]
        for index, event in enumerate(active[:5], start=1):
            lines.append(
                f"{index}. [{event.get('severity', 'low')}] {event.get('title', '')}: "
                f"{event.get('message', '')} status={event.get('status', '')}"
            )
        return "\n".join(lines)

    def _focus_expired_candidate(self, focus_state: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        current = (focus_state or {}).get("current") or {}
        if current.get("status") != "expired" or not current.get("id"):
            return {}
        return {
            "type": "focus_expired",
            "subject_type": "focus_session",
            "subject_id": current.get("id", ""),
            "subject_title": current.get("goal", ""),
            "severity": "medium",
            "title": "专注会话已超时",
            "message": (
                f"专注会话【{current.get('goal', '')}】已超过计划 "
                f"{current.get('duration_minutes', 0)} 分钟，适合温和收束进展。"
            ),
            "metadata": {
                "duration_minutes": current.get("duration_minutes", 0),
                "elapsed_minutes": current.get("elapsed_minutes", 0),
                "expected_end_at": current.get("expected_end_at", ""),
            },
        }

    def _commitment_deadline_candidates(self, commitments: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
        candidates = []
        for item in commitments:
            if item.get("status") != "open" or not item.get("id") or not item.get("deadline"):
                continue
            deadline = self._parse_time(item.get("deadline", ""))
            if not deadline:
                continue
            if deadline < now:
                event_type = "commitment_overdue"
                severity = "medium"
                title = "承诺已逾期"
                message = f"承诺【{item.get('commitment', '')}】已超过截止时间，适合提醒用户关闭、延期或放下。"
            elif deadline.date() == now.date():
                event_type = "commitment_due_today"
                severity = "low"
                title = "承诺今日到期"
                message = f"承诺【{item.get('commitment', '')}】今天到期，适合在相关时轻轻提醒。"
            else:
                continue
            candidates.append({
                "type": event_type,
                "subject_type": "commitment",
                "subject_id": item.get("id", ""),
                "subject_title": item.get("commitment", ""),
                "severity": severity,
                "title": title,
                "message": message,
                "metadata": {
                    "deadline": item.get("deadline", ""),
                    "task": item.get("task", ""),
                },
            })
        return candidates

    def _stale_task_candidate(self, task_view: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        current = (task_view or {}).get("current") or {}
        if not current.get("id") or current.get("status") in {"done", "abandoned"}:
            return {}
        updated_at = self._parse_time(current.get("updated_at", ""))
        if not updated_at:
            return {}
        hours = (now - updated_at).total_seconds() / 3600
        if hours < 24:
            return {}
        return {
            "type": "task_stale",
            "subject_type": "task",
            "subject_id": current.get("id", ""),
            "subject_title": current.get("title", ""),
            "severity": "low",
            "title": "当前任务久未更新",
            "message": f"当前任务【{current.get('title', '')}】约 {int(hours)} 小时未更新，适合温和提醒它还被记着。",
            "metadata": {
                "updated_at": current.get("updated_at", ""),
                "stale_hours": int(hours),
                "status": current.get("status", ""),
            },
        }

    def _upsert_candidate(
        self,
        events: List[Dict[str, Any]],
        candidate: Dict[str, Any],
        now: datetime,
    ) -> List[Dict[str, Any]]:
        now_text = now.isoformat(timespec="seconds")
        dedupe_key = self._dedupe_key(candidate)
        existing = next(
            (
                event for event in events
                if event.get("dedupe_key") == dedupe_key
                and event.get("status") in (self.ACTIVE_STATUSES | self.PAUSED_STATUSES)
            ),
            None,
        )
        if existing:
            existing.update({
                "severity": candidate.get("severity", existing.get("severity", "low")),
                "title": candidate.get("title", existing.get("title", "")),
                "message": candidate.get("message", existing.get("message", "")),
                "metadata": candidate.get("metadata", existing.get("metadata", {})),
                "last_detected_at": now_text,
                "updated_at": now_text,
            })
            return events

        events.append({
            "id": self._make_id(now_text, dedupe_key),
            "dedupe_key": dedupe_key,
            "type": candidate.get("type", "general"),
            "subject_type": candidate.get("subject_type", ""),
            "subject_id": candidate.get("subject_id", ""),
            "subject_title": candidate.get("subject_title", ""),
            "severity": candidate.get("severity", "low"),
            "title": candidate.get("title", ""),
            "message": candidate.get("message", ""),
            "status": "detected",
            "source": "scheduler",
            "metadata": candidate.get("metadata", {}),
            "detected_at": now_text,
            "last_detected_at": now_text,
            "notified_at": "",
            "acknowledged_at": "",
            "snoozed_at": "",
            "snoozed_until": "",
            "resolved_at": "",
            "muted_at": "",
            "muted_until": "",
            "linked_updates": [],
            "feedback_history": [],
            "created_at": now_text,
            "updated_at": now_text,
        })
        return events

    def _auto_resolve_missing_events(
        self,
        events: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        now: datetime,
    ) -> None:
        active_keys = {self._dedupe_key(candidate) for candidate in candidates}
        now_text = now.isoformat(timespec="seconds")
        for event in events:
            if event.get("status") not in (self.ACTIVE_STATUSES | self.PAUSED_STATUSES):
                continue
            if event.get("dedupe_key") not in active_keys and event.get("type") in {
                "focus_expired",
                "commitment_due_today",
                "commitment_overdue",
                "task_stale",
            }:
                event["status"] = "resolved"
                event["resolved_at"] = now_text
                event["updated_at"] = now_text

    def _transition(self, event_id: str, status: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"invalid supervision event status: {status}")
        events = self.load_events()
        now_text = datetime.now().isoformat(timespec="seconds")
        for event in events:
            if event.get("id") == event_id:
                event["status"] = status
                event["updated_at"] = now_text
                event.update(fields)
                self._append_feedback(event, status, now_text, fields)
                self.save_events(events)
                return event
        raise ValueError(f"supervision event not found: {event_id}")

    def _normalize_event(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        status = str(item.get("status", "detected")).strip().lower()
        if status not in self.VALID_STATUSES:
            status = "detected"
        return {
            "id": item.get("id", ""),
            "dedupe_key": item.get("dedupe_key", ""),
            "type": item.get("type", "general"),
            "subject_type": item.get("subject_type", ""),
            "subject_id": item.get("subject_id", ""),
            "subject_title": item.get("subject_title", ""),
            "severity": item.get("severity", "low"),
            "title": item.get("title", ""),
            "message": item.get("message", ""),
            "status": status,
            "source": item.get("source", ""),
            "metadata": item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
            "linked_updates": item.get("linked_updates", [])
            if isinstance(item.get("linked_updates", []), list) else [],
            "detected_at": item.get("detected_at", ""),
            "last_detected_at": item.get("last_detected_at", ""),
            "notified_at": item.get("notified_at", ""),
            "acknowledged_at": item.get("acknowledged_at", ""),
            "snoozed_at": item.get("snoozed_at", ""),
            "snoozed_until": item.get("snoozed_until", ""),
            "resolved_at": item.get("resolved_at", ""),
            "muted_at": item.get("muted_at", ""),
            "muted_until": item.get("muted_until", ""),
            "feedback_history": item.get("feedback_history", [])
            if isinstance(item.get("feedback_history", []), list) else [],
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def _append_feedback(self, event: Dict[str, Any], action: str, now_text: str, fields: Dict[str, Any]) -> None:
        history = event.get("feedback_history", [])
        if not isinstance(history, list):
            history = []
        history.append({
            "action": action,
            "at": now_text,
            "details": {
                key: value
                for key, value in fields.items()
                if key.endswith("_until") or key.endswith("_at")
            },
        })
        event["feedback_history"] = history[-20:]

    def _feedback_stats(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_action: Dict[str, int] = {}
        by_type: Dict[str, Dict[str, int]] = {}
        last_feedback = ""
        total = 0
        for event in events:
            event_type = event.get("type", "general")
            for item in event.get("feedback_history", []) or []:
                if not isinstance(item, dict):
                    continue
                action = str(item.get("action", "")).strip() or "unknown"
                by_action[action] = by_action.get(action, 0) + 1
                by_type.setdefault(event_type, {})
                by_type[event_type][action] = by_type[event_type].get(action, 0) + 1
                total += 1
                if str(item.get("at", "")) > last_feedback:
                    last_feedback = str(item.get("at", ""))
        return {
            "total": total,
            "by_action": by_action,
            "by_type": by_type,
            "last_feedback_at": last_feedback,
        }

    def _is_muted_now(self, event: Dict[str, Any]) -> bool:
        if event.get("status") != "muted":
            return False
        muted_until = self._parse_time(event.get("muted_until", ""))
        return bool(muted_until and muted_until > datetime.now())

    def _is_snoozed_now(self, event: Dict[str, Any]) -> bool:
        if event.get("status") != "snoozed":
            return False
        snoozed_until = self._parse_time(event.get("snoozed_until", ""))
        return bool(snoozed_until and snoozed_until > datetime.now())

    def _reactivate_paused_events(self, events: List[Dict[str, Any]], now: datetime) -> None:
        now_text = now.isoformat(timespec="seconds")
        for event in events:
            if event.get("status") == "snoozed":
                snoozed_until = self._parse_time(event.get("snoozed_until", ""))
                if snoozed_until and snoozed_until <= now:
                    event["status"] = "detected"
                    event["updated_at"] = now_text
            if event.get("status") == "muted":
                muted_until = self._parse_time(event.get("muted_until", ""))
                if muted_until and muted_until <= now:
                    event["status"] = "detected"
                    event["updated_at"] = now_text

    def _severity_rank(self, event: Dict[str, Any]) -> int:
        return {"high": 3, "medium": 2, "low": 1}.get(event.get("severity", "low"), 1)

    def _in_quiet_hours(self, now: datetime, preferences: Dict[str, Any]) -> bool:
        start = self._parse_clock(preferences.get("quiet_hours_start", "23:00"))
        end = self._parse_clock(preferences.get("quiet_hours_end", "07:00"))
        if start is None or end is None:
            return False
        current = now.hour * 60 + now.minute
        if start <= end:
            return start <= current < end
        return current >= start or current < end

    def _parse_clock(self, text: str) -> Optional[int]:
        parts = str(text or "").split(":")
        if len(parts) != 2:
            return None
        try:
            hour = max(0, min(23, int(parts[0])))
            minute = max(0, min(59, int(parts[1])))
        except ValueError:
            return None
        return hour * 60 + minute

    def _normalize_preferences(self, preferences: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.default_preferences()
        severity = str(preferences.get("min_severity", defaults["min_severity"])).lower()
        if severity not in {"low", "medium", "high"}:
            severity = defaults["min_severity"]
        push_min_severity = str(preferences.get("push_min_severity", defaults["push_min_severity"])).lower()
        if push_min_severity not in {"low", "medium", "high"}:
            push_min_severity = defaults["push_min_severity"]
        strength = str(preferences.get("reminder_strength", defaults["reminder_strength"])).lower()
        if strength not in {"gentle", "normal"}:
            strength = defaults["reminder_strength"]
        return {
            "enabled": bool(preferences.get("enabled", defaults["enabled"])),
            "reminder_strength": strength,
            "min_severity": severity,
            "push_min_severity": push_min_severity,
            "default_snooze_minutes": self._bounded_int(preferences.get("default_snooze_minutes", 60), 5, 1440),
            "default_mute_hours": self._bounded_int(preferences.get("default_mute_hours", 24), 1, 168),
            "quiet_hours_enabled": bool(preferences.get("quiet_hours_enabled", defaults["quiet_hours_enabled"])),
            "quiet_hours_start": preferences.get("quiet_hours_start", defaults["quiet_hours_start"])
            if self._parse_clock(preferences.get("quiet_hours_start", "")) is not None else defaults["quiet_hours_start"],
            "quiet_hours_end": preferences.get("quiet_hours_end", defaults["quiet_hours_end"])
            if self._parse_clock(preferences.get("quiet_hours_end", "")) is not None else defaults["quiet_hours_end"],
            "notify_focus": bool(preferences.get("notify_focus", defaults["notify_focus"])),
            "notify_commitments": bool(preferences.get("notify_commitments", defaults["notify_commitments"])),
            "notify_tasks": bool(preferences.get("notify_tasks", defaults["notify_tasks"])),
        }

    def _dedupe_key(self, event: Dict[str, Any]) -> str:
        return "|".join([
            str(event.get("type", "")),
            str(event.get("subject_type", "")),
            str(event.get("subject_id", "")),
        ])

    def _make_id(self, now: str, dedupe_key: str) -> str:
        safe_time = now.replace("-", "").replace(":", "").replace("T", "-")
        digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:10]
        return f"sup-{safe_time}-{digest}"

    def _parse_time(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _bounded_int(self, value: Any, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = minimum
        return max(minimum, min(maximum, number))
