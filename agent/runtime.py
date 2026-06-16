import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Generator, List


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
            self._finish_stage(stage, metadata={
                "message_count": len(messages),
                "context_stats": trace["context_stats_before_tools"],
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
            trace["tool_observation"] = observation
            trace["message_count_after_tools"] = len(messages)
            trace["context_stats_after_tools"] = self._estimate_context(messages)
            self._finish_stage(stage, metadata={
                "tool_call_count": len(self.last_tool_calls),
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
        trace = {
            "turn_id": str(uuid.uuid4()),
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
            "tool_calls": [],
            "tool_observation": "",
            "memory_result": {},
            "supervision_update": {},
            "response_preview": "",
            "error": "",
            "_started_perf": time.perf_counter(),
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
        trace.pop("_started_perf", None)
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

    def _elapsed_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _preview(self, text: Any, limit: int) -> str:
        value = str(text or "").replace("\n", " ").strip()
        return value[:limit]

    def _public_trace(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        public = deepcopy(trace or {})
        public.pop("_started_perf", None)
        for stage in public.get("stages", []):
            if isinstance(stage, dict):
                stage.pop("_started_perf", None)
        return public
