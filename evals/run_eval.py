import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory import CommitmentManager, ContextPlanner, IntentManager, MemoryRetriever, SupervisionEventManager
from agent import AgentRuntime
from observability import record_provider_call
from tools import ToolExecutor, ToolRegistry, build_workmate_tool_registry


@dataclass
class EvalResult:
    case_id: str
    category: str
    passed: bool
    score: float
    expected: Dict[str, Any]
    actual: Dict[str, Any]
    error: str = ""


CATEGORY_NOTES = {
    "intent_accuracy": "Intent routing selects the right context and downstream agent path.",
    "memory_recall": "Hybrid memory retrieval returns the expected long-term memory source.",
    "task_tracking": "Internal state tools update task lifecycle state correctly.",
    "commitment_extraction": "Commitment state is opened, closed, and assigned deadlines.",
    "reminder_control": "Natural-language reminder preferences map to supervision policy updates.",
    "tool_calling": "Schema-driven tools execute with bounded calls, read/write flags, and traces.",
    "context_planning": "Context planner injects the right memory, task, and support blocks.",
    "supervision_lifecycle": "Proactive supervision events move through auditable lifecycle states.",
    "observability_trace": "Runtime trace summarizes stages, provider calls, RAG, tools, memory writeback, and supervision updates.",
    "api_schema_smoke": "FastAPI OpenAPI schema exposes the agent context, memory, chat, and observability contracts.",
}


COVERAGE_AREAS = [
    {
        "area": "Intent and context routing",
        "categories": ["intent_accuracy", "context_planning"],
        "resume_signal": "agent planning",
    },
    {
        "area": "Long-term memory RAG",
        "categories": ["memory_recall"],
        "resume_signal": "hybrid retrieval",
    },
    {
        "area": "Internal action layer",
        "categories": ["tool_calling", "task_tracking", "commitment_extraction"],
        "resume_signal": "tool use and state mutation",
    },
    {
        "area": "Proactive supervision loop",
        "categories": ["reminder_control", "supervision_lifecycle"],
        "resume_signal": "closed-loop supervision",
    },
    {
        "area": "Runtime observability",
        "categories": ["observability_trace", "api_schema_smoke"],
        "resume_signal": "traceability and evaluation",
    },
]


class EvaluationSuite:
    def __init__(self, cases: List[Dict[str, Any]]):
        self.cases = cases
        self.handlers: Dict[str, Callable[[Dict[str, Any]], EvalResult]] = {
            "intent_accuracy": self.eval_intent_accuracy,
            "memory_recall": self.eval_memory_recall,
            "task_tracking": self.eval_task_tracking,
            "commitment_extraction": self.eval_commitment_extraction,
            "reminder_control": self.eval_reminder_control,
            "tool_calling": self.eval_tool_calling,
            "context_planning": self.eval_context_planning,
            "supervision_lifecycle": self.eval_supervision_lifecycle,
            "observability_trace": self.eval_observability_trace,
            "api_schema_smoke": self.eval_api_schema_smoke,
        }

    def run(self) -> Dict[str, Any]:
        results = []
        for case in self.cases:
            handler = self.handlers.get(case.get("category", ""))
            if not handler:
                results.append(self._result(case, False, {}, f"unknown category: {case.get('category')}"))
                continue
            try:
                results.append(handler(case))
            except Exception as exc:
                results.append(self._result(case, False, {}, str(exc)))
        return self._report(results)

    def eval_intent_accuracy(self, case: Dict[str, Any]) -> EvalResult:
        manager = IntentManager()
        actual = manager.classify(case.get("input", ""))
        expected = case.get("expected", {})
        passed = actual.get("intent") == expected.get("intent")
        return self._result(case, passed, actual)

    def eval_memory_recall(self, case: Dict[str, Any]) -> EvalResult:
        retriever = MemoryRetriever(vector_enabled=False)
        actual_results = retriever.search(
            case.get("input", ""),
            case.get("items", []),
            limit=3,
            filters=case.get("filters", {}),
        )
        expected = case.get("expected", {})
        expected_source = expected.get("top_source_id")
        hit_ids = [item.get("source_id", "") for item in actual_results]
        actual = {
            "top_source_id": actual_results[0].get("source_id", "") if actual_results else "",
            "top_source_type": actual_results[0].get("source_type", "") if actual_results else "",
            "hit_count": len(actual_results),
            "top_score": actual_results[0].get("score", 0) if actual_results else 0,
            "has_task_relevance_score": "task_relevance" in ((actual_results[0].get("score_breakdown", {}) if actual_results else {})),
            "hit_rate": 1.0 if expected_source and expected_source in hit_ids else 0.0,
            "has_source_attribution": bool((actual_results[0].get("source_attribution") if actual_results else {})),
            "filter_types": case.get("filters", {}).get("types", []),
        }
        passed = actual.get("top_source_id") == expected_source
        if "has_source_attribution" in expected:
            passed = passed and actual["has_source_attribution"] == expected["has_source_attribution"]
        if "has_task_relevance_score" in expected:
            passed = passed and actual["has_task_relevance_score"] == expected["has_task_relevance_score"]
        return self._result(case, passed, actual)

    def eval_task_tracking(self, case: Dict[str, Any]) -> EvalResult:
        memory = FakeMemoryManager(task=case.get("task", {}))
        registry = build_workmate_tool_registry(memory)
        executor = ToolExecutor(registry)
        result = executor.execute({
            "tool": "update_task_status",
            "arguments": {
                "task_id": case.get("task", {}).get("id", ""),
                "status": case.get("action", {}).get("status", ""),
                "reason": case.get("action", {}).get("reason", "eval"),
            },
            "reason": "eval task tracking",
        })
        actual = {
            "tool_status": result.get("status"),
            "status": result.get("observation", {}).get("status"),
            "read_only": result.get("read_only"),
        }
        expected = case.get("expected", {})
        passed = actual.get("tool_status") == "success" and actual.get("status") == expected.get("status")
        return self._result(case, passed, actual)

    def eval_commitment_extraction(self, case: Dict[str, Any]) -> EvalResult:
        with TemporaryDirectory() as tmpdir:
            manager = CommitmentManager(commitments_path=f"{tmpdir}/commitments.json")
            if case.get("seed_commitments"):
                manager.save_commitments(case.get("seed_commitments", []))
            commitments = manager.update(
                case.get("extracted", {}),
                case.get("input", ""),
                "",
                task_state={"active_task": "eval"},
            )
            expected = case.get("expected", {})
            open_items = [item for item in commitments if item.get("status") == "open"]
            closed_items = [item for item in commitments if item.get("status") == "closed"]
            actual = {
                "open": [item.get("commitment", "") for item in open_items],
                "closed_ids": [item.get("id", "") for item in closed_items],
                "has_deadline": any(item.get("deadline") for item in open_items),
            }
            passed = True
            if expected.get("open_contains"):
                passed = passed and any(expected["open_contains"] in text for text in actual["open"])
            if expected.get("closed_id"):
                passed = passed and expected["closed_id"] in actual["closed_ids"]
            if "has_deadline" in expected:
                passed = passed and actual["has_deadline"] == expected["has_deadline"]
            return self._result(case, passed, actual)

    def eval_reminder_control(self, case: Dict[str, Any]) -> EvalResult:
        with TemporaryDirectory() as tmpdir:
            manager = SupervisionEventManager(
                events_path=f"{tmpdir}/events.json",
                preferences_path=f"{tmpdir}/preferences.json",
            )
            actual = manager.apply_natural_language_control(case.get("input", ""))
            preferences = actual.get("preferences", {})
            flattened = {"applied": actual.get("applied", False), **preferences}
            expected = case.get("expected", {})
            passed = all(flattened.get(key) == value for key, value in expected.items())
            return self._result(case, passed, flattened)

    def eval_tool_calling(self, case: Dict[str, Any]) -> EvalResult:
        if case.get("plan"):
            registry = ToolRegistry()
            registry.register(
                "noop",
                "no operation",
                {"type": "object", "properties": {}, "required": []},
                lambda args: {"ok": True},
            )
            executor = ToolExecutor(registry, max_calls=int(case.get("max_calls", 3)))
            llm = PlannedToolLLM(case.get("plan", []))
            results = executor.plan_and_execute(llm, [], "eval")
            actual = {"call_count": len(results), "statuses": [item.get("status") for item in results]}
            passed = actual["call_count"] == case.get("expected", {}).get("call_count")
            return self._result(case, passed, actual)

        memory = FakeMemoryManager()
        registry = build_workmate_tool_registry(memory)
        executor = ToolExecutor(registry)
        result = executor.execute({
            "tool": case.get("tool", ""),
            "arguments": case.get("arguments", {}),
            "reason": "eval direct tool call",
        })
        actual = {
            "status": result.get("status"),
            "read_only": result.get("read_only"),
            "duration_ms": result.get("duration_ms", 0),
            "has_output_schema": bool(result.get("output_schema")),
            "has_audit_record": bool(result.get("audit_record")),
        }
        expected = case.get("expected", {})
        passed = all(actual.get(key) == value for key, value in expected.items())
        return self._result(case, passed, actual)

    def eval_context_planning(self, case: Dict[str, Any]) -> EvalResult:
        planner = ContextPlanner()
        keys = planner.required_context_keys(case.get("input", ""))
        expected = case.get("expected", {})
        missing = [key for key in expected.get("includes", []) if key not in keys]
        actual = {"keys": keys, "missing": missing}
        return self._result(case, not missing, actual)

    def eval_supervision_lifecycle(self, case: Dict[str, Any]) -> EvalResult:
        with TemporaryDirectory() as tmpdir:
            manager = SupervisionEventManager(
                events_path=f"{tmpdir}/events.json",
                preferences_path=f"{tmpdir}/preferences.json",
            )
            scenario = case.get("scenario")
            if scenario == "focus_expired_acknowledge":
                active = manager.detect_events(
                    focus_state={"current": {
                        "id": "focus-1",
                        "status": "expired",
                        "goal": "写 eval",
                        "duration_minutes": 25,
                        "elapsed_minutes": 40,
                        "expected_end_at": "2026-06-16T10:25:00",
                    }},
                    commitments=[],
                    task_view={"current": {}},
                )
                event = manager.acknowledge(active[0]["id"])
            elif scenario == "commitment_overdue_resolve":
                yesterday = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
                active = manager.detect_events(
                    focus_state={"current": {}},
                    commitments=[{
                        "id": "commit-1",
                        "commitment": "补 eval 报告",
                        "deadline": yesterday,
                        "status": "open",
                    }],
                    task_view={"current": {}},
                )
                event = manager.resolve(active[0]["id"])
            elif scenario == "task_stale_snooze":
                old = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
                active = manager.detect_events(
                    focus_state={"current": {}},
                    commitments=[],
                    task_view={"current": {
                        "id": "task-1",
                        "title": "补 eval",
                        "status": "active",
                        "updated_at": old,
                    }},
                )
                event = manager.snooze(active[0]["id"], minutes=30)
            elif scenario == "task_stale_dismiss":
                old = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
                active = manager.detect_events(
                    focus_state={"current": {}},
                    commitments=[],
                    task_view={"current": {
                        "id": "task-dismiss",
                        "title": "关闭旧提醒",
                        "status": "active",
                        "updated_at": old,
                    }},
                )
                event = manager.dismiss(active[0]["id"])
            else:
                raise ValueError(f"unknown supervision scenario: {scenario}")

            state = manager.build_state()
            actual = {
                "detected_type": active[0].get("type", ""),
                "final_status": event.get("status", ""),
                "has_transition_history": bool(event.get("transition_history")),
                "last_transition_reason": event.get("last_transition_reason", ""),
                "state_machine_final_count": (
                    state.get("state_machine", {})
                    .get("states", {})
                    .get(event.get("status", ""), 0)
                ),
            }
            expected = case.get("expected", {})
            passed = all(actual.get(key) == value for key, value in expected.items())
            return self._result(case, passed, actual)

    def eval_observability_trace(self, case: Dict[str, Any]) -> EvalResult:
        runtime = AgentRuntime(
            EvalLLM(),
            EvalRuntimeMemoryManager(),
            EvalRuntimeToolExecutor(fail_tool=bool(case.get("fail_tool"))),
        )
        runtime.run(case.get("input", "eval observability"))
        trace = runtime.get_last_turn_trace()
        observability = trace.get("observability", {})
        tools = observability.get("tools", {})
        tool_trace = observability.get("tool_trace", {})
        tool_planner = tool_trace.get("planner", {}) if isinstance(tool_trace, dict) else {}
        tool_sequence = tool_trace.get("sequence", []) if isinstance(tool_trace, dict) else []
        first_tool_call = tool_sequence[0] if tool_sequence else {}
        rag = observability.get("rag", {})
        rag_explainability = observability.get("rag_explainability", {})
        rag_top_sources = rag_explainability.get("top_sources", []) if isinstance(rag_explainability, dict) else []
        first_rag_source = rag_top_sources[0] if rag_top_sources else {}
        provider_detail = observability.get("provider_detail", {})
        provider_sequence = provider_detail.get("sequence", []) if isinstance(provider_detail, dict) else []
        first_provider_call = provider_sequence[0] if provider_sequence else {}
        usage = observability.get("usage", {})
        actual = {
            "status": observability.get("status"),
            "has_timeline": bool(observability.get("stage_timeline")),
            "has_slowest_stage": bool((observability.get("slowest_stage") or {}).get("name")),
            "llm_generate": (observability.get("model_calls") or {}).get("llm_generate"),
            "provider_total": (observability.get("provider_trace") or {}).get("total"),
            "provider_detail_has_sequence": bool(provider_sequence),
            "provider_detail_has_metadata_keys": bool(first_provider_call.get("metadata_keys")),
            "estimated_tokens_positive": int(usage.get("estimated_tokens", 0) or 0) > 0,
            "tool_total": tools.get("total"),
            "tool_errors": tools.get("error"),
            "tool_trace_has_sequence": bool(tool_sequence),
            "tool_trace_has_io_summary": bool(first_tool_call.get("argument_keys")) and bool(first_tool_call.get("observation_keys")),
            "tool_planner_source": tool_planner.get("decision_source", ""),
            "tool_planner_selected": tool_planner.get("selected_count"),
            "rag_hit_count": rag.get("hit_count"),
            "rag_explainability": bool(rag_explainability),
            "rag_score_breakdown": bool(first_rag_source.get("score_breakdown")),
            "rag_injection_decision": rag_explainability.get("injection_decision", "") if isinstance(rag_explainability, dict) else "",
            "memory_status": (observability.get("memory") or {}).get("status"),
            "supervision_event_count": (observability.get("supervision") or {}).get("event_count"),
        }
        expected = case.get("expected", {})
        passed = all(actual.get(key) == value for key, value in expected.items())
        return self._result(case, passed, actual)

    def eval_api_schema_smoke(self, case: Dict[str, Any]) -> EvalResult:
        previous_scheduler = os.environ.get("WORKMATE_DISABLE_SCHEDULER")
        os.environ["WORKMATE_DISABLE_SCHEDULER"] = "1"
        try:
            web = importlib.import_module("src.web")
            schema = web.app.openapi()
        finally:
            if previous_scheduler is None:
                os.environ.pop("WORKMATE_DISABLE_SCHEDULER", None)
            else:
                os.environ["WORKMATE_DISABLE_SCHEDULER"] = previous_scheduler

        paths = schema.get("paths", {})
        components = schema.get("components", {}).get("schemas", {})
        expected = case.get("expected", {})
        missing_paths = [path for path in expected.get("paths", []) if path not in paths]
        missing_schemas = [name for name in expected.get("schemas", []) if name not in components]
        missing_properties = {}
        for schema_name, properties in (expected.get("properties") or {}).items():
            schema_properties = (components.get(schema_name, {}) or {}).get("properties", {})
            missing = [prop for prop in properties if prop not in schema_properties]
            if missing:
                missing_properties[schema_name] = missing

        actual = {
            "path_count": len(paths),
            "schema_count": len(components),
            "missing_paths": missing_paths,
            "missing_schemas": missing_schemas,
            "missing_properties": missing_properties,
        }
        passed = not missing_paths and not missing_schemas and not missing_properties
        return self._result(case, passed, actual)

    def _result(self, case: Dict[str, Any], passed: bool, actual: Dict[str, Any], error: str = "") -> EvalResult:
        return EvalResult(
            case_id=case.get("id", ""),
            category=case.get("category", ""),
            passed=passed,
            score=1.0 if passed else 0.0,
            expected=case.get("expected", {}),
            actual=actual,
            error=error,
        )

    def _report(self, results: List[EvalResult]) -> Dict[str, Any]:
        by_category: Dict[str, List[EvalResult]] = {}
        for result in results:
            by_category.setdefault(result.category, []).append(result)

        metrics = {}
        for category, items in by_category.items():
            passed = sum(1 for item in items if item.passed)
            metrics[category] = {
                "passed": passed,
                "total": len(items),
                "score": round(passed / max(len(items), 1), 4),
            }

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "mode": "rule_fake",
            "summary": {
                "passed": sum(1 for item in results if item.passed),
                "total": len(results),
                "score": round(sum(1 for item in results if item.passed) / max(len(results), 1), 4),
            },
            "metrics": metrics,
            "category_notes": {
                category: CATEGORY_NOTES.get(category, "")
                for category in sorted(metrics)
            },
            "coverage": self._coverage_snapshot(metrics),
            "results": [item.__dict__ for item in results],
        }

    def _coverage_snapshot(self, metrics: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        snapshot = []
        for item in COVERAGE_AREAS:
            categories = item["categories"]
            covered = [category for category in categories if category in metrics]
            passed = sum(metrics.get(category, {}).get("passed", 0) for category in categories)
            total = sum(metrics.get(category, {}).get("total", 0) for category in categories)
            snapshot.append({
                "area": item["area"],
                "categories": categories,
                "resume_signal": item["resume_signal"],
                "status": "covered" if len(covered) == len(categories) else "partial" if covered else "missing",
                "passed": passed,
                "total": total,
                "score": round(passed / max(total, 1), 4) if total else 0,
            })
        return snapshot


class PlannedToolLLM:
    def __init__(self, plan: List[Dict[str, Any]]):
        self.plan = plan

    def invoke_raw(self, messages):
        return json.dumps({"tool_calls": self.plan}, ensure_ascii=False)


class EvalLLM:
    def invoke(self, messages):
        record_provider_call(
            "llm",
            provider="fake",
            operation="chat.completions.create",
            model="fake-eval-model",
            metadata={
                "message_count": len(messages),
                "input_chars": sum(len(item.get("content", "")) for item in messages),
                "response_chars": len("eval response"),
            },
        )
        return "eval response"


class EvalRuntimeContextCompressor:
    def estimate_context(self, messages):
        return {
            "message_count": len(messages),
            "approx_chars": sum(len(item.get("content", "")) for item in messages),
        }


class EvalRuntimeContextEngine:
    def build_retrieval_plan(self, query, results):
        return {
            "needs_retrieval": True,
            "mode": "hybrid",
            "vector_status": "disabled",
            "hit_count": len(results),
            "top_score": 0.8 if results else 0,
            "sufficiency": "enough" if results else "low",
            "top_results": [
                {
                    "source_type": "memory_item",
                    "source_id": "eval-memory",
                    "score": 0.8,
                    "reason": "eval retrieval hit",
                    "score_breakdown": {
                        "keyword": 0.75,
                        "recency": 0.2,
                        "salience": 0.7,
                        "type_weight": 1.2,
                        "vector": 0,
                    },
                    "text": "eval memory explains observability retrieval",
                }
            ],
        }


class EvalRuntimeMemoryManager:
    context_compressor = EvalRuntimeContextCompressor()
    context_engine = EvalRuntimeContextEngine()
    last_reminder_control = {"applied_updates": []}

    def apply_reminder_control_from_text(self, prompt):
        return None

    def build_context_messages(self, prompt):
        return [
            {"role": "system", "content": "eval memory context"},
            {"role": "user", "content": prompt},
        ]

    def search_related_memories(self, prompt, limit=5):
        return [{"source_type": "memory_item", "source_id": "eval-memory", "score": 0.8}][:limit]

    def process_turn(self, prompt, response):
        return {"status": "success", "stages": [{"name": "save_record"}], "errors": []}

    def refresh_supervision_events(self):
        return [{"id": "eval-event"}]


class EvalRuntimeToolExecutor:
    registry = object()

    def __init__(self, fail_tool: bool = False):
        self.fail_tool = fail_tool
        self.last_plan_trace = {}

    def plan_and_execute(self, llm_client, messages, prompt):
        status = "error" if self.fail_tool else "success"
        self.last_plan_trace = {
            "decision_source": "llm_plan",
            "available_tools": ["search_memory"],
            "max_calls": 3,
            "parsed_count": 1,
            "selected_count": 1,
            "executed_count": 1,
            "truncated": False,
            "error": "",
        }
        return [
            {
                "tool": "search_memory",
                "status": status,
                "read_only": True,
                "duration_ms": 1,
                "arguments": {"query": "eval observability"},
                "observation": {"results": [{"source_id": "eval-memory"}]},
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {"results": {"type": "array"}}},
                "side_effects": [],
                "decision_source": "llm_plan",
                "planner_call_index": 1,
                "error": "eval tool failed" if self.fail_tool else "",
                "reason": "eval observability",
            }
        ]

    def format_observations(self, results):
        return "eval tool observation"

    def get_last_plan_trace(self):
        return self.last_plan_trace


class FakeTaskManager:
    def __init__(self, task: Dict[str, Any] = None):
        now = datetime.now().isoformat(timespec="seconds")
        task = task or {"id": "task-1", "title": "eval task", "status": "active"}
        self.tasks = [{
            "progress": [],
            "next_actions": [],
            "created_at": now,
            "updated_at": now,
            **task,
        }]
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
    def __init__(self, task_id: str = "task-1"):
        self.state = {"task_id": task_id, "active_task": "eval task", "status": "active"}

    def load_state(self):
        return dict(self.state)

    def save_state(self, state):
        self.state = state


class FakeTaskState:
    def __init__(self, task: Dict[str, Any] = None):
        self.task_manager = FakeTaskManager(task=task)
        self.task_state_manager = FakeTaskStateManager(task_id=(task or {}).get("id", "task-1"))


class FakeMemoryManager:
    def __init__(self, task: Dict[str, Any] = None):
        self.task_state = FakeTaskState(task=task)
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
        return [{"id": "commit-1", "commitment": "补 eval", "status": "open"}]

    def search_related_memories(self, query, limit=5):
        return [{"source_type": "memory_item", "source_id": "memory-1", "text": query, "score": 0.9}][:limit]

    def start_focus_session(self, goal, duration_minutes=45):
        return {
            "goal": goal,
            "duration_minutes": duration_minutes,
            "started_at": "2026-06-16T10:00:00",
            "expected_end_at": "2026-06-16T10:45:00",
        }

    def complete_focus_session(self, outcome=""):
        return {"goal": "eval", "elapsed_minutes": 25, "outcome": outcome}

    def abandon_focus_session(self, outcome=""):
        return {"goal": "eval", "elapsed_minutes": 5, "outcome": outcome}

    def get_supervision_preferences(self):
        return dict(self.supervision_preferences)

    def update_supervision_preferences(self, updates):
        self.supervision_preferences.update(updates)
        return dict(self.supervision_preferences)


def load_cases(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("eval cases must be a JSON list")
    return data


def write_reports(report: Dict[str, Any], report_dir: Path) -> Dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = report_dir / f"eval-{stamp}.json"
    md_path = report_dir / f"eval-{stamp}.md"
    latest_json = report_dir / "latest.json"
    latest_md = report_dir / "latest.md"

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    json_path.write_text(payload, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")

    markdown = format_markdown(report)
    md_path.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "latest_json": latest_json, "latest_markdown": latest_md}


def format_markdown(report: Dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Workmate Agent Evaluation Report",
        "",
        f"- generated_at: {report.get('generated_at', '')}",
        f"- mode: {report.get('mode', '')}",
        f"- score: {summary.get('passed', 0)}/{summary.get('total', 0)} ({summary.get('score', 0)})",
        "",
        "## Metrics",
        "",
        "| category | passed | total | score |",
        "| --- | ---: | ---: | ---: |",
    ]
    for category, metric in sorted((report.get("metrics") or {}).items()):
        lines.append(f"| {category} | {metric.get('passed', 0)} | {metric.get('total', 0)} | {metric.get('score', 0)} |")

    lines.extend(["", "## Coverage Map", ""])
    lines.extend([
        "| area | status | passed | total | resume signal |",
        "| --- | --- | ---: | ---: | --- |",
    ])
    for item in report.get("coverage", []) or []:
        lines.append(
            f"| {item.get('area', '')} | {item.get('status', '')} | "
            f"{item.get('passed', 0)} | {item.get('total', 0)} | {item.get('resume_signal', '')} |"
        )

    category_notes = report.get("category_notes") or {}
    if category_notes:
        lines.extend(["", "## Category Notes", ""])
        for category in sorted(category_notes):
            metric = (report.get("metrics") or {}).get(category, {})
            lines.append(
                f"- `{category}`: {metric.get('passed', 0)}/{metric.get('total', 0)}. "
                f"{category_notes.get(category, '')}"
            )

    memory_cases = [
        item for item in report.get("results", [])
        if item.get("category") == "memory_recall"
    ]
    if memory_cases:
        lines.extend(["", "## Memory Retrieval Cases", ""])
        lines.extend([
            "| case | passed | top source | type | hit rate | citation | task score | filters |",
            "| --- | --- | --- | --- | ---: | --- | --- | --- |",
        ])
        for item in memory_cases:
            actual = item.get("actual") or {}
            filters = actual.get("filter_types") or []
            lines.append(
                f"| `{item.get('case_id', '')}` | {item.get('passed')} | "
                f"{actual.get('top_source_id', '')} | {actual.get('top_source_type', '')} | "
                f"{actual.get('hit_rate', 0)} | {actual.get('has_source_attribution')} | "
                f"{actual.get('has_task_relevance_score')} | "
                f"{', '.join(filters) if isinstance(filters, list) else filters} |"
            )

    observability_cases = [
        item for item in report.get("results", [])
        if item.get("category") == "observability_trace"
    ]
    if observability_cases:
        lines.extend(["", "## Observability Trace Cases", ""])
        lines.extend([
            "| case | passed | status | timeline | provider calls | provider detail | estimated tokens | rag hits | rag explain | tool trace | planner | tool errors | memory | supervision events |",
            "| --- | --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- | ---: | --- | ---: |",
        ])
        for item in observability_cases:
            actual = item.get("actual") or {}
            lines.append(
                f"| `{item.get('case_id', '')}` | {item.get('passed')} | {actual.get('status', '')} | "
                f"{actual.get('has_timeline')} | {actual.get('provider_total', 0)} | {actual.get('provider_detail_has_sequence')} | {actual.get('estimated_tokens_positive')} | {actual.get('rag_hit_count', 0)} | "
                f"{actual.get('rag_explainability')} | {actual.get('tool_trace_has_sequence')} | {actual.get('tool_planner_source', '')}:{actual.get('tool_planner_selected', 0)} | {actual.get('tool_errors', 0)} | {actual.get('memory_status', '')} | "
                f"{actual.get('supervision_event_count', '')} |"
            )

    api_schema_cases = [
        item for item in report.get("results", [])
        if item.get("category") == "api_schema_smoke"
    ]
    if api_schema_cases:
        lines.extend(["", "## API Schema Smoke Cases", ""])
        lines.extend([
            "| case | passed | paths | schemas | missing paths | missing schemas | missing properties |",
            "| --- | --- | ---: | ---: | --- | --- | --- |",
        ])
        for item in api_schema_cases:
            actual = item.get("actual") or {}
            lines.append(
                f"| `{item.get('case_id', '')}` | {item.get('passed')} | "
                f"{actual.get('path_count', 0)} | {actual.get('schema_count', 0)} | "
                f"{', '.join(actual.get('missing_paths') or []) or 'none'} | "
                f"{', '.join(actual.get('missing_schemas') or []) or 'none'} | "
                f"{json.dumps(actual.get('missing_properties') or {}, ensure_ascii=False)} |"
            )

    lines.extend(["", "## Failed Cases", ""])
    failed = [item for item in report.get("results", []) if not item.get("passed")]
    if not failed:
        lines.append("No failed cases.")
    else:
        for item in failed:
            lines.append(f"- `{item.get('case_id')}` ({item.get('category')}): {item.get('error') or item.get('actual')}")

    lines.extend(["", "## Report Use", ""])
    lines.append("Use this report as a lightweight regression artifact for the agent loop, memory RAG, tool layer, proactive supervision, provider trace, and observability trace.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Workmate Agent evaluation suite.")
    parser.add_argument("--cases", default=str(PROJECT_ROOT / "evals" / "cases.json"))
    parser.add_argument("--report-dir", default=str(PROJECT_ROOT / "evals" / "reports"))
    parser.add_argument("--min-score", type=float, default=1.0)
    args = parser.parse_args()

    report = EvaluationSuite(load_cases(Path(args.cases))).run()
    paths = write_reports(report, Path(args.report_dir))
    summary = report["summary"]
    print(f"Workmate eval: {summary['passed']}/{summary['total']} score={summary['score']}")
    print(f"JSON report: {paths['json']}")
    print(f"Markdown report: {paths['markdown']}")
    return 0 if float(summary["score"]) >= args.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
