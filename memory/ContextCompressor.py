from typing import Dict, List


class ContextCompressor:
    def __init__(
        self,
        system_budget: int = 9000,
        recent_message_budget: int = 4000,
        message_budget: int = 1800,
    ):
        self.system_budget = system_budget
        self.recent_message_budget = recent_message_budget
        self.message_budget = message_budget

    def compress_system_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        compressed = []
        used = 0
        for message in messages:
            content = message.get("content", "")
            if used >= self.system_budget:
                break
            remaining = self.system_budget - used
            trimmed = self._compact(content, min(self.message_budget, remaining))
            if trimmed:
                compressed.append({**message, "content": trimmed})
                used += len(trimmed)
        if len(compressed) < len(messages):
            compressed.append({
                "role": "system",
                "content": "部分长期上下文已被压缩或省略；如当前问题需要旧细节，请优先依赖相关记忆项和摘要。",
            })
        return compressed

    def recent_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        kept = []
        used = 0
        for message in reversed(messages):
            content = message.get("content", "")
            compacted = self._compact(content, self.message_budget)
            if not compacted:
                continue
            if used + len(compacted) > self.recent_message_budget and kept:
                break
            kept.append({**message, "content": compacted})
            used += len(compacted)
        return list(reversed(kept))

    def estimate_context(self, messages: List[Dict[str, str]]) -> Dict[str, int]:
        total_chars = sum(len(message.get("content", "")) for message in messages)
        return {
            "message_count": len(messages),
            "estimated_chars": total_chars,
            "rough_token_estimate": max(1, total_chars // 2),
        }

    def _compact(self, text: str, max_length: int) -> str:
        text = str(text or "").strip()
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "\n...（已压缩）"
