"""Storage layer for resources, memory items, and memory categories."""

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path


class MemoryResourceManager:
    def __init__(self, resources_path: Optional[str] = None):
        self.resources_path = Path(resources_path) if resources_path else memory_data_path("memory_resources.json")
        self.resources_path.parent.mkdir(parents=True, exist_ok=True)

    def load_resources(self) -> List[Dict[str, Any]]:
        if not self.resources_path.exists() or self.resources_path.stat().st_size == 0:
            return []
        try:
            with self.resources_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [resource for resource in (self._normalize_resource(item) for item in data) if resource]

    def save_resources(self, resources: List[Dict[str, Any]]) -> None:
        with self.resources_path.open("w", encoding="utf-8") as file:
            json.dump(resources[-800:], file, ensure_ascii=False, indent=2)

    def update_from_record(
        self,
        record: Dict[str, Any],
        task_state: Optional[Dict[str, Any]] = None,
        task_view: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resources = self.load_resources()
        task_state = task_state or {}
        current_task = (task_view or {}).get("current") or {}
        record_id = record.get("id", "")
        now = datetime.now().isoformat(timespec="seconds")
        resource = {
            "id": self._make_id(record_id or record.get("time", "")),
            "resource_type": "conversation_turn",
            "record_id": record_id,
            "time": record.get("time", ""),
            "modality": "text",
            "local_ref": "memory/data/records.json",
            "user_preview": self._compact(record.get("user", ""), 220),
            "assistant_preview": self._compact(record.get("assistant", ""), 220),
            "extracted_categories": (record.get("extracted") or {}).get("categories", []),
            "task_id": task_state.get("task_id", "") or current_task.get("id", ""),
            "task_title": task_state.get("active_task", "") or current_task.get("title", ""),
            "task_status": current_task.get("status", task_state.get("status", "")),
            "created_at": record.get("time", now),
            "updated_at": now,
        }

        match = next((item for item in resources if item.get("record_id") == record_id and record_id), None)
        if match:
            match.update(resource)
        else:
            resources.append(resource)
        self.save_resources(resources)
        return resource

    def get_recent_resources(self, limit: int = 20) -> List[Dict[str, Any]]:
        resources = self.load_resources()
        return sorted(resources, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit]

    def format_for_context(self, resources: Optional[List[Dict[str, Any]]] = None, limit: int = 5) -> str:
        resources = resources if resources is not None else self.get_recent_resources(limit=limit)
        if not resources:
            return "暂无资源层记录。"
        lines = ["以下是记忆资源层记录，用于追溯记忆来源。只在需要核对来源时使用。"]
        for index, resource in enumerate(resources[:limit], start=1):
            parts = [
                f"{index}. record={resource.get('record_id', '')}",
                f"time={resource.get('time', '')}",
            ]
            if resource.get("task_title"):
                parts.append(f"task={resource['task_title']}")
            if resource.get("user_preview"):
                parts.append("user=" + resource["user_preview"])
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def _normalize_resource(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        record_id = item.get("record_id", "")
        user_preview = self._compact(item.get("user_preview", ""), 220)
        assistant_preview = self._compact(item.get("assistant_preview", ""), 220)
        if not record_id and not user_preview and not assistant_preview:
            return {}
        categories = item.get("extracted_categories", [])
        if not isinstance(categories, list):
            categories = []
        return {
            "id": item.get("id") or self._make_id(record_id or user_preview),
            "resource_type": item.get("resource_type", "conversation_turn"),
            "record_id": record_id,
            "time": item.get("time", ""),
            "modality": item.get("modality", "text"),
            "local_ref": item.get("local_ref", "memory/data/records.json"),
            "user_preview": user_preview,
            "assistant_preview": assistant_preview,
            "extracted_categories": categories[:8],
            "task_id": item.get("task_id", ""),
            "task_title": item.get("task_title", ""),
            "task_status": item.get("task_status", ""),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }

    def _make_id(self, seed: str) -> str:
        digest = hashlib.sha256(str(seed or datetime.now().isoformat()).encode("utf-8")).hexdigest()[:16]
        return f"res-{digest}"

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."


class MemoryItemManager:
    def __init__(self, items_path: Optional[str] = None):
        self.items_path = Path(items_path) if items_path else memory_data_path("memory_items.json")
        self.items_path.parent.mkdir(parents=True, exist_ok=True)

    def load_items(self) -> List[Dict[str, Any]]:
        if not self.items_path.exists() or self.items_path.stat().st_size == 0:
            return []
        try:
            with self.items_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in (self._normalize_item(item) for item in data) if item]

    def save_items(self, items: List[Dict[str, Any]]) -> None:
        with self.items_path.open("w", encoding="utf-8") as file:
            json.dump(items[-800:], file, ensure_ascii=False, indent=2)

    def update_from_turn(
        self,
        record: Dict[str, Any],
        extracted: Dict[str, Any],
        task_state: Dict[str, Any],
        task_view: Dict[str, Any],
        recent_summary: Dict[str, Any],
        commitments: List[Dict[str, Any]],
        user_profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        items = self.load_items()
        now = datetime.now().isoformat(timespec="seconds")
        record_id = record.get("id", "")
        task_id = task_state.get("task_id", "") or (task_view.get("current") or {}).get("id", "")
        task_title = task_state.get("active_task", "")

        candidates = []
        if extracted.get("task"):
            candidates.append(self._candidate("task", "tasks", extracted["task"], task_id, record_id, 0.88))
        if extracted.get("progress"):
            candidates.append(self._candidate("progress", "progress", extracted["progress"], task_id, record_id, 0.82))
        for subtask in extracted.get("subtasks") or []:
            title = subtask.get("title", "") if isinstance(subtask, dict) else str(subtask)
            status = subtask.get("status", "planned") if isinstance(subtask, dict) else "planned"
            candidates.append(self._candidate("subtask", "tasks", title, task_id, record_id, 0.78, {"status": status}))
        for blocker in extracted.get("blockers") or []:
            candidates.append(self._candidate("blocker", "risks", blocker, task_id, record_id, 0.82))
        for action in extracted.get("next_actions") or []:
            candidates.append(self._candidate("next_action", "actions", action, task_id, record_id, 0.62))
        for commitment in extracted.get("user_commitments") or []:
            candidates.append(self._candidate("commitment", "commitments", commitment, task_id, record_id, 0.84))

        for pattern in recent_summary.get("repeated_patterns") or []:
            candidates.append(self._candidate("pattern", "patterns", pattern, task_id, record_id, 0.72))
        for advice in recent_summary.get("supervision_advice") or []:
            candidates.append(self._candidate("supervision", "supervision", advice, task_id, record_id, 0.68))
        for preference in user_profile.get("communication_preference") or []:
            candidates.append(self._candidate("profile", "profile", preference, "", record_id, 0.7))
        for commitment in commitments[-8:]:
            if commitment.get("status") == "open":
                candidates.append(
                    self._candidate(
                        "commitment",
                        "commitments",
                        commitment.get("commitment", ""),
                        task_id,
                        record_id,
                        0.8,
                        {"owner": commitment.get("owner", "user")},
                    )
                )

        for candidate in candidates:
            if self._looks_like_forced_proof(candidate.get("content", "")):
                continue
            self._upsert(items, candidate, now, task_title)

        items = self._sort_items(items)
        self.save_items(items)
        return items

    def search_items(self, query: str, limit: int = 8, categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        items = self.load_items()
        terms = self._terms(query)
        if not terms:
            return []
        category_set = set(categories or [])
        results = []
        for item in items:
            if item.get("status") == "archived":
                continue
            if category_set and item.get("category") not in category_set:
                continue
            text = " ".join([
                item.get("content", ""),
                item.get("category", ""),
                item.get("type", ""),
                item.get("task_title", ""),
            ])
            item_terms = self._terms(text)
            score = sum(item_terms.count(term) for term in terms)
            if score:
                if item.get("status") == "stale":
                    score -= 0.8
                usage_bonus = min(int(item.get("usage_count", 0)), 5) * 0.1
                salience_bonus = float(item.get("salience", 0))
                results.append({**item, "score": round(score + usage_bonus + salience_bonus, 3)})
        results.sort(key=lambda item: (item["score"], item.get("updated_at", "")), reverse=True)
        for item in results[:limit]:
            self.mark_accessed(item.get("id", ""))
        return results[:limit]

    def mark_accessed(self, item_id: str) -> None:
        if not item_id:
            return
        items = self.load_items()
        now = datetime.now().isoformat(timespec="seconds")
        changed = False
        for item in items:
            if item.get("id") == item_id:
                item["last_accessed_at"] = now
                item["usage_count"] = int(item.get("usage_count", 0)) + 1
                changed = True
                break
        if changed:
            self.save_items(items)

    def get_recent_items(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._sort_items(self.load_items())[:limit]

    def format_for_context(self, items: Optional[List[Dict[str, Any]]] = None, limit: int = 8) -> str:
        items = items if items is not None else self.get_recent_items(limit=limit)
        if not items:
            return "暂无统一记忆项。"
        lines = ["以下是统一记忆项。请优先使用高相关、高显著性的事实来记住和整理，不要机械复述，不要制造压力。"]
        for index, item in enumerate(items[:limit], start=1):
            parts = [
                f"{index}. [{item.get('type', '')}/{item.get('category', '')}/{item.get('status', 'active')}] {self._soften_context_text(item.get('content', ''))}",
                f"salience={item.get('salience', 0)}",
            ]
            if item.get("task_title"):
                parts.append(f"task={item['task_title']}")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def _candidate(
        self,
        item_type: str,
        category: str,
        content: str,
        task_id: str,
        record_id: str,
        salience: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "type": item_type,
            "category": category,
            "content": self._compact(content, 220),
            "task_id": task_id,
            "source_record_ids": [record_id] if record_id else [],
            "confidence": 0.75,
            "salience": salience,
            "status": "active",
            "metadata": metadata or {},
        }

    def _upsert(self, items: List[Dict[str, Any]], candidate: Dict[str, Any], now: str, task_title: str) -> None:
        content = self._compact(candidate.get("content", ""), 220)
        if not content:
            return
        key = self._key(candidate)
        match = next((item for item in items if item.get("dedupe_key") == key), None)
        if not match:
            candidate.update({
                "id": self._make_id(now, content),
                "dedupe_key": key,
                "content_hash": self._content_hash(candidate.get("type", ""), content),
                "task_title": task_title,
                "created_at": now,
                "updated_at": now,
                "last_accessed_at": "",
                "usage_count": 0,
            })
            items.append(candidate)
            return

        match["updated_at"] = now
        match["content"] = content
        match["content_hash"] = self._content_hash(candidate.get("type", ""), content)
        match["task_id"] = match.get("task_id") or candidate.get("task_id", "")
        match["task_title"] = match.get("task_title") or task_title
        match["confidence"] = max(float(match.get("confidence", 0)), float(candidate.get("confidence", 0)))
        match["salience"] = max(float(match.get("salience", 0)), float(candidate.get("salience", 0)))
        match["status"] = candidate.get("status", match.get("status", "active"))
        match["source_record_ids"] = self._merge_unique(
            match.get("source_record_ids", []),
            candidate.get("source_record_ids", []),
            20,
        )
        metadata = match.get("metadata", {})
        if isinstance(metadata, dict):
            metadata.update(candidate.get("metadata", {}))
            match["metadata"] = metadata

    def _normalize_item(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        content = self._compact(item.get("content", ""), 220)
        if not content or self._looks_like_forced_proof(content):
            return {}
        normalized = {
            "id": item.get("id") or self._make_id(item.get("created_at", ""), content),
            "type": item.get("type", "note"),
            "category": item.get("category", "general"),
            "content": content,
            "task_id": item.get("task_id", ""),
            "task_title": item.get("task_title", ""),
            "source_record_ids": item.get("source_record_ids", []),
            "confidence": float(item.get("confidence", 0.6)),
            "salience": float(item.get("salience", 0.5)),
            "status": item.get("status", "active"),
            "metadata": item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "last_accessed_at": item.get("last_accessed_at", ""),
            "usage_count": int(item.get("usage_count", 0)),
        }
        normalized["content_hash"] = item.get("content_hash") or self._content_hash(normalized["type"], content)
        normalized["dedupe_key"] = item.get("dedupe_key") or self._key(normalized)
        if not isinstance(normalized["source_record_ids"], list):
            normalized["source_record_ids"] = []
        return normalized

    def _sort_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            items,
            key=lambda item: (float(item.get("salience", 0)), item.get("updated_at", "")),
            reverse=True,
        )

    def _key(self, item: Dict[str, Any]) -> str:
        return "|".join([
            item.get("type", ""),
            item.get("category", ""),
            item.get("task_id", ""),
            self._content_hash(item.get("type", ""), item.get("content", "")),
        ])

    def _terms(self, text: str) -> List[str]:
        separators = " \n\t\r，。！？、；;:：/\\|+-_*()（）[]【】{}<>\"'"
        normalized = str(text).lower()
        for separator in separators:
            normalized = normalized.replace(separator, " ")
        terms = [part.strip() for part in normalized.split() if len(part.strip()) >= 2]
        chinese_keywords = [
            "任务", "进度", "完成", "阻塞", "拖延", "分心", "复盘", "监督",
            "承诺", "子任务", "计划", "偏离", "输出", "实习", "大模型",
        ]
        for keyword in chinese_keywords:
            if keyword.lower() in normalized:
                terms.append(keyword.lower())
        return terms

    def _merge_unique(self, first: List[str], second: List[str], limit: int) -> List[str]:
        result = []
        for item in [*first, *second]:
            if item and item not in result:
                result.append(item)
        return result[:limit]

    def _make_id(self, now: str, content: str) -> str:
        safe_time = (now or datetime.now().isoformat(timespec="seconds")).replace("-", "").replace(":", "").replace("T", "-")
        return f"mem-{safe_time}-{self._content_hash('item', content)[:10]}"

    def _content_hash(self, item_type: str, content: str) -> str:
        normalized = " ".join(str(content or "").lower().split())
        return hashlib.sha256(f"{item_type}:{normalized}".encode("utf-8")).hexdigest()[:16]

    def _looks_like_forced_proof(self, text: str) -> bool:
        return any(keyword in str(text) for keyword in ["证据", "截图", "截屏", "强制验证", "无证据不承认"])

    def _soften_context_text(self, text: Any) -> str:
        replacements = {
            "强制用户": "可以轻量提醒用户",
            "直接指出": "温和指出",
            "强调真实产出": "关注核心事项和实际进展",
            "监督": "轻量提醒",
            "质疑": "提出一个问题",
            "催促": "轻轻提醒",
        }
        softened = str(text or "")
        for old, new in replacements.items():
            softened = softened.replace(old, new)
        return self._compact(softened, 220)

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."


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
        self.categories_path = Path(categories_path) if categories_path else memory_data_path("memory_categories.json")
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
