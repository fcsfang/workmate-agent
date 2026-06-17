import os
import time

from observability import record_provider_call
from .xfyun_tts import XFYunTTSClient


def synthesize_speech(text: str, provider: str = "") -> tuple[bytes, str]:
    provider = (provider or os.getenv("TTS_PROVIDER", "browser")).strip().lower()
    started = time.perf_counter()
    if provider == "xfyun":
        try:
            audio = XFYunTTSClient().synthesize(text)
            record_provider_call(
                "tts",
                provider="xfyun",
                operation="synthesize",
                model=os.getenv("XFYUN_TTS_VOICE", "xiaoyan"),
                started_perf=started,
                metadata={"text_chars": len(text or ""), "audio_bytes": len(audio)},
            )
            return audio, "audio/mpeg"
        except Exception as exc:
            record_provider_call(
                "tts",
                provider="xfyun",
                operation="synthesize",
                model=os.getenv("XFYUN_TTS_VOICE", "xiaoyan"),
                status="error",
                started_perf=started,
                error=exc,
                metadata={"text_chars": len(text or "")},
            )
            raise
    error = ValueError(f"unsupported tts provider: {provider}")
    record_provider_call(
        "tts",
        provider=provider or "unknown",
        operation="synthesize",
        status="error",
        started_perf=started,
        error=error,
        metadata={"text_chars": len(text or "")},
    )
    raise error
