import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path


class BehaviorPatternManager:
    def __init__(self, patterns_path: Optional[str] = None):
        self.patterns_path = Path(patterns_path) if patterns_path else memory_data_path("behavior_patterns.json")
        self.patterns_path.parent.mkdir(parents=True, exist_ok=True)

    def load_patterns(self) -> List[Dict[str, Any]]:
        if not self.patterns_path.exists() or self.patterns_path.stat().st_size == 0:
            return []
        try:
            with self.patterns_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [pattern for pattern in (self._normalize_pattern(item) for item in data) if pattern]

    def save_patterns(self, patterns: List[Dict[str, Any]]) -> None:
        with self.patterns_path.open("w", encoding="utf-8") as file:
            json.dump(patterns[-80:], file, ensure_ascii=False, indent=2)

    def analyze(
        self,
        tasks: List[Dict[str, Any]],
        focus_sessions: List[Dict[str, Any]],
        commitments: List[Dict[str, Any]],
        supervision_events: List[Dict[str, Any]],
        stats: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        previous = {item.get("id"): item for item in self.load_patterns()}
        now = datetime.now()
        now_text = now.isoformat(timespec="seconds")
        patterns = []

        patterns.extend(self._focus_patterns(focus_sessions, supervision_events, stats, now_text))
        patterns.extend(self._commitment_patterns(commitments, supervision_events, stats, now_text))
        patterns.extend(self._task_patterns(tasks, supervision_events, now, now_text))
        patterns.extend(self._reminder_feedback_patterns(supervision_events, now_text))
        patterns.extend(self._positive_activity_patterns(focus_sessions, stats, now_text))

        for pattern in patterns:
            old = previous.get(pattern["id"], {})
            pattern["first_seen_at"] = old.get("first_seen_at") or now_text
            pattern["updated_at"] = now_text

        self.save_patterns(patterns)
        return patterns

    def build_state(self, patterns: Optional[List[Dict[str, Any]]] = None, limit: int = 8) -> Dict[str, Any]:
        patterns = patterns if patterns is not None else self.load_patterns()
        active = [item for item in patterns if item.get("status") == "active"]
        active_sorted = sorted(active, key=lambda item: (self._severity_rank(item), item.get("updated_at", "")), reverse=True)
        return {
            "active": active_sorted[:limit],
            "recent": sorted(patterns, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit],
            "counts": {
                "active": len(active),
                "total": len(patterns),
                "positive": len([item for item in patterns if item.get("tone") == "positive"]),
                "watch": len([item for item in patterns if item.get("tone") == "watch"]),
            },
        }

    def format_for_context(self, state: Optional[Dict[str, Any]] = None) -> str:
        state = state or self.build_state()
        active = state.get("active") or []
        if not active:
            return "暂无稳定行为模式。不要凭单次行为推断用户长期状态。"
        lines = [
            "以下是从任务、专注、承诺和监督事件中提炼的行为模式。它们只是观察线索，不是评价或诊断。",
            "使用方式：只在相关时给一句轻量建议，避免给用户施压。",
        ]
        for index, pattern in enumerate(active[:5], start=1):
            evidence = "；".join(pattern.get("evidence", [])[:2])
            lines.append(
                f"{index}. [{pattern.get('severity', 'low')}] {pattern.get('title', '')}: "
                f"{pattern.get('summary', '')} 证据: {evidence}"
            )
        return "\n".join(lines)

    def _focus_patterns(
        self,
        sessions: List[Dict[str, Any]],
        supervision_events: List[Dict[str, Any]],
        stats: Dict[str, Any],
        now_text: str,
    ) -> List[Dict[str, Any]]:
        patterns = []
        focus_stats = stats.get("focus", {})
        total = int(focus_stats.get("total_sessions", 0) or 0)
        completed = int(focus_stats.get("completed_sessions", 0) or 0)
        rate = float(focus_stats.get("completion_rate", 0) or 0)
        expired_events = [event for event in supervision_events if event.get("type") == "focus_expired"]
        abandoned = [session for session in sessions if session.get("status") == "abandoned"]

        if total >= 3 and rate < 0.5:
            patterns.append(self._pattern(
                "focus_completion_fragile",
                "专注会话完成率偏低",
                f"历史专注会话完成 {completed}/{total} 次，说明专注启动后容易中断或超时。",
                "watch",
                "medium",
                len(sessions),
                [
                    f"专注完成率 {int(rate * 100)}%",
                    f"放弃会话 {len(abandoned)} 次，超时提醒 {len(expired_events)} 次",
                ],
                "用户准备开始任务时，可以建议先收窄任务边界，回来时只汇报一个最小进展。",
                now_text,
            ))

        if len(expired_events) >= 2:
            patterns.append(self._pattern(
                "focus_often_overruns",
                "专注会话经常超时",
                "多次出现专注超时事件，适合在用户开始任务前提醒留一个自然收束点。",
                "watch",
                "low",
                len(expired_events),
                [f"累计专注超时监督事件 {len(expired_events)} 个"],
                "提醒用户离开前选一个可收束的小成果，而不是要求严格打卡。",
                now_text,
            ))
        return patterns

    def _commitment_patterns(
        self,
        commitments: List[Dict[str, Any]],
        supervision_events: List[Dict[str, Any]],
        stats: Dict[str, Any],
        now_text: str,
    ) -> List[Dict[str, Any]]:
        patterns = []
        commitment_stats = stats.get("commitments", {})
        open_items = [item for item in commitments if item.get("status") == "open"]
        overdue_events = [event for event in supervision_events if event.get("type") == "commitment_overdue"]
        opened = int(commitment_stats.get("opened_this_week", 0) or 0)
        closed = int(commitment_stats.get("closed_this_week", 0) or 0)
        rate = float(commitment_stats.get("fulfillment_rate_week", 0) or 0)

        if len(open_items) >= 3 or len(overdue_events) >= 2:
            patterns.append(self._pattern(
                "commitment_backlog",
                "未关闭承诺偏多",
                "存在多个未关闭或逾期承诺，Agent 需要帮用户收束主线，而不是继续增加新承诺。",
                "watch",
                "medium",
                len(open_items) + len(overdue_events),
                [
                    f"当前未关闭承诺 {len(open_items)} 个",
                    f"承诺逾期事件 {len(overdue_events)} 个",
                ],
                "当用户继续加任务时，可以温和提示先关闭、延期或放下一个旧承诺。",
                now_text,
            ))

        if opened >= 2 and rate < 0.5:
            patterns.append(self._pattern(
                "commitment_followthrough_low",
                "本周承诺履行率偏低",
                f"本周新增承诺 {opened} 个，关闭 {closed} 个，说明承诺可能比执行节奏更快累积。",
                "watch",
                "low",
                opened,
                [f"本周承诺履行率 {int(rate * 100)}%"],
                "减少追问，多帮助用户选择一个最值得先关闭的承诺。",
                now_text,
            ))
        return patterns

    def _task_patterns(
        self,
        tasks: List[Dict[str, Any]],
        supervision_events: List[Dict[str, Any]],
        now: datetime,
        now_text: str,
    ) -> List[Dict[str, Any]]:
        patterns = []
        open_tasks = [task for task in tasks if task.get("status") in {"inbox", "planned", "active", "blocked"}]
        stale_tasks = []
        for task in open_tasks:
            updated_at = self._parse_time(task.get("updated_at", ""))
            if updated_at and (now - updated_at).total_seconds() >= 24 * 3600:
                stale_tasks.append(task)
        stale_events = [event for event in supervision_events if event.get("type") == "task_stale"]

        if len(open_tasks) >= 5:
            patterns.append(self._pattern(
                "task_scatter",
                "未关闭任务偏分散",
                "当前开放任务较多，用户打开页面时可能不容易一眼看到主线。",
                "watch",
                "medium",
                len(open_tasks),
                [f"开放任务 {len(open_tasks)} 个"],
                "回复时优先帮用户收束为一个当前主线，而不是展开所有任务细节。",
                now_text,
            ))

        if len(stale_tasks) >= 2 or len(stale_events) >= 2:
            patterns.append(self._pattern(
                "task_staleness",
                "任务更新间隔偏长",
                "多个任务或监督事件显示任务长时间没有更新，适合轻提醒用户回到主线。",
                "watch",
                "low",
                len(stale_tasks) + len(stale_events),
                [
                    f"久未更新任务 {len(stale_tasks)} 个",
                    f"任务停滞事件 {len(stale_events)} 个",
                ],
                "用户回来时可以先问一个很轻的问题：现在要继续、完成还是先放下。",
                now_text,
            ))
        return patterns

    def _reminder_feedback_patterns(
        self,
        supervision_events: List[Dict[str, Any]],
        now_text: str,
    ) -> List[Dict[str, Any]]:
        feedback_actions: Dict[str, int] = {}
        for event in supervision_events:
            for item in event.get("feedback_history", []) or []:
                if not isinstance(item, dict):
                    continue
                action = str(item.get("action", "")).strip()
                if action:
                    feedback_actions[action] = feedback_actions.get(action, 0) + 1
        delayed = feedback_actions.get("snoozed", 0) + feedback_actions.get("muted", 0)
        closed = feedback_actions.get("resolved", 0) + feedback_actions.get("acknowledged", 0)
        if delayed >= 3 and delayed > closed:
            return [self._pattern(
                "reminder_friction",
                "提醒可能偏打扰",
                "用户对提醒更多选择稍后或静音，说明主动监督强度可能需要降低。",
                "watch",
                "medium",
                delayed,
                [f"snooze/mute 共 {delayed} 次", f"ack/done 共 {closed} 次"],
                "降低提醒强度，把更多低优先级事件留在页面内显示。",
                now_text,
            )]
        return []

    def _positive_activity_patterns(
        self,
        sessions: List[Dict[str, Any]],
        stats: Dict[str, Any],
        now_text: str,
    ) -> List[Dict[str, Any]]:
        focus = stats.get("focus", {})
        activity = stats.get("activity", {})
        active_days = int(activity.get("active_days_this_week", 0) or 0)
        completed = int(focus.get("completed_sessions", 0) or 0)
        if active_days >= 4 and completed >= 1:
            return [self._pattern(
                "steady_checkin",
                "本周有稳定回访节奏",
                "用户本周多天回到 Agent，并有已完成的专注片段，这是可以被温和强化的好节奏。",
                "positive",
                "low",
                active_days,
                [f"过去 7 天活跃 {active_days} 天", f"累计完成专注会话 {completed} 次"],
                "在合适时轻轻肯定稳定回访，不要夸张表扬或制造压力。",
                now_text,
            )]
        return []

    def _pattern(
        self,
        pattern_id: str,
        title: str,
        summary: str,
        tone: str,
        severity: str,
        frequency: int,
        evidence: List[str],
        intervention: str,
        now_text: str,
    ) -> Dict[str, Any]:
        return {
            "id": pattern_id,
            "title": title,
            "summary": summary,
            "tone": tone,
            "severity": severity,
            "frequency": int(frequency),
            "evidence": [item for item in evidence if item],
            "suggested_intervention": intervention,
            "status": "active",
            "first_seen_at": now_text,
            "updated_at": now_text,
        }

    def _normalize_pattern(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict) or not item.get("id"):
            return {}
        return {
            "id": str(item.get("id", "")),
            "title": str(item.get("title", "")),
            "summary": str(item.get("summary", "")),
            "tone": str(item.get("tone", "watch")),
            "severity": str(item.get("severity", "low")),
            "frequency": int(item.get("frequency", 0) or 0),
            "evidence": item.get("evidence", []) if isinstance(item.get("evidence", []), list) else [],
            "suggested_intervention": str(item.get("suggested_intervention", "")),
            "status": str(item.get("status", "active")),
            "first_seen_at": str(item.get("first_seen_at", "")),
            "updated_at": str(item.get("updated_at", "")),
        }

    def _severity_rank(self, pattern: Dict[str, Any]) -> int:
        if pattern.get("tone") == "positive":
            return 0
        return {"high": 3, "medium": 2, "low": 1}.get(pattern.get("severity", "low"), 1)

    def _parse_time(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
