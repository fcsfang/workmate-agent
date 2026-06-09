from datetime import datetime
from typing import Dict, List


class ContextPlanner:
    def plan(
        self,
        current_prompt: str,
        available: Dict[str, str],
        classification: Dict[str, str] = None,
        is_morning: bool = False,
        has_gap: bool = False,
        is_goodbye: bool = False,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for key in self.required_context_keys(
            current_prompt,
            classification=classification,
            is_morning=is_morning,
            has_gap=has_gap,
            is_goodbye=is_goodbye,
        ):
            self._append(messages, available.get(key))
        return messages

    def is_evening_goodbye(self, prompt: str) -> bool:
        hour = datetime.now().hour
        # 傍晚/深夜/清晨时段可能准备收工
        if hour >= 18 or hour < 6:
            goodbye_kws = ["下班", "收工", "走啦", "走人", "今天先到这里", "明天见", "休息了", "不搞了", "睡觉了", "晚安"]
            return any(kw in prompt for kw in goodbye_kws)
        return False

    def required_context_keys(
        self,
        current_prompt: str,
        classification: Dict[str, str] = None,
        is_morning: bool = False,
        has_gap: bool = False,
        is_goodbye: bool = False,
    ) -> List[str]:
        intent = (classification or {}).get("intent") or self.intent(current_prompt)
        period = self.time_period()
        keys = ["intent", "user_profile", "task_lifecycle", "task_state", "focus_session", "time_context"]

        if is_morning:
            keys.append("morning_briefing")
        if is_goodbye:
            keys.append("evening_review")
        if has_gap:
            keys.append("gap_context")

        if period in {"morning", "evening"}:
            keys.append("behavior_stats")

        if intent in {"task", "review", "supervision", "search"}:
            keys.extend(["high_level_insights", "memory_governance"])

        if intent in {"task", "review", "supervision"} and period != "night":
            keys.append("supervision")

        if self.needs_support_knowledge(current_prompt):
            keys.append("support_knowledge")

        if intent in {"task", "review", "search", "supervision"}:
            keys.extend(["retrieval_plan", "semantic_dialogues", "memory_categories", "memory_items"])

        if intent in {"task", "review", "supervision"}:
            keys.extend(["commitments", "recent_summary"])

        if intent in {"task", "review", "search"}:
            keys.append("related_memories")

        if intent == "review":
            keys.extend(["reflections", "memory_summary", "structured_summary", "behavior_stats"])
        elif intent == "task":
            keys.append("structured_summary")
        elif intent == "weekly_report":
            keys.extend(["weekly_report_data", "high_level_insights", "behavior_stats", "commitments", "reflections"])
        return self._unique(keys)

    def time_period(self) -> str:
        hour = datetime.now().hour
        if 6 <= hour < 11:
            return "morning"
        if 11 <= hour < 18:
            return "afternoon"
        if 18 <= hour < 22:
            return "evening"
        return "night"

    def intent(self, prompt: str) -> str:
        if self._has_any(prompt, ["周报", "周复盘", "每周总结", "每周回顾", "本周总结", "本周复盘"]):
            return "weekly_report"
        if self._has_any(prompt, ["提醒", "监督", "检查", "催我"]):
            return "supervision"
        if self._has_any(prompt, ["之前", "上次", "相关", "找一下"]):
            return "search"
        if self._has_any(prompt, ["任务", "进度", "完成", "做完", "计划", "下一步", "卡住", "继续", "开发", "优化"]):
            return "task"
        if self._has_any(prompt, ["总结", "复盘", "回顾", "最近", "历史", "记忆"]):
            return "review"
        return "chat"

    def needs_support_knowledge(self, prompt: str) -> bool:
        return self._has_any(
            str(prompt or ""),
            [
                "焦虑", "慌", "烦", "压力", "害怕", "担心",
                "分心", "走神", "乱", "发散", "任务太多",
                "累", "困", "疲惫", "没力气", "低能量",
                "拖延", "不想做", "逃避", "刷手机", "开始不了",
                "过度规划", "想太多", "卡住", "卡在", "不会", "没思路",
                "接下来读", "先去读", "准备读", "接下来刷题", "先去刷题",
                "接下来写", "先去写", "接下来整理", "先去整理", "接下来调试",
            ],
        )

    def _append(self, messages: List[Dict[str, str]], content: str) -> None:
        if content and content.strip() and content not in [message["content"] for message in messages]:
            messages.append({"role": "system", "content": content})

    def _has_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _unique(self, keys: List[str]) -> List[str]:
        result = []
        for key in keys:
            if key not in result:
                result.append(key)
        return result
