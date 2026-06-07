import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .CommitmentManager import CommitmentManager
from .ContextCompressor import ContextCompressor
from .ContextPlanner import ContextPlanner
from .InsightManager import InsightManager
from .IntentManager import IntentManager
from .MemoryCategoryManager import MemoryCategoryManager
from .MemoryGovernanceManager import MemoryGovernanceManager
from .MemoryExtractor import MemoryExtractor
from .MemoryItemManager import MemoryItemManager
from .MemoryPipeline import MemoryPipeline
from .MemoryResourceManager import MemoryResourceManager
from .ReflectionManager import ReflectionManager
from .SearchManager import SearchManager
from .SemanticDialogueManager import SemanticDialogueManager
from .SupervisionManager import SupervisionManager
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
        context_compressor: Optional[ContextCompressor] = None,
        context_planner: Optional[ContextPlanner] = None,
        extractor: Optional[MemoryExtractor] = None,
        insight_manager: Optional[InsightManager] = None,
        intent_manager: Optional[IntentManager] = None,
        memory_category_manager: Optional[MemoryCategoryManager] = None,
        memory_governance_manager: Optional[MemoryGovernanceManager] = None,
        memory_item_manager: Optional[MemoryItemManager] = None,
        memory_pipeline: Optional[MemoryPipeline] = None,
        memory_resource_manager: Optional[MemoryResourceManager] = None,
        reflection_manager: Optional[ReflectionManager] = None,
        search_manager: Optional[SearchManager] = None,
        semantic_dialogue_manager: Optional[SemanticDialogueManager] = None,
        supervision_manager: Optional[SupervisionManager] = None,
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
        self.context_compressor = context_compressor or ContextCompressor()
        self.context_planner = context_planner or ContextPlanner()
        self.extractor = extractor or MemoryExtractor()
        self.insight_manager = insight_manager or InsightManager()
        self.intent_manager = intent_manager or IntentManager()
        self.memory_category_manager = memory_category_manager or MemoryCategoryManager()
        self.memory_governance_manager = memory_governance_manager or MemoryGovernanceManager()
        self.memory_item_manager = memory_item_manager or MemoryItemManager()
        self.memory_pipeline = memory_pipeline or MemoryPipeline()
        self.memory_resource_manager = memory_resource_manager or MemoryResourceManager()
        self.reflection_manager = reflection_manager or ReflectionManager()
        self.search_manager = search_manager or SearchManager()
        self.semantic_dialogue_manager = semantic_dialogue_manager or SemanticDialogueManager()
        self.supervision_manager = supervision_manager or SupervisionManager()
        self.summary_manager = summary_manager or SummaryManager()
        self.task_manager = task_manager or TaskManager()
        self.task_state_manager = task_state_manager or TaskStateManager()
        self.user_profile_manager = user_profile_manager or UserProfileManager()
        self.last_pipeline_result: Dict[str, Any] = {}
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

    def set_llm_client(self, llm_client: Any) -> None:
        self.commitment_manager.set_llm_client(llm_client)
        self.extractor.set_llm_client(llm_client)
        self.insight_manager.set_llm_client(llm_client)
        self.intent_manager.set_llm_client(llm_client)
        self.memory_governance_manager.set_llm_client(llm_client)
        self.semantic_dialogue_manager.set_llm_client(llm_client)
        self.summary_manager.set_llm_client(llm_client)
        self.task_manager.set_llm_client(llm_client)
        self.user_profile_manager.set_llm_client(llm_client)

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

    def process_turn(self, user_input: str, assistant_output: str) -> Dict[str, Any]:
        self.last_pipeline_result = self.memory_pipeline.process_turn(self, user_input, assistant_output)
        return self.last_pipeline_result

    #每轮对话都开启记录保存
    def add_record(
        self,
        user_input: str,
        assistant_output: str,
        extracted: Optional[Dict[str, Any]] = None,
        task_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        extracted = extracted or self.extract_memory(user_input, assistant_output)
        task_state = task_state or self.update_task_state(extracted, user_input, assistant_output)
        record = self.persist_record(
            user_input,
            assistant_output,
            extracted=extracted,
            task_state=task_state,
        )
        self.update_derived_memory(record, extracted, task_state, user_input, assistant_output)
        return record

    def persist_record(
        self,
        user_input: str,
        assistant_output: str,
        extracted: Dict[str, Any],
        task_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        records = self.load_records()
        now_text = datetime.now().isoformat(timespec="seconds")
        record = {
            "id": self._make_record_id(now_text, len(records), user_input),
            "time": now_text,
            "user": user_input,
            "assistant": assistant_output,
            "extracted": extracted,
            "task_state_snapshot": task_state,
        }
        records.append(record)
        self.save_records(records)
        return record

    def update_derived_memory(
        self,
        record: Dict[str, Any],
        extracted: Dict[str, Any],
        task_state: Dict[str, Any],
        user_input: str,
        assistant_output: str,
    ) -> Dict[str, Any]:
        records = self.load_records()
        self.summary_manager.summarize_day(records)
        recent_summary = self.get_recent_summary(days=7)
        commitments = self.commitment_manager.update(extracted, user_input, assistant_output, task_state=task_state)
        user_profile = self.user_profile_manager.update(
            extracted,
            user_input,
            assistant_output,
            recent_summary=recent_summary,
        )
        resource = self.memory_resource_manager.update_from_record(
            record=record,
            task_state=task_state,
            task_view=self.get_task_view(),
        )
        semantic_dialogue = self.semantic_dialogue_manager.update_from_record(
            record=record,
            extracted=extracted,
            task_state=task_state,
        )
        memory_items = self.memory_item_manager.update_from_turn(
            record=record,
            extracted=extracted,
            task_state=task_state,
            task_view=self.get_task_view(),
            recent_summary=recent_summary,
            commitments=commitments,
            user_profile=user_profile,
        )
        memory_categories = self.memory_category_manager.rebuild_from_items(memory_items)
        reflection = self.run_reflection_if_needed(
            records=records,
            user_input=user_input,
            memory_items=memory_items,
            memory_categories=memory_categories,
        )
        memory_items = self.memory_item_manager.load_items()
        memory_categories = self.memory_category_manager.rebuild_from_items(memory_items)
        retrieval_index = self.refresh_search_index(
            records,
            memory_items=memory_items,
            memory_categories=memory_categories,
            memory_resources=self.memory_resource_manager.load_resources(),
            semantic_dialogues=self.semantic_dialogue_manager.load_dialogues(),
            insights=self.insight_manager.load_insights(),
        )
        return {
            "resource": resource,
            "semantic_dialogue": semantic_dialogue,
            "memory_items": memory_items,
            "memory_categories": memory_categories,
            "reflection": reflection,
            "retrieval_index": retrieval_index,
            "commitments": commitments,
            "user_profile": user_profile,
            "recent_summary": recent_summary,
        }

    def run_reflection_if_needed(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        user_input: str = "",
        memory_items: Optional[List[Dict[str, Any]]] = None,
        memory_categories: Optional[List[Dict[str, Any]]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        records = records if records is not None else self.load_records()
        if not force and not self.reflection_manager.should_reflect(records, user_input=user_input):
            return {"triggered": False, "reason": "interval_not_met"}

        memory_items = memory_items if memory_items is not None else self.memory_item_manager.load_items()
        memory_categories = memory_categories if memory_categories is not None else self.memory_category_manager.load_categories()
        semantic_dialogues = self.semantic_dialogue_manager.load_dialogues()
        trigger = "manual" if force or any(keyword in str(user_input) for keyword in ["复盘一下", "自我反省", "反省一下", "总结最近状态"]) else "interval"
        insights = self.insight_manager.update_from_reflection(
            memory_items=memory_items,
            categories=memory_categories,
            semantic_dialogues=semantic_dialogues,
            trigger=trigger,
        )
        governance = self.memory_governance_manager.govern_items(memory_items, insights)
        self.memory_item_manager.save_items(governance.get("updated_items", memory_items))
        reflection = self.reflection_manager.record_reflection(
            records=records,
            trigger=trigger,
            semantic_dialogues=semantic_dialogues,
            insights=insights,
            governance=governance,
        )
        return {
            "triggered": True,
            "reflection": reflection,
            "insights": insights[:8],
            "governance": governance,
        }

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

    def get_memory_items(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.memory_item_manager.get_recent_items(limit=limit)

    def get_memory_categories(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.memory_category_manager.get_top_categories(limit=limit)

    def get_memory_resources(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.memory_resource_manager.get_recent_resources(limit=limit)

    def get_semantic_dialogues(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.semantic_dialogue_manager.get_recent_dialogues(limit=limit)

    def get_high_level_insights(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.insight_manager.get_active_insights(limit=limit)

    def get_memory_conflicts(self) -> List[Dict[str, Any]]:
        return self.memory_governance_manager.load_conflicts()

    def get_reflections(self) -> List[Dict[str, Any]]:
        return self.reflection_manager.load_reflections()

    def get_supervision_state(self) -> Dict[str, Any]:
        return self.supervision_manager.build_state(
            task_view=self.get_task_view(),
            commitments=self.commitment_manager.load_commitments(),
            memory_items=self.memory_item_manager.load_items(),
            user_profile=self.get_user_profile(),
        )

    def refresh_search_index(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        memory_items: Optional[List[Dict[str, Any]]] = None,
        memory_categories: Optional[List[Dict[str, Any]]] = None,
        memory_resources: Optional[List[Dict[str, Any]]] = None,
        semantic_dialogues: Optional[List[Dict[str, Any]]] = None,
        insights: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        records = records if records is not None else self.load_records()
        memory_items = memory_items if memory_items is not None else self.memory_item_manager.load_items()
        memory_categories = (
            memory_categories if memory_categories is not None else self.memory_category_manager.load_categories()
        )
        memory_resources = memory_resources if memory_resources is not None else self.memory_resource_manager.load_resources()
        semantic_dialogues = semantic_dialogues if semantic_dialogues is not None else self.semantic_dialogue_manager.load_dialogues()
        insights = insights if insights is not None else self.insight_manager.load_insights()
        return self.search_manager.build_index(
            records,
            daily_summaries=self.get_recent_summary(days=7).get("daily_summaries", []),
            user_profile=self.get_user_profile(),
            commitments=self.commitment_manager.load_commitments(),
            memory_items=memory_items,
            memory_categories=memory_categories,
            memory_resources=memory_resources,
            semantic_dialogues=semantic_dialogues,
            insights=insights,
        )

    def search_related_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.search_manager.search(query, limit=limit)

    def search_memory_items(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        return self.memory_item_manager.search_items(query, limit=limit)

    def search_memory_categories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.memory_category_manager.search_categories(query, limit=limit)

    def get_recent_messages(self) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        selected_records = self.load_records()[-self.recent_limit:]
        semantic_lookup = {
            item.get("record_id"): item
            for item in self.semantic_dialogue_manager.load_dialogues()
            if item.get("record_id")
        }
        raw_keep_count = 2
        semantic_cutoff = max(len(selected_records) - raw_keep_count, 0)
        for index, record in enumerate(selected_records):
            semantic = semantic_lookup.get(record.get("id"))
            if semantic and index < semantic_cutoff:
                messages.append({
                    "role": "system",
                    "content": self._with_time(
                        record,
                        "[语义压缩历史]\n" + semantic.get("semantic_summary", ""),
                    ),
                })
                continue
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
        # 先做上下文规划，再按需加载和格式化对应记忆块。
        intent_classification = self.intent_manager.classify(current_prompt)
        required_keys = self.context_planner.required_context_keys(
            current_prompt,
            classification=intent_classification,
        )
        available_context = self._load_context_blocks(current_prompt, required_keys, intent_classification)
        messages = self.context_planner.plan(current_prompt, available_context, classification=intent_classification)

        system_messages = self.context_compressor.compress_system_messages(messages)
        recent_messages = self.context_compressor.recent_messages(self.get_recent_messages())

        messages = [*system_messages, *recent_messages]
        messages.append(
            {
                "role": "user",
                "content": self._with_current_time(current_prompt),
            }
        )
        return messages

    def _load_context_blocks(
        self,
        current_prompt: str,
        keys: List[str],
        intent_classification: Dict[str, Any],
    ) -> Dict[str, str]:
        key_set = set(keys)
        available: Dict[str, str] = {}
        related_memories: List[Dict[str, Any]] = []

        if {"related_memories", "retrieval_plan"} & key_set:
            related_memories = self.search_related_memories(current_prompt, limit=5)

        if "intent" in key_set:
            available["intent"] = self.intent_manager.format_for_context(intent_classification)
        if "user_profile" in key_set:
            available["user_profile"] = self.user_profile_manager.format_for_context()
        if "task_lifecycle" in key_set:
            available["task_lifecycle"] = self.task_manager.format_for_context()
        if "task_state" in key_set:
            available["task_state"] = self.task_state_manager.format_for_context()
        if "high_level_insights" in key_set:
            available["high_level_insights"] = self.insight_manager.format_for_context()
        if "semantic_dialogues" in key_set:
            available["semantic_dialogues"] = self.semantic_dialogue_manager.format_for_context()
        if "memory_governance" in key_set:
            available["memory_governance"] = self.memory_governance_manager.format_for_context()
        if "reflections" in key_set:
            available["reflections"] = self.reflection_manager.format_for_context()
        if "memory_summary" in key_set:
            available["memory_summary"] = self.get_memory_summary()
        if "structured_summary" in key_set:
            available["structured_summary"] = self.get_structured_memory_summary()
        if "recent_summary" in key_set:
            available["recent_summary"] = self.get_recent_summary_context(days=7)
        if "commitments" in key_set:
            available["commitments"] = self.commitment_manager.format_for_context()
        if "related_memories" in key_set:
            available["related_memories"] = self.search_manager.format_for_context(related_memories)
        if "memory_categories" in key_set:
            related_categories = self.search_memory_categories(current_prompt, limit=5) or self.get_memory_categories(limit=5)
            available["memory_categories"] = self.memory_category_manager.format_for_context(related_categories)
        if "memory_items" in key_set:
            related_items = self.search_memory_items(current_prompt, limit=8)
            available["memory_items"] = self.memory_item_manager.format_for_context(related_items)
        if "supervision" in key_set:
            available["supervision"] = self.supervision_manager.format_for_context(self.get_supervision_state())
        if "retrieval_plan" in key_set:
            retrieval_plan = self.search_manager.build_retrieval_plan(current_prompt, related_memories)
            available["retrieval_plan"] = self.search_manager.format_retrieval_plan(retrieval_plan)
        return available

    def build_context_debug(self, current_prompt: str = "") -> Dict[str, Any]:
        debug_results = self.search_related_memories(current_prompt, limit=5) if current_prompt else []
        intent_classification = self.intent_manager.classify(current_prompt) if current_prompt else {}
        messages = self.build_context_messages(current_prompt) if current_prompt else [
            {"role": "system", "content": self.get_memory_summary()},
            {"role": "system", "content": self.user_profile_manager.format_for_context()},
            {"role": "system", "content": self.task_manager.format_for_context()},
            {"role": "system", "content": self.task_state_manager.format_for_context()},
            {"role": "system", "content": self.insight_manager.format_for_context()},
            {"role": "system", "content": self.semantic_dialogue_manager.format_for_context()},
            {"role": "system", "content": self.memory_governance_manager.format_for_context()},
            {"role": "system", "content": self.reflection_manager.format_for_context()},
            {"role": "system", "content": self.get_structured_memory_summary()},
            {"role": "system", "content": self.get_recent_summary_context(days=7)},
            {"role": "system", "content": self.commitment_manager.format_for_context()},
            {"role": "system", "content": self.search_manager.format_for_context([])},
            {"role": "system", "content": self.memory_category_manager.format_for_context()},
            {"role": "system", "content": self.memory_item_manager.format_for_context()},
            {"role": "system", "content": self.supervision_manager.format_for_context(self.get_supervision_state())},
            *self.get_recent_messages(),
        ]
        return {
            "messages": messages,
            "context_stats": self.context_compressor.estimate_context(messages),
            "memory_pipeline": self.memory_pipeline.describe(),
            "last_pipeline_result": self.last_pipeline_result,
            "intent": intent_classification,
            "retrieval_plan": self.search_manager.build_retrieval_plan(current_prompt, debug_results) if current_prompt else {},
            "task_state": self.get_task_state(),
            "task_view": self.get_task_view(),
            "structured_summary": self.get_structured_memory_summary(),
            "recent_summary": self.get_recent_summary(days=7),
            "open_commitments": self.get_open_commitments(),
            "user_profile": self.get_user_profile(),
            "memory_items": self.get_memory_items(limit=20),
            "memory_categories": self.get_memory_categories(limit=10),
            "memory_resources": self.get_memory_resources(limit=10),
            "semantic_dialogues": self.get_semantic_dialogues(limit=10),
            "high_level_insights": self.get_high_level_insights(limit=10),
            "memory_conflicts": self.get_memory_conflicts(),
            "reflections": self.get_reflections(),
            "supervision": self.get_supervision_state(),
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

    def _make_record_id(self, now: str, index: int, user_input: str) -> str:
        safe_time = now.replace("-", "").replace(":", "").replace("T", "-")
        digest = hashlib.sha256(str(user_input or "").encode("utf-8")).hexdigest()[:10]
        return f"record-{safe_time}-{index + 1:05d}-{digest}"

    def _compact(self, text: str, max_length: int = 300) -> str:
        text = " ".join(str(text).split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
