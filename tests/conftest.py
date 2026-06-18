from pathlib import Path

import pytest

from memory import (
    BehaviorPatternManager,
    CommitmentManager,
    ContextEngine,
    FocusSessionManager,
    InsightManager,
    LongTermKnowledgeManager,
    MemoryCategoryManager,
    MemoryGovernanceManager,
    MemoryItemManager,
    MemoryManager,
    MemoryResourceManager,
    ReflectionManager,
    SearchManager,
    SemanticDialogueManager,
    SummaryManager,
    SupervisionEventManager,
    TaskManager,
    TaskState,
    TaskStateManager,
    UserProfileManager,
)


@pytest.fixture
def temp_memory_paths(tmp_path):
    data = tmp_path / "memory"
    data.mkdir()
    return data


@pytest.fixture
def tmp_memory_manager(temp_memory_paths):
    data = Path(temp_memory_paths)
    task_manager = TaskManager(
        tasks_path=str(data / "tasks.json"),
        events_path=str(data / "task_events.json"),
    )
    task_state_manager = TaskStateManager(state_path=str(data / "task_state.json"))
    commitment_manager = CommitmentManager(commitments_path=str(data / "commitments.json"))
    task_state = TaskState(
        task_manager=task_manager,
        task_state_manager=task_state_manager,
        commitment_manager=commitment_manager,
    )
    context_engine = ContextEngine(search_manager=SearchManager(index_path=str(data / "retrieval_index.json")))
    return MemoryManager(
        memory_path=str(data / "records.json"),
        commitment_manager=commitment_manager,
        context_engine=context_engine,
        focus_session_manager=FocusSessionManager(sessions_path=str(data / "focus_sessions.json")),
        insight_manager=InsightManager(insights_path=str(data / "high_level_insights.json")),
        long_term_knowledge_manager=LongTermKnowledgeManager(str(data / "knowledge")),
        memory_category_manager=MemoryCategoryManager(categories_path=str(data / "memory_categories.json")),
        memory_governance_manager=MemoryGovernanceManager(conflicts_path=str(data / "memory_conflicts.json")),
        memory_item_manager=MemoryItemManager(items_path=str(data / "memory_items.json")),
        memory_resource_manager=MemoryResourceManager(resources_path=str(data / "memory_resources.json")),
        reflection_manager=ReflectionManager(reflections_path=str(data / "reflections.json")),
        semantic_dialogue_manager=SemanticDialogueManager(dialogues_path=str(data / "semantic_dialogues.json")),
        summary_manager=SummaryManager(summaries_dir=str(data / "daily_summaries")),
        supervision_event_manager=SupervisionEventManager(
            events_path=str(data / "supervision_events.json"),
            preferences_path=str(data / "supervision_preferences.json"),
        ),
        behavior_pattern_manager=BehaviorPatternManager(patterns_path=str(data / "behavior_patterns.json")),
        task_state=task_state,
        user_profile_manager=UserProfileManager(profile_path=str(data / "user_profile.json")),
    )
