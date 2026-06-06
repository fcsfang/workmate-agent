import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryItemManager:
    def __init__(self, items_path: Optional[str] = None):
        memory_dir = Path(__file__).resolve().parent
        self.items_path = Path(items_path) if items_path else memory_dir / "memory_items.json"
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
        lines = ["以下是统一记忆项。请优先使用高相关、高显著性的事实，不要机械复述。"]
        for index, item in enumerate(items[:limit], start=1):
            parts = [
                f"{index}. [{item.get('type', '')}/{item.get('category', '')}] {item.get('content', '')}",
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

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
