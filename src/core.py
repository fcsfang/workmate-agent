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
        self.memory_manager.set_llm_client(self.llmclient)
        self.last_context_messages = []

    def invoke(self, prompt):
        messages = self.memory_manager.build_context_messages(prompt)
        self.last_context_messages = messages
        response = self.llmclient.invoke(messages=messages)
        self._save_memory(prompt, response)
        return response

    def invoke_stream(self, prompt):
        messages = self.memory_manager.build_context_messages(prompt)
        self.last_context_messages = messages
        chunks = []
        for chunk in self.llmclient.invoke_stream(messages=messages):
            chunks.append(chunk)
            yield chunk
        response = "".join(chunks).strip()
        self._save_memory(prompt, response)

    def _save_memory(self, prompt, response):
        self.memory_manager.process_turn(prompt, response)

    def get_last_context(self):
        return self.last_context_messages


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
