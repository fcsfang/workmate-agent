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
        import threading
        from memory import Notifier

        self.memory_manager = MemoryManager()
        self.agent = None
        
        self.notifier = Notifier()
        self.notified_focus_ids = set()
        self.notified_commitment_keys = set()

        threading.Thread(target=self.start_scheduler, daemon=True).start()

    def get_agent(self):
        if self.agent is None:
            self.agent = WorkmateAgent(memory_manager=self.memory_manager)
        return self.agent

    def chat(self, prompt):
        response = self.get_agent().invoke(prompt)
        return {
            "response": response,
            "memory": self.memory_state(prompt),
            "context": self.context_state(),
            "tool_calls": self.tool_state(),
        }

    def chat_stream(self, prompt):
        for chunk in self.get_agent().invoke_stream(prompt):
            yield {"type": "delta", "content": chunk}
        yield {
            "type": "done",
            "memory": self.memory_state(prompt),
            "context": self.context_state(),
            "tool_calls": self.tool_state(),
        }

    def memory_state(self, current_prompt=""):
        records = self.memory_manager.load_records()
        recent_records = records[-30:]
        context_debug = self.memory_manager.build_context_debug()
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
            "memory_items": self.memory_manager.get_memory_items(limit=30),
            "memory_categories": self.memory_manager.get_memory_categories(limit=12),
            "memory_resources": self.memory_manager.get_memory_resources(limit=12),
            "semantic_dialogues": self.memory_manager.get_semantic_dialogues(limit=12),
            "high_level_insights": self.memory_manager.get_high_level_insights(limit=12),
            "memory_conflicts": self.memory_manager.get_memory_conflicts(),
            "reflections": self.memory_manager.get_reflections(),
            "supervision": self.memory_manager.get_supervision_state(),
            "focus_session": self.memory_manager.get_focus_session_state(),
            "support_knowledge": self.memory_manager.get_support_knowledge_state(current_prompt),
            "tool_calls": self.tool_state(),
            "memory_pipeline": context_debug.get("memory_pipeline", {}),
            "last_pipeline_result": context_debug.get("last_pipeline_result", {}),
            "context_stats": context_debug.get("context_stats", {}),
            "retrieval_plan": context_debug.get("retrieval_plan", {}),
        }

    def context_state(self):
        if self.agent and self.agent.get_last_context():
            messages = self.agent.get_last_context()
        else:
            messages = self.memory_manager.build_context_debug().get("messages", [])
        return {
            "messages": messages,
            "message_count": len(messages),
            "context_stats": self.memory_manager.context_compressor.estimate_context(messages),
            "open_commitments": self.memory_manager.get_open_commitments(),
            "task_view": self.memory_manager.get_task_view(),
            "user_profile": self.memory_manager.get_user_profile(),
            "memory_items": self.memory_manager.get_memory_items(limit=20),
            "memory_categories": self.memory_manager.get_memory_categories(limit=10),
            "memory_resources": self.memory_manager.get_memory_resources(limit=10),
            "semantic_dialogues": self.memory_manager.get_semantic_dialogues(limit=10),
            "high_level_insights": self.memory_manager.get_high_level_insights(limit=10),
            "memory_conflicts": self.memory_manager.get_memory_conflicts(),
            "reflections": self.memory_manager.get_reflections(),
            "supervision": self.memory_manager.get_supervision_state(),
            "focus_session": self.memory_manager.get_focus_session_state(),
            "support_knowledge": self.memory_manager.get_support_knowledge_state(""),
            "tool_calls": self.tool_state(),
            "last_pipeline_result": self.memory_manager.last_pipeline_result,
        }

    def focus(self, payload):
        action = str(payload.get("action", "")).strip().lower()
        if action == "start":
            goal = str(payload.get("goal", "")).strip()
            duration_minutes = int(payload.get("duration_minutes", 45) or 45)
            session = self.memory_manager.start_focus_session(goal, duration_minutes=duration_minutes)
        elif action == "complete":
            outcome = str(payload.get("outcome", "")).strip()
            session = self.memory_manager.complete_focus_session(outcome=outcome)
        elif action == "abandon":
            outcome = str(payload.get("outcome", "")).strip()
            session = self.memory_manager.abandon_focus_session(outcome=outcome)
        else:
            raise ValueError("Unknown focus action")

        return {
            "session": session,
            "focus_session": self.memory_manager.get_focus_session_state(),
            "memory": self.memory_state(),
            "context": self.context_state(),
        }

    def tool_state(self):
        if not self.agent:
            return []
        return self.agent.get_last_tool_calls()

    def update_task_status(self, payload):
        task_id = payload.get("id")
        status = payload.get("status")
        if not task_id or not status:
            raise ValueError("id and status are required")
        res = self.memory_manager.update_task_status(task_id, status)
        return {
            "task_view": res.get("task_view"),
            "task_details": res.get("updated_task"),
            "memory": self.memory_state(),
            "context": self.context_state(),
        }

    def start_scheduler(self):
        import time
        import sys
        # 启动等待 5 秒以避开服务初始载入
        time.sleep(5)
        while True:
            try:
                self.run_background_checks()
            except Exception as e:
                print(f"[Background Scheduler Error] {e}", file=sys.stderr)
            time.sleep(60) # 每分钟扫描一次

    def run_background_checks(self):
        from datetime import datetime, date
        today_str = date.today().isoformat()
        
        # 1. 专注会话超时监控
        focus_state = self.memory_manager.get_focus_session_state()
        current_session = focus_state.get("current") or {}
        if current_session.get("status") == "expired" and current_session.get("id"):
            sess_id = current_session["id"]
            if sess_id not in self.notified_focus_ids:
                title = "专注超时提醒 ⏳"
                body = f"专注会话【{current_session.get('goal')}】已超时，建议回来跟 Agent 记录进度哦！"
                self.notifier.send_notification(title, body)
                self.notified_focus_ids.add(sess_id)

        # 2. 承诺到期监控
        open_commitments = self.memory_manager.get_open_commitments()
        now = datetime.now()
        for c in open_commitments:
            c_id = c.get("id")
            deadline_str = c.get("deadline")
            if not c_id or not deadline_str:
                continue
            try:
                deadline_dt = datetime.fromisoformat(deadline_str)
                is_overdue = deadline_dt < now
                is_due_today = deadline_dt.date() == now.date()
                
                if is_overdue or is_due_today:
                    notify_key = f"{c_id}_{today_str}"
                    if notify_key not in self.notified_commitment_keys:
                        title = "承诺逾期提醒 ⚠" if is_overdue else "承诺今日到期提醒 ⏰"
                        desc = "已超出承诺截止时间" if is_overdue else "截止今天完成"
                        body = f"你有一个承诺【{c.get('commitment')}】{desc}，请记得及时处理。"
                        
                        self.notifier.send_notification(title, body)
                        self.notified_commitment_keys.add(notify_key)
            except Exception as e:
                pass


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

        if path == "/api/notify/status":
            import os
            channels = [c.strip() for c in os.getenv("PUSH_CHANNELS", "").split(",") if c.strip()]
            status = {
                "enabled_channels": channels,
                "local_configured": True,  # macOS native is always supported
                "bark_configured": bool(os.getenv("BARK_URL")),
                "lark_configured": bool(os.getenv("LARK_WEBHOOK")),
            }
            self._send_json(status)
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
        try:
            payload = self._read_json()
            if path == "/api/focus":
                self._send_json(APP.focus(payload))
                return

            if path == "/api/notify/test":
                try:
                    APP.notifier.send_notification(
                        "自检测试通知 🔔",
                        "这是一条来自 Workmate Agent 的自检测试通知，听到/看到声音表示配置正确！"
                    )
                    self._send_json({"success": True})
                except Exception as e:
                    self._send_json({"success": False, "error": str(e)}, status=500)
                return

            if path == "/api/task/update-status":
                self._send_json(APP.update_task_status(payload))
                return

            if path != "/api/chat":
                self._send_error(404, "Not found")
                return

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
