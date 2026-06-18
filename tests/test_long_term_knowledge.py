from memory import LongTermKnowledgeManager


def test_long_term_knowledge_sync_creates_layered_markdown(tmp_path):
    manager = LongTermKnowledgeManager(str(tmp_path / "knowledge"))

    paths = manager.sync(
        user_profile={
            "long_term_goal": "完成可展示的 Agent 项目",
            "working_style": ["适合围绕单一主线推进"],
            "failure_modes": ["任务过多时容易分散"],
            "effective_interventions": ["只给一个轻量建议"],
            "communication_preference": ["中文", "低压力回应"],
        },
        insights=[{
            "id": "insight-1",
            "status": "active",
            "content": "缩小当前工作面有助于恢复专注",
            "why_it_matters": "减少切换成本",
        }],
        behavior_patterns=[{
            "id": "pattern-1",
            "status": "active",
            "summary": "并行任务过多时推进速度下降",
            "suggested_intervention": "保留一条当前主线",
        }],
    )

    assert set(paths) == {"user", "goals", "preferences", "patterns", "insights"}
    assert "完成可展示的 Agent 项目" in (tmp_path / "knowledge" / "GOALS.md").read_text(encoding="utf-8")
    assert "低压力回应" in (tmp_path / "knowledge" / "PREFERENCES.md").read_text(encoding="utf-8")

    task_context = manager.format_for_context(intent="task")
    assert "不能覆盖当前任务" in task_context
    assert "并行任务过多" in task_context
    assert "缩小当前工作面" in task_context


def test_chat_context_omits_reflection_heavy_documents(tmp_path):
    manager = LongTermKnowledgeManager(str(tmp_path / "knowledge"))
    manager.sync(
        user_profile={"working_style": ["先整理再推进"]},
        insights=[{"status": "active", "content": "仅用于复盘的洞察"}],
        behavior_patterns=[{"status": "active", "summary": "仅用于监督的模式"}],
    )

    chat_context = manager.format_for_context(intent="chat")

    assert "先整理再推进" in chat_context
    assert "仅用于复盘的洞察" not in chat_context
    assert "仅用于监督的模式" not in chat_context
