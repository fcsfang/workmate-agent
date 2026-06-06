import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryResourceManager:
    def __init__(self, resources_path: Optional[str] = None):
        memory_dir = Path(__file__).resolve().parent
        self.resources_path = Path(resources_path) if resources_path else memory_dir / "memory_resources.json"
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
            "local_ref": "memory/records.json",
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
            "local_ref": item.get("local_ref", "memory/records.json"),
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
