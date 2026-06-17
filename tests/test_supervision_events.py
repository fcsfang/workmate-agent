from datetime import datetime, timedelta

from memory import SupervisionEventManager


def test_supervision_event_lifecycle_detect_ack_snooze_resolve(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    active = manager.detect_events(
        focus_state={"current": {
            "id": "focus-1",
            "status": "expired",
            "goal": "写测试",
            "duration_minutes": 25,
            "elapsed_minutes": 40,
        }},
        commitments=[],
        task_view={"current": {}},
    )

    assert active[0]["type"] == "focus_expired"
    acknowledged = manager.acknowledge(active[0]["id"])
    assert acknowledged["status"] == "acknowledged"
    snoozed = manager.snooze(active[0]["id"], minutes=30)
    assert snoozed["status"] == "snoozed"
    assert snoozed["snoozed_until"]
    resolved = manager.resolve(active[0]["id"])
    assert resolved["status"] == "resolved"


def test_supervision_event_detects_overdue_commitment_and_stale_task(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    yesterday = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    old = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")

    active = manager.detect_events(
        focus_state={"current": {}},
        commitments=[{
            "id": "commit-1",
            "commitment": "补测试报告",
            "deadline": yesterday,
            "status": "open",
        }],
        task_view={"current": {
            "id": "task-1",
            "title": "补 CI",
            "status": "active",
            "updated_at": old,
        }},
    )

    event_types = {event["type"] for event in active}
    assert "commitment_overdue" in event_types
    assert "task_stale" in event_types


def test_reminder_preference_strategy_reduces_push_after_delays(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    now = datetime.now().isoformat(timespec="seconds")
    manager.save_events([
        {
            "id": f"event-{index}",
            "type": "task_stale",
            "subject_id": f"task-{index}",
            "status": "snoozed",
            "severity": "low",
            "feedback_history": [{"action": "snoozed", "at": now, "details": {}}],
            "created_at": now,
            "updated_at": now,
        }
        for index in range(3)
    ])

    state = manager.build_state()
    strategy = state["strategy"]

    assert strategy["mode"] == "reduce_push"
    assert strategy["preference_updates"]["browser_min_severity"] == "high"


def test_voice_preferences_are_normalized_and_persisted(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )

    preferences = manager.update_preferences({
        "voice_enabled": True,
        "voice_provider": "xfyun",
        "voice_min_severity": "high",
        "voice_volume": 1.5,
        "voice_rate": 0.2,
        "voice_include_accompaniment": True,
        "event_type_min_severity": {
            "screen_deviation": {"voice": "medium"},
        },
    })

    assert preferences["voice_enabled"] is True
    assert preferences["voice_provider"] == "xfyun"
    assert preferences["voice_min_severity"] == "high"
    assert preferences["voice_volume"] == 1.0
    assert preferences["voice_rate"] == 0.6
    assert preferences["voice_include_accompaniment"] is True
    assert preferences["event_type_min_severity"]["screen_deviation"]["voice"] == "medium"


def test_screen_accompaniment_copy_respects_model_suggestion(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    candidate = {
        "type": "screen_accompaniment",
        "subject_title": "继续优化 workmate agent",
        "subject_id": "task-1",
        "display_message": "这个点先收一下，别急着开新分支。",
        "metadata": {
            "focus_goal": "继续优化 workmate agent",
            "activity_summary": "控制台验证",
        },
    }

    polished = manager._apply_copy_policy(candidate, manager._copy_policy({}))

    assert polished["display_message"] == "这个点先收一下，别急着开新分支。"


def test_screen_observation_policy_waits_for_continuous_deviation(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    now = datetime.now()
    base_analysis = {
        "is_deviated": True,
        "activity_summary": "在浏览与当前任务弱相关的网页",
        "activity_category": "research",
        "goal_relation": "off_track",
        "likely_intent": "可能临时查资料，也可能开始发散",
        "visual_evidence": "浏览器页面与当前任务不直接相关",
        "uncertainty": "可能是短暂切换",
        "confidence": 0.64,
        "deviation_reason": "与当前主线关系较弱",
        "deviation_level": "medium",
        "intervention_hint": "gentle_pullback",
    }

    first = manager._record_screen_observation(
        analysis=base_analysis,
        now=now,
        subject_id="focus-1",
        subject_title="写论文",
        subject_type="focus",
        goal="写论文",
        app_name="Safari",
        window_title="参考资料",
    )
    first_policy = manager._screen_observation_policy(first)

    second = manager._record_screen_observation(
        analysis=base_analysis,
        now=now + timedelta(minutes=5),
        subject_id="focus-1",
        subject_title="写论文",
        subject_type="focus",
        goal="写论文",
        app_name="Safari",
        window_title="参考资料",
    )
    second_policy = manager._screen_observation_policy(second)

    assert first_policy["action"] == "record_only"
    assert first_policy["reason"] == "first_or_uncertain_deviation_observed"
    assert second_policy["action"] == "emit_event"
    assert second_policy["reason"] == "continuous_screen_deviation"
    assert second_policy["severity"] == "medium"
    assert len(manager.load_screen_observations()) == 2
