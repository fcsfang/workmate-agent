from datetime import datetime, timedelta
from unittest.mock import patch

from memory import SupervisionEventManager


def test_supervision_event_lifecycle_detect_ack_snooze_resolve(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("", "")):
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
    assert acknowledged["last_transition_reason"] == "user_acknowledged"
    assert acknowledged["transition_history"][-1]["from"] == "detected"
    assert acknowledged["transition_history"][-1]["to"] == "acknowledged"
    snoozed = manager.snooze(active[0]["id"], minutes=30)
    assert snoozed["status"] == "snoozed"
    assert snoozed["snoozed_until"]
    resolved = manager.resolve(active[0]["id"])
    assert resolved["status"] == "resolved"
    state = manager.build_state()
    assert state["state_machine"]["states"]["resolved"] == 1
    assert state["state_machine"]["recent_transitions"][0]["to"] == "resolved"


def test_supervision_event_can_be_dismissed_as_final_state(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    old = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")

    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("", "")):
        active = manager.detect_events(
            focus_state={"current": {}},
            commitments=[],
            task_view={"current": {
                "id": "task-1",
                "title": "整理状态机",
                "status": "active",
                "updated_at": old,
            }},
        )

    dismissed = manager.dismiss(active[0]["id"])
    assert dismissed["status"] == "dismissed"
    assert dismissed["dismissed_at"]
    assert dismissed["last_transition_reason"] == "user_dismissed"
    state = manager.build_state()
    assert state["counts"]["dismissed"] == 1
    assert state["state_machine"]["states"]["dismissed"] == 1


def test_supervision_event_detects_overdue_commitment_and_stale_task(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    yesterday = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    old = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")

    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("", "")):
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
    assert strategy["explanations"][0]["decision"] == "raise_browser_threshold"
    assert strategy["explanations"][0]["evidence"]["snoozed_or_muted"] == 3


def test_reminder_strategy_keeps_explainable_steady_state(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )

    state = manager.build_state()
    strategy = state["strategy"]

    assert strategy["mode"] == "steady"
    assert strategy["preference_updates"] == {}
    assert strategy["explanations"][0]["decision"] == "keep_current_strategy"
    assert strategy["explanations"][0]["auto_applicable"] is False


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
        "screen_force_message": True,
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
    assert preferences["screen_force_message"] is True
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


def test_screen_copy_policy_does_not_truncate_vision_message(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    message = (
        "你现在更像是在处理聊天和一段与老师沟通相关的内容，不是在推进 Workmate Agent 优化。"
        "若这是临时必须处理的事，尽量收尾到一个明确节点；处理完就切回 Console/代码。"
    )
    candidate = {
        "type": "screen_deviation",
        "subject_title": "继续优化 Workmate Agent",
        "subject_id": "task-1",
        "display_message": message,
        "metadata": {"focus_goal": "继续优化 Workmate Agent"},
    }

    polished = manager._apply_copy_policy(candidate, {"concise": True, "summary": "只给一个小提示"})

    assert polished["display_message"] == message
    assert polished["display_message"].endswith("Console/代码。")
    assert not polished["display_message"].endswith("/代。")


def test_screen_observation_policy_respects_vision_silence_and_force_message(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    now = datetime.now()
    base_analysis = {
        "observation": "在浏览与当前任务弱相关的网页",
        "goal_note": "可能是短暂查资料，也可能有点发散",
        "message_type": "pullback",
        "should_message": False,
        "message": "这段好像有点偏开了，先回来接一下论文主线。",
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

    preferences = manager.load_preferences()
    preferences["screen_force_message"] = True
    manager.save_preferences(preferences)

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
    assert first_policy["reason"] == "vision_chose_silence"
    assert second_policy["action"] == "emit_event"
    assert second_policy["reason"] == "force_message_enabled"
    assert second_policy["severity"] == "high"
    assert len(manager.load_screen_observations()) == 2
