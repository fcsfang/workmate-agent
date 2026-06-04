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


class WorkmateAgent:
    def __init__(self, llmclient=None, memory_manager=None):
        self.llmclient = llmclient or LLMClient()
        self.memory_manager = memory_manager or MemoryManager()

    def invoke(self, prompt):
        messages = self.memory_manager.build_context_messages(prompt)
        response = self.llmclient.invoke(messages=messages)
        self.memory_manager.add_record(prompt, response)
        return response


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

        response = agent.invoke(prompt)
        print(f"\n搭子：{response}")


if __name__ == "__main__":
    run_chat()
