import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from .registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, max_calls: int = 3):
        self.registry = registry
        self.max_calls = max_calls

    def plan_and_execute(
        self,
        llm_client: Any,
        messages: List[Dict[str, str]],
        user_input: str,
    ) -> List[Dict[str, Any]]:
        if not self.registry.names():
            return []

        try:
            raw_plan = self._request_plan(llm_client, messages, user_input)
        except Exception as exc:
            return [self._planning_error(exc)]
        calls = self._parse_tool_calls(raw_plan)
        results = []
        for call in calls[:self.max_calls]:
            results.append(self.execute(call))
        return results

    def execute(self, call: Dict[str, Any]) -> Dict[str, Any]:
        started_perf = time.perf_counter()
        started_at = datetime.now().isoformat(timespec="seconds")
        name = str(call.get("tool", "")).strip()
        arguments = call.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        result = {
            "call_id": str(uuid.uuid4()),
            "tool": name,
            "arguments": arguments,
            "reason": str(call.get("reason", ""))[:180],
            "started_at": started_at,
            "status": "error",
            "observation": {},
            "error": "",
            "duration_ms": 0,
            "read_only": True,
            "side_effects": [],
            "input_schema": {},
            "output_schema": {},
        }
        try:
            tool = self.registry.get(name)
            result["read_only"] = tool.read_only
            result["side_effects"] = tool.side_effects
            result["input_schema"] = tool.schema
            result["output_schema"] = tool.output_schema
            observation = tool.handler(arguments)
            if not isinstance(observation, dict):
                raise TypeError("tool handler must return dict")
            result["status"] = "success"
            result["observation"] = observation
        except Exception as exc:
            result["error"] = str(exc)
        result["completed_at"] = datetime.now().isoformat(timespec="seconds")
        result["duration_ms"] = int((time.perf_counter() - started_perf) * 1000)
        return result

    def format_observations(self, results: List[Dict[str, Any]]) -> str:
        if not results:
            return ""
        payload = [
            {
                "tool": result.get("tool", ""),
                "status": result.get("status", ""),
                "read_only": result.get("read_only", True),
                "side_effects": result.get("side_effects", []),
                "duration_ms": result.get("duration_ms", 0),
                "reason": result.get("reason", ""),
                "arguments": result.get("arguments", {}),
                "observation": result.get("observation", {}),
                "error": result.get("error", ""),
            }
            for result in results
        ]
        return (
            "以下是本轮内部状态工具调用结果。"
            "这些工具只管理 Workmate Agent 内部状态，不代表用户完成了额外外部动作。"
            "请基于 observation 自然回复用户，不要暴露工具 JSON，失败时轻描淡写地降级。\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    def _request_plan(self, llm_client: Any, messages: List[Dict[str, str]], user_input: str) -> str:
        planning_messages = [
            *messages,
            {
                "role": "system",
                "content": self._tool_instruction(),
            },
            {
                "role": "user",
                "content": (
                    "请只判断是否需要调用内部状态工具。"
                    "如果需要，输出 tool_calls JSON；如果不需要，输出空数组。\n"
                    f"当前用户输入:\n{user_input[:1600]}"
                ),
            },
        ]
        if hasattr(llm_client, "invoke_raw"):
            return llm_client.invoke_raw(planning_messages)
        return llm_client.invoke(messages=planning_messages)

    def _tool_instruction(self) -> str:
        schema = {
            "tool_calls": [
                {
                    "tool": "工具名",
                    "arguments": {},
                    "reason": "为什么需要调用",
                }
            ]
        }
        return (
            "你是 Workmate Agent 的内部状态工具选择器。\n"
            "工具只允许读取或更新 Workmate Agent 自己的任务、承诺和记忆状态。\n"
            "不要调用外部网页、文件、shell、GitHub 或任何外部自动化工具。\n"
            "只有用户明确汇报完成、开始、阻塞、放弃，或明确要求查询记忆/任务状态时，才调用工具。\n"
            "如果只是闲聊、普通计划、信息不足或工具不能确定参数，输出空 tool_calls。\n"
            "一轮最多选择 3 个工具。不要猜 task_id；如果不知道 task_id，先调用 get_current_task 或 list_open_tasks。\n"
            "只输出合法 JSON，不要 Markdown，不要解释。\n\n"
            f"可用工具:\n{json.dumps(self.registry.list_prompt_specs(), ensure_ascii=False, indent=2)}\n\n"
            f"输出 schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

    def _parse_tool_calls(self, raw: str) -> List[Dict[str, Any]]:
        parsed = self._parse_json_object(raw)
        calls = parsed.get("tool_calls", [])
        if isinstance(calls, dict):
            calls = [calls]
        if not isinstance(calls, list):
            return []
        result = []
        for call in calls:
            if not isinstance(call, dict):
                continue
            name = str(call.get("tool", "")).strip()
            if name not in self.registry.names():
                continue
            arguments = call.get("arguments", {})
            result.append({
                "tool": name,
                "arguments": arguments if isinstance(arguments, dict) else {},
                "reason": str(call.get("reason", ""))[:180],
            })
        return result[:self.max_calls]

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return {"tool_calls": []}
        try:
            parsed = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return {"tool_calls": []}
        return parsed if isinstance(parsed, dict) else {"tool_calls": []}

    def _planning_error(self, exc: Exception) -> Dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        return {
            "call_id": str(uuid.uuid4()),
            "tool": "__tool_planning__",
            "arguments": {},
            "reason": "tool planning failed",
            "started_at": now,
            "completed_at": now,
            "status": "error",
            "observation": {},
            "error": str(exc),
            "duration_ms": 0,
            "read_only": True,
            "side_effects": [],
            "input_schema": {},
            "output_schema": {},
        }
