import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class SupportKnowledgeManager:
    SUPPORT_STATES = {
        "anxious",
        "scattered",
        "tired",
        "avoidant",
        "overplanning",
        "stuck",
        "execution_focus",
    }

    def __init__(self, notes_path: Optional[str] = None):
        project_root = Path(__file__).resolve().parent.parent
        self.notes_path = Path(notes_path) if notes_path else project_root / "knowledge" / "support_notes.json"

    def detect_state(self, prompt: str) -> Dict[str, Any]:
        text = str(prompt or "")
        states = []
        matched_keywords = []
        rules = {
            "anxious": ["焦虑", "慌", "烦", "压力", "害怕", "担心", "完蛋", "没意义"],
            "scattered": ["分心", "走神", "乱", "发散", "任务太多", "不知道先做什么", "切换"],
            "tired": ["累", "困", "疲惫", "没力气", "低能量", "不想动"],
            "avoidant": ["拖延", "不想做", "逃避", "刷手机", "开始不了", "提不起劲"],
            "overplanning": ["一直规划", "过度规划", "想太多", "计划太多", "还在想"],
            "stuck": ["卡住", "卡在", "不会", "没思路", "阻塞", "报错", "做不下去"],
        }
        for state, keywords in rules.items():
            hits = [keyword for keyword in keywords if keyword in text]
            if hits:
                states.append(state)
                matched_keywords.extend(hits)
        execution_hits = self._execution_focus_hits(text)
        if execution_hits:
            states.append("execution_focus")
            matched_keywords.extend(execution_hits)
        return {
            "states": self._unique(states),
            "matched_keywords": matched_keywords[:8],
            "should_inject": bool(states),
        }

    def load_notes(self) -> List[Dict[str, Any]]:
        if not self.notes_path.exists() or self.notes_path.stat().st_size == 0:
            return []
        try:
            with self.notes_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [note for note in (self._normalize_note(item) for item in data) if note]

    def search(self, prompt: str, states: Optional[List[str]] = None, limit: int = 3) -> List[Dict[str, Any]]:
        states = states if states is not None else self.detect_state(prompt).get("states", [])
        if not states:
            return []
        query_terms = self._terms(prompt)
        scored = []
        for note in self.load_notes():
            score = 0
            note_states = set(note.get("trigger_states", []))
            state_overlap = note_states & set(states)
            keyword_overlap = set(note.get("keywords", [])) & query_terms
            if state_overlap == {"execution_focus"} and not keyword_overlap:
                continue
            score += 4 * len(state_overlap)
            score += len(keyword_overlap)
            if score <= 0:
                continue
            item = {**note, "score": score}
            scored.append(item)
        return sorted(scored, key=lambda item: item.get("score", 0), reverse=True)[:limit]

    def build_state(self, prompt: str, limit: int = 3) -> Dict[str, Any]:
        detected = self.detect_state(prompt)
        notes = self.search(prompt, states=detected.get("states", []), limit=limit)
        return {
            **detected,
            "notes": notes,
        }

    def format_for_context(self, state: Dict[str, Any]) -> str:
        notes = state.get("notes") or []
        states = state.get("states") or []
        if not states or not notes:
            return ""
        lines = [
            "以下是支持性知识层，只在用户焦虑、分散、拖延、疲惫、卡住或准备进入学习/执行任务时辅助回应。",
            "这些内容不是诊断，不是心理治疗，不是权威说教；只把它转成一句温和、具体、低压力的小提醒。",
            "不要直接复述书名来教育用户。不要要求证明、汇报或完整复盘。",
            "如果用户已经准备去执行，可以自然给一个很轻柔的执行焦点；如果会增加压力，就不要使用。",
            "detected_states: " + "、".join(states),
        ]
        for index, note in enumerate(notes[:3], start=1):
            parts = [
                f"{index}. topic={note.get('topic', '')}",
                f"principle={note.get('principle', '')}",
                f"gentle_application={note.get('gentle_application', '')}",
                f"soft_focus={note.get('soft_focus', '')}",
            ]
            if note.get("avoid"):
                parts.append(f"avoid={note['avoid']}")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def _normalize_note(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        note_id = self._compact(item.get("id", ""), 80)
        principle = self._compact(item.get("principle", ""), 220)
        soft_focus = self._compact(item.get("soft_focus", ""), 180)
        if not note_id or not principle or not soft_focus:
            return {}
        return {
            "id": note_id,
            "source": self._compact(item.get("source", ""), 80),
            "topic": self._compact(item.get("topic", "support"), 80),
            "trigger_states": self._list_field(item.get("trigger_states"), 8),
            "keywords": self._list_field(item.get("keywords"), 16),
            "principle": principle,
            "gentle_application": self._compact(item.get("gentle_application", ""), 220),
            "soft_focus": soft_focus,
            "avoid": self._compact(item.get("avoid", ""), 160),
        }

    def _list_field(self, value: Any, limit: int) -> List[str]:
        if isinstance(value, str):
            value = [value] if value else []
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            text = self._compact(item, 80)
            if text and text not in result:
                result.append(text)
        return result[:limit]

    def _terms(self, text: str) -> set:
        text = str(text or "").lower()
        terms = set()
        for chunk in text.replace("\n", " ").split():
            cleaned = chunk.strip("，。！？；：,.!?;:()（）[]【】\"'")
            if cleaned:
                terms.add(cleaned)
        for keyword in ["焦虑", "分心", "拖延", "卡住", "读书", "阅读", "看书", "深度工作", "力扣", "刷题", "写", "整理", "开发", "调试"]:
            if keyword in text:
                terms.add(keyword)
        if "读" in text or "看书" in text:
            terms.update({"读书", "阅读"})
        return terms

    def _execution_focus_hits(self, text: str) -> List[str]:
        if not self._has_any(text, ["接下来", "先去", "准备", "开始", "去", "我先", "我要"]):
            return []
        return [
            keyword
            for keyword in ["读书", "阅读", "看书", "深度工作", "力扣", "刷题", "写", "整理", "调试", "开发"]
            if keyword in text
        ][:4]

    def _has_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _unique(self, values: List[str]) -> List[str]:
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
