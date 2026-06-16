from memory import ContextPlanner


def test_context_planner_task_includes_retrieval_and_task_state():
    planner = ContextPlanner()
    keys = planner.required_context_keys(
        "我继续开发测试体系，下一步补 CI",
        classification={"intent": "task"},
    )

    assert "task_lifecycle" in keys
    assert "task_state" in keys
    assert "retrieval_plan" in keys
    assert "related_memories" in keys
    assert "commitments" in keys


def test_context_planner_weekly_report_includes_report_blocks():
    planner = ContextPlanner()
    keys = planner.required_context_keys("帮我生成本周复盘")

    assert "weekly_report_data" in keys
    assert "behavior_stats" in keys
    assert "commitments" in keys
    assert "supervision_events" in keys


def test_context_planner_support_knowledge_for_low_energy_state():
    planner = ContextPlanner()
    keys = planner.required_context_keys("我现在很焦虑，任务太多")

    assert "support_knowledge" in keys
