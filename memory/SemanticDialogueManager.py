import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class SemanticDialogueManager:
    def __init__(self, dialogues_path: Optional[str] = None, llm_client: Any = None):
        memory_dir = Path(__file__).resolve().parent
        self.dialogues_path = Path(dialogues_path) if dialogues_path else memory_dir / "semantic_dialogues.json"
        self.llm_client = llm_client
        self.dialogues_path.parent.mkdir(parents=True, exist_ok=True)

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def load_dialogues(self) -> List[Dict[str, Any]]:
        if not self.dialogues_path.exists() or self.dialogues_path.stat().st_size == 0:
            return []
        try:
            with self.dialogues_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in (self._normalize_dialogue(item) for item in data) if item]

    def save_dialogues(self, dialogues: List[Dict[str, Any]]) -> None:
        with self.dialogues_path.open("w", encoding="utf-8") as file:
            json.dump(dialogues[-800:], file, ensure_ascii=False, indent=2)

    def update_from_record(
        self,
        record: Dict[str, Any],
        extracted: Dict[str, Any],
        task_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        dialogues = self.load_dialogues()
        record_id = record.get("id", "")
        semantic = self._build_llm_semantic(record, extracted, task_state or {})
        if not semantic or not semantic.get("semantic_summary"):
            semantic = self._build_rule_semantic(record, extracted, task_state or {})

        item = {
            "id": f"sem-{record_id}" if record_id else self._make_fallback_id(record),
            "record_id": record_id,
            "time": record.get("time", ""),
            "task_id": (task_state or {}).get("task_id", ""),
            "task_title": (task_state or {}).get("active_task", ""),
            "semantic_summary": self._compact(semantic.get("semantic_summary", ""), 420),
            "user_intent": self._compact(semantic.get("user_intent", ""), 180),
            "key_points": self._list_field(semantic.get("key_points"), 8),
            "kept_fields": self._list_field(semantic.get("kept_fields"), 8),
            "dropped_noise": self._list_field(semantic.get("dropped_noise"), 8),
            "source": semantic.get("source", "rule"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

        match = next((dialogue for dialogue in dialogues if dialogue.get("record_id") == record_id and record_id), None)
        if match:
            match.update(item)
        else:
            dialogues.append(item)
        self.save_dialogues(dialogues)
        return item

    def get_recent_dialogues(self, limit: int = 12) -> List[Dict[str, Any]]:
        dialogues = self.load_dialogues()
        return sorted(dialogues, key=lambda item: item.get("updated_at", ""), reverse=True)[:limit]

    def format_for_context(self, dialogues: Optional[List[Dict[str, Any]]] = None, limit: int = 6) -> str:
        dialogues = dialogues if dialogues is not None else self.get_recent_dialogues(limit=limit)
        if not dialogues:
            return "暂无语义压缩对话。"
        lines = ["以下是原始对话的语义压缩版本。上下文注入时优先使用这些核心语义，而不是完整原文。"]
        for index, item in enumerate(dialogues[:limit], start=1):
            parts = [
                f"{index}. time={item.get('time', '')}",
                item.get("semantic_summary", ""),
            ]
            if item.get("task_title"):
                parts.append(f"task={item['task_title']}")
            lines.append(" | ".join([part for part in parts if part]))
        return "\n".join(lines)

    def _build_llm_semantic(
        self,
        record: Dict[str, Any],
        extracted: Dict[str, Any],
        task_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.llm_client:
            return {}
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的对话语义压缩器。"
                    "你的任务是把一轮原始对话压缩成用于长期上下文注入的核心语义。"
                    "只输出合法 JSON，不要 Markdown，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": self._build_prompt(record, extracted, task_state),
            },
        ]
        try:
            raw = self.llm_client.invoke_raw(messages) if hasattr(self.llm_client, "invoke_raw") else self.llm_client.invoke(messages=messages)
            parsed = self._parse_json_object(raw)
            parsed["source"] = "llm"
            return parsed
        except Exception as exc:
            return {"source": "rule_fallback", "error": str(exc)}

    def _build_rule_semantic(
        self,
        record: Dict[str, Any],
        extracted: Dict[str, Any],
        task_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        key_points = []
        if extracted.get("task"):
            key_points.append("任务: " + extracted["task"])
        if extracted.get("progress"):
            key_points.append("进展: " + extracted["progress"])
        subtasks = []
        for subtask in extracted.get("subtasks") or []:
            if isinstance(subtask, dict) and subtask.get("title"):
                subtasks.append(subtask["title"])
            elif isinstance(subtask, str):
                subtasks.append(subtask)
        if subtasks:
            key_points.append("子任务: " + "；".join(subtasks[:5]))
        if extracted.get("blockers"):
            key_points.append("阻塞: " + "、".join(extracted["blockers"][:5]))
        if extracted.get("user_commitments"):
            key_points.append("承诺: " + "；".join(extracted["user_commitments"][:5]))

        user_intent = extracted.get("task") or self._compact(record.get("user", ""), 120)
        if not key_points:
            key_points = [self._compact(record.get("user", ""), 180)]
        return {
            "semantic_summary": "；".join([point for point in key_points if point]),
            "user_intent": user_intent,
            "key_points": key_points,
            "kept_fields": ["用户意图", "任务", "进展", "阻塞", "承诺", "时间"],
            "dropped_noise": ["寒暄", "重复表达", "低价值解释"],
            "source": "rule",
        }

    def _build_prompt(self, record: Dict[str, Any], extracted: Dict[str, Any], task_state: Dict[str, Any]) -> str:
        schema = {
            "semantic_summary": "用于上下文注入的短摘要，保留核心语义",
            "user_intent": "用户真实意图",
            "key_points": ["任务/进展/阻塞/承诺/必要时间信息"],
            "kept_fields": ["保留了哪些信息类型"],
            "dropped_noise": ["丢弃了哪些低价值内容"],
        }
        payload = {
            "record": {
                "time": record.get("time", ""),
                "user": record.get("user", ""),
                "assistant": record.get("assistant", ""),
            },
            "extracted": extracted,
            "task_state": task_state,
        }
        return (
            "请把以下一轮对话压缩成更短的核心语义，用于长期上下文注入。\n"
            "要求：\n"
            "1. 保留用户真实意图、任务、进展、阻塞、关键承诺、重要上下文和必要时间信息。\n"
            "2. 不保留寒暄、重复表达、低价值解释、与长期监督无关的细节。\n"
            "3. 不要要求证据，不要新增用户没有表达的任务。\n"
            "4. 输出合法 JSON，字段按 schema。\n\n"
            f"schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("semantic dialogue output is not JSON object")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("semantic dialogue JSON is not object")
        return parsed

    def _normalize_dialogue(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        summary = self._compact(item.get("semantic_summary", ""), 420)
        if not summary:
            return {}
        return {
            "id": item.get("id", ""),
            "record_id": item.get("record_id", ""),
            "time": item.get("time", ""),
            "task_id": item.get("task_id", ""),
            "task_title": item.get("task_title", ""),
            "semantic_summary": summary,
            "user_intent": self._compact(item.get("user_intent", ""), 180),
            "key_points": self._list_field(item.get("key_points"), 8),
            "kept_fields": self._list_field(item.get("kept_fields"), 8),
            "dropped_noise": self._list_field(item.get("dropped_noise"), 8),
            "source": item.get("source", "unknown"),
            "updated_at": item.get("updated_at", ""),
        }

    def _list_field(self, value: Any, limit: int) -> List[str]:
        if isinstance(value, str):
            value = [value] if value else []
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            compacted = self._compact(item, 160)
            if compacted and compacted not in result:
                result.append(compacted)
        return result[:limit]

    def _make_fallback_id(self, record: Dict[str, Any]) -> str:
        seed = str(record.get("time", "")) + str(record.get("user", ""))
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        return f"sem-{digest}"

    def _compact(self, text: Any, max_length: int = 160) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
