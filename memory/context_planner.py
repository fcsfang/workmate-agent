from typing import Dict, List


class ContextPlanner:
    def plan(
        self,
        current_prompt: str,
        available: Dict[str, str],
        classification: Dict[str, str] = None,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for key in self.required_context_keys(current_prompt, classification=classification):
            self._append(messages, available.get(key))
        return messages

    def required_context_keys(self, current_prompt: str, classification: Dict[str, str] = None) -> List[str]:
        intent = (classification or {}).get("intent") or self.intent(current_prompt)
        keys = ["intent", "user_profile", "task_lifecycle", "task_state", "focus_session"]

        if intent in {"task", "review", "supervision", "search"}:
            keys.extend(["high_level_insights", "memory_governance"])

        if intent in {"task", "review", "supervision"}:
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
            keys.extend(["reflections", "memory_summary", "structured_summary"])
        elif intent == "task":
            keys.append("structured_summary")
        return self._unique(keys)

    def intent(self, prompt: str) -> str:
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
