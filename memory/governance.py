import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import memory_data_path


class MemoryGovernanceManager:
    VERSION_PATTERN = re.compile(r"V(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)

    def __init__(self, conflicts_path: Optional[str] = None, llm_client: Optional[Any] = None):
        self.conflicts_path = Path(conflicts_path) if conflicts_path else memory_data_path("memory_conflicts.json")
        self.llm_client = llm_client
        self.conflicts_path.parent.mkdir(parents=True, exist_ok=True)

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

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
        llm_result = self._govern_with_llm(memory_items, insights)
        if llm_result:
            return llm_result
        return self._govern_with_rules(memory_items, insights)

    def _govern_with_rules(self, memory_items: List[Dict[str, Any]], insights: List[Dict[str, Any]]) -> Dict[str, Any]:
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

    def _govern_with_llm(self, memory_items: List[Dict[str, Any]], insights: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.llm_client or not memory_items:
            return {}
        now = datetime.now().isoformat(timespec="seconds")
        active_items = [item for item in memory_items if item.get("status", "active") == "active"][:80]
        schema = {
            "changes": [
                {
                    "item_id": "必须来自 memory_items",
                    "action": "active_to_stale|active_to_archived|stale_to_archived|salience_boost",
                    "reason": "version_conflict|contradiction|low_value|supported_by_insight|obsolete",
                    "stale_reason": "简短说明",
                    "salience": 0.9,
                }
            ],
            "conflicts": [
                {
                    "type": "version_conflict|contradiction|obsolete_fact|low_value",
                    "stale_item_id": "相关记忆 id",
                    "stale_content": "相关记忆内容",
                    "resolution": "marked_stale|archived|salience_boost",
                }
            ],
        }
        payload = {
            "memory_items": [
                {
                    "id": item.get("id", ""),
                    "type": item.get("type", ""),
                    "category": item.get("category", ""),
                    "content": item.get("content", ""),
                    "status": item.get("status", "active"),
                    "salience": item.get("salience", 0),
                    "usage_count": item.get("usage_count", 0),
                    "updated_at": item.get("updated_at", ""),
                }
                for item in active_items
            ],
            "insights": insights[:20],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的记忆治理器。"
                    "请识别陈旧事实、冲突事实、低价值记忆，以及应提高显著性的记忆。"
                    "只输出合法 JSON，不要 Markdown，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "要求：\n"
                    "1. 只能引用 payload.memory_items 中存在的 item_id。\n"
                    "2. 不确定时不要改动。\n"
                    "3. 不要物理删除记忆，只建议 stale/archive/salience_boost。\n"
                    "4. changes 最多 12 条，conflicts 最多 12 条。\n\n"
                    f"schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                    f"payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
                ),
            },
        ]
        try:
            raw = self.llm_client.invoke_raw(messages) if hasattr(self.llm_client, "invoke_raw") else self.llm_client.invoke(messages=messages)
            parsed = self._parse_json_object(raw)
            return self._apply_llm_governance(memory_items, parsed, now)
        except Exception:
            return {}

    def _apply_llm_governance(self, memory_items: List[Dict[str, Any]], parsed: Dict[str, Any], now: str) -> Dict[str, Any]:
        item_by_id = {item.get("id", ""): item for item in memory_items if item.get("id")}
        changes = []
        insight_changes = []
        conflicts = self.load_conflicts()
        for change in self._list_dicts(parsed.get("changes", []))[:12]:
            item_id = change.get("item_id", "")
            item = item_by_id.get(item_id)
            if not item:
                continue
            action = change.get("action", "")
            reason = self._compact(change.get("reason", ""), 120)
            if action == "active_to_stale" and item.get("status", "active") == "active":
                item["status"] = "stale"
                item.setdefault("metadata", {})
                if isinstance(item["metadata"], dict):
                    item["metadata"]["stale_reason"] = self._compact(change.get("stale_reason", reason), 160)
                item["updated_at"] = now
                changes.append({"item_id": item_id, "action": action, "reason": reason})
            elif action in {"active_to_archived", "stale_to_archived"}:
                if item.get("status", "active") in {"active", "stale"}:
                    item["status"] = "archived"
                    item["updated_at"] = now
                    changes.append({"item_id": item_id, "action": action, "reason": reason})
            elif action == "salience_boost":
                item["salience"] = max(float(item.get("salience", 0)), self._float(change.get("salience", 0.9)))
                item["updated_at"] = now
                insight_changes.append({"item_id": item_id, "action": action, "reason": reason})

        for conflict in self._list_dicts(parsed.get("conflicts", []))[:12]:
            item_id = conflict.get("stale_item_id", "")
            if item_id and item_id not in item_by_id:
                continue
            conflicts.append({
                "time": now,
                "type": self._compact(conflict.get("type", "memory_governance"), 80),
                "stale_item_id": item_id,
                "stale_content": self._compact(conflict.get("stale_content", ""), 240),
                "resolution": self._compact(conflict.get("resolution", ""), 120),
            })

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

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("governance output is not a JSON object")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("governance output JSON is not object")
        return parsed

    def _list_dicts(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _float(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.9

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
