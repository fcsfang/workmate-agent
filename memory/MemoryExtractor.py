import json
import re
from typing import Any, Dict, List, Optional


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
