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
