import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .core import WorkmateAgent
except ImportError:
    from core import WorkmateAgent

from memory import MemoryManager

WEB_ROOT = PROJECT_ROOT / "web"


class WorkmateWebApp:
    def __init__(self):
        self.memory_manager = MemoryManager()
        self.agent = None

    def get_agent(self):
        if self.agent is None:
            self.agent = WorkmateAgent(memory_manager=self.memory_manager)
        return self.agent

    def chat(self, prompt):
        response = self.get_agent().invoke(prompt)
        return {
            "response": response,
            "memory": self.memory_state(),
            "context": self.context_state(),
        }

    def chat_stream(self, prompt):
        for chunk in self.get_agent().invoke_stream(prompt):
            yield {"type": "delta", "content": chunk}
        yield {
            "type": "done",
            "memory": self.memory_state(),
            "context": self.context_state(),
        }

    def memory_state(self):
        records = self.memory_manager.load_records()
        recent_records = records[-8:]
        return {
            "count": len(records),
            "recent": recent_records,
            "summary": self.memory_manager.get_memory_summary(),
            "structured_summary": self.memory_manager.get_structured_memory_summary(),
            "recent_summary": self.memory_manager.get_recent_summary(days=7),
            "recent_summary_context": self.memory_manager.get_recent_summary_context(days=7),
            "task_state": self.memory_manager.get_task_state(),
            "task_view": self.memory_manager.get_task_view(),
            "open_commitments": self.memory_manager.get_open_commitments(),
            "user_profile": self.memory_manager.get_user_profile(),
        }

    def context_state(self):
        if self.agent and self.agent.get_last_context():
            messages = self.agent.get_last_context()
        else:
            messages = self.memory_manager.build_context_debug().get("messages", [])
        return {
            "messages": messages,
            "message_count": len(messages),
            "open_commitments": self.memory_manager.get_open_commitments(),
            "task_view": self.memory_manager.get_task_view(),
            "user_profile": self.memory_manager.get_user_profile(),
        }


APP = WorkmateWebApp()


class WorkmateRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send_file(WEB_ROOT / "index.html")
            return

        if path == "/api/memory":
            self._send_json(APP.memory_state())
            return

        if path == "/api/context":
            self._send_json(APP.context_state())
            return

        safe_path = path.lstrip("/")
        file_path = (WEB_ROOT / safe_path).resolve()
        if WEB_ROOT.resolve() not in file_path.parents and file_path != WEB_ROOT.resolve():
            self._send_error(403, "Forbidden")
            return

        if file_path.is_file():
            self._send_file(file_path)
            return

        self._send_error(404, "Not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/chat":
            self._send_error(404, "Not found")
            return

        try:
            payload = self._read_json()
            prompt = str(payload.get("prompt", "")).strip()
            if not prompt:
                self._send_error(400, "Prompt is required")
                return
            self._send_chat_stream(prompt)
        except Exception as exc:
            self._send_error(500, str(exc))

    def log_message(self, format, *args):
        return

    def _read_json(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        if not raw_body:
            return {}
        return json.loads(raw_body)

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_chat_stream(self, prompt):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            for event in APP.chat_stream(prompt):
                self._send_sse_event(event)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            self._send_sse_event({"type": "error", "error": str(exc)})

    def _send_sse_event(self, payload):
        body = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _send_file(self, file_path):
        body = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status=status)


def run_web(host="127.0.0.1", port=7860):
    server = ThreadingHTTPServer((host, port), WorkmateRequestHandler)
    print(f"Workmate Web 已启动：http://{host}:{port}")
    print("按 Ctrl+C 结束服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已结束。")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_web()
