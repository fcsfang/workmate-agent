import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .LLMClient import LLMClient
except ImportError:
    from LLMClient import LLMClient

from memory import MemoryManager
from agent import AgentRuntime
from tools import ToolExecutor, build_workmate_tool_registry


class WorkmateAgent:
    def __init__(self, llmclient=None, memory_manager=None, tool_executor=None):
        self.llmclient = llmclient or LLMClient()
        self.memory_manager = memory_manager or MemoryManager()
        self.memory_manager.set_llm_client(self.llmclient)
        self.tool_registry = build_workmate_tool_registry(self.memory_manager)
        self.tool_executor = tool_executor or ToolExecutor(self.tool_registry)
        self.runtime = AgentRuntime(self.llmclient, self.memory_manager, self.tool_executor)

    def invoke(self, prompt):
        return self.runtime.run(prompt)

    def invoke_stream(self, prompt):
        for chunk in self.runtime.stream(prompt):
            yield chunk

    def get_last_context(self):
        return self.runtime.get_last_context()

    def get_last_tool_calls(self):
        return self.runtime.get_last_tool_calls()

    def get_last_turn_trace(self):
        return self.runtime.get_last_turn_trace()


def run_chat():
    agent = None
    print("Workmate Agent 已启动。输入 exit / quit / 退出 结束对话。")

    while True:
        try:
            prompt = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n对话已结束。")
            break

        if not prompt:
            continue

        if prompt.lower() in {"exit", "quit", "q"} or prompt in {"退出", "结束"}:
            print("对话已结束。")
            break

        if agent is None:
            agent = WorkmateAgent()

        print("\n搭子：", end="", flush=True)
        for chunk in agent.invoke_stream(prompt):
            print(chunk, end="", flush=True)
        print()


if __name__ == "__main__":
    run_chat()
