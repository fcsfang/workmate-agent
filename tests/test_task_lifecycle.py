from datetime import datetime

from memory import TaskManager


def test_task_manager_creates_and_updates_task_with_subtasks(tmp_path):
    manager = TaskManager(
        tasks_path=str(tmp_path / "tasks.json"),
        events_path=str(tmp_path / "events.json"),
    )

    task = manager.update(
        {
            "task": "完善测试体系",
            "progress": "已补 memory pipeline 测试",
            "next_actions": ["补 CI"],
            "subtasks": [{"title": "补 pytest", "status": "active"}],
        },
        "我继续完善测试体系",
        "收到",
    )

    assert task["title"] == "完善测试体系"
    assert task["status"] in {"active", "planned", "inbox"}
    assert task["subtasks"][0]["title"] == "补 pytest"
    assert manager.get_task_view()["current"]["id"] == task["id"]


def test_task_manager_update_status_marks_subtasks_done(tmp_path):
    manager = TaskManager(
        tasks_path=str(tmp_path / "tasks.json"),
        events_path=str(tmp_path / "events.json"),
    )
    now = datetime.now().isoformat(timespec="seconds")
    task = {
        **manager.default_task(),
        "id": "task-1",
        "title": "完成测试",
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "subtasks": [{"id": "sub-1", "title": "补单测", "status": "active"}],
    }
    manager.save_tasks([task])

    updated = manager.update_task_status("task-1", "done")

    assert updated["status"] == "done"
    assert updated["completed_at"]
    assert updated["subtasks"][0]["status"] == "done"
    assert manager.load_events()[-1]["payload"]["via"] == "web_ui"
