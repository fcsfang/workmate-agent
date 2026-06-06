import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MemoryGovernanceManager:
    VERSION_PATTERN = re.compile(r"V(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)

    def __init__(self, conflicts_path: Optional[str] = None):
        memory_dir = Path(__file__).resolve().parent
        self.conflicts_path = Path(conflicts_path) if conflicts_path else memory_dir / "memory_conflicts.json"
        self.conflicts_path.parent.mkdir(parents=True, exist_ok=True)

    def load_conflicts(self) -> List[Dict[str, Any]]:
        if not self.conflicts_path.exists() or self.conflicts_path.stat().st_size == 0:
            return []
        try:
            with self.conflicts_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def save_conflicts(self, conflicts: List[Dict[str, Any]]) -> None:
        with self.conflicts_path.open("w", encoding="utf-8") as file:
            json.dump(conflicts[-300:], file, ensure_ascii=False, indent=2)

    def govern_items(self, memory_items: List[Dict[str, Any]], insights: List[Dict[str, Any]]) -> Dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        conflicts = self.load_conflicts()
        changes = []
        version_items = []
        for item in memory_items:
            version = self._extract_version(item.get("content", ""))
            if version:
                version_items.append((item, version))

        if version_items:
            latest_version = max(version for _, version in version_items)
            for item, version in version_items:
                if version < latest_version and item.get("status", "active") == "active":
                    item["status"] = "stale"
                    item.setdefault("metadata", {})
                    if isinstance(item["metadata"], dict):
                        item["metadata"]["stale_reason"] = f"version_conflict_with_V{self._version_text(latest_version)}"
                    item["updated_at"] = now
                    changes.append({"item_id": item.get("id", ""), "action": "active_to_stale", "reason": "version_conflict"})
                    conflicts.append({
                        "time": now,
                        "type": "version_conflict",
                        "stale_item_id": item.get("id", ""),
                        "stale_content": item.get("content", ""),
                        "latest_version": f"V{self._version_text(latest_version)}",
                        "resolution": "marked_stale",
                    })

        for item in memory_items:
            if item.get("type") == "next_action" and int(item.get("usage_count", 0)) == 0:
                if item.get("status") == "stale":
                    item["status"] = "archived"
                    item["updated_at"] = now
                    changes.append({"item_id": item.get("id", ""), "action": "stale_to_archived", "reason": "unused_next_action"})

        insight_changes = []
        insight_text = " ".join(insight.get("content", "") for insight in insights if insight.get("status") == "active")
        for item in memory_items:
            if item.get("status") != "active":
                continue
            if item.get("type") in {"blocker", "pattern"} and item.get("content") and item.get("content") in insight_text:
                item["salience"] = max(float(item.get("salience", 0)), 0.9)
                item["updated_at"] = now
                insight_changes.append({"item_id": item.get("id", ""), "action": "salience_boost", "reason": "supported_by_insight"})

        self.save_conflicts(conflicts)
        return {
            "changed_items": changes,
            "insight_changes": insight_changes,
            "conflicts": conflicts[-20:],
            "updated_items": memory_items,
        }

    def format_for_context(self, conflicts: Optional[List[Dict[str, Any]]] = None, limit: int = 5) -> str:
        conflicts = conflicts if conflicts is not None else self.load_conflicts()
        if not conflicts:
            return "暂无记忆冲突或陈旧事实。"
        lines = ["以下是记忆治理记录。命中陈旧或冲突事实时，请优先使用 active 事实。"]
        for index, item in enumerate(conflicts[-limit:], start=1):
            lines.append(f"{index}. [{item.get('type', '')}] {item.get('stale_content', '')} -> {item.get('resolution', '')}")
        return "\n".join(lines)

    def _extract_version(self, text: str) -> Tuple[int, int, int]:
        match = self.VERSION_PATTERN.search(str(text or ""))
        if not match:
            return ()
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3) or 0)
        return (major, minor, patch)

    def _version_text(self, version: Tuple[int, int, int]) -> str:
        major, minor, patch = version
        if patch:
            return f"{major}.{minor}.{patch}"
        return f"{major}.{minor}"
