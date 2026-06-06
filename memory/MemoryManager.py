import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .CommitmentManager import CommitmentManager
from .ContextPlanner import ContextPlanner
from .MemoryExtractor import MemoryExtractor
from .SearchManager import SearchManager
from .SummaryManager import SummaryManager
from .TaskManager import TaskManager
from .TaskStateManager import TaskStateManager
from .UserProfileManager import UserProfileManager


class MemoryManager:
    def __init__(
        self,
        memory_path: Optional[str] = None,
        recent_limit: int = 5,
        summary_limit: int = 20,
        commitment_manager: Optional[CommitmentManager] = None,
        context_planner: Optional[ContextPlanner] = None,
        extractor: Optional[MemoryExtractor] = None,
        search_manager: Optional[SearchManager] = None,
        summary_manager: Optional[SummaryManager] = None,
        task_manager: Optional[TaskManager] = None,
        task_state_manager: Optional[TaskStateManager] = None,
        user_profile_manager: Optional[UserProfileManager] = None,
    ):
        memory_dir = Path(__file__).resolve().parent
        self.memory_path = Path(memory_path) if memory_path else memory_dir / "records.json"
        self.recent_limit = recent_limit
        self.summary_limit = summary_limit
        self.commitment_manager = commitment_manager or CommitmentManager()
        self.context_planner = context_planner or ContextPlanner()
        self.extractor = extractor or MemoryExtractor()
        self.search_manager = search_manager or SearchManager()
        self.summary_manager = summary_manager or SummaryManager()
        self.task_manager = task_manager or TaskManager()
        self.task_state_manager = task_state_manager or TaskStateManager()
        self.user_profile_manager = user_profile_manager or UserProfileManager()
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

    def set_llm_client(self, llm_client: Any) -> None:
        self.extractor.set_llm_client(llm_client)
        self.summary_manager.set_llm_client(llm_client)

    def set_summary_client(self, llm_client: Any) -> None:
        self.set_llm_client(llm_client)

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
    def add_record(
        self,
        user_input: str,
        assistant_output: str,
        extracted: Optional[Dict[str, Any]] = None,
        task_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        records = self.load_records()
        extracted = extracted or self.extract_memory(user_input, assistant_output)
        task_state = task_state or self.update_task_state(extracted, user_input, assistant_output)
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "user": user_input,
            "assistant": assistant_output,
            "extracted": extracted,
            "task_state_snapshot": task_state,
        }
        records.append(record)
        self.save_records(records)
        self.summary_manager.summarize_day(records)
        recent_summary = self.get_recent_summary(days=7)
        self.commitment_manager.update(extracted, user_input, assistant_output, task_state=task_state)
        self.user_profile_manager.update(extracted, user_input, assistant_output, recent_summary=recent_summary)
        self.refresh_search_index(records)
        return record

    def extract_memory(self, user_input: str, assistant_output: str) -> Dict[str, Any]:
        return self.extractor.extract(user_input, assistant_output)

    def update_task_state(
        self,
        extracted: Dict[str, Any],
        user_input: str,
        assistant_output: str,
    ) -> Dict[str, Any]:
        task_lifecycle = self.task_manager.update(extracted, user_input, assistant_output)
        return self.task_state_manager.update(
            extracted,
            user_input,
            assistant_output,
            task_lifecycle=task_lifecycle,
        )

    def get_task_state(self) -> Dict[str, Any]:
        return self.task_state_manager.load_state()

    def get_task_view(self) -> Dict[str, Any]:
        return self.task_manager.get_task_view()

    def get_open_commitments(self) -> List[Dict[str, Any]]:
        return self.commitment_manager.get_open_commitments()

    def get_user_profile(self) -> Dict[str, Any]:
        return self.user_profile_manager.load_profile()

    def refresh_search_index(self, records: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        records = records if records is not None else self.load_records()
        return self.search_manager.build_index(
            records,
            daily_summaries=self.get_recent_summary(days=7).get("daily_summaries", []),
            user_profile=self.get_user_profile(),
            commitments=self.commitment_manager.load_commitments(),
        )

    def search_related_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        recent_summary = self.get_recent_summary(days=7)
        return self.search_manager.search(
            query,
            self.load_records(),
            daily_summaries=recent_summary.get("daily_summaries", []),
            user_profile=self.get_user_profile(),
            commitments=self.commitment_manager.load_commitments(),
            limit=limit,
        )

    def get_recent_messages(self) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for record in self.load_records()[-self.recent_limit:]:
            user_text = record.get("user")
            assistant_text = record.get("assistant")
            if user_text:
                messages.append({"role": "user", "content": self._with_time(record, user_text)})
            if assistant_text:
                messages.append({"role": "assistant", "content": self._sanitize_context_text(assistant_text)})
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
            assistant_text = self._compact(self._sanitize_context_text(record.get("assistant", "")))
            lines.append(f"{index}. 时间: {time_text}")
            if user_text:
                lines.append(f"   用户: {user_text}")
            if assistant_text:
                lines.append(f"   你的回应: {assistant_text}")

        return "\n".join(lines)

    def get_structured_memory_summary(self) -> str:
        records = self.load_records()
        selected_records = [record for record in records if record.get("extracted")][-self.summary_limit:]
        if not selected_records:
            return "暂无结构化记忆。"

        lines = [
            "以下是结构化记忆。请优先关注任务、进度、阻塞和下一步。",
        ]
        for index, record in enumerate(selected_records, start=1):
            extracted = record.get("extracted", {})
            parts = []
            if extracted.get("task"):
                parts.append(f"任务: {extracted['task']}")
            if extracted.get("progress"):
                parts.append(f"进度: {extracted['progress']}")
            if extracted.get("subtasks"):
                subtask_titles = [
                    subtask.get("title", "") if isinstance(subtask, dict) else str(subtask)
                    for subtask in extracted["subtasks"][:3]
                ]
                parts.append("子任务: " + "；".join([title for title in subtask_titles if title]))
            if extracted.get("blockers"):
                parts.append("阻塞: " + "、".join(extracted["blockers"]))
            if extracted.get("next_actions"):
                parts.append("下一步: " + "；".join(extracted["next_actions"][:2]))
            if parts:
                lines.append(f"{index}. {record.get('time', 'unknown time')} | " + " | ".join(parts))
        return "\n".join(lines)

    def get_recent_summary(self, days: int = 7) -> Dict[str, Any]:
        return self.summary_manager.summarize_recent_days(self.load_records(), days=days)

    def get_recent_summary_context(self, days: int = 7) -> str:
        return self.summary_manager.format_recent_summary_for_context(self.load_records(), days=days)

    def build_context_messages(self, current_prompt: str) -> List[Dict[str, str]]:
        related_memories = self.search_related_memories(current_prompt, limit=5)
        available_context = {
            "user_profile": self.user_profile_manager.format_for_context(),
            "task_lifecycle": self.task_manager.format_for_context(),
            "task_state": self.task_state_manager.format_for_context(),
            "memory_summary": self.get_memory_summary(),
            "structured_summary": self.get_structured_memory_summary(),
            "recent_summary": self.get_recent_summary_context(days=7),
            "commitments": self.commitment_manager.format_for_context(),
            "related_memories": self.search_manager.format_for_context(related_memories),
        }
        messages = self.context_planner.plan(current_prompt, available_context)
        messages.extend(self.get_recent_messages())
        messages.append(
            {
                "role": "user",
                "content": self._with_current_time(current_prompt),
            }
        )
        return messages

    def build_context_debug(self, current_prompt: str = "") -> Dict[str, Any]:
        messages = self.build_context_messages(current_prompt) if current_prompt else [
            {"role": "system", "content": self.get_memory_summary()},
            {"role": "system", "content": self.user_profile_manager.format_for_context()},
            {"role": "system", "content": self.task_manager.format_for_context()},
            {"role": "system", "content": self.task_state_manager.format_for_context()},
            {"role": "system", "content": self.get_structured_memory_summary()},
            {"role": "system", "content": self.get_recent_summary_context(days=7)},
            {"role": "system", "content": self.commitment_manager.format_for_context()},
            {"role": "system", "content": self.search_manager.format_for_context([])},
            *self.get_recent_messages(),
        ]
        return {
            "messages": messages,
            "task_state": self.get_task_state(),
            "task_view": self.get_task_view(),
            "structured_summary": self.get_structured_memory_summary(),
            "recent_summary": self.get_recent_summary(days=7),
            "open_commitments": self.get_open_commitments(),
            "user_profile": self.get_user_profile(),
        }

    def _with_time(self, record: Dict[str, Any], text: str) -> str:
        time_text = record.get("time")
        if not time_text:
            return text
        return f"[历史记录时间: {time_text}]\n{text}"

    def _with_current_time(self, text: str) -> str:
        current_time = datetime.now().isoformat(timespec="seconds")
        return f"[当前时间: {current_time}]\n{text}"

    def _sanitize_context_text(self, text: str) -> str:
        lines = []
        for line in str(text or "").splitlines():
            if self._looks_like_forced_proof(line):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _looks_like_forced_proof(self, text: str) -> bool:
        return any(keyword in str(text) for keyword in ["证据", "截图", "截屏", "强制验证", "不承认无证据"])

    def _compact(self, text: str, max_length: int = 300) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
