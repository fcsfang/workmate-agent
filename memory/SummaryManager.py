import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class SummaryManager:
    def __init__(self, summaries_dir: Optional[str] = None, llm_client: Any = None):
        memory_dir = Path(__file__).resolve().parent
        self.summaries_dir = Path(summaries_dir) if summaries_dir else memory_dir / "daily_summaries"
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
        for day in dates:
            cached_summary = self.load_daily_summary(day)
            if cached_summary:
                daily_summaries.append(cached_summary)
            else:
                daily_summaries.append(self.summarize_day(records, target_date=day, save=save_daily, use_llm=use_llm))

        task_counter = Counter()
        blocker_counter = Counter()
        completed_items = []
        in_progress_items = []
        progress_items = []
        next_actions = []
        evidence_required = []
        patterns = []
        supervision_advice = []

        for summary in daily_summaries:
            task_counter.update(summary.get("main_tasks", []))
            blocker_counter.update(summary.get("blockers", []))
            completed_items.extend(summary.get("completed", []))
            in_progress_items.extend(summary.get("in_progress", []))
            progress_items.extend(summary.get("progress", []))
            next_actions.extend(summary.get("next_actions", []))
            evidence_required.extend(summary.get("evidence_required", []))
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
            "repeated_blockers": [blocker for blocker, count in blocker_counter.most_common(8) if count >= 1],
            "repeated_patterns": repeated_patterns,
            "next_actions": self._unique(next_actions, limit=8),
            "evidence_required": self._unique(evidence_required, limit=6),
            "supervision_advice": self._unique(supervision_advice, limit=5),
        }

    def format_recent_summary_for_context(self, records: List[Dict[str, Any]], days: int = 7) -> str:
        summary = self.summarize_recent_days(records, days=days, save_daily=True, use_llm=False)
        lines = [
            f"以下是最近{days}天摘要。请用它判断用户近期主线、反复阻塞和下一步监督方式。",
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
        if summary["repeated_blockers"]:
            lines.append("反复阻塞/风险: " + "、".join(summary["repeated_blockers"][:6]))
        if summary["repeated_patterns"]:
            lines.append("行为模式: " + "；".join(summary["repeated_patterns"]))
        if summary["next_actions"]:
            lines.append("待推进下一步: " + "；".join(summary["next_actions"][:5]))
        if summary["evidence_required"]:
            lines.append("待验证证据: " + "；".join(summary["evidence_required"][:4]))
        if summary["supervision_advice"]:
            lines.append("监督建议: " + "；".join(summary["supervision_advice"][:3]))

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
                    "你的任务是把一天的对话记录总结成稳定、可复用、可监督的 JSON 记忆。"
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
            "blockers": ["阻塞、拖延、分心、风险"],
            "next_actions": ["下一步具体行动"],
            "evidence_required": ["需要用户提供的证据"],
            "patterns": ["当天暴露出的行为模式"],
            "supervision_advice": "下次应该如何监督用户",
        }

        return (
            "请根据以下一天内的对话记录生成日摘要。\n"
            "要求：\n"
            "1. 只保留对长期监督有用的信息。\n"
            "2. 不要把普通寒暄写入摘要。\n"
            "3. 区分真实完成、仍在推进、需要证据验证的内容。\n"
            "4. 所有数组最多 8 项，每项尽量短。\n"
            "5. 必须输出合法 JSON，字段使用下面 schema。\n\n"
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
            "blockers": self._list_field(summary, "blockers", fallback["blockers"], 8),
            "next_actions": self._list_field(summary, "next_actions", fallback["next_actions"], 8),
            "evidence_required": self._list_field(summary, "evidence_required", fallback["evidence_required"], 6),
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
        return summary if isinstance(summary, dict) else {}

    def _build_day_summary(self, target_date: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = []
        progress = []
        blockers = []
        next_actions = []
        evidence_required = []
        categories = []

        for record in records:
            extracted = record.get("extracted") or {}
            if extracted.get("task"):
                tasks.append(extracted["task"])
            if extracted.get("progress"):
                progress.append(extracted["progress"])
            blockers.extend(extracted.get("blockers") or [])
            next_actions.extend(extracted.get("next_actions") or [])
            evidence_required.extend(extracted.get("evidence_required") or [])
            categories.extend(extracted.get("categories") or [])

        return {
            "date": target_date,
            "record_count": len(records),
            "main_tasks": self._unique(tasks, limit=8),
            "completed": [],
            "in_progress": [],
            "progress": self._unique(progress, limit=10),
            "blockers": self._unique(blockers, limit=8),
            "next_actions": self._unique(next_actions, limit=8),
            "evidence_required": self._unique(evidence_required, limit=6),
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
        if any("证据" in action or "截图" in action for action in next_actions):
            patterns.append("监督上需要继续要求可验证证据，而不是只接受模糊进展")
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
