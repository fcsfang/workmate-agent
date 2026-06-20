import importlib
import os

from fastapi.testclient import TestClient


def test_web_api_context_and_memory_smoke(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKMATE_DISABLE_SCHEDULER", "1")
    web = importlib.import_module("src.web")

    class FakeAgent:
        def invoke_stream(self, prompt):
            from observability import finish_provider_turn, start_provider_turn

            token = start_provider_turn("stream-test-turn")
            try:
                yield "第一段"
                yield "第二段"
            finally:
                finish_provider_turn(token)

        def get_last_context(self):
            return [{"role": "system", "content": "fake context"}]

        def get_last_tool_calls(self):
            return []

        def get_last_turn_trace(self):
            return {"turn_id": "turn-1", "stages": []}

        def get_tool_schemas(self):
            return [{"name": "noop", "input_schema": {}, "output_schema": {}, "read_only": True, "side_effects": []}]

    class FakeMemory:
        last_reminder_control = {}
        last_pipeline_result = {}

        def __init__(self):
            self.refresh_calls = 0

        class Compressor:
            def estimate_context(self, messages):
                return {"message_count": len(messages)}

        context_compressor = Compressor()

        class SupervisionEventManager:
            def should_notify(self, event, channel="background"):
                return True

        supervision_event_manager = SupervisionEventManager()

        def load_records(self):
            return []

        def recent_records_with_transient_supervision(self, limit=30):
            return []

        def refresh_supervision_events(self):
            self.refresh_calls += 1
            return [{"id": "event-1", "title": "提醒", "message": "回来看看"}]

        def get_behavior_patterns(self):
            return {"active": [], "recent": []}

        def get_dashboard_state(self):
            return {}

        def build_context_debug(self, current_prompt=""):
            return {"messages": [], "retrieval_plan": {}, "context_stats": {}}

        def get_memory_summary(self):
            return "empty"

        def get_structured_memory_summary(self):
            return "empty"

        def get_recent_summary(self, days=7):
            return {}

        def get_recent_summary_context(self, days=7):
            return ""

        def get_task_state(self):
            return {}

        def get_task_view(self):
            return {}

        def get_open_commitments(self):
            return []

        def get_user_profile(self):
            return {}

        def get_long_term_knowledge_files(self):
            return []

        def get_memory_items(self, limit=20):
            return []

        def get_memory_categories(self, limit=10):
            return []

        def get_memory_resources(self, limit=10):
            return []

        def get_semantic_dialogues(self, limit=10):
            return []

        def get_high_level_insights(self, limit=10):
            return []

        def get_memory_conflicts(self):
            return []

        def get_reflections(self):
            return []

        def get_supervision_state(self):
            return {}

        def get_supervision_event_state(self, current_prompt=""):
            return {"active": [], "state_machine": {"recent_transitions": []}}

        def update_supervision_event(self, event_id, action, hours=24, minutes=0):
            return {"id": event_id, "status": "notified", "action": action}

        def get_focus_session_state(self):
            return {}

        def get_support_knowledge_state(self, current_prompt=""):
            return {}

        def get_privacy_inventory(self):
            return {
                "data_root": str(tmp_path),
                "file_count": 1,
                "total_bytes": 2,
                "exportable_file_count": 1,
                "exportable_bytes": 2,
                "sensitive_file_count": 0,
                "files": [{
                    "path": "records.json",
                    "size_bytes": 2,
                    "modified_at": "2026-06-18T10:00:00",
                    "category": "conversation",
                    "exportable": True,
                    "sensitive": False,
                    "exclusion_reason": "",
                }],
                "export_policy": {"included": ["JSON data"], "excluded": ["API keys"]},
            }

        def export_local_data(self):
            export_path = tmp_path / "workmate-memory-export-test.zip"
            export_path.write_bytes(b"PK")
            return {
                "filename": export_path.name,
                "created_at": "2026-06-18T10:00:00",
                "file_count": 1,
                "total_bytes": 2,
                "download_url": f"/api/privacy/exports/{export_path.name}",
                "excluded": ["API keys"],
            }

        def resolve_local_export(self, filename):
            path = tmp_path / filename
            if path.name != filename or not path.exists():
                raise ValueError("Export file not found")
            return path

    fake_memory = FakeMemory()

    class FakeNotifier:
        def __init__(self):
            self.sent = []

        def send_notification(self, title, body):
            self.sent.append({"title": title, "body": body})

    fake_notifier = FakeNotifier()
    app = web.WorkmateWebApp(memory_manager=fake_memory, notifier=fake_notifier, start_background=False)
    workmate_app = app
    workmate_app.agent = FakeAgent()
    monkeypatch.setattr(web, "APP", workmate_app)

    client = TestClient(web.app)
    try:
        response = client.get("/api/context")
        assert response.status_code == 200
        context = response.json()
        assert context["message_count"] == 1
        assert context["tool_schemas"][0]["name"] == "noop"
        assert context["turn_trace"]["turn_id"] == "turn-1"

        response = client.get("/api/memory")
        assert response.status_code == 200
        memory = response.json()
        assert memory["count"] == 0
        assert memory["tool_schemas"][0]["read_only"] is True
        assert fake_memory.refresh_calls == 0

        response = client.get("/api/supervision/events")
        assert response.status_code == 200
        assert fake_memory.refresh_calls == 0

        response = client.get("/api/privacy/inventory")
        assert response.status_code == 200
        assert response.json()["files"][0]["category"] == "conversation"

        response = client.post("/api/privacy/export")
        assert response.status_code == 200
        export = response.json()
        assert export["download_url"].startswith("/api/privacy/exports/")

        response = client.get(export["download_url"])
        assert response.status_code == 200
        assert response.content == b"PK"

        response = client.post("/api/scheduler/tick")
        assert response.status_code == 200
        tick = response.json()
        assert tick["checked_events"] == 1
        assert tick["notified_events"] == 1
        assert fake_memory.refresh_calls == 1
        assert fake_notifier.sent[0]["title"] == "提醒"

        response = client.get("/openapi.json")
        assert response.status_code == 200
        openapi = response.json()
        assert "/api/chat" in openapi["paths"]
        assert "/api/scheduler/tick" in openapi["paths"]
        assert "/api/privacy/inventory" in openapi["paths"]
        assert "/api/privacy/export" in openapi["paths"]
        assert "ChatStreamDeltaEvent" in openapi["components"]["schemas"]
        assert "ChatStreamDoneEvent" in openapi["components"]["schemas"]

        with client.stream("POST", "/api/chat", json={"prompt": "测试流式输出"}) as response:
            assert response.status_code == 200
            lines = [line for line in response.iter_lines() if line.startswith("data: ")]
        events = [__import__("json").loads(line[6:]) for line in lines]
        assert [event["type"] for event in events] == ["delta", "delta", "done"]
        assert "".join(event.get("content", "") for event in events) == "第一段第二段"
    finally:
        os.environ.pop("WORKMATE_DISABLE_SCHEDULER", None)
