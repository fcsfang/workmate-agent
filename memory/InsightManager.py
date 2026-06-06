import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class InsightManager:
    def __init__(self, insights_path: Optional[str] = None, llm_client: Any = None):
        memory_dir = Path(__file__).resolve().parent
        self.insights_path = Path(insights_path) if insights_path else memory_dir / "high_level_insights.json"
        self.llm_client = llm_client
        self.insights_path.parent.mkdir(parents=True, exist_ok=True)

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def load_insights(self) -> List[Dict[str, Any]]:
        if not self.insights_path.exists() or self.insights_path.stat().st_size == 0:
            return []
        try:
            with self.insights_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in (self._normalize_insight(item) for item in data) if item]

    def save_insights(self, insights: List[Dict[str, Any]]) -> None:
        with self.insights_path.open("w", encoding="utf-8") as file:
            json.dump(insights[-300:], file, ensure_ascii=False, indent=2)

    def update_from_reflection(
        self,
        memory_items: List[Dict[str, Any]],
        categories: List[Dict[str, Any]],
        semantic_dialogues: List[Dict[str, Any]],
        trigger: str,
    ) -> List[Dict[str, Any]]:
        insights = self.load_insights()
        candidates = self._build_llm_insights(memory_items, categories, semantic_dialogues)
        if not candidates:
            candidates = self._build_rule_insights(memory_items, categories, semantic_dialogues)
        now = datetime.now().isoformat(timespec="seconds")
        for candidate in candidates:
            content = self._compact(candidate.get("content", ""), 260)
            if not content:
                continue
            key = self._content_hash(content)
            match = next((item for item in insights if item.get("content_hash") == key), None)
            if match:
                match["updated_at"] = now
                match["support_count"] = max(int(match.get("support_count", 1)), int(candidate.get("support_count", 1)))
                match["confidence"] = max(float(match.get("confidence", 0.6)), float(candidate.get("confidence", 0.6)))
                match["status"] = "active"
            else:
                insights.append({
                    "id": f"ins-{now.replace('-', '').replace(':', '').replace('T', '-')}-{key[:8]}",
                    "type": candidate.get("type", "pattern"),
                    "content": content,
                    "why_it_matters": self._compact(candidate.get("why_it_matters", ""), 220),
                    "suggested_intervention": self._compact(candidate.get("suggested_intervention", ""), 220),
                    "support_count": int(candidate.get("support_count", 1)),
                    "confidence": float(candidate.get("confidence", 0.65)),
                    "status": "active",
                    "source": candidate.get("source", "rule"),
                    "trigger": trigger,
                    "content_hash": key,
                    "created_at": now,
                    "updated_at": now,
                })
        insights = sorted(insights, key=lambda item: (item.get("status") == "active", float(item.get("confidence", 0)), item.get("updated_at", "")), reverse=True)
        self.save_insights(insights)
        return insights

    def get_active_insights(self, limit: int = 8) -> List[Dict[str, Any]]:
        return [item for item in self.load_insights() if item.get("status") == "active"][:limit]

    def format_for_context(self, insights: Optional[List[Dict[str, Any]]] = None, limit: int = 6) -> str:
        insights = insights if insights is not None else self.get_active_insights(limit=limit)
        if not insights:
            return "暂无高阶洞察。"
        lines = ["以下是长期反省得到的高阶洞察。它们比低层碎片记忆更稳定，相关时优先使用。"]
        for index, item in enumerate(insights[:limit], start=1):
            parts = [
                f"{index}. [{item.get('type', 'pattern')}] {item.get('content', '')}",
                f"confidence={item.get('confidence', 0)}",
            ]
            if item.get("suggested_intervention"):
                parts.append("intervention=" + item["suggested_intervention"])
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def _build_llm_insights(
        self,
        memory_items: List[Dict[str, Any]],
        categories: List[Dict[str, Any]],
        semantic_dialogues: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not self.llm_client:
            return []
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的高阶洞察提炼器。"
                    "你要从近期记忆中找长期行为模式，不要做普通摘要。"
                    "只输出合法 JSON 数组，不要 Markdown。"
                ),
            },
            {
                "role": "user",
                "content": self._build_prompt(memory_items, categories, semantic_dialogues),
            },
        ]
        try:
            raw = self.llm_client.invoke_raw(messages) if hasattr(self.llm_client, "invoke_raw") else self.llm_client.invoke(messages=messages)
            parsed = self._parse_json_array(raw)
            result = []
            for item in parsed:
                if isinstance(item, dict):
                    normalized = dict(item)
                    normalized["source"] = "llm"
                    result.append(normalized)
            return result[:8]
        except Exception:
            return []

    def _build_rule_insights(
        self,
        memory_items: List[Dict[str, Any]],
        categories: List[Dict[str, Any]],
        semantic_dialogues: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        insights = []
        blockers = [item.get("content", "") for item in memory_items if item.get("type") == "blocker" and item.get("status") == "active"]
        blocker_counter = Counter([item for item in blockers if item])
        for blocker, count in blocker_counter.most_common(3):
            if count >= 2:
                insights.append({
                    "type": "repeated_blocker",
                    "content": f"用户反复遇到的阻塞是：{blocker}",
                    "why_it_matters": "这不是单次问题，后续监督应优先帮助用户收敛当前主线。",
                    "suggested_intervention": "先确认真实进展，再减少新分支。",
                    "support_count": count,
                    "confidence": 0.75,
                    "source": "rule",
                })

        category_counts = {category.get("name", ""): int(category.get("item_count", 0)) for category in categories}
        if category_counts.get("tasks", 0) >= 4 and category_counts.get("progress", 0) <= 1:
            insights.append({
                "type": "planning_over_execution",
                "content": "任务类记忆明显多于进展类记忆，用户可能在持续增加规划而不是交付产出。",
                "why_it_matters": "这会让任务系统膨胀，但真实推进不足。",
                "suggested_intervention": "提醒用户选择一个主线，并汇报具体产出。",
                "support_count": category_counts.get("tasks", 0),
                "confidence": 0.72,
                "source": "rule",
            })

        recent_text = " ".join(item.get("semantic_summary", "") for item in semantic_dialogues[:8])
        if any(keyword in recent_text for keyword in ["优化", "架构", "规划"]) and not any(keyword in recent_text for keyword in ["完成", "已实现", "跑通"]):
            insights.append({
                "type": "architecture_drift",
                "content": "近期对话偏向架构优化和规划，但完成/跑通类信号不足。",
                "why_it_matters": "这可能让记忆系统越做越复杂，却缺少可验证的实际闭环。",
                "suggested_intervention": "把下一步收束到一个可运行改动或一次明确验证。",
                "support_count": 1,
                "confidence": 0.68,
                "source": "rule",
            })
        return insights[:8]

    def _build_prompt(
        self,
        memory_items: List[Dict[str, Any]],
        categories: List[Dict[str, Any]],
        semantic_dialogues: List[Dict[str, Any]],
    ) -> str:
        schema = [{
            "type": "repeated_blocker|planning_over_execution|architecture_drift|effective_intervention|task_pattern",
            "content": "高阶洞察，不是普通摘要",
            "why_it_matters": "为什么重要",
            "suggested_intervention": "以后如何监督",
            "support_count": 2,
            "confidence": 0.7,
        }]
        payload = {
            "memory_items": memory_items[:40],
            "categories": categories[:12],
            "semantic_dialogues": semantic_dialogues[:20],
        }
        return (
            "请从近期记忆中提炼高阶洞察。\n"
            "要求：\n"
            "1. 不要做普通摘要；只输出长期行为模式、任务推进模式、反复风险、有效监督方式。\n"
            "2. 不要提供技术路线，不要新增任务。\n"
            "3. 输出 JSON 数组，最多 8 项。\n\n"
            f"schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _parse_json_array(self, text: str) -> List[Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise ValueError("insight output is not JSON array")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, list):
            raise ValueError("insight output JSON is not array")
        return parsed

    def _normalize_insight(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        content = self._compact(item.get("content", ""), 260)
        if not content:
            return {}
        return {
            "id": item.get("id", ""),
            "type": item.get("type", "pattern"),
            "content": content,
            "why_it_matters": self._compact(item.get("why_it_matters", ""), 220),
            "suggested_intervention": self._compact(item.get("suggested_intervention", ""), 220),
            "support_count": int(item.get("support_count", 1)),
            "confidence": float(item.get("confidence", 0.65)),
            "status": item.get("status", "active"),
            "source": item.get("source", "unknown"),
            "trigger": item.get("trigger", ""),
            "content_hash": item.get("content_hash") or self._content_hash(content),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def _content_hash(self, content: str) -> str:
        normalized = " ".join(str(content or "").lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
