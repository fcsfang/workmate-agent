import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from email.utils import formatdate
from typing import Any, Dict
from urllib.parse import urlencode, urlparse

import websocket
from dotenv import load_dotenv

load_dotenv()


class XFYunTTSError(RuntimeError):
    pass


@dataclass
class XFYunTTSConfig:
    app_id: str
    api_key: str
    api_secret: str
    host_url: str = "wss://tts-api.xfyun.cn/v2/tts"
    voice: str = "xiaoyan"
    speed: int = 45
    volume: int = 60
    pitch: int = 50
    timeout: int = 20

    @classmethod
    def from_env(cls) -> "XFYunTTSConfig":
        app_id = os.getenv("XFYUN_TTS_APP_ID", "").strip()
        api_key = os.getenv("XFYUN_TTS_API_KEY", "").strip()
        api_secret = os.getenv("XFYUN_TTS_API_SECRET", "").strip()
        if not app_id or not api_key or not api_secret:
            raise XFYunTTSError("XFYUN_TTS_APP_ID, XFYUN_TTS_API_KEY and XFYUN_TTS_API_SECRET are required")
        return cls(
            app_id=app_id,
            api_key=api_key,
            api_secret=api_secret,
            host_url=os.getenv("XFYUN_TTS_HOST_URL", "wss://tts-api.xfyun.cn/v2/tts").strip(),
            voice=os.getenv("XFYUN_TTS_VOICE", "xiaoyan").strip() or "xiaoyan",
            speed=_bounded_int(os.getenv("XFYUN_TTS_SPEED", "45"), 0, 100),
            volume=_bounded_int(os.getenv("XFYUN_TTS_VOLUME", "60"), 0, 100),
            pitch=_bounded_int(os.getenv("XFYUN_TTS_PITCH", "50"), 0, 100),
            timeout=_bounded_int(os.getenv("XFYUN_TTS_TIMEOUT", "20"), 5, 60),
        )


class XFYunTTSClient:
    def __init__(self, config: XFYunTTSConfig | None = None):
        self.config = config or XFYunTTSConfig.from_env()

    def synthesize(self, text: str) -> bytes:
        text = _normalize_text(text)
        if not text:
            raise XFYunTTSError("text is required")
        if not hasattr(websocket, "create_connection"):
            raise XFYunTTSError(
                "websocket-client is required for XFYun TTS. "
                "Run `pip uninstall websocket && pip install websocket-client` in the active environment."
            )
        ws = websocket.create_connection(self._authorized_url(), timeout=self.config.timeout)
        try:
            ws.send(json.dumps(self._payload(text), ensure_ascii=False))
            chunks = []
            while True:
                raw = ws.recv()
                if not raw:
                    continue
                message = json.loads(raw)
                code = int(message.get("code", 0))
                if code != 0:
                    raise XFYunTTSError(message.get("message") or f"XFYun TTS failed with code {code}")
                data = message.get("data") or {}
                audio = data.get("audio")
                if audio:
                    chunks.append(base64.b64decode(audio))
                if int(data.get("status", 0)) == 2:
                    break
            audio_bytes = b"".join(chunks)
            if not audio_bytes:
                raise XFYunTTSError("XFYun TTS returned empty audio")
            return audio_bytes
        finally:
            ws.close()

    def _authorized_url(self) -> str:
        parsed = urlparse(self.config.host_url)
        host = parsed.netloc
        path = parsed.path or "/v2/tts"
        date = formatdate(usegmt=True)
        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
        signature_sha = hmac.new(
            self.config.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode("utf-8")
        authorization_origin = (
            f'api_key="{self.config.api_key}", '
            'algorithm="hmac-sha256", '
            'headers="host date request-line", '
            f'signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        query = urlencode({"authorization": authorization, "date": date, "host": host})
        return f"{self.config.host_url}?{query}"

    def _payload(self, text: str) -> Dict[str, Any]:
        return {
            "common": {"app_id": self.config.app_id},
            "business": {
                "aue": "lame",
                "sfl": 1,
                "auf": "audio/L16;rate=16000",
                "vcn": self.config.voice,
                "speed": self.config.speed,
                "volume": self.config.volume,
                "pitch": self.config.pitch,
                "tte": "UTF8",
            },
            "data": {
                "status": 2,
                "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
            },
        }


def _normalize_text(text: str) -> str:
    text = " ".join(str(text or "").split())
    encoded = text.encode("utf-8")
    if len(encoded) <= 8000:
        return text
    return encoded[:8000].decode("utf-8", errors="ignore")


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))
