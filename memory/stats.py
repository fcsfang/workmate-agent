"""Lightweight behavioral statistics computed from existing memory JSON files."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path


class BehaviorStatsManager:
    def __init__(
        self,
        focus_sessions_path: Optional[str] = None,
        commitments_path: Optional[str] = None,
        records_path: Optional[str] = None,
    ):
        self.focus_sessions_path = (
            Path(focus_sessions_path) if focus_sessions_path else memory_data_path("focus_sessions.json")
        )
        self.commitments_path = (
            Path(commitments_path) if commitments_path else memory_data_path("commitments.json")
        )
        self.records_path = (
            Path(records_path) if records_path else memory_data_path("records.json")
        )

    def compute_focus_stats(self, sessions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if sessions is None:
            sessions = self._load_json(self.focus_sessions_path)

        today_str = date.today().isoformat()
        last_7_days = {(date.today() - timedelta(days=i)).isoformat() for i in range(7)}

        completed = [s for s in sessions if s.get("status") == "completed"]
        sessions_today = [s for s in sessions if s.get("started_at", "")[:10] == today_str]

        active_days = {s.get("started_at", "")[:10] for s in sessions if s.get("started_at", "")[:10]}
        active_days_week = len(active_days & last_7_days)

        total_focus_minutes = sum(int(s.get("elapsed_minutes") or 0) for s in completed)
        avg_minutes = total_focus_minutes // len(completed) if completed else 0
        completion_rate = round(len(completed) / len(sessions), 2) if sessions else 0.0

        return {
            "total_sessions": len(sessions),
            "completed_sessions": len(completed),
            "completion_rate": completion_rate,
            "total_focus_minutes": total_focus_minutes,
            "avg_session_minutes": avg_minutes,
            "sessions_today": len(sessions_today),
            "active_days_this_week": active_days_week,
        }

    def compute_commitment_stats(self, commitments: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if commitments is None:
            commitments = self._load_json(self.commitments_path)

        now = datetime.now()
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

        open_items = [c for c in commitments if c.get("status") == "open"]
        closed_this_week = [
            c for c in commitments
            if c.get("status") == "closed"
            and self._parse_time(c.get("closed_at", ""))
            and self._parse_time(c.get("closed_at", "")) >= week_start
        ]
        opened_this_week = [
            c for c in commitments
            if self._parse_time(c.get("created_at", ""))
            and self._parse_time(c.get("created_at", "")) >= week_start
        ]

        fulfillment_rate = (
            round(len(closed_this_week) / len(opened_this_week), 2) if opened_this_week else 0.0
        )

        return {
            "open_count": len(open_items),
            "closed_this_week": len(closed_this_week),
            "opened_this_week": len(opened_this_week),
            "fulfillment_rate_week": fulfillment_rate,
        }

    def compute_activity_stats(self, records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if records is None:
            records = self._load_json(self.records_path)

        today = date.today()
        last_7_days = [(today - timedelta(days=i)).isoformat() for i in range(7)]
        active_days = {r.get("time", "")[:10] for r in records if r.get("time", "")[:10]}

        active_this_week = len(set(last_7_days) & active_days)

        consecutive = 0
        for i in range(7):
            if (today - timedelta(days=i)).isoformat() in active_days:
                consecutive += 1
            else:
                break

        return {
            "active_days_this_week": active_this_week,
            "consecutive_active_days": consecutive,
            "total_conversations": len(records),
        }

    def build_stats(
        self,
        sessions: Optional[List[Dict[str, Any]]] = None,
        commitments: Optional[List[Dict[str, Any]]] = None,
        records: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return {
            "focus": self.compute_focus_stats(sessions),
            "commitments": self.compute_commitment_stats(commitments),
            "activity": self.compute_activity_stats(records),
        }

    def format_for_context(self, stats: Optional[Dict[str, Any]] = None) -> str:
        if stats is None:
            stats = self.build_stats()

        focus = stats.get("focus", {})
        commitment = stats.get("commitments", {})
        activity = stats.get("activity", {})

        lines = ["以下是行为统计数据，用于理解用户的工作节奏。不要用这些数字给用户施压。"]

        if focus.get("total_sessions", 0) > 0:
            rate_pct = int(focus.get("completion_rate", 0) * 100)
            lines.append(
                f"专注会话：历史共 {focus['total_sessions']} 次，"
                f"完成 {focus['completed_sessions']} 次（完成率 {rate_pct}%），"
                f"累计 {focus['total_focus_minutes']} 分钟。"
                f"今日已开启 {focus['sessions_today']} 次。"
            )
        else:
            lines.append("专注会话：暂无历史记录。")

        if commitment.get("opened_this_week", 0) > 0:
            rate_pct = int(commitment.get("fulfillment_rate_week", 0) * 100)
            lines.append(
                f"承诺履行：本周新增 {commitment['opened_this_week']} 个，"
                f"关闭 {commitment['closed_this_week']} 个（履行率 {rate_pct}%）。"
                f"当前未关闭 {commitment['open_count']} 个。"
            )

        lines.append(
            f"活跃度：过去 7 天有 {activity['active_days_this_week']} 天与 Agent 交流，"
            f"已连续 {activity['consecutive_active_days']} 天。"
        )

        return "\n".join(lines)

    def format_time_context(self) -> str:
        hour = datetime.now().hour
        stats = self.build_stats()
        focus = stats.get("focus", {})

        if 6 <= hour < 11:
            period = "上午（工作启动时段）"
            tip = "适合帮用户整理今日主线任务，给一个轻量启动建议。"
        elif 11 <= hour < 18:
            period = "下午（专注工作时段）"
            tip = "适合聚焦当前任务推进，减少发散性建议。"
        elif 18 <= hour < 22:
            period = "傍晚（收尾时段）"
            tip = "适合帮用户做简短收束，不要发起新的大任务。"
        else:
            period = "深夜（休息时段）"
            tip = "适合轻松回应，不要推送任务压力或监督信号。"

        lines = [f"当前时间段：{period}"]
        sessions_today = focus.get("sessions_today", 0)
        focus_today_min = sum(
            int(s.get("elapsed_minutes") or 0)
            for s in self._load_json(self.focus_sessions_path)
            if s.get("status") == "completed" and s.get("started_at", "")[:10] == date.today().isoformat()
        )
        if sessions_today > 0:
            lines.append(f"今天已完成专注会话 {sessions_today} 次，共约 {focus_today_min} 分钟。")
        else:
            lines.append("今天还没有已完成的专注会话。")
        lines.append(tip)
        return "\n".join(lines)

    def get_behavior_stats(self) -> Dict[str, Any]:
        return self.build_stats()

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def _parse_time(self, text: str) -> Optional[datetime]:
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def is_first_message_today(self, records: Optional[List[Dict[str, Any]]] = None) -> bool:
        if records is None:
            records = self._load_json(self.records_path)
        if not records:
            return True
        last_time_str = records[-1].get("time", "")
        if not last_time_str:
            return True
        return last_time_str[:10] < date.today().isoformat()

    def get_conversation_gap_minutes(self, records: Optional[List[Dict[str, Any]]] = None) -> int:
        if records is None:
            records = self._load_json(self.records_path)
        if not records:
            return 0
        last_time_str = records[-1].get("time", "")
        if not last_time_str:
            return 0
        try:
            last_time = datetime.fromisoformat(last_time_str)
            delta = datetime.now() - last_time
            return max(0, int(delta.total_seconds() // 60))
        except Exception:
            return 0

    def format_morning_briefing(self, memory_manager: Any) -> str:
        today_str = date.today().isoformat()
        all_commitments = memory_manager.task_state.all_commitments()
        
        # 昨天的遗留承诺（在今天之前创建且依然为 open）
        yesterday_commitments = [
            c for c in all_commitments
            if c.get("status") == "open" and c.get("created_at", "")[:10] < today_str
        ]
        
        # 今天到期或已逾期的承诺
        now = datetime.now()
        due_or_overdue = []
        for c in all_commitments:
            if c.get("status") != "open":
                continue
            deadline_str = c.get("deadline", "")
            if deadline_str:
                try:
                    deadline_dt = datetime.fromisoformat(deadline_str)
                    if deadline_dt.date() <= now.date():
                        due_or_overdue.append(c)
                except ValueError:
                    pass

        task_view = memory_manager.get_task_view()
        current_task = task_view.get("current", {})
        current_title = current_task.get("title") if current_task.get("id") else "暂无当前任务"

        stats = self.build_stats()
        focus = stats.get("focus", {})
        commitment = stats.get("commitments", {})
        activity = stats.get("activity", {})

        lines = [
            "[今日首次对话早间简报]",
            "这是用户今天第一次发来消息。回复时请先温和地向用户问好（如“新的一天开始啦！”），简要提及状态并给出一个轻量的、无压力的工作/专注启动建议。",
            f"当前主线任务：{current_title}"
        ]

        if yesterday_commitments:
            lines.append("昨天未完成的承诺：")
            for c in yesterday_commitments:
                lines.append(f"  * {c.get('commitment')} (创建于: {c.get('created_at')[:10]})")

        if due_or_overdue:
            lines.append("今天到期/已逾期的承诺：")
            for c in due_or_overdue:
                dl_str = c.get("deadline", "")
                dl_label = f"截止 {dl_str[5:10]} {dl_str[11:16]}" if dl_str else "无期限"
                status_label = "[⚠ 已逾期]" if dl_str and datetime.fromisoformat(dl_str) < now else "[今天到期]"
                lines.append(f"  * {status_label} {c.get('commitment')} ({dl_label})")

        rate_pct = int(focus.get("completion_rate", 0) * 100)
        lines.extend([
            "本周行为统计：",
            f"  * 专注会话：本周已完成 {focus.get('completed_sessions', 0)} 次，累计 {focus.get('total_focus_minutes', 0)} 分钟，完成率 {rate_pct}%。",
            f"  * 承诺履行：本周新增 {commitment.get('opened_this_week', 0)} 个，履行率 {int(commitment.get('fulfillment_rate_week', 0) * 100)}%。",
            f"  * 活跃度：过去 7 天交流了 {activity.get('active_days_this_week', 0)} 天，已连续 {activity.get('consecutive_active_days', 0)} 天。"
        ])

        return "\n".join(lines)

    def format_evening_review(self, memory_manager: Any) -> str:
        today_str = date.today().isoformat()
        
        # 统计今日完成的专注会话
        sessions = self._load_json(self.focus_sessions_path)
        completed_today = [
            s for s in sessions 
            if s.get("status") == "completed" and s.get("started_at", "")[:10] == today_str
        ]
        total_minutes = sum(int(s.get("elapsed_minutes") or 0) for s in completed_today)
        
        # 统计今日关闭的承诺
        commitments = memory_manager.task_state.all_commitments()
        closed_today = [
            c for c in commitments
            if c.get("status") == "closed" and c.get("closed_at", "")[:10] == today_str
        ]
        
        # 获取当前阻塞任务
        task_view = memory_manager.get_task_view()
        current_task = task_view.get("current", {})
        blockers = current_task.get("blockers", []) if current_task else []

        lines = [
            "[晚间收工复盘指令]",
            "用户已表达下班/收工/走啦等意向。请用极其温暖、有同理心的纯自然语言口吻总结用户今天的成果并说再见。",
            "【今日数据参考】：",
            f"  - 累计完成专注会话：{len(completed_today)} 次，共 {total_minutes} 分钟",
            f"  - 今日关闭的承诺：{', '.join([c.get('commitment') for c in closed_today]) or '无'}",
            f"  - 当前卡点/阻塞项：{', '.join(blockers) or '无'}",
            "",
            "【Agent 回复策略（非常重要）】：",
            "1. 必须使用自然的段落式口吻，顺带提及上述工作进展与卡点（比如：“虽然跨域问题把你卡住了... 搞定了写简历... 专注了2次...”）。",
            "2. 严禁使用任何表格、硬性的 Markdown 列表、分割线或带有符号的清单，保持纯文本自然对话流。",
            "3. 绝对不要向用户提任何问题！直接给予温暖的祝愿（如“晚上好好休息，明天见”）收尾，引导对话自然结束。"
        ]
        return "\n".join(lines)

    def format_gap_context(self, memory_manager: Any) -> str:
        gap_min = self.get_conversation_gap_minutes()
        focus_state = memory_manager.get_focus_session_state()
        current_session = focus_state.get("current") or {}
        
        has_expired_focus = current_session.get("status") == "expired"
        
        # 只有间隔大于 30 分钟，或者存在已超时的专注会话时，才生成间隔感知上下文
        if gap_min < 30 and not has_expired_focus:
            return ""
            
        hours = gap_min // 60
        minutes = gap_min % 60
        gap_label = f"{hours} 小时 {minutes} 分钟" if hours > 0 else f"{minutes} 分钟"
        
        lines = [
            "[对话间隔与专注会话状态]"
        ]
        if gap_min >= 30:
            lines.append(f"距离上一次对话已过去：{gap_label}。")
            
        if has_expired_focus:
            lines.extend([
                f"专注会话超时：当前存在一个已超时（未标记完成）的专注会话：【{current_session.get('goal')}】。",
                f"该会话计划时长 {current_session.get('duration_minutes')} 分钟，实际已过去 {current_session.get('elapsed_minutes')} 分钟。",
                "【Agent 回复策略】：这是用户在会话超时后首次开口。请在回复中自然且温和地提及专注已超时，询问该会话的进展（如：是否完成了？被打断了？或者是否需要延期？），切忌催促或施加压力。"
            ])
        elif gap_min >= 30:
            lines.append("【Agent 回复策略】：距离上次对话已过去一段时间。请在回复中用温和的语气欢迎用户回来，引导用户继续刚才的话题或同步最新任务进度。")
            
        return "\n".join(lines)
