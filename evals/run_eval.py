import argparse
import json
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
        actual_results = retriever.search(case.get("input", ""), case.get("items", []), limit=3)
        actual = {
            "top_source_id": actual_results[0].get("source_id", "") if actual_results else "",
            "top_source_type": actual_results[0].get("source_type", "") if actual_results else "",
            "hit_count": len(actual_results),
            "top_score": actual_results[0].get("score", 0) if actual_results else 0,
        }
        expected = case.get("expected", {})
        passed = actual.get("top_source_id") == expected.get("top_source_id")
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
            else:
                raise ValueError(f"unknown supervision scenario: {scenario}")

            actual = {"detected_type": active[0].get("type", ""), "final_status": event.get("status", "")}
            expected = case.get("expected", {})
            passed = all(actual.get(key) == value for key, value in expected.items())
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
            "results": [item.__dict__ for item in results],
        }


class PlannedToolLLM:
    def __init__(self, plan: List[Dict[str, Any]]):
        self.plan = plan

    def invoke_raw(self, messages):
        return json.dumps({"tool_calls": self.plan}, ensure_ascii=False)


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
    lines.extend(["", "## Failed Cases", ""])
    failed = [item for item in report.get("results", []) if not item.get("passed")]
    if not failed:
        lines.append("No failed cases.")
    else:
        for item in failed:
            lines.append(f"- `{item.get('case_id')}` ({item.get('category')}): {item.get('error') or item.get('actual')}")
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
