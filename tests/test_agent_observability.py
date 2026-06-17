from agent import AgentRuntime
from observability import record_provider_call


class FakeLLM:
    def invoke(self, messages):
        record_provider_call(
            "llm",
            provider="fake",
            operation="chat.completions.create",
            model="fake-model",
            metadata={
                "message_count": len(messages),
                "input_chars": sum(len(item.get("content", "")) for item in messages),
                "response_chars": len("收到，我会记录这次推进。"),
            },
        )
        return "收到，我会记录这次推进。"


class FakeContextCompressor:
    def estimate_context(self, messages):
        return {"message_count": len(messages), "approx_chars": sum(len(item.get("content", "")) for item in messages)}


class FakeContextEngine:
    def build_retrieval_plan(self, prompt, results):
        return {
            "needs_retrieval": True,
            "mode": "hybrid",
            "vector_status": "disabled",
            "hit_count": len(results),
            "top_score": 0.82,
            "sufficiency": "enough",
            "top_results": [
                {
                    "source_type": "memory_item",
                    "source_id": "mem-1",
                    "score": 0.82,
                    "reason": "matches task progress",
                    "score_breakdown": {
                        "keyword": 0.7,
                        "recency": 0.4,
                        "salience": 0.8,
                        "type_weight": 1.2,
                        "vector": 0,
                    },
                    "text": "用户正在推进 observability 摘要和 RAG 解释性。",
                }
            ],
        }


class FakeMemoryManager:
    context_compressor = FakeContextCompressor()
    context_engine = FakeContextEngine()
    last_reminder_control = {"applied_updates": []}

    def apply_reminder_control_from_text(self, prompt):
        return None

    def build_context_messages(self, prompt):
        return [
            {"role": "system", "content": "memory context"},
            {"role": "user", "content": prompt},
        ]

    def search_related_memories(self, prompt, limit=5):
        return [{"source_type": "memory_item", "source_id": "mem-1", "score": 0.82}][:limit]

    def process_turn(self, prompt, response):
        return {"status": "success", "stages": [{"name": "save_record"}], "errors": []}

    def refresh_supervision_events(self):
        return [{"id": "event-1"}]


class FakeToolExecutor:
    registry = object()

    def plan_and_execute(self, llm_client, messages, prompt):
        self.last_plan_trace = {
            "decision_source": "llm_plan",
            "available_tools": ["search_memory", "update_task_status"],
            "max_calls": 3,
            "parsed_count": 2,
            "selected_count": 2,
            "executed_count": 2,
            "truncated": False,
            "error": "",
        }
        return [
            {
                "tool": "search_memory",
                "status": "success",
                "read_only": True,
                "duration_ms": 3,
                "arguments": {"query": "observability"},
                "observation": {"results": [{"source_id": "mem-1"}]},
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {"results": {"type": "array"}}},
                "side_effects": [],
                "decision_source": "llm_plan",
                "planner_call_index": 1,
                "error": "",
                "reason": "check related memory",
            },
            {
                "tool": "update_task_status",
                "status": "success",
                "read_only": False,
                "duration_ms": 4,
                "arguments": {"task_id": "task-1", "status": "done"},
                "observation": {"status": "done"},
                "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}, "status": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {"status": {"type": "string"}}},
                "side_effects": ["updates tasks.json"],
                "decision_source": "llm_plan",
                "planner_call_index": 2,
                "audit_record": {
                    "audit_id": "audit-1",
                    "tool": "update_task_status",
                    "status": "success",
                    "side_effects": ["updates tasks.json"],
                },
                "error": "",
                "reason": "user reported progress",
            },
        ]

    def format_observations(self, calls):
        return "tool observation"

    def get_last_plan_trace(self):
        return self.last_plan_trace


def test_agent_runtime_builds_observability_summary():
    runtime = AgentRuntime(FakeLLM(), FakeMemoryManager(), FakeToolExecutor())

    response = runtime.run("我完成了 observability 摘要")
    trace = runtime.get_last_turn_trace()
    observability = trace["observability"]

    assert response
    assert observability["status"] == "success"
    assert observability["stage_count"] >= 5
    assert observability["slowest_stage"]["name"]
    assert observability["model_calls"]["llm_generate"] == 1
    assert observability["model_calls"]["tool_planner"] == 1
    assert observability["rag"]["hit_count"] == 1
    assert observability["rag"]["top_sources"][0]["source_id"] == "mem-1"
    assert observability["rag_explainability"]["injection_decision"] == "inject_strong"
    assert observability["rag_explainability"]["top_sources"][0]["score_breakdown"]["keyword"] == 0.7
    assert "observability" in observability["rag_explainability"]["top_sources"][0]["text_preview"]
    assert observability["tools"]["total"] == 2
    assert observability["tools"]["read"] == 1
    assert observability["tools"]["write"] == 1
    assert observability["tools"]["side_effect_count"] == 1
    assert trace["tool_plan"]["decision_source"] == "llm_plan"
    assert observability["tool_trace"]["planner"]["selected_count"] == 2
    assert observability["tool_trace"]["sequence"][0]["argument_keys"] == ["query"]
    assert observability["tool_trace"]["sequence"][1]["mode"] == "write"
    assert "updates tasks.json" in observability["tool_trace"]["side_effects"]
    assert observability["tool_trace"]["audit_records"][0]["tool"] == "update_task_status"
    assert observability["memory"]["status"] == "success"
    assert observability["supervision"]["event_count"] == 1
    assert observability["provider_trace"]["total"] == 1
    assert observability["provider_trace"]["by_kind"]["llm"]["total"] == 1
    assert observability["provider_detail"]["sequence"][0]["kind"] == "llm"
    assert "message_count" in observability["provider_detail"]["sequence"][0]["metadata_keys"]
    assert observability["usage"]["estimated_tokens"] > 0
