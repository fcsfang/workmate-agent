import unittest
from datetime import datetime

from tools import ToolExecutor, ToolRegistry, build_workmate_tool_registry


class FakeTaskManager:
    def __init__(self):
        now = datetime.now().isoformat(timespec="seconds")
        self.tasks = [
            {
                "id": "task-1",
                "title": "实现工具 trace",
                "status": "active",
                "progress": [],
                "next_actions": ["补测试"],
                "created_at": now,
                "updated_at": now,
            }
        ]
        self.events = []

    def load_tasks(self):
        return list(self.tasks)

    def save_tasks(self, tasks):
        self.tasks = tasks

    def _sort_tasks(self, tasks):
        return tasks

    def _append_event(self, event_type, task, now_text, payload):
        self.events.append({"type": event_type, "task_id": task.get("id"), "payload": payload})


class FakeTaskStateManager:
    def __init__(self):
        self.state = {"task_id": "task-1", "active_task": "实现工具 trace", "status": "active"}

    def load_state(self):
        return dict(self.state)

    def save_state(self, state):
        self.state = state


class FakeTaskState:
    def __init__(self):
        self.task_manager = FakeTaskManager()
        self.task_state_manager = FakeTaskStateManager()


class FakeMemoryManager:
    def __init__(self):
        self.task_state = FakeTaskState()
        self.focus_started = []
        self.supervision_preferences = {
            "enabled": True,
            "reminder_strength": "gentle",
            "browser_min_severity": "medium",
            "notify_focus": True,
        }

    def get_task_view(self, limit=8):
        tasks = self.task_state.task_manager.tasks
        return {
            "current": tasks[0],
            "active": tasks[:limit],
            "counts": {"active": len(tasks)},
        }

    def get_open_commitments(self):
        return [{"id": "commit-1", "commitment": "今天补齐工具测试", "status": "open"}]

    def search_related_memories(self, query, limit=5):
        return [{"source_type": "memory_item", "source_id": "mem-1", "text": query, "score": 0.9}][:limit]

    def start_focus_session(self, goal, duration_minutes=45):
        session = {
            "goal": goal,
            "duration_minutes": duration_minutes,
            "started_at": "2026-06-16T10:00:00",
            "expected_end_at": "2026-06-16T10:45:00",
        }
        self.focus_started.append(session)
        return session

    def complete_focus_session(self, outcome=""):
        return {"goal": "实现工具 trace", "elapsed_minutes": 25, "outcome": outcome}

    def abandon_focus_session(self, outcome=""):
        return {"goal": "实现工具 trace", "elapsed_minutes": 5, "outcome": outcome}

    def get_supervision_preferences(self):
        return dict(self.supervision_preferences)

    def update_supervision_preferences(self, updates):
        self.supervision_preferences.update(updates)
        return dict(self.supervision_preferences)


class ToolExecutorTest(unittest.TestCase):
    def test_workmate_tool_schemas_export_read_write_metadata(self):
        registry = build_workmate_tool_registry(FakeMemoryManager())
        schemas = {item["name"]: item for item in registry.export_schemas()}

        self.assertFalse(schemas["update_task_status"]["read_only"])
        self.assertTrue(schemas["search_memory"]["read_only"])
        self.assertFalse(schemas["update_supervision_preferences"]["read_only"])
        self.assertIn("output_schema", schemas["start_focus_session"])
        self.assertIn("updates focus_sessions.json", schemas["start_focus_session"]["side_effects"])
        self.assertIn("updates supervision_preferences.json", schemas["update_supervision_preferences"]["side_effects"])

    def test_task_commitment_memory_and_focus_tool_traces(self):
        registry = build_workmate_tool_registry(FakeMemoryManager())
        executor = ToolExecutor(registry)

        task_result = executor.execute({
            "tool": "update_task_status",
            "arguments": {"task_id": "task-1", "status": "done", "reason": "测试完成"},
            "reason": "用户明确完成任务",
        })
        commitment_result = executor.execute({"tool": "list_open_commitments", "arguments": {}})
        memory_result = executor.execute({"tool": "search_memory", "arguments": {"query": "工具 trace"}})
        focus_result = executor.execute({"tool": "start_focus_session", "arguments": {"goal": "写测试", "duration_minutes": 25}})
        preference_result = executor.execute({
            "tool": "update_supervision_preferences",
            "arguments": {
                "updates": {"browser_min_severity": "high", "notify_focus": False, "unsupported": "ignored"},
                "reason": "测试提醒偏好更新",
            },
        })

        self.assertEqual(task_result["status"], "success")
        self.assertFalse(task_result["read_only"])
        self.assertIn("duration_ms", task_result)
        self.assertIn("input_schema", task_result)
        self.assertEqual(task_result["observation"]["status"], "done")
        self.assertTrue(task_result["audit_record"]["audit_id"])
        self.assertEqual(task_result["audit_record"]["tool"], "update_task_status")
        self.assertTrue(commitment_result["read_only"])
        self.assertEqual(commitment_result["observation"]["open_commitments"][0]["id"], "commit-1")
        self.assertEqual(commitment_result["audit_record"], {})
        self.assertTrue(memory_result["read_only"])
        self.assertEqual(memory_result["observation"]["results"][0]["source_id"], "mem-1")
        self.assertFalse(focus_result["read_only"])
        self.assertIn("updates focus_sessions.json", focus_result["side_effects"])
        self.assertTrue(focus_result["audit_record"]["side_effects"])
        self.assertFalse(preference_result["read_only"])
        self.assertEqual(preference_result["observation"]["applied_updates"]["browser_min_severity"], "high")
        self.assertNotIn("unsupported", preference_result["observation"]["applied_updates"])
        self.assertIn("updates supervision_preferences.json", preference_result["audit_record"]["side_effects"])

    def test_tool_planning_failure_is_returned_as_trace(self):
        class FailingLLM:
            def invoke_raw(self, messages):
                raise RuntimeError("planner unavailable")

        registry = ToolRegistry()
        registry.register(
            "noop",
            "no operation",
            {"type": "object", "properties": {}, "required": []},
            lambda args: {"ok": True},
        )
        executor = ToolExecutor(registry)
        results = executor.plan_and_execute(FailingLLM(), [], "hello")

        self.assertEqual(results[0]["tool"], "__tool_planning__")
        self.assertEqual(results[0]["status"], "error")
        self.assertTrue(results[0]["recoverable"])
        self.assertIn("continue", results[0]["recovery_hint"].lower())
        self.assertIn("planner unavailable", results[0]["error"])

    def test_max_tool_calls_is_bounded(self):
        class PlanningLLM:
            def invoke_raw(self, messages):
                return '{"tool_calls":[{"tool":"noop","arguments":{}},{"tool":"noop","arguments":{}},{"tool":"noop","arguments":{}}]}'

        registry = ToolRegistry()
        registry.register(
            "noop",
            "no operation",
            {"type": "object", "properties": {}, "required": []},
            lambda args: {"ok": True},
        )
        executor = ToolExecutor(registry, max_calls=2)
        results = executor.plan_and_execute(PlanningLLM(), [], "hello")
        plan_trace = executor.get_last_plan_trace()

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result["status"] == "success" for result in results))
        self.assertEqual(plan_trace["decision_source"], "llm_plan")
        self.assertEqual(plan_trace["parsed_count"], 3)
        self.assertEqual(plan_trace["selected_count"], 2)
        self.assertTrue(plan_trace["truncated"])
        self.assertTrue(all(result["decision_source"] == "llm_plan" for result in results))


if __name__ == "__main__":
    unittest.main()
