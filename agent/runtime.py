import json
import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Generator, List

from observability import finish_provider_turn, get_provider_trace_summary, start_provider_turn


class AgentRuntime:
    """One-turn Workmate Agent loop with an observable execution trace."""

    def __init__(self, llm_client: Any, memory_manager: Any, tool_executor: Any):
        self.llm_client = llm_client
        self.memory_manager = memory_manager
        self.tool_executor = tool_executor
        self.last_context_messages: List[Dict[str, str]] = []
        self.last_tool_calls: List[Dict[str, Any]] = []
        self.last_turn_trace: Dict[str, Any] = {}

    def run(self, prompt: str) -> str:
        trace = self._new_trace(prompt, streaming=False)
        response = ""
        try:
            messages = self._prepare_messages(prompt, trace)
            response = self._generate_response(messages, trace)
            self._write_memory(prompt, response, trace)
            self._update_supervision_state(trace)
            self._finish_trace(trace, response=response)
            return response
        except Exception as exc:
            self._finish_trace(trace, error=exc, response=response)
            raise

    def stream(self, prompt: str) -> Generator[str, None, None]:
        trace = self._new_trace(prompt, streaming=True)
        chunks: List[str] = []
        try:
            messages = self._prepare_messages(prompt, trace)
            stage = self._start_stage(trace, "generate_response")
            try:
                for chunk in self.llm_client.invoke_stream(messages=messages):
                    chunks.append(chunk)
                    yield chunk
                response = "".join(chunks).strip()
                self._finish_stage(stage, metadata={
                    "response_chars": len(response),
                    "response_preview": self._preview(response, 240),
                })
            except Exception as exc:
                self._finish_stage(stage, status="error", error=exc)
                raise

            self._write_memory(prompt, response, trace)
            self._update_supervision_state(trace)
            self._finish_trace(trace, response=response)
        except Exception as exc:
            self._finish_trace(trace, error=exc, response="".join(chunks).strip())
            raise

    def get_last_context(self) -> List[Dict[str, str]]:
        return deepcopy(self.last_context_messages)

    def get_last_tool_calls(self) -> List[Dict[str, Any]]:
        return deepcopy(self.last_tool_calls)

    def get_last_turn_trace(self) -> Dict[str, Any]:
        return self._public_trace(self.last_turn_trace)

    def _prepare_messages(self, prompt: str, trace: Dict[str, Any]) -> List[Dict[str, str]]:
        stage = self._start_stage(trace, "apply_reminder_control")
        try:
            self.memory_manager.apply_reminder_control_from_text(prompt)
            trace["reminder_control"] = deepcopy(getattr(self.memory_manager, "last_reminder_control", {}))
            self._finish_stage(stage, metadata={"changed": bool(trace["reminder_control"].get("applied_updates"))})
        except Exception as exc:
            self._finish_stage(stage, status="error", error=exc)
            raise

        stage = self._start_stage(trace, "plan_context")
        try:
            messages = self.memory_manager.build_context_messages(prompt)
            trace["message_count_before_tools"] = len(messages)
            trace["context_stats_before_tools"] = self._estimate_context(messages)
            trace["retrieval_plan"] = self._build_retrieval_plan(prompt)
            self._finish_stage(stage, metadata={
                "message_count": len(messages),
                "context_stats": trace["context_stats_before_tools"],
                "retrieval_plan": self._retrieval_stage_metadata(trace["retrieval_plan"]),
            })
        except Exception as exc:
            self._finish_stage(stage, status="error", error=exc)
            raise

        stage = self._start_stage(trace, "execute_tools")
        try:
            self.last_tool_calls = self.tool_executor.plan_and_execute(
                self.llm_client,
                messages,
                prompt,
            )
            observation = self.tool_executor.format_observations(self.last_tool_calls)
            if observation:
                messages = [*messages, {"role": "system", "content": observation}]
            self.last_context_messages = messages
            trace["tool_calls"] = deepcopy(self.last_tool_calls)
            trace["tool_plan"] = self._tool_plan_trace()
            trace["tool_observation"] = observation
            trace["message_count_after_tools"] = len(messages)
            trace["context_stats_after_tools"] = self._estimate_context(messages)
            self._finish_stage(stage, metadata={
                "tool_call_count": len(self.last_tool_calls),
                "tool_plan": trace["tool_plan"],
                "message_count": len(messages),
            })
            return messages
        except Exception as exc:
            self._finish_stage(stage, status="error", error=exc)
            raise

    def _generate_response(self, messages: List[Dict[str, str]], trace: Dict[str, Any]) -> str:
        stage = self._start_stage(trace, "generate_response")
        try:
            response = self.llm_client.invoke(messages=messages)
            self._finish_stage(stage, metadata={
                "response_chars": len(response or ""),
                "response_preview": self._preview(response, 240),
            })
            return response
        except Exception as exc:
            self._finish_stage(stage, status="error", error=exc)
            raise

    def _write_memory(self, prompt: str, response: str, trace: Dict[str, Any]) -> None:
        stage = self._start_stage(trace, "write_memory")
        try:
            memory_result = self.memory_manager.process_turn(prompt, response)
            trace["memory_result"] = deepcopy(memory_result)
            self._finish_stage(stage, metadata=self._memory_stage_metadata(memory_result))
        except Exception as exc:
            self._finish_stage(stage, status="error", error=exc)
            raise

    def _update_supervision_state(self, trace: Dict[str, Any]) -> None:
        stage = self._start_stage(trace, "update_supervision_state")
        refresher = getattr(self.memory_manager, "refresh_supervision_events", None)
        if not callable(refresher):
            self._finish_stage(stage, metadata={"available": False})
            return
        try:
            events = refresher()
            trace["supervision_update"] = {
                "event_count": len(events) if isinstance(events, list) else 0,
            }
            self._finish_stage(stage, metadata=trace["supervision_update"])
        except Exception as exc:
            self._finish_stage(stage, status="error", error=exc)
            raise

    def _new_trace(self, prompt: str, streaming: bool) -> Dict[str, Any]:
        now = self._now()
        turn_id = str(uuid.uuid4())
        trace = {
            "turn_id": turn_id,
            "started_at": now,
            "completed_at": "",
            "duration_ms": 0,
            "status": "running",
            "streaming": streaming,
            "prompt_preview": self._preview(prompt, 240),
            "stages": [],
            "reminder_control": {},
            "message_count_before_tools": 0,
            "message_count_after_tools": 0,
            "context_stats_before_tools": {},
            "context_stats_after_tools": {},
            "retrieval_plan": {},
            "tool_calls": [],
            "tool_plan": {},
            "tool_observation": "",
            "memory_result": {},
            "supervision_update": {},
            "observability": {},
            "provider_trace": {},
            "response_preview": "",
            "error": "",
            "_started_perf": time.perf_counter(),
            "_provider_token": start_provider_turn(turn_id),
        }
        self.last_turn_trace = trace
        return trace

    def _finish_trace(self, trace: Dict[str, Any], response: str = "", error: Exception = None) -> None:
        trace["completed_at"] = self._now()
        trace["duration_ms"] = self._elapsed_ms(trace.get("_started_perf", time.perf_counter()))
        trace["response_preview"] = self._preview(response, 360)
        if error:
            trace["status"] = "error"
            trace["error"] = str(error)
        else:
            trace["status"] = "success"
        trace["provider_trace"] = get_provider_trace_summary(trace.get("turn_id", ""))
        trace["observability"] = self._build_observability_summary(trace)
        finish_provider_turn(trace.get("_provider_token"))
        trace.pop("_started_perf", None)
        trace.pop("_provider_token", None)
        self.last_turn_trace = deepcopy(trace)

    def _start_stage(self, trace: Dict[str, Any], name: str) -> Dict[str, Any]:
        stage = {
            "name": name,
            "status": "running",
            "started_at": self._now(),
            "completed_at": "",
            "duration_ms": 0,
            "metadata": {},
            "error": "",
            "_started_perf": time.perf_counter(),
        }
        trace["stages"].append(stage)
        return stage

    def _finish_stage(
        self,
        stage: Dict[str, Any],
        status: str = "success",
        metadata: Dict[str, Any] = None,
        error: Exception = None,
    ) -> None:
        stage["completed_at"] = self._now()
        stage["duration_ms"] = self._elapsed_ms(stage.get("_started_perf", time.perf_counter()))
        stage["status"] = "error" if error else status
        stage["metadata"] = metadata or {}
        stage["error"] = str(error) if error else ""
        stage.pop("_started_perf", None)

    def _estimate_context(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        compressor = getattr(self.memory_manager, "context_compressor", None)
        if not compressor or not hasattr(compressor, "estimate_context"):
            return {"message_count": len(messages)}
        try:
            return compressor.estimate_context(messages)
        except Exception as exc:
            return {"message_count": len(messages), "error": str(exc)}

    def _memory_stage_metadata(self, memory_result: Any) -> Dict[str, Any]:
        if not isinstance(memory_result, dict):
            return {}
        stages = memory_result.get("stages", [])
        if not isinstance(stages, list):
            stages = []
        return {
            "stage_count": len(stages),
            "status": memory_result.get("status", ""),
            "errors": memory_result.get("errors", []),
        }

    def _tool_plan_trace(self) -> Dict[str, Any]:
        getter = getattr(self.tool_executor, "get_last_plan_trace", None)
        if not callable(getter):
            return {}
        try:
            return getter()
        except Exception as exc:
            return {"decision_source": "trace_error", "error": str(exc)}

    def _build_retrieval_plan(self, prompt: str) -> Dict[str, Any]:
        context_engine = getattr(self.memory_manager, "context_engine", None)
        if not context_engine or not hasattr(context_engine, "build_retrieval_plan"):
            return {}
        try:
            related = []
            searcher = getattr(self.memory_manager, "search_related_memories", None)
            if callable(searcher):
                related = searcher(prompt, limit=5)
            return context_engine.build_retrieval_plan(prompt, related)
        except Exception as exc:
            return {"error": str(exc)}

    def _retrieval_stage_metadata(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(plan, dict) or not plan:
            return {}
        return {
            "needs_retrieval": plan.get("needs_retrieval"),
            "mode": plan.get("mode", ""),
            "vector_status": plan.get("vector_status", ""),
            "hit_count": plan.get("hit_count", 0),
            "sufficiency": plan.get("sufficiency", ""),
            "error": plan.get("error", ""),
        }

    def _build_rag_explainability(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(plan, dict) or not plan:
            return {}

        top_results = [item for item in (plan.get("top_results", []) or []) if isinstance(item, dict)]
        score_keys = ["keyword", "recency", "salience", "type_weight", "vector", "status_penalty"]
        score_coverage = {}
        for key in score_keys:
            values = []
            for item in top_results:
                breakdown = item.get("score_breakdown", {})
                if not isinstance(breakdown, dict) or key not in breakdown:
                    continue
                values.append(self._float_value(breakdown.get(key), 0))
            if values:
                score_coverage[key] = {
                    "avg": round(sum(values) / len(values), 4),
                    "max": round(max(values), 4),
                }

        hit_count = int(self._float_value(plan.get("hit_count", 0), 0))
        top_score = self._float_value(plan.get("top_score", 0), 0)
        sufficiency = str(plan.get("sufficiency", "") or "")
        needs_retrieval = bool(plan.get("needs_retrieval"))
        if not needs_retrieval:
            injection_decision = "skipped_not_needed"
        elif hit_count <= 0:
            injection_decision = "needed_but_empty"
        elif sufficiency in {"enough", "strong"} or top_score >= 0.55:
            injection_decision = "inject_strong"
        elif top_score >= 0.25:
            injection_decision = "inject_weak"
        else:
            injection_decision = "inject_low_confidence"

        audit_notes = []
        if plan.get("error"):
            audit_notes.append("retrieval_error")
        if needs_retrieval and hit_count <= 0:
            audit_notes.append("retrieval_needed_without_hits")
        if top_results and not score_coverage:
            audit_notes.append("top_results_without_score_breakdown")

        return {
            "needs_retrieval": plan.get("needs_retrieval"),
            "mode": plan.get("mode", ""),
            "vector_status": plan.get("vector_status", ""),
            "preferred_types": plan.get("preferred_types", []),
            "query_terms": plan.get("query_terms", []),
            "hit_count": hit_count,
            "hit_types": plan.get("hit_types", []),
            "top_score": round(top_score, 4),
            "sufficiency": sufficiency,
            "reason": plan.get("reason", ""),
            "injection_decision": injection_decision,
            "score_coverage": score_coverage,
            "top_sources": [
                {
                    "source_type": item.get("source_type", ""),
                    "source_id": item.get("source_id", ""),
                    "score": item.get("score", 0),
                    "reason": item.get("reason", ""),
                    "score_breakdown": item.get("score_breakdown", {}),
                    "text_preview": self._preview(item.get("text", ""), 120),
                }
                for item in top_results[:5]
            ],
            "audit_notes": audit_notes,
        }

    def _build_tool_trace_summary(self, tool_calls: List[Dict[str, Any]], tool_plan: Dict[str, Any] = None) -> Dict[str, Any]:
        calls = [call for call in (tool_calls or []) if isinstance(call, dict)]
        tool_plan = tool_plan if isinstance(tool_plan, dict) else {}
        sequence = []
        side_effects = []
        audit_records = []
        for index, call in enumerate(calls[:8]):
            arguments = call.get("arguments", {}) if isinstance(call.get("arguments", {}), dict) else {}
            observation = call.get("observation", {}) if isinstance(call.get("observation", {}), dict) else {}
            input_schema = call.get("input_schema", {}) if isinstance(call.get("input_schema", {}), dict) else {}
            output_schema = call.get("output_schema", {}) if isinstance(call.get("output_schema", {}), dict) else {}
            call_side_effects = call.get("side_effects", []) or []
            if isinstance(call_side_effects, list):
                side_effects.extend(call_side_effects)
            audit_record = call.get("audit_record", {}) if isinstance(call.get("audit_record", {}), dict) else {}
            if audit_record:
                audit_records.append(audit_record)
            sequence.append({
                "index": index + 1,
                "call_id": call.get("call_id", ""),
                "tool": call.get("tool", ""),
                "status": call.get("status", ""),
                "mode": "write" if call.get("read_only") is False else "read",
                "read_only": call.get("read_only") is not False,
                "duration_ms": call.get("duration_ms", 0),
                "reason": self._preview(call.get("reason", ""), 180),
                "argument_keys": sorted(arguments.keys()),
                "arguments_preview": self._json_preview(arguments, 220),
                "observation_keys": sorted(observation.keys()),
                "observation_preview": self._json_preview(observation, 260),
                "input_schema_keys": self._schema_keys(input_schema),
                "output_schema_keys": self._schema_keys(output_schema),
                "side_effects": call_side_effects if isinstance(call_side_effects, list) else [],
                "audit_record": audit_record,
                "recoverable": bool(call.get("recoverable", False)),
                "recovery_hint": self._preview(call.get("recovery_hint", ""), 220),
                "error": self._preview(call.get("error", ""), 220),
            })
        return {
            "total": len(calls),
            "planner": {
                "decision_source": tool_plan.get("decision_source", ""),
                "available_tool_count": len(tool_plan.get("available_tools", []) or []),
                "max_calls": tool_plan.get("max_calls", 0),
                "parsed_count": tool_plan.get("parsed_count", 0),
                "selected_count": tool_plan.get("selected_count", 0),
                "executed_count": tool_plan.get("executed_count", 0),
                "truncated": tool_plan.get("truncated", False),
                "error": self._preview(tool_plan.get("error", ""), 220),
            },
            "sequence": sequence,
            "read_tools": [call.get("tool", "") for call in calls if call.get("read_only") is not False],
            "write_tools": [call.get("tool", "") for call in calls if call.get("read_only") is False],
            "error_tools": [call.get("tool", "") for call in calls if call.get("status") == "error"],
            "side_effects": side_effects,
            "audit_records": audit_records,
            "truncated": len(calls) > len(sequence),
        }

    def _build_provider_detail(self, provider_trace: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(provider_trace, dict):
            return {}
        calls = [call for call in (provider_trace.get("calls", []) or []) if isinstance(call, dict)]
        sequence = []
        by_provider: Dict[str, int] = {}
        for index, call in enumerate(calls[:12]):
            provider = str(call.get("provider", "") or call.get("kind", "") or "unknown")
            by_provider[provider] = by_provider.get(provider, 0) + 1
            metadata = call.get("metadata", {}) if isinstance(call.get("metadata", {}), dict) else {}
            usage = call.get("usage", {}) if isinstance(call.get("usage", {}), dict) else {}
            sequence.append({
                "index": index + 1,
                "call_id": call.get("call_id", ""),
                "kind": call.get("kind", ""),
                "provider": provider,
                "operation": call.get("operation", ""),
                "model": call.get("model", ""),
                "status": call.get("status", ""),
                "duration_ms": call.get("duration_ms", 0),
                "fallback": call.get("fallback", ""),
                "metadata_keys": sorted(metadata.keys()),
                "metadata_preview": self._json_preview(metadata, 220),
                "usage": usage,
                "error": self._preview(call.get("error", ""), 220),
            })

        slowest = max(sequence, key=lambda item: self._float_value(item.get("duration_ms", 0), 0), default={})
        fallback_timeline = [
            {
                "index": item.get("index"),
                "kind": item.get("kind", ""),
                "operation": item.get("operation", ""),
                "fallback": item.get("fallback", ""),
            }
            for item in sequence
            if item.get("fallback")
        ]
        error_summary = [
            {
                "index": item.get("index"),
                "kind": item.get("kind", ""),
                "operation": item.get("operation", ""),
                "error": item.get("error", ""),
            }
            for item in sequence
            if item.get("status") == "error" or item.get("error")
        ]
        return {
            "total": len(calls),
            "sequence": sequence,
            "by_provider": by_provider,
            "slowest_call": slowest,
            "fallback_timeline": fallback_timeline,
            "error_summary": error_summary,
            "truncated": len(calls) > len(sequence),
        }

    def _build_observability_summary(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        stages = [stage for stage in trace.get("stages", []) if isinstance(stage, dict)]
        completed_stages = [stage for stage in stages if stage.get("status") != "running"]
        slowest = max(completed_stages, key=lambda item: item.get("duration_ms", 0), default={})
        errors = [
            {
                "stage": stage.get("name", ""),
                "error": stage.get("error", ""),
            }
            for stage in completed_stages
            if stage.get("status") == "error" or stage.get("error")
        ]
        if trace.get("error"):
            errors.append({"stage": "turn", "error": trace.get("error", "")})

        tool_calls = [call for call in trace.get("tool_calls", []) if isinstance(call, dict)]
        failed_tools = [call.get("tool", "") for call in tool_calls if call.get("status") == "error"]
        write_tools = [call for call in tool_calls if call.get("read_only") is False]
        read_tools = [call for call in tool_calls if call.get("read_only") is not False]
        side_effects = []
        for call in tool_calls:
            side_effects.extend(call.get("side_effects", []) or [])
        tool_plan = trace.get("tool_plan") if isinstance(trace.get("tool_plan"), dict) else {}
        tool_trace_summary = self._build_tool_trace_summary(tool_calls, tool_plan)

        retrieval_plan = trace.get("retrieval_plan") if isinstance(trace.get("retrieval_plan"), dict) else {}
        rag_explainability = self._build_rag_explainability(retrieval_plan)
        provider_trace = trace.get("provider_trace") if isinstance(trace.get("provider_trace"), dict) else {}
        provider_detail = self._build_provider_detail(provider_trace)
        provider_kinds = provider_trace.get("by_kind", {}) if isinstance(provider_trace.get("by_kind"), dict) else {}
        memory_result = trace.get("memory_result") if isinstance(trace.get("memory_result"), dict) else {}
        memory_errors = memory_result.get("errors", [])
        if not isinstance(memory_errors, list):
            memory_errors = []

        stage_names = {stage.get("name") for stage in completed_stages}
        tool_planning_attempted = "execute_tools" in stage_names and bool(getattr(self.tool_executor, "registry", None))
        return {
            "turn_id": trace.get("turn_id", ""),
            "status": trace.get("status", ""),
            "duration_ms": trace.get("duration_ms", 0),
            "started_at": trace.get("started_at", ""),
            "completed_at": trace.get("completed_at", ""),
            "stage_count": len(completed_stages),
            "slowest_stage": {
                "name": slowest.get("name", ""),
                "duration_ms": slowest.get("duration_ms", 0),
                "status": slowest.get("status", ""),
            },
            "stage_timeline": [
                {
                    "name": stage.get("name", ""),
                    "status": stage.get("status", ""),
                    "duration_ms": stage.get("duration_ms", 0),
                }
                for stage in completed_stages
            ],
            "errors": errors,
            "model_calls": {
                "llm_generate": provider_kinds.get("llm", {}).get("total", 0) or (1 if "generate_response" in stage_names else 0),
                "tool_planner": 1 if tool_planning_attempted else 0,
                "vision": provider_kinds.get("vision", {}).get("total", 0),
                "tts": provider_kinds.get("tts", {}).get("total", 0),
                "embedding": provider_kinds.get("embedding", {}).get("total", 0),
            },
            "provider_trace": provider_trace,
            "provider_detail": provider_detail,
            "usage": provider_trace.get("usage", {}),
            "rag": {
                "needs_retrieval": retrieval_plan.get("needs_retrieval"),
                "mode": retrieval_plan.get("mode", ""),
                "vector_status": retrieval_plan.get("vector_status", ""),
                "hit_count": retrieval_plan.get("hit_count", 0),
                "top_score": retrieval_plan.get("top_score", 0),
                "sufficiency": retrieval_plan.get("sufficiency", ""),
                "top_sources": [
                    {
                        "source_type": item.get("source_type", ""),
                        "source_id": item.get("source_id", ""),
                        "score": item.get("score", 0),
                    }
                    for item in (retrieval_plan.get("top_results", []) or [])[:5]
                    if isinstance(item, dict)
                ],
            },
            "rag_explainability": rag_explainability,
            "tools": {
                "total": len(tool_calls),
                "success": sum(1 for call in tool_calls if call.get("status") == "success"),
                "error": sum(1 for call in tool_calls if call.get("status") == "error"),
                "read": len(read_tools),
                "write": len(write_tools),
                "side_effect_count": len(side_effects),
                "failed_tools": failed_tools,
            },
            "tool_trace": tool_trace_summary,
            "memory": {
                "status": memory_result.get("status", ""),
                "stage_count": len(memory_result.get("stages", []) or []),
                "error_count": len(memory_errors),
            },
            "supervision": trace.get("supervision_update", {}),
            "context": {
                "before_tools": trace.get("context_stats_before_tools", {}),
                "after_tools": trace.get("context_stats_after_tools", {}),
                "message_count_before_tools": trace.get("message_count_before_tools", 0),
                "message_count_after_tools": trace.get("message_count_after_tools", 0),
            },
        }

    def _elapsed_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _preview(self, text: Any, limit: int) -> str:
        value = str(text or "").replace("\n", " ").strip()
        return value[:limit]

    def _float_value(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _json_preview(self, value: Any, limit: int) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value or "")
        return self._preview(text, limit)

    def _schema_keys(self, schema: Dict[str, Any]) -> List[str]:
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if not isinstance(properties, dict):
            return []
        return sorted(properties.keys())

    def _public_trace(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        public = deepcopy(trace or {})
        public.pop("_started_perf", None)
        public.pop("_provider_token", None)
        for stage in public.get("stages", []):
            if isinstance(stage, dict):
                stage.pop("_started_perf", None)
        return public
