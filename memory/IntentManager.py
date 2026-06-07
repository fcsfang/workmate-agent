import json
from typing import Any, Dict, List, Optional


class IntentManager:
    VALID_INTENTS = {"chat", "task", "review", "supervision", "search"}

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def classify(self, prompt: str) -> Dict[str, Any]:
        prompt = str(prompt or "")
        fallback_intent = self.rule_intent(prompt)
        if not self.llm_client or not prompt.strip():
            return self._result(fallback_intent, "rule", 0.5, "llm_unavailable")

        try:
            raw = self._invoke_llm(prompt)
            parsed = self._parse_json_object(raw)
            intent = str(parsed.get("intent", "")).strip().lower()
            if intent not in self.VALID_INTENTS:
                raise ValueError(f"invalid intent: {intent}")
            confidence = self._confidence(parsed.get("confidence", 0.7))
            reason = str(parsed.get("reason", "")).strip()[:160]
            return self._result(intent, "llm", confidence, reason)
        except Exception as exc:
            return self._result(fallback_intent, "rule_fallback", 0.45, str(exc)[:160])

    def rule_intent(self, prompt: str) -> str:
        prompt = str(prompt or "")
        if self._has_any(prompt, ["提醒", "监督", "检查", "催我"]):
            return "supervision"
        if self._has_any(prompt, ["之前", "上次", "相关", "找一下"]):
            return "search"
        if self._has_any(prompt, ["任务", "进度", "完成", "做完", "计划", "下一步", "卡住", "继续", "开发", "优化"]):
            return "task"
        if self._has_any(prompt, ["总结", "复盘", "回顾", "最近", "历史", "记忆"]):
            return "review"
        return "chat"

    def format_for_context(self, classification: Dict[str, Any]) -> str:
        if not classification:
            return "暂无意图识别结果。"
        return "\n".join([
            "以下是本轮输入的意图识别结果。请按该意图选择上下文使用方式，不要机械复述。",
            f"intent: {classification.get('intent', 'chat')}",
            f"source: {classification.get('source', 'rule')}",
            f"confidence: {classification.get('confidence', 0)}",
            f"reason: {classification.get('reason', '')}",
        ])

    def _invoke_llm(self, prompt: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的意图分类器。"
                    "只判断用户当前输入属于哪一种意图，不要回答用户问题。"
                    "只能输出合法 JSON，不要 Markdown。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请把下面输入分类到一个 intent。\n"
                    "可选 intent:\n"
                    "- chat: 普通聊天、表达想法、让我记住但不需要历史检索\n"
                    "- task: 任务规划、进度汇报、下一步、卡住、开发或优化\n"
                    "- review: 总结、复盘、回顾最近状态、查看记忆趋势\n"
                    "- supervision: 明确要求提醒、监督、检查、催促\n"
                    "- search: 明确询问之前、上次、相关历史或要求查找旧记录\n\n"
                    "输出 schema:\n"
                    '{"intent":"chat|task|review|supervision|search","confidence":0.0,"reason":"一句话理由"}\n\n'
                    f"用户输入:\n{prompt[:1200]}"
                ),
            },
        ]
        if hasattr(self.llm_client, "invoke_raw"):
            return self.llm_client.invoke_raw(messages)
        return self.llm_client.invoke(messages=messages)

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("intent output is not a JSON object")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("intent output JSON is not object")
        return parsed

    def _confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.7
        return max(0.0, min(1.0, confidence))

    def _result(self, intent: str, source: str, confidence: float, reason: str) -> Dict[str, Any]:
        return {
            "intent": intent if intent in self.VALID_INTENTS else "chat",
            "source": source,
            "confidence": round(confidence, 3),
            "reason": reason,
        }

    def _has_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)
