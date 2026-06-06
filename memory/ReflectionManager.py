import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ReflectionManager:
    def __init__(self, reflections_path: Optional[str] = None, interval_turns: int = 5):
        memory_dir = Path(__file__).resolve().parent
        self.reflections_path = Path(reflections_path) if reflections_path else memory_dir / "reflections.json"
        self.interval_turns = interval_turns
        self.reflections_path.parent.mkdir(parents=True, exist_ok=True)

    def load_reflections(self) -> List[Dict[str, Any]]:
        if not self.reflections_path.exists() or self.reflections_path.stat().st_size == 0:
            return []
        try:
            with self.reflections_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def save_reflections(self, reflections: List[Dict[str, Any]]) -> None:
        with self.reflections_path.open("w", encoding="utf-8") as file:
            json.dump(reflections[-200:], file, ensure_ascii=False, indent=2)

    def should_reflect(self, records: List[Dict[str, Any]], user_input: str = "") -> bool:
        if not records:
            return False
        if any(keyword in str(user_input) for keyword in ["复盘一下", "自我反省", "反省一下", "总结最近状态"]):
            return True
        count = len(records)
        return count > 0 and count % self.interval_turns == 0

    def record_reflection(
        self,
        records: List[Dict[str, Any]],
        trigger: str,
        semantic_dialogues: List[Dict[str, Any]],
        insights: List[Dict[str, Any]],
        governance: Dict[str, Any],
    ) -> Dict[str, Any]:
        reflections = self.load_reflections()
        item = {
            "id": self._make_id(len(reflections)),
            "time": datetime.now().isoformat(timespec="seconds"),
            "trigger": trigger,
            "record_count": len(records),
            "semantic_dialogue_count": len(semantic_dialogues),
            "active_insight_count": len([insight for insight in insights if insight.get("status") == "active"]),
            "changed_item_count": len(governance.get("changed_items", [])),
            "conflict_count": len(governance.get("conflicts", [])),
            "latest_insights": [
                {
                    "type": insight.get("type", ""),
                    "content": insight.get("content", ""),
                    "confidence": insight.get("confidence", 0),
                }
                for insight in insights[:5]
            ],
            "governance_changes": governance.get("changed_items", [])[:10],
        }
        reflections.append(item)
        self.save_reflections(reflections)
        return item

    def format_for_context(self, reflections: Optional[List[Dict[str, Any]]] = None, limit: int = 3) -> str:
        reflections = reflections if reflections is not None else self.load_reflections()
        if not reflections:
            return "暂无自我反省记录。"
        lines = ["以下是最近的自我反省记录。它们用于理解长期记忆是如何被提炼和治理的。"]
        for index, item in enumerate(reflections[-limit:], start=1):
            lines.append(
                f"{index}. time={item.get('time', '')} | trigger={item.get('trigger', '')} | "
                f"insights={item.get('active_insight_count', 0)} | changed={item.get('changed_item_count', 0)}"
            )
        return "\n".join(lines)

    def _make_id(self, index: int) -> str:
        safe_time = datetime.now().isoformat(timespec="seconds").replace("-", "").replace(":", "").replace("T", "-")
        return f"ref-{safe_time}-{index + 1:04d}"
