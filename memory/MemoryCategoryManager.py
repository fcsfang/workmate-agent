import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryCategoryManager:
    CATEGORY_DESCRIPTIONS = {
        "tasks": "主任务和用户明确提出的子任务",
        "progress": "用户汇报的真实进展",
        "risks": "阻塞、拖延、分心和偏离风险",
        "actions": "下一步行动建议",
        "commitments": "用户明确承诺的事项",
        "patterns": "长期行为模式",
        "supervision": "对用户有效的轻量提醒方式",
        "profile": "长期用户画像和沟通偏好",
        "general": "其他可复用记忆",
    }

    def __init__(self, categories_path: Optional[str] = None):
        memory_dir = Path(__file__).resolve().parent
        self.categories_path = Path(categories_path) if categories_path else memory_dir / "memory_categories.json"
        self.categories_path.parent.mkdir(parents=True, exist_ok=True)

    def load_categories(self) -> List[Dict[str, Any]]:
        if not self.categories_path.exists() or self.categories_path.stat().st_size == 0:
            return []
        try:
            with self.categories_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [category for category in (self._normalize_category(item) for item in data) if category]

    def save_categories(self, categories: List[Dict[str, Any]]) -> None:
        with self.categories_path.open("w", encoding="utf-8") as file:
            json.dump(categories, file, ensure_ascii=False, indent=2)

    def rebuild_from_items(self, memory_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = datetime.now().isoformat(timespec="seconds")
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in memory_items:
            category = item.get("category") or "general"
            grouped.setdefault(category, []).append(item)

        categories = []
        for name, items in grouped.items():
            sorted_items = sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)
            type_counts = Counter(item.get("type", "note") for item in sorted_items)
            latest_items = [
                {
                    "id": item.get("id", ""),
                    "type": item.get("type", ""),
                    "content": self._compact(item.get("content", ""), 120),
                    "updated_at": item.get("updated_at", ""),
                }
                for item in sorted_items[:5]
            ]
            salience = round(sum(float(item.get("salience", 0)) for item in sorted_items) / max(len(sorted_items), 1), 3)
            categories.append({
                "id": self._make_id(name),
                "name": name,
                "description": self.CATEGORY_DESCRIPTIONS.get(name, self.CATEGORY_DESCRIPTIONS["general"]),
                "summary": self._build_summary(name, sorted_items, type_counts),
                "item_count": len(sorted_items),
                "type_counts": dict(type_counts),
                "latest_item_ids": [item.get("id", "") for item in sorted_items[:10] if item.get("id")],
                "latest_items": latest_items,
                "salience": salience,
                "updated_at": now,
            })

        categories.sort(key=lambda item: (item.get("item_count", 0), item.get("salience", 0)), reverse=True)
        self.save_categories(categories)
        return categories

    def search_categories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        terms = self._terms(query)
        if not terms:
            return []
        results = []
        for category in self.load_categories():
            text = " ".join([
                category.get("name", ""),
                category.get("description", ""),
                category.get("summary", ""),
                json.dumps(category.get("type_counts", {}), ensure_ascii=False),
            ])
            category_terms = self._terms(text)
            score = sum(category_terms.count(term) for term in terms)
            if score:
                results.append({**category, "score": round(score + float(category.get("salience", 0)), 3)})
        results.sort(key=lambda item: (item["score"], item.get("updated_at", "")), reverse=True)
        return results[:limit]

    def get_top_categories(self, limit: int = 6) -> List[Dict[str, Any]]:
        return self.load_categories()[:limit]

    def format_for_context(self, categories: Optional[List[Dict[str, Any]]] = None, limit: int = 5) -> str:
        categories = categories if categories is not None else self.get_top_categories(limit=limit)
        if not categories:
            return "暂无记忆分类摘要。"
        lines = ["以下是记忆分类摘要。请用它先判断当前问题应关注哪类记忆；回应时优先记住和整理。"]
        for index, category in enumerate(categories[:limit], start=1):
            lines.append(
                f"{index}. [{category.get('name', '')}] "
                f"items={category.get('item_count', 0)} | {self._soften_context_text(category.get('summary', ''))}"
            )
        return "\n".join(lines)

    def _normalize_category(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict) or not item.get("name"):
            return {}
        latest_items = item.get("latest_items", [])
        if not isinstance(latest_items, list):
            latest_items = []
        return {
            "id": item.get("id") or self._make_id(item.get("name", "")),
            "name": item.get("name", "general"),
            "description": item.get("description", ""),
            "summary": self._compact(item.get("summary", ""), 360),
            "item_count": int(item.get("item_count", 0)),
            "type_counts": item.get("type_counts", {}) if isinstance(item.get("type_counts", {}), dict) else {},
            "latest_item_ids": item.get("latest_item_ids", []) if isinstance(item.get("latest_item_ids", []), list) else [],
            "latest_items": latest_items[:8],
            "salience": float(item.get("salience", 0)),
            "updated_at": item.get("updated_at", ""),
        }

    def _build_summary(self, name: str, items: List[Dict[str, Any]], type_counts: Counter) -> str:
        examples = [self._compact(item.get("content", ""), 80) for item in items[:3] if item.get("content")]
        count_text = "、".join(f"{key}:{value}" for key, value in type_counts.most_common(4))
        example_text = "；".join(examples)
        if example_text:
            return f"{self.CATEGORY_DESCRIPTIONS.get(name, name)}。类型分布: {count_text}。最近: {example_text}"
        return f"{self.CATEGORY_DESCRIPTIONS.get(name, name)}。类型分布: {count_text}"

    def _terms(self, text: str) -> List[str]:
        separators = " \n\t\r，。！？、；;:：/\\|+-_*()（）[]【】{}<>\"'"
        normalized = str(text).lower()
        for separator in separators:
            normalized = normalized.replace(separator, " ")
        terms = [part.strip() for part in normalized.split() if len(part.strip()) >= 2]
        for keyword in ["任务", "进度", "阻塞", "风险", "承诺", "监督", "画像", "偏好", "子任务"]:
            if keyword in normalized:
                terms.append(keyword)
        return terms

    def _make_id(self, name: str) -> str:
        digest = hashlib.sha256(str(name or "general").encode("utf-8")).hexdigest()[:12]
        return f"cat-{digest}"

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."

    def _soften_context_text(self, text: Any) -> str:
        replacements = {
            "强制用户": "可以轻量提醒用户",
            "直接指出问题": "温和指出一个可能风险",
            "直接指出": "温和指出",
            "强调真实产出": "关注核心事项和实际进展",
            "监督方式": "轻量提醒方式",
            "监督": "轻量提醒",
            "质疑": "提出一个问题",
            "催促": "轻轻提醒",
        }
        softened = str(text or "")
        for old, new in replacements.items():
            softened = softened.replace(old, new)
        return self._compact(softened, 360)
