from typing import Any, Dict, List, Optional

from .context_compressor import ContextCompressor
from .context_planner import ContextPlanner
from .search import SearchManager


class ContextEngine:
    def __init__(
        self,
        search_manager: Optional[SearchManager] = None,
        context_planner: Optional[ContextPlanner] = None,
        context_compressor: Optional[ContextCompressor] = None,
    ):
        self.search_manager = search_manager or SearchManager()
        self.context_planner = context_planner or ContextPlanner()
        self.context_compressor = context_compressor or ContextCompressor()

    def build_messages(self, current_prompt: str, memory_manager: Any) -> List[Dict[str, str]]:
        intent_classification = memory_manager.intent_manager.classify(current_prompt)
        required_keys = self.context_planner.required_context_keys(
            current_prompt,
            classification=intent_classification,
        )
        available_context = self.load_context_blocks(
            current_prompt,
            required_keys,
            intent_classification,
            memory_manager,
        )
        planned_messages = self.context_planner.plan(
            current_prompt,
            available_context,
            classification=intent_classification,
        )
        system_messages = self.context_compressor.compress_system_messages(planned_messages)
        recent_messages = self.context_compressor.recent_messages(memory_manager.get_recent_messages())
        return [
            *system_messages,
            *recent_messages,
            {
                "role": "user",
                "content": memory_manager.with_current_time(current_prompt),
            },
        ]

    def load_context_blocks(
        self,
        current_prompt: str,
        keys: List[str],
        intent_classification: Dict[str, Any],
        memory_manager: Any,
    ) -> Dict[str, str]:
        key_set = set(keys)
        available: Dict[str, str] = {}
        related_memories: List[Dict[str, Any]] = []

        if {"related_memories", "retrieval_plan"} & key_set:
            related_memories = self.search_related_memories(current_prompt, limit=5)

        if "intent" in key_set:
            available["intent"] = memory_manager.intent_manager.format_for_context(intent_classification)
        if "user_profile" in key_set:
            available["user_profile"] = memory_manager.user_profile_manager.format_for_context()
        if "task_lifecycle" in key_set:
            available["task_lifecycle"] = memory_manager.task_state.format_task_lifecycle()
        if "task_state" in key_set:
            available["task_state"] = memory_manager.task_state.format_current_state()
        if "high_level_insights" in key_set:
            available["high_level_insights"] = memory_manager.insight_manager.format_for_context()
        if "semantic_dialogues" in key_set:
            available["semantic_dialogues"] = memory_manager.semantic_dialogue_manager.format_for_context()
        if "memory_governance" in key_set:
            available["memory_governance"] = memory_manager.memory_governance_manager.format_for_context()
        if "reflections" in key_set:
            available["reflections"] = memory_manager.reflection_manager.format_for_context()
        if "memory_summary" in key_set:
            available["memory_summary"] = memory_manager.get_memory_summary()
        if "structured_summary" in key_set:
            available["structured_summary"] = memory_manager.get_structured_memory_summary()
        if "recent_summary" in key_set:
            available["recent_summary"] = memory_manager.get_recent_summary_context(days=7)
        if "commitments" in key_set:
            available["commitments"] = memory_manager.task_state.format_commitments()
        if "related_memories" in key_set:
            available["related_memories"] = self.search_manager.format_for_context(related_memories)
        if "memory_categories" in key_set:
            related_categories = memory_manager.search_memory_categories(current_prompt, limit=5) or memory_manager.get_memory_categories(limit=5)
            available["memory_categories"] = memory_manager.memory_category_manager.format_for_context(related_categories)
        if "memory_items" in key_set:
            related_items = memory_manager.search_memory_items(current_prompt, limit=8)
            available["memory_items"] = memory_manager.memory_item_manager.format_for_context(related_items)
        if "supervision" in key_set:
            available["supervision"] = memory_manager.supervision_manager.format_for_context(memory_manager.get_supervision_state())
        if "support_knowledge" in key_set:
            support_state = memory_manager.get_support_knowledge_state(current_prompt)
            available["support_knowledge"] = memory_manager.support_knowledge_manager.format_for_context(support_state)
        if "retrieval_plan" in key_set:
            retrieval_plan = self.search_manager.build_retrieval_plan(current_prompt, related_memories)
            available["retrieval_plan"] = self.search_manager.format_retrieval_plan(retrieval_plan)
        return available

    def refresh_search_index(
        self,
        records: List[Dict[str, Any]],
        daily_summaries: List[Dict[str, Any]],
        user_profile: Dict[str, Any],
        commitments: List[Dict[str, Any]],
        memory_items: List[Dict[str, Any]],
        memory_categories: List[Dict[str, Any]],
        memory_resources: List[Dict[str, Any]],
        semantic_dialogues: List[Dict[str, Any]],
        insights: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return self.search_manager.build_index(
            records,
            daily_summaries=daily_summaries,
            user_profile=user_profile,
            commitments=commitments,
            memory_items=memory_items,
            memory_categories=memory_categories,
            memory_resources=memory_resources,
            semantic_dialogues=semantic_dialogues,
            insights=insights,
        )

    def search_related_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.search_manager.search(query, limit=limit)

    def build_retrieval_plan(self, query: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.search_manager.build_retrieval_plan(query, results)

    def format_empty_retrieval(self) -> str:
        return self.search_manager.format_for_context([])

    def estimate_context(self, messages: List[Dict[str, str]]) -> Dict[str, int]:
        return self.context_compressor.estimate_context(messages)
