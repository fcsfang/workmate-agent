import importlib
import json
import os
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen


def test_web_api_context_and_memory_smoke(monkeypatch):
    monkeypatch.setenv("WORKMATE_DISABLE_SCHEDULER", "1")
    web = importlib.import_module("src.web")

    class FakeAgent:
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

        class Compressor:
            def estimate_context(self, messages):
                return {"message_count": len(messages)}

        context_compressor = Compressor()

        def load_records(self):
            return []

        def refresh_supervision_events(self):
            return []

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
            return {"active": []}

        def get_focus_session_state(self):
            return {}

        def get_support_knowledge_state(self, current_prompt=""):
            return {}

    app = web.WorkmateWebApp(memory_manager=FakeMemory(), notifier=object(), start_background=False)
    app.agent = FakeAgent()
    monkeypatch.setattr(web, "APP", app)

    server = ThreadingHTTPServer(("127.0.0.1", 0), web.WorkmateRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base_url}/api/context", timeout=5) as response:
            context = json.loads(response.read().decode("utf-8"))
        assert context["message_count"] == 1
        assert context["tool_schemas"][0]["name"] == "noop"
        assert context["turn_trace"]["turn_id"] == "turn-1"

        request = Request(f"{base_url}/api/memory", method="GET")
        with urlopen(request, timeout=5) as response:
            memory = json.loads(response.read().decode("utf-8"))
        assert memory["count"] == 0
        assert memory["tool_schemas"][0]["read_only"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        os.environ.pop("WORKMATE_DISABLE_SCHEDULER", None)
