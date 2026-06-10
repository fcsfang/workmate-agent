from typing import Any, Dict, List, Optional

from .commitment import CommitmentManager
from .task_manager import TaskManager
from .task_state_manager import TaskStateManager


class TaskState:
    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        task_state_manager: Optional[TaskStateManager] = None,
        commitment_manager: Optional[CommitmentManager] = None,
    ):
        self.task_manager = task_manager or TaskManager()
        self.task_state_manager = task_state_manager or TaskStateManager()
        self.commitment_manager = commitment_manager or CommitmentManager()

    def set_llm_client(self, llm_client: Any) -> None:
        self.task_manager.set_llm_client(llm_client)
        self.commitment_manager.set_llm_client(llm_client)

    def update(self, extracted: Dict[str, Any], user_input: str, assistant_output: str) -> Dict[str, Any]:
        task_lifecycle = self.task_manager.update(extracted, user_input, assistant_output)
        return self.task_state_manager.update(
            extracted,
            user_input,
            assistant_output,
            task_lifecycle=task_lifecycle,
        )

    def update_task_status(self, task_id: str, status: str) -> Dict[str, Any]:
        task = self.task_manager.update_task_status(task_id, status)
        if task:
            from datetime import datetime
            state = self.task_state_manager.load_state()
            if state.get("task_id") == task_id or (not state.get("task_id") and state.get("active_task") == task.get("title")):
                state["status"] = self.task_state_manager._state_status(status)
                state["task_id"] = task_id
                state["active_task"] = task.get("title", "")
                if status == "done":
                    state["current_progress"] = "任务已完成"
                elif status == "abandoned":
                    state["current_progress"] = "任务已放弃"
                state["updated_at"] = datetime.now().isoformat(timespec="seconds")
                self.task_state_manager.save_state(state)
        return {
            "task_view": self.task_view(),
            "updated_task": task
        }

    def update_commitments(
        self,
        extracted: Dict[str, Any],
        user_input: str,
        assistant_output: str,
        task_state: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return self.commitment_manager.update(extracted, user_input, assistant_output, task_state=task_state)

    def current_state(self) -> Dict[str, Any]:
        return self.task_state_manager.load_state()

    def task_view(self) -> Dict[str, Any]:
        return self.task_manager.get_task_view()

    def open_commitments(self) -> List[Dict[str, Any]]:
        return self.commitment_manager.get_open_commitments()

    def all_commitments(self) -> List[Dict[str, Any]]:
        return self.commitment_manager.load_commitments()

    def format_task_lifecycle(self) -> str:
        return self.task_manager.format_for_context()

    def format_current_state(self) -> str:
        return self.task_state_manager.format_for_context()

    def format_commitments(self) -> str:
        return self.commitment_manager.format_for_context()
