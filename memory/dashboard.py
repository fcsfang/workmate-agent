from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


class DashboardManager:
    def build_state(
        self,
        task_view: Dict[str, Any],
        tasks: List[Dict[str, Any]],
        focus_state: Dict[str, Any],
        focus_sessions: List[Dict[str, Any]],
        commitments: List[Dict[str, Any]],
        records: List[Dict[str, Any]],
        supervision_events: Dict[str, Any],
        behavior_patterns: Dict[str, Any],
    ) -> Dict[str, Any]:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        today_text = today.isoformat()
        week_start_text = week_start.isoformat()

        current_task = (task_view or {}).get("current") or {}
        open_tasks = [
            task for task in tasks
            if task.get("status") in {"inbox", "planned", "active", "blocked"}
        ]
        blocked_tasks = [task for task in open_tasks if task.get("status") == "blocked"]
        completed_today = [
            task for task in tasks
            if task.get("status") == "done" and self._date_prefix(task.get("completed_at", "")) == today_text
        ]
        completed_week = [
            task for task in tasks
            if task.get("status") == "done" and self._date_prefix(task.get("completed_at", "")) >= week_start_text
        ]

        completed_focus_today = [
            session for session in focus_sessions
            if session.get("status") == "completed" and self._date_prefix(session.get("started_at", "")) == today_text
        ]
        completed_focus_week = [
            session for session in focus_sessions
            if session.get("status") == "completed" and self._date_prefix(session.get("started_at", "")) >= week_start_text
        ]

        open_commitments = [item for item in commitments if item.get("status") == "open"]
        closed_commitments_today = [
            item for item in commitments
            if item.get("status") == "closed" and self._date_prefix(item.get("closed_at", "")) == today_text
        ]
        opened_commitments_week = [
            item for item in commitments
            if self._date_prefix(item.get("created_at", "")) >= week_start_text
        ]
        closed_commitments_week = [
            item for item in commitments
            if item.get("status") == "closed" and self._date_prefix(item.get("closed_at", "")) >= week_start_text
        ]
        due_or_overdue = [
            item for item in open_commitments
            if item.get("deadline") and self._is_due_or_overdue(item.get("deadline", ""))
        ]

        active_days_week = {
            self._date_prefix(record.get("time", ""))
            for record in records
            if self._date_prefix(record.get("time", "")) >= week_start_text
        }
        active_days_week.discard("")

        active_patterns = (behavior_patterns or {}).get("active") or []
        active_events = (supervision_events or {}).get("active") or []

        dashboard = {
            "today": {
                "date": today_text,
                "focus_completed": len(completed_focus_today),
                "focus_minutes": self._sum_minutes(completed_focus_today),
                "tasks_completed": len(completed_today),
                "commitments_closed": len(closed_commitments_today),
                "open_commitments": len(open_commitments),
                "due_or_overdue_commitments": len(due_or_overdue),
                "active_supervision_events": len(active_events),
            },
            "mainline": self._mainline(current_task),
            "load": {
                "open_tasks": len(open_tasks),
                "blocked_tasks": len(blocked_tasks),
                "task_dispersion": self._dispersion_label(len(open_tasks)),
                "active_patterns": len(active_patterns),
            },
            "week": {
                "start": week_start_text,
                "focus_completed": len(completed_focus_week),
                "focus_minutes": self._sum_minutes(completed_focus_week),
                "tasks_completed": len(completed_week),
                "commitments_opened": len(opened_commitments_week),
                "commitments_closed": len(closed_commitments_week),
                "commitment_fulfillment_rate": (
                    round(len(closed_commitments_week) / len(opened_commitments_week), 2)
                    if opened_commitments_week else 0.0
                ),
                "active_days": len(active_days_week),
            },
            "suggestion": self._suggestion(
                current_task=current_task,
                open_tasks=open_tasks,
                due_or_overdue=due_or_overdue,
                active_events=active_events,
                active_patterns=active_patterns,
                focus_state=focus_state,
            ),
            "quick_actions": self._quick_actions(current_task, focus_state, active_events),
        }
        return dashboard

    def format_for_context(self, dashboard: Dict[str, Any]) -> str:
        today = dashboard.get("today", {})
        week = dashboard.get("week", {})
        mainline = dashboard.get("mainline", {})
        suggestion = dashboard.get("suggestion", {})
        lines = [
            "以下是个人自律仪表盘摘要。它用于帮助用户一眼回到主线，不要变成评分或压力。",
            f"当前主线: {mainline.get('title') or '暂无'} ({mainline.get('status') or 'idle'})",
            (
                f"今日: 完成专注 {today.get('focus_completed', 0)} 次/{today.get('focus_minutes', 0)} 分钟，"
                f"完成任务 {today.get('tasks_completed', 0)} 个，"
                f"未关闭承诺 {today.get('open_commitments', 0)} 个。"
            ),
            (
                f"本周: 专注 {week.get('focus_minutes', 0)} 分钟，"
                f"完成任务 {week.get('tasks_completed', 0)} 个，"
                f"活跃 {week.get('active_days', 0)} 天。"
            ),
        ]
        if suggestion.get("message"):
            lines.append("轻建议: " + suggestion["message"])
        return "\n".join(lines)

    def _mainline(self, task: Dict[str, Any]) -> Dict[str, Any]:
        subtasks = task.get("subtasks", []) if isinstance(task.get("subtasks", []), list) else []
        return {
            "task_id": task.get("id", ""),
            "title": task.get("title", ""),
            "status": task.get("status", "idle") if task.get("id") else "idle",
            "next_action": (task.get("next_actions") or [""])[0] if task.get("next_actions") else "",
            "progress": (task.get("progress") or [""])[-1] if task.get("progress") else "",
            "subtasks_done": len([item for item in subtasks if item.get("status") == "done"]),
            "subtasks_total": len(subtasks),
            "updated_at": task.get("updated_at", ""),
        }

    def _suggestion(
        self,
        current_task: Dict[str, Any],
        open_tasks: List[Dict[str, Any]],
        due_or_overdue: List[Dict[str, Any]],
        active_events: List[Dict[str, Any]],
        active_patterns: List[Dict[str, Any]],
        focus_state: Dict[str, Any],
    ) -> Dict[str, str]:
        current_focus = (focus_state or {}).get("current") or {}
        if current_focus.get("status") == "expired":
            return {
                "tone": "gentle",
                "source": "focus_expired",
                "message": "当前有一段专注已经超时，回来时先轻轻收束一下进展就好。",
            }
        if due_or_overdue:
            return {
                "tone": "gentle",
                "source": "commitments",
                "message": "今天可以先处理一个到期承诺，关闭、延期或放下都算把状态整理清楚。",
            }
        if active_events:
            return {
                "tone": "gentle",
                "source": "supervision_events",
                "message": "有未处理的监督事件，适合先看一眼，再决定继续、稍后还是关闭。",
            }
        if len(open_tasks) >= 5:
            return {
                "tone": "gentle",
                "source": "task_dispersion",
                "message": "当前开放任务有点多，先选一个主线推进，比同时摊开更轻松。",
            }
        if active_patterns:
            return {
                "tone": "gentle",
                "source": "behavior_patterns",
                "message": "最近有一些可观察的行动模式，今天只需要抓住一个小闭环就很好。",
            }
        if current_task.get("id"):
            return {
                "tone": "gentle",
                "source": "mainline",
                "message": "当前主线已经在这里了，先推进一个最小进展就可以。",
            }
        return {
            "tone": "gentle",
            "source": "idle",
            "message": "现在还没有明确主线，可以先写下一件接下来要做的小事。",
        }

    def _quick_actions(
        self,
        current_task: Dict[str, Any],
        focus_state: Dict[str, Any],
        active_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        current_focus = (focus_state or {}).get("current") or {}
        actions = []
        if current_task.get("id") and not current_focus:
            actions.append({
                "id": "start_focus_mainline",
                "label": "Start focus",
                "kind": "focus",
                "target_id": current_task.get("id", ""),
                "enabled": True,
                "hint": "用当前主线开启一段专注",
            })
        if current_task.get("id"):
            actions.append({
                "id": "complete_mainline",
                "label": "Complete task",
                "kind": "task",
                "target_id": current_task.get("id", ""),
                "enabled": current_task.get("status") not in {"done", "abandoned"},
                "hint": "把当前主线标记完成",
            })
        if active_events:
            actions.append({
                "id": "review_supervision",
                "label": "Review reminders",
                "kind": "supervision",
                "target_id": active_events[0].get("id", ""),
                "enabled": True,
                "hint": "处理第一个监督事件",
            })
        return actions[:3]

    def _sum_minutes(self, sessions: List[Dict[str, Any]]) -> int:
        return sum(int(item.get("elapsed_minutes") or 0) for item in sessions)

    def _date_prefix(self, value: str) -> str:
        return str(value or "")[:10]

    def _is_due_or_overdue(self, deadline: str) -> bool:
        parsed = self._parse_time(deadline)
        return bool(parsed and parsed.date() <= date.today())

    def _parse_time(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _dispersion_label(self, open_task_count: int) -> str:
        if open_task_count >= 8:
            return "high"
        if open_task_count >= 4:
            return "medium"
        return "low"
