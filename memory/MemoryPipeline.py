from datetime import datetime
from typing import Any, Callable, Dict, List, Set


class MemoryPipeline:
    STAGE_CONTRACTS = [
        {
            "stage": "record_turn",
            "requires": {"user_input", "assistant_output"},
            "produces": set(),
            "description": "接收一轮用户输入和助手输出。",
        },
        {
            "stage": "extract_items",
            "requires": {"user_input", "assistant_output"},
            "produces": {"extracted"},
            "description": "从一轮对话中提取结构化记忆。",
        },
        {
            "stage": "update_task_state",
            "requires": {"extracted", "user_input", "assistant_output"},
            "produces": {"task_state"},
            "description": "更新任务生命周期和当前任务快照。",
        },
        {
            "stage": "persist_record",
            "requires": {"extracted", "task_state", "user_input", "assistant_output"},
            "produces": {"record"},
            "description": "保存原始对话资源记录。",
        },
        {
            "stage": "update_derived_memory",
            "requires": {"record", "extracted", "task_state", "user_input", "assistant_output"},
            "produces": {"derived_memory"},
            "description": "更新资源层、语义压缩对话、记忆项、分类层、反省结果、治理状态和检索索引。",
        },
        {
            "stage": "build_response",
            "requires": {"record", "extracted", "task_state", "derived_memory"},
            "produces": set(),
            "description": "生成流水线诊断结果。",
        },
    ]

    def process_turn(self, memory_manager: Any, user_input: str, assistant_output: str) -> Dict[str, Any]:
        started_at = datetime.now().isoformat(timespec="seconds")
        progress: List[Dict[str, Any]] = []
        state: Dict[str, Any] = {
            "user_input": user_input,
            "assistant_output": assistant_output,
        }

        self._check_contract("record_turn", state, before=True)
        self._record_stage(progress, "record_turn", "done", [], "")

        try:
            self._run_stage(
                state,
                progress,
                "extract_items",
                lambda current: {"extracted": memory_manager.extract_memory(
                    current["user_input"],
                    current["assistant_output"],
                )},
            )
            self._run_stage(
                state,
                progress,
                "update_task_state",
                lambda current: {"task_state": memory_manager.update_task_state(
                    current["extracted"],
                    current["user_input"],
                    current["assistant_output"],
                )},
            )
            self._run_stage(
                state,
                progress,
                "persist_record",
                lambda current: {"record": memory_manager.persist_record(
                    current["user_input"],
                    current["assistant_output"],
                    extracted=current["extracted"],
                    task_state=current["task_state"],
                )},
            )
            self._run_stage(
                state,
                progress,
                "update_derived_memory",
                lambda current: {"derived_memory": memory_manager.update_derived_memory(
                    current["record"],
                    current["extracted"],
                    current["task_state"],
                    current["user_input"],
                    current["assistant_output"],
                )},
            )
            self._check_contract("build_response", state, before=True)
            self._record_stage(progress, "build_response", "done", [], "")
        except Exception as exc:
            if not progress or progress[-1].get("status") != "error":
                self._record_stage(progress, "unknown", "error", [], str(exc))
            raise

        return {
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "stages": progress,
            "record": state["record"],
            "extracted": state["extracted"],
            "task_state": state["task_state"],
            "derived_memory": state["derived_memory"],
        }

    def describe(self) -> Dict[str, Any]:
        return {
            "name": "workmate_memory_v0_5_2",
            "stages": [
                {
                    "stage": contract["stage"],
                    "requires": sorted(contract["requires"]),
                    "produces": sorted(contract["produces"]),
                    "description": contract["description"],
                }
                for contract in self.STAGE_CONTRACTS
            ],
            "description": "带输入/输出契约的记忆流水线，统一处理提取、任务更新、语义压缩、反省、治理、索引刷新和诊断。",
        }

    def _run_stage(
        self,
        state: Dict[str, Any],
        progress: List[Dict[str, Any]],
        stage: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        try:
            self._check_contract(stage, state, before=True)
            updates = handler(state)
            if not isinstance(updates, dict):
                raise TypeError(f"stage {stage} must return dict")
            state.update(updates)
            self._check_contract(stage, state, before=False)
            self._record_stage(progress, stage, "done", sorted(updates.keys()), "")
        except Exception as exc:
            self._record_stage(progress, stage, "error", [], str(exc))
            raise

    def _check_contract(self, stage: str, state: Dict[str, Any], before: bool = False) -> None:
        contract = self._contract(stage)
        required: Set[str] = contract["requires"] if before else contract["produces"]
        missing = [key for key in sorted(required) if key not in state]
        if missing:
            kind = "required" if before else "produced"
            raise KeyError(f"stage {stage} missing {kind} keys: {', '.join(missing)}")

    def _contract(self, stage: str) -> Dict[str, Any]:
        for contract in self.STAGE_CONTRACTS:
            if contract["stage"] == stage:
                return contract
        raise KeyError(f"unknown memory pipeline stage: {stage}")

    def _record_stage(
        self,
        progress: List[Dict[str, Any]],
        stage: str,
        status: str,
        produced_keys: List[str],
        error: str,
    ) -> None:
        item = {
            "stage": stage,
            "status": status,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        if produced_keys:
            item["produced"] = produced_keys
        if error:
            item["error"] = error
        progress.append(item)
