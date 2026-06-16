import base64

from fastapi.testclient import TestClient

from src import web
from tts.xfyun_tts import XFYunTTSClient, XFYunTTSConfig


def test_xfyun_tts_payload_encodes_text():
    client = XFYunTTSClient(
        XFYunTTSConfig(
            app_id="app",
            api_key="key",
            api_secret="secret",
            voice="xiaoyan",
            speed=40,
            volume=50,
            pitch=60,
        )
    )

    payload = client._payload("回来做一小步就好")

    assert payload["common"]["app_id"] == "app"
    assert payload["business"]["aue"] == "lame"
    assert payload["business"]["sfl"] == 1
    assert payload["business"]["vcn"] == "xiaoyan"
    assert base64.b64decode(payload["data"]["text"]).decode("utf-8") == "回来做一小步就好"


def test_tts_endpoint_returns_audio(monkeypatch):
    def fake_synthesize(text, provider=""):
        assert text == "测试语音"
        assert provider == "xfyun"
        return b"audio-bytes", "audio/mpeg"

    monkeypatch.setattr(web, "synthesize_speech", fake_synthesize)
    client = TestClient(web.app)

    response = client.post("/api/tts/speech", json={"text": "测试语音", "provider": "xfyun"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"audio-bytes"
