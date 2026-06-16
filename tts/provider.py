import os

from .xfyun_tts import XFYunTTSClient


def synthesize_speech(text: str, provider: str = "") -> tuple[bytes, str]:
    provider = (provider or os.getenv("TTS_PROVIDER", "browser")).strip().lower()
    if provider == "xfyun":
        return XFYunTTSClient().synthesize(text), "audio/mpeg"
    raise ValueError(f"unsupported tts provider: {provider}")
