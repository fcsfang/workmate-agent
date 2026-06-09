import os
import sys
import subprocess
import urllib.request
import urllib.parse
import json

class Notifier:
    def __init__(self):
        # 默认启用 macOS 本地通知
        channels_str = os.getenv("PUSH_CHANNELS", "local")
        self.channels = [c.strip().lower() for c in channels_str.split(",") if c.strip()]
        self.bark_key = os.getenv("BARK_KEY", "").strip()
        self.lark_webhook_url = os.getenv("LARK_WEBHOOK_URL", "").strip()

    def send_notification(self, title: str, body: str) -> None:
        """分发通知到各个启用的通道"""
        for channel in self.channels:
            try:
                if channel == "local":
                    self._send_local_macos(title, body)
                elif channel == "bark" and self.bark_key:
                    self._send_bark(title, body)
                elif channel == "lark" and self.lark_webhook_url:
                    self._send_lark(title, body)
            except Exception as e:
                print(f"[Notifier Error] Failed to send via {channel}: {e}", file=sys.stderr)

    def _send_local_macos(self, title: str, body: str) -> None:
        """调用 macOS System AppleScript 原生弹窗"""
        # 转义双引号以防 Shell 命令截断
        title_esc = title.replace('"', '\\"')
        body_esc = body.replace('"', '\\"')
        script = f'display notification "{body_esc}" with title "{title_esc}"'
        cmd = ["osascript", "-e", script]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _send_bark(self, title: str, body: str) -> None:
        """向 iOS Bark APP 发送推送"""
        title_q = urllib.parse.quote(title)
        body_q = urllib.parse.quote(body)
        url = f"https://api.day.app/{self.bark_key}/{title_q}/{body_q}"
        
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()

    def _send_lark(self, title: str, body: str) -> None:
        """向飞书群自定义机器人 Webhook 发送推送"""
        payload = {
            "msg_type": "text",
            "content": {
                "text": f"🔔 {title}\n\n{body}"
            }
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.lark_webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
