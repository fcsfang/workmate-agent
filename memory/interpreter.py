"""LLM interpretation layer for extraction, semantic compression, summaries, insights, and intent."""

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import memory_data_path


class MemoryExtractor:
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def extract(self, user_input: str, assistant_output: str) -> Dict[str, Any]:
        llm_result = self._extract_with_llm(user_input, assistant_output)
        if llm_result:
            return llm_result
        return self._extract_with_rules(user_input, assistant_output)

    def _extract_with_rules(self, user_input: str, assistant_output: str) -> Dict[str, Any]:
        return {
            "categories": self._categories(user_input),
            "task": self._extract_task(user_input),
            "subtasks": self._extract_subtasks(user_input),
            "progress": self._extract_progress(user_input),
            "blockers": self._extract_blockers(user_input),
            "next_actions": self._extract_next_actions(assistant_output),
            "user_commitments": self._extract_commitments(user_input),
            "signals": self._extract_signals(user_input),
            "extract_source": "rule",
        }

    def _extract_with_llm(self, user_input: str, assistant_output: str) -> Dict[str, Any]:
        if not self.llm_client:
            return {}

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的结构化记忆提取器。"
                    "你的任务是从一轮用户输入和助手回复中提取对长期监督有用的事实。"
                    "只输出合法 JSON，不要 Markdown，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": self._build_llm_prompt(user_input, assistant_output),
            },
        ]

        try:
            if hasattr(self.llm_client, "invoke_raw"):
                raw_output = self.llm_client.invoke_raw(messages)
            else:
                raw_output = self.llm_client.invoke(messages=messages)
            parsed = self._parse_json_object(raw_output)
            result = self._normalize_llm_result(parsed)
            result["extract_source"] = "llm"
            return result
        except Exception as exc:
            result = self._extract_with_rules(user_input, assistant_output)
            result["extract_source"] = "rule_fallback"
            result["extract_error"] = str(exc)
            return result

    def _build_llm_prompt(self, user_input: str, assistant_output: str) -> str:
        schema = {
            "categories": ["task", "progress", "blocker", "review", "chat"],
            "task": "当前或新出现的主任务，若没有则为空字符串",
            "subtasks": [
                {
                    "title": "主任务下面的具体子任务",
                    "status": "inbox|planned|active|blocked|done|abandoned",
                }
            ],
            "progress": "用户声称的实际进展，若没有则为空字符串",
            "blockers": ["阻塞、分心、拖延、风险"],
            "next_actions": ["助手要求或建议的下一步行动"],
            "user_commitments": ["用户明确承诺接下来要做的事"],
            "signals": ["可能未完成", "有进展声明", "注意力风险"],
        }
        payload = {
            "user_input": user_input,
            "assistant_output": assistant_output,
        }
        return (
            "请提取一轮对话中的结构化记忆。\n"
            "要求：\n"
            "1. 只提取对长期监督、任务推进、承诺追踪有用的信息。\n"
            "2. 不要把普通寒暄当成任务。\n"
            "3. 如果用户说完成了，只记录用户声称的进展；不要要求强制证明，也不要把缺少证明当成阻塞。\n"
            "4. subtasks 只能来自 user_input 中用户明确提出的子任务；不要从 assistant_output 的建议中生成子任务。\n"
            "5. 如果用户说的是一个项目/版本/方向，把它作为 task；该项目下用户明确提出的具体动作放入 subtasks，不要把子任务拆成多个平级 task。\n"
            "6. user_commitments 只能来自 user_input 中用户明确承诺的内容。\n"
            "7. assistant_output 中的建议只能进入 next_actions，不能进入 subtasks 或 user_commitments。\n"
            "8. 所有数组最多 6 项，每项简短。\n"
            "9. 必须输出合法 JSON，字段使用下面 schema。\n\n"
            f"JSON schema 示例：\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"对话：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("extract output is not a JSON object")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("extract output JSON is not an object")
        return parsed

    def _normalize_llm_result(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "categories": self._list_field(parsed, "categories", ["chat"], 5),
            "task": self._compact(parsed.get("task", ""), max_length=160),
            "subtasks": self._subtasks_field(parsed.get("subtasks", []), limit=8),
            "progress": self._compact(parsed.get("progress", ""), max_length=160),
            "blockers": self._list_field(parsed, "blockers", [], 5),
            "next_actions": self._list_field(parsed, "next_actions", [], 5),
            "user_commitments": self._list_field(parsed, "user_commitments", [], 5),
            "signals": self._list_field(parsed, "signals", [], 5),
        }

    def _list_field(self, parsed: Dict[str, Any], key: str, fallback: List[str], limit: int) -> List[str]:
        value = parsed.get(key, fallback)
        if isinstance(value, str):
            value = [value] if value else []
        if not isinstance(value, list):
            value = fallback

        result = []
        for item in value:
            item = self._compact(item)
            if item and item not in result:
                result.append(item)
        return result[:limit]

    def _subtasks_field(self, value: Any, limit: int) -> List[Dict[str, str]]:
        if isinstance(value, str):
            value = [value] if value else []
        if not isinstance(value, list):
            return []

        result = []
        for item in value:
            if isinstance(item, dict):
                title = self._compact(item.get("title", ""), max_length=120)
                status = self._status(item.get("status", "inbox"))
            else:
                title = self._compact(item, max_length=120)
                status = "inbox"
            if title and title not in [subtask["title"] for subtask in result]:
                result.append({"title": title, "status": status})
        return result[:limit]

    def _categories(self, text: str) -> List[str]:
        categories = []
        if self._has_any(text, ["目标", "计划", "任务", "今天要", "我要", "准备"]):
            categories.append("task")
        if self._has_any(text, ["完成", "已经", "做了", "进度", "整理了", "找了"]):
            categories.append("progress")
        if self._has_any(text, ["卡", "困难", "问题", "分心", "拖延", "焦虑", "不会"]):
            categories.append("blocker")
        if self._has_any(text, ["总结", "复盘", "根据你的记忆"]):
            categories.append("review")
        return categories or ["chat"]

    def _extract_task(self, text: str) -> str:
        patterns = [
            r"(?:任务是|目标是|计划是|今天要|我要|准备)([^。！？\n]{4,80})",
            r"(?:首先|第一步|第一个任务是)([^。！？\n]{4,80})",
        ]
        return self._first_match(text, patterns)

    def _extract_subtasks(self, text: str) -> List[Dict[str, str]]:
        subtasks = []
        for cleaned in self._subtask_candidates(text):
            if not cleaned or self._looks_like_forced_proof(cleaned):
                continue
            if self._has_any(cleaned, ["优化", "完善", "实现", "开发", "补", "修改", "清理", "测试", "设计"]):
                subtasks.append({"title": cleaned, "status": self._status_from_text(cleaned)})
        return subtasks[:6]

    def _extract_progress(self, text: str) -> str:
        patterns = [
            r"((?:已经|现在|目前)?[^。！？\n]{0,18}(?:完成了|做完了|整理了|找了|拉取了)[^。！？\n]{1,80})",
            r"((?:进度|当前进展)[：:][^。！？\n]{1,80})",
        ]
        return self._first_match(text, patterns)

    def _extract_blockers(self, text: str) -> List[str]:
        blockers = []
        for keyword in ["分心", "拖延", "卡住", "不会", "困难", "焦虑", "走神", "没思路"]:
            if keyword in text:
                blockers.append(keyword)
        return blockers

    def _extract_next_actions(self, text: str) -> List[str]:
        actions = []
        for line in self._lines(text):
            if self._looks_like_forced_proof(line):
                continue
            if self._has_any(line, ["下一步", "现在", "继续", "先", "需要", "不要"]):
                cleaned = self._clean_marker(line)
                if 4 <= len(cleaned) <= 120:
                    actions.append(cleaned)
        return actions[:5]

    def _extract_commitments(self, text: str) -> List[str]:
        commitments = []
        for line in self._lines(text):
            if self._has_any(line, ["我会", "我准备", "我打算", "接下来", "下一步"]):
                cleaned = self._clean_marker(line)
                if 4 <= len(cleaned) <= 120:
                    commitments.append(cleaned)
        return commitments[:3]

    def _extract_signals(self, text: str) -> List[str]:
        signals = []
        if self._has_any(text, ["只是", "还没", "没有", "没"]):
            signals.append("可能未完成")
        if self._has_any(text, ["完成了", "做完了", "已经"]):
            signals.append("有进展声明")
        if self._has_any(text, ["分心", "走神", "刷", "拖延"]):
            signals.append("注意力风险")
        return signals

    def _first_match(self, text: str, patterns: List[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._compact(match.group(1))
        return ""

    def _lines(self, text: str) -> List[str]:
        return [line.strip() for line in str(text).splitlines() if line.strip()]

    def _clean_marker(self, text: str) -> str:
        text = re.sub(r"^[\-\*\d\.\s、]+", "", text.strip())
        return self._compact(text)

    def _subtask_candidates(self, text: str) -> List[str]:
        candidates = []
        for line in self._lines(text):
            line = re.sub(r"^(?:接下来|下面|然后|同时|以及|另外|还有|我想|我要|需要|计划)[:：，,\s]*", "", line.strip())
            parts = re.split(r"[；;。！？\n]|(?:，|,)(?=(?:优化|完善|实现|开发|补|修改|清理|测试|设计))", line)
            for part in parts:
                cleaned = self._clean_marker(part)
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)
        return candidates

    def _compact(self, text: str, max_length: int = 120) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."

    def _has_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _looks_like_forced_proof(self, text: str) -> bool:
        return any(keyword in str(text) for keyword in ["证据", "截图", "截屏", "证明", "可验证"])

    def _status(self, status: Any) -> str:
        status = str(status or "inbox").strip().lower()
        if status in {"inbox", "planned", "active", "blocked", "done", "abandoned"}:
            return status
        return "inbox"

    def _status_from_text(self, text: str) -> str:
        if self._has_any(text, ["卡住", "不会", "困难"]):
            return "blocked"
        if self._has_any(text, ["完成", "做完", "已实现"]):
            return "done"
        if self._has_any(text, ["正在", "开始", "继续"]):
            return "active"
        return "planned"


class SemanticDialogueManager:
    def __init__(self, dialogues_path: Optional[str] = None, llm_client: Any = None):
        self.dialogues_path = Path(dialogues_path) if dialogues_path else memory_data_path("semantic_dialogues.json")
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


class SummaryManager:
    def __init__(self, summaries_dir: Optional[str] = None, llm_client: Any = None):
        self.summaries_dir = Path(summaries_dir) if summaries_dir else memory_data_path("daily_summaries")
        self.llm_client = llm_client
        self.summaries_dir.mkdir(parents=True, exist_ok=True)

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def summarize_day(
        self,
        records: List[Dict[str, Any]],
        target_date: Optional[str] = None,
        save: bool = True,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        target_date = target_date or date.today().isoformat()
        day_records = [record for record in records if self._record_date(record) == target_date]
        summary = self._build_llm_day_summary(target_date, day_records) if use_llm else {}
        if not summary:
            summary = self._build_day_summary(target_date, day_records)
        if save and day_records:
            self.save_daily_summary(summary)
        return summary

    def summarize_recent_days(
        self,
        records: List[Dict[str, Any]],
        days: int = 7,
        save_daily: bool = True,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        today = date.today()
        dates = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
        daily_summaries = []
        records_by_date = {day: [] for day in dates}
        for record in records:
            record_day = self._record_date(record)
            if record_day in records_by_date:
                records_by_date[record_day].append(record)

        for day in dates:
            cached_summary = self.load_daily_summary(day)
            if cached_summary:
                daily_summaries.append(cached_summary)
            elif records_by_date.get(day):
                daily_summaries.append(self.summarize_day(records, target_date=day, save=save_daily, use_llm=use_llm))

        task_counter = Counter()
        blocker_counter = Counter()
        completed_items = []
        in_progress_items = []
        progress_items = []
        subtask_items = []
        next_actions = []
        patterns = []
        supervision_advice = []

        for summary in daily_summaries:
            task_counter.update(summary.get("main_tasks", []))
            blocker_counter.update(summary.get("blockers", []))
            completed_items.extend(summary.get("completed", []))
            in_progress_items.extend(summary.get("in_progress", []))
            progress_items.extend(summary.get("progress", []))
            subtask_items.extend(summary.get("subtasks", []))
            next_actions.extend(summary.get("next_actions", []))
            patterns.extend(summary.get("patterns", []))
            if summary.get("supervision_advice"):
                supervision_advice.append(summary["supervision_advice"])

        repeated_patterns = self._unique([*patterns, *self._repeated_patterns(blocker_counter, next_actions)], limit=8)
        return {
            "range": {
                "start": dates[0],
                "end": dates[-1],
                "days": days,
            },
            "daily_summaries": daily_summaries,
            "active_tasks": [task for task, _ in task_counter.most_common(6)],
            "completed": self._unique(completed_items, limit=10),
            "in_progress": self._unique(in_progress_items, limit=10),
            "progress": self._unique(progress_items, limit=10),
            "subtasks": self._unique(subtask_items, limit=12),
            "repeated_blockers": [blocker for blocker, count in blocker_counter.most_common(8) if count >= 1],
            "repeated_patterns": repeated_patterns,
            "next_actions": self._unique(next_actions, limit=8),
            "supervision_advice": self._unique(supervision_advice, limit=5),
        }

    def format_recent_summary_for_context(self, records: List[Dict[str, Any]], days: int = 7) -> str:
        summary = self.summarize_recent_days(records, days=days, save_daily=True, use_llm=False)
        lines = [
            f"以下是最近{days}天摘要。请用它记住用户近期主线和反复阻塞；只有相关时给一句轻量建议。",
            f"时间范围: {summary['range']['start']} 到 {summary['range']['end']}",
        ]

        if summary["active_tasks"]:
            lines.append("活跃任务: " + "；".join(summary["active_tasks"]))
        if summary["completed"]:
            lines.append("已完成成果: " + "；".join(summary["completed"][:6]))
        if summary["in_progress"]:
            lines.append("进行中事项: " + "；".join(summary["in_progress"][:6]))
        if summary["progress"]:
            lines.append("近期进展: " + "；".join(summary["progress"][:6]))
        if summary.get("subtasks"):
            lines.append("相关子任务: " + "；".join(summary["subtasks"][:8]))
        if summary["repeated_blockers"]:
            lines.append("反复阻塞/风险: " + "、".join(summary["repeated_blockers"][:6]))
        if summary["repeated_patterns"]:
            lines.append("行为模式: " + "；".join(summary["repeated_patterns"]))
        if summary["next_actions"]:
            lines.append("待推进下一步: " + "；".join(summary["next_actions"][:5]))
        if summary["supervision_advice"]:
            lines.append("轻量建议: " + "；".join(summary["supervision_advice"][:3]))

        if len(lines) == 2:
            lines.append("暂无足够记录形成趋势。")
        return "\n".join(lines)

    def _build_llm_day_summary(self, target_date: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.llm_client or not records:
            return {}

        prompt = self._build_llm_prompt(target_date, records)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的记忆总结器。"
                    "你的任务是把一天的对话记录总结成稳定、可复用、低压力的 JSON 记忆。"
                    "只输出 JSON，不要 Markdown，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        try:
            if hasattr(self.llm_client, "invoke_raw"):
                raw_output = self.llm_client.invoke_raw(messages)
            else:
                raw_output = self.llm_client.invoke(messages=messages)
            summary = self._parse_json_object(raw_output)
        except Exception as exc:
            fallback = self._build_day_summary(target_date, records)
            fallback["summary_source"] = "rule_fallback"
            fallback["summary_error"] = str(exc)
            return fallback

        normalized = self._normalize_llm_summary(target_date, records, summary)
        normalized["summary_source"] = "llm"
        return normalized

    def _build_llm_prompt(self, target_date: str, records: List[Dict[str, Any]]) -> str:
        compact_records = []
        for record in records[-30:]:
            compact_records.append({
                "time": record.get("time", ""),
                "user": self._compact(record.get("user", ""), max_length=360),
                "assistant": self._compact(record.get("assistant", ""), max_length=360),
                "extracted": record.get("extracted", {}),
            })

        schema = {
            "date": target_date,
            "record_count": len(records),
            "main_tasks": ["当天主要任务"],
            "completed": ["已经完成的真实成果"],
            "in_progress": ["仍在推进的事项"],
            "progress": ["重要进展描述"],
            "subtasks": ["主任务下的具体子任务"],
            "blockers": ["阻塞、拖延、分心、风险"],
            "next_actions": ["下一步具体行动"],
            "patterns": ["当天暴露出的行为模式"],
            "supervision_advice": "下次如何低压力回应或给一句轻量建议",
        }

        return (
            "请根据以下一天内的对话记录生成日摘要。\n"
            "要求：\n"
            "1. 只保留对长期记忆、任务整理和轻量陪伴有用的信息。\n"
            "2. 不要把普通寒暄写入摘要。\n"
            "3. 区分已经完成、仍在推进和遇到阻塞的内容；不要把缺少证明本身写成问题。\n"
            "4. 如果需要建议，保持低压力，不要催促，不要整段施压。\n"
            "5. 所有数组最多 8 项，每项尽量短。\n"
            "6. 必须输出合法 JSON，字段使用下面 schema。\n\n"
            f"JSON schema 示例：\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"对话记录：\n{json.dumps(compact_records, ensure_ascii=False, indent=2)}"
        )

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("summary output is not a JSON object")
        return json.loads(text[start:end + 1])

    def _normalize_llm_summary(
        self,
        target_date: str,
        records: List[Dict[str, Any]],
        summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        fallback = self._build_day_summary(target_date, records)
        normalized = {
            "date": target_date,
            "record_count": len(records),
            "main_tasks": self._list_field(summary, "main_tasks", fallback["main_tasks"], 8),
            "completed": self._list_field(summary, "completed", [], 8),
            "in_progress": self._list_field(summary, "in_progress", [], 8),
            "progress": self._list_field(summary, "progress", fallback["progress"], 10),
            "subtasks": self._list_field(summary, "subtasks", fallback.get("subtasks", []), 12),
            "blockers": self._list_field(summary, "blockers", fallback["blockers"], 8),
            "next_actions": self._list_field(summary, "next_actions", fallback["next_actions"], 8),
            "patterns": self._list_field(summary, "patterns", [], 8),
            "categories": fallback["categories"],
            "supervision_advice": self._compact(summary.get("supervision_advice", ""), max_length=240),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        return normalized

    def save_daily_summary(self, summary: Dict[str, Any]) -> None:
        path = self.summaries_dir / f"{summary['date']}.json"
        with path.open("w", encoding="utf-8") as file:
            json.dump(summary, file, ensure_ascii=False, indent=2)

    def load_daily_summary(self, target_date: str) -> Dict[str, Any]:
        path = self.summaries_dir / f"{target_date}.json"
        if not path.exists() or path.stat().st_size == 0:
            return {}
        try:
            with path.open("r", encoding="utf-8") as file:
                summary = json.load(file)
        except json.JSONDecodeError:
            return {}
        return self._sanitize_summary(summary) if isinstance(summary, dict) else {}

    def _build_day_summary(self, target_date: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = []
        progress = []
        subtasks = []
        blockers = []
        next_actions = []
        categories = []

        for record in records:
            extracted = record.get("extracted") or {}
            if extracted.get("task"):
                tasks.append(extracted["task"])
            if extracted.get("progress"):
                progress.append(extracted["progress"])
            for subtask in extracted.get("subtasks") or []:
                if isinstance(subtask, dict) and subtask.get("title"):
                    subtasks.append(subtask["title"])
                elif isinstance(subtask, str):
                    subtasks.append(subtask)
            blockers.extend(extracted.get("blockers") or [])
            next_actions.extend(extracted.get("next_actions") or [])
            categories.extend(extracted.get("categories") or [])

        return {
            "date": target_date,
            "record_count": len(records),
            "main_tasks": self._unique(tasks, limit=8),
            "completed": [],
            "in_progress": [],
            "progress": self._unique(progress, limit=10),
            "subtasks": self._unique(subtasks, limit=12),
            "blockers": self._unique(blockers, limit=8),
            "next_actions": self._unique(next_actions, limit=8),
            "patterns": self._repeated_patterns(Counter(blockers), next_actions),
            "categories": self._unique(categories, limit=8),
            "supervision_advice": "",
            "summary_source": "rule",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _record_date(self, record: Dict[str, Any]) -> str:
        time_text = str(record.get("time", ""))
        if len(time_text) >= 10:
            return time_text[:10]
        return ""

    def _repeated_patterns(self, blocker_counter: Counter, next_actions: List[str]) -> List[str]:
        patterns = []
        if blocker_counter:
            common = "、".join([blocker for blocker, _ in blocker_counter.most_common(3)])
            patterns.append(f"近期反复出现的阻塞是：{common}")
        if any("不要" in action or "先" in action for action in next_actions):
            patterns.append("下一步行动经常需要收窄范围，避免发散")
        return patterns[:5]

    def _unique(self, values: List[str], limit: int) -> List[str]:
        result = []
        for value in values:
            value = self._compact(value)
            if value and value not in result:
                result.append(value)
        return result[:limit]

    def _sanitize_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        summary = dict(summary)
        summary.pop("evidence_required", None)
        for key in ["blockers", "patterns", "supervision_advice", "next_actions"]:
            values = summary.get(key, [])
            if isinstance(values, list):
                summary[key] = [value for value in values if not self._looks_like_forced_proof(value)]
            elif isinstance(values, str) and self._looks_like_forced_proof(values):
                summary[key] = ""
        return summary

    def _looks_like_forced_proof(self, text: str) -> bool:
        return any(keyword in str(text) for keyword in ["证据", "截图", "截屏", "无证据", "验证证据", "可验证证据"])

    def _list_field(self, summary: Dict[str, Any], key: str, fallback: List[str], limit: int) -> List[str]:
        value = summary.get(key, fallback)
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            value = fallback
        return self._unique(value, limit=limit)

    def _compact(self, text: str, max_length: int = 140) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."


class InsightManager:
    def __init__(self, insights_path: Optional[str] = None, llm_client: Any = None):
        self.insights_path = Path(insights_path) if insights_path else memory_data_path("high_level_insights.json")
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
                    "why_it_matters": "这不是单次问题，后续可以帮用户先保留一个清晰主线。",
                    "suggested_intervention": "先确认已记住，再给一句小建议，避免新增太多分支。",
                    "support_count": count,
                    "confidence": 0.75,
                    "source": "rule",
                })

        category_counts = {category.get("name", ""): int(category.get("item_count", 0)) for category in categories}
        if category_counts.get("tasks", 0) >= 4 and category_counts.get("progress", 0) <= 1:
            insights.append({
                "type": "planning_over_execution",
                "content": "任务类记忆明显多于进展类记忆，用户可能在持续增加规划而不是交付产出。",
                "why_it_matters": "这会让任务系统变得分散，用户可能更需要整理而不是压力。",
                "suggested_intervention": "帮用户把任务整理成一个主线；必要时只补一句小建议。",
                "support_count": category_counts.get("tasks", 0),
                "confidence": 0.72,
                "source": "rule",
            })

        recent_text = " ".join(item.get("semantic_summary", "") for item in semantic_dialogues[:8])
        if any(keyword in recent_text for keyword in ["优化", "架构", "规划"]) and not any(keyword in recent_text for keyword in ["完成", "已实现", "跑通"]):
            insights.append({
                "type": "architecture_drift",
                "content": "近期对话偏向架构优化和规划，但完成/跑通类信号不足。",
                "why_it_matters": "这可能让记忆系统越做越复杂，用户需要更清爽的主线感。",
                "suggested_intervention": "可以建议先保留一个最小闭环，不要展开成技术路线。",
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
            "suggested_intervention": "以后如何低压力回应或给一句轻量建议",
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
            "1. 不要做普通摘要；只输出长期行为模式、任务推进模式、反复风险、有效低压力回应方式。\n"
            "2. 不要提供技术路线，不要新增任务。\n"
            "3. 建议必须轻，不要催促用户，不要把整段回复变成压力提醒。\n"
            "4. 输出 JSON 数组，最多 8 项。\n\n"
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

class IntentManager:
    VALID_INTENTS = {"chat", "task", "review", "supervision", "search", "weekly_report"}

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def set_llm_client(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def classify(self, prompt: str) -> Dict[str, Any]:
        prompt = str(prompt or "")
        fallback_intent = self.rule_intent(prompt)
        if not self.llm_client or not prompt.strip():
            return self._result(fallback_intent, "rule", 0.5, "llm_unavailable")

        try:
            raw = self._invoke_llm(prompt)
            parsed = self._parse_json_object(raw)
            intent = str(parsed.get("intent", "")).strip().lower()
            if intent not in self.VALID_INTENTS:
                raise ValueError(f"invalid intent: {intent}")
            confidence = self._confidence(parsed.get("confidence", 0.7))
            reason = str(parsed.get("reason", "")).strip()[:160]
            return self._result(intent, "llm", confidence, reason)
        except Exception as exc:
            return self._result(fallback_intent, "rule_fallback", 0.45, str(exc)[:160])

    def rule_intent(self, prompt: str) -> str:
        prompt = str(prompt or "")
        if self._has_any(prompt, ["周报", "周复盘", "每周总结", "每周回顾", "本周总结", "本周复盘"]):
            return "weekly_report"
        if self._has_any(prompt, ["提醒", "监督", "检查", "催我"]):
            return "supervision"
        if self._has_any(prompt, ["之前", "上次", "相关", "找一下"]):
            return "search"
        if self._has_any(prompt, ["任务", "进度", "完成", "做完", "计划", "下一步", "卡住", "继续", "开发", "优化"]):
            return "task"
        if self._has_any(prompt, ["总结", "复盘", "回顾", "最近", "历史", "记忆"]):
            return "review"
        return "chat"

    def format_for_context(self, classification: Dict[str, Any]) -> str:
        if not classification:
            return "暂无意图识别结果。"
        return "\n".join([
            "以下是本轮输入的意图识别结果。请按该意图选择上下文使用方式，不要机械复述。",
            f"intent: {classification.get('intent', 'chat')}",
            f"source: {classification.get('source', 'rule')}",
            f"confidence: {classification.get('confidence', 0)}",
            f"reason: {classification.get('reason', '')}",
        ])

    def _invoke_llm(self, prompt: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Workmate Agent 的意图分类器。"
                    "只判断用户当前输入属于哪一种意图，不要回答用户问题。"
                    "只能输出合法 JSON，不要 Markdown。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请把下面输入分类到一个 intent。\n"
                    "可选 intent:\n"
                    "- chat: 普通聊天、表达想法、让我记住但不需要历史检索\n"
                    "- task: 任务规划、进度汇报、下一步、卡住、开发或优化\n"
                    "- review: 总结、复盘、回顾最近状态、查看记忆趋势 (注意：若是请求生成本周总结或周报/每周回顾等周度总结，请归类为 weekly_report)\n"
                    "- weekly_report: 请求生成本周总结、周报、每周复盘或每周回顾等周度总结\n"
                    "- supervision: 明确要求提醒、监督、检查、催促\n"
                    "- search: 明确询问之前、上次、相关历史或要求查找旧记录\n\n"
                    "输出 schema:\n"
                    '{"intent":"chat|task|review|supervision|search|weekly_report","confidence":0.0,"reason":"一句话理由"}\n\n'
                    f"用户输入:\n{prompt[:1200]}"
                ),
            },
        ]
        if hasattr(self.llm_client, "invoke_raw"):
            return self.llm_client.invoke_raw(messages)
        return self.llm_client.invoke(messages=messages)

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("intent output is not a JSON object")
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("intent output JSON is not object")
        return parsed

    def _confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.7
        return max(0.0, min(1.0, confidence))

    def _result(self, intent: str, source: str, confidence: float, reason: str) -> Dict[str, Any]:
        return {
            "intent": intent if intent in self.VALID_INTENTS else "chat",
            "source": source,
            "confidence": round(confidence, 3),
            "reason": reason,
        }

    def _has_any(self, text: str, keywords: List[str]) -> bool:
        return any(keyword in text for keyword in keywords)
