from typing import Dict, List


class ContextPlanner:
    def plan(self, current_prompt: str, available: Dict[str, str]) -> List[Dict[str, str]]:
        prompt = str(current_prompt or "")
        intent = self._intent(prompt)
        messages: List[Dict[str, str]] = []

        self._append(messages, available.get("user_profile"))
        self._append(messages, available.get("task_lifecycle"))
        self._append(messages, available.get("task_state"))

        if intent in {"task", "review", "supervision", "search"}:
            self._append(messages, available.get("high_level_insights"))
            self._append(messages, available.get("memory_governance"))

        if intent in {"task", "review", "supervision"}:
            self._append(messages, available.get("supervision"))

        if intent in {"task", "review", "search", "supervision"}:
            self._append(messages, available.get("retrieval_plan"))
            self._append(messages, available.get("semantic_dialogues"))
            self._append(messages, available.get("memory_categories"))
            self._append(messages, available.get("memory_items"))

        if intent in {"task", "review", "supervision"}:
            self._append(messages, available.get("commitments"))
            self._append(messages, available.get("recent_summary"))

        if intent in {"task", "review", "search"}:
            self._append(messages, available.get("related_memories"))

        if intent == "review":
            self._append(messages, available.get("reflections"))
            self._append(messages, available.get("memory_summary"))
            self._append(messages, available.get("structured_summary"))
        elif intent == "task":
            self._append(messages, available.get("structured_summary"))

        if len(messages) <= 3:
            self._append(messages, available.get("high_level_insights"))
            self._append(messages, available.get("semantic_dialogues"))
            self._append(messages, available.get("memory_categories"))
            self._append(messages, available.get("memory_items"))
            self._append(messages, available.get("related_memories"))

        return messages

    def _intent(self, prompt: str) -> str:
        if self._has_any(prompt, ["总结", "复盘", "回顾", "最近", "历史", "记忆"]):
            return "review"
        if self._has_any(prompt, ["任务", "进度", "完成", "做完", "计划", "下一步", "卡住", "继续", "开发", "优化"]):
            return "task"
        if self._has_any(prompt, ["提醒", "监督", "检查", "催我"]):
            return "supervision"
        if self._has_any(prompt, ["之前", "上次", "相关", "找一下"]):
            return "search"
        return "chat"

    def _append(self, messages: List[Dict[str, str]], content: str) -> None:
        if content and content.strip() and content not in [message["content"] for message in messages]:
            messages.append({"role": "system", "content": content})

    def _has_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)
