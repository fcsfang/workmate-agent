import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryManager:
    def __init__(
        self,
        memory_path: Optional[str] = None,
        recent_limit: int = 5,
        summary_limit: int = 20,
    ):
        memory_dir = Path(__file__).resolve().parent
        self.memory_path = Path(memory_path) if memory_path else memory_dir / "records.json"
        self.recent_limit = recent_limit
        self.summary_limit = summary_limit
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

    def load_records(self) -> List[Dict[str, Any]]:
        if not self.memory_path.exists() or self.memory_path.stat().st_size == 0:
            return []

        try:
            with self.memory_path.open("r", encoding="utf-8") as file:
                records = json.load(file)
        except json.JSONDecodeError:
            return []

        if not isinstance(records, list):
            return []
        return records

    #最终保存写回文件
    def save_records(self, records: List[Dict[str, Any]]) -> None:
        with self.memory_path.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)

    #每轮对话都开启记录保存
    def add_record(self, user_input: str, assistant_output: str) -> Dict[str, Any]:
        records = self.load_records()
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "user": user_input,
            "assistant": assistant_output,
        }
        records.append(record)
        self.save_records(records)
        return record

    def get_recent_messages(self) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for record in self.load_records()[-self.recent_limit:]:
            user_text = record.get("user")
            assistant_text = record.get("assistant")
            if user_text:
                messages.append({"role": "user", "content": self._with_time(record, user_text)})
            if assistant_text:
                messages.append({"role": "assistant", "content": assistant_text})
        return messages

    def get_memory_summary(self) -> str:
        records = self.load_records()
        if not records:
            return "暂无历史记录。这是你和用户当前会话的开始。"

        selected_records = records[-self.summary_limit:]
        lines = [
            "以下是你可用的长期记忆。请把它当作真实历史，而不是用户本轮新输入。",
            "你需要关注时间、任务推进、反复出现的问题和已经做出的承诺。",
        ]

        for index, record in enumerate(selected_records, start=1):
            time_text = record.get("time", "unknown time")
            user_text = self._compact(record.get("user", ""))
            assistant_text = self._compact(record.get("assistant", ""))
            lines.append(f"{index}. 时间: {time_text}")
            if user_text:
                lines.append(f"   用户: {user_text}")
            if assistant_text:
                lines.append(f"   你的回应: {assistant_text}")

        return "\n".join(lines)

    def build_context_messages(self, current_prompt: str) -> List[Dict[str, str]]:
        messages = [
            {
                "role": "system",
                "content": self.get_memory_summary(),
            }
        ]
        messages.extend(self.get_recent_messages())
        messages.append(
            {
                "role": "user",
                "content": self._with_current_time(current_prompt),
            }
        )
        return messages

    def _with_time(self, record: Dict[str, Any], text: str) -> str:
        time_text = record.get("time")
        if not time_text:
            return text
        return f"[历史记录时间: {time_text}]\n{text}"

    def _with_current_time(self, text: str) -> str:
        current_time = datetime.now().isoformat(timespec="seconds")
        return f"[当前时间: {current_time}]\n{text}"

    def _compact(self, text: str, max_length: int = 300) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
