import contextvars
import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

_current_turn_id: contextvars.ContextVar[str] = contextvars.ContextVar("workmate_provider_turn_id", default="")
_provider_calls: List[Dict[str, Any]] = []
_MAX_CALLS = 300


def start_provider_turn(turn_id: str) -> contextvars.Token:
    return _current_turn_id.set(str(turn_id or ""))


def finish_provider_turn(token: Optional[contextvars.Token] = None) -> None:
    if token is not None:
        try:
            _current_turn_id.reset(token)
        except ValueError:
            # Defensive fallback for callers crossing an execution context.
            _current_turn_id.set("")
    else:
        _current_turn_id.set("")


def clear_provider_traces(turn_id: str = "") -> None:
    global _provider_calls
    if turn_id:
        _provider_calls = [item for item in _provider_calls if item.get("turn_id") != turn_id]
    else:
        _provider_calls = []


def record_provider_call(
    kind: str,
    provider: str = "",
    operation: str = "",
    model: str = "",
    status: str = "success",
    started_perf: Optional[float] = None,
    error: Any = "",
    fallback: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    turn_id: str = "",
) -> Dict[str, Any]:
    safe_metadata = _safe_metadata(metadata or {})
    call = {
        "call_id": str(uuid.uuid4()),
        "turn_id": str(turn_id or _current_turn_id.get() or ""),
        "kind": str(kind or ""),
        "provider": _safe_text(provider, 80),
        "operation": _safe_text(operation, 120),
        "model": _safe_text(model, 120),
        "status": str(status or "success"),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "duration_ms": _elapsed_ms(started_perf),
        "error": _safe_text(error, 240),
        "fallback": _safe_text(fallback, 120),
        "metadata": safe_metadata,
        "usage": _usage_from_metadata(safe_metadata),
    }
    _provider_calls.append(call)
    if len(_provider_calls) > _MAX_CALLS:
        del _provider_calls[:-_MAX_CALLS]
    return deepcopy(call)


def get_provider_trace_summary(turn_id: str = "", limit: int = 20) -> Dict[str, Any]:
    calls = [
        item for item in _provider_calls
        if not turn_id or item.get("turn_id") == turn_id
    ]
    calls = calls[-limit:]
    by_kind: Dict[str, Dict[str, Any]] = {}
    providers = set()
    fallbacks = []
    errors = []
    total_duration = 0
    usage = _empty_usage()
    for call in calls:
        kind = call.get("kind") or "unknown"
        status = call.get("status") or "unknown"
        metadata = call.get("metadata") if isinstance(call.get("metadata"), dict) else {}
        providers.add(call.get("provider") or kind)
        total_duration += int(call.get("duration_ms") or 0)
        bucket = by_kind.setdefault(kind, {
            "total": 0,
            "success": 0,
            "error": 0,
            "fallback": 0,
            "duration_ms": 0,
            "usage": _empty_usage(),
        })
        bucket["total"] += 1
        bucket["duration_ms"] += int(call.get("duration_ms") or 0)
        call_usage = call.get("usage") if isinstance(call.get("usage"), dict) else _usage_from_metadata(metadata)
        _merge_usage(usage, call_usage)
        _merge_usage(bucket["usage"], call_usage)
        if status == "error":
            bucket["error"] += 1
            errors.append({
                "kind": kind,
                "operation": call.get("operation", ""),
                "error": call.get("error", ""),
            })
        else:
            bucket["success"] += 1
        if call.get("fallback") or status == "fallback":
            bucket["fallback"] += 1
            fallbacks.append({
                "kind": kind,
                "operation": call.get("operation", ""),
                "fallback": call.get("fallback", ""),
            })
    return {
        "total": len(calls),
        "duration_ms": total_duration,
        "providers": sorted(provider for provider in providers if provider),
        "by_kind": by_kind,
        "usage": usage,
        "fallbacks": fallbacks,
        "errors": errors,
        "calls": deepcopy(calls),
    }


def _empty_usage() -> Dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_tokens": 0,
        "input_chars": 0,
        "response_chars": 0,
        "text_chars": 0,
        "image_count": 0,
        "image_bytes": 0,
        "audio_bytes": 0,
        "embedding_dimensions": 0,
    }


def _usage_from_metadata(metadata: Dict[str, Any]) -> Dict[str, int]:
    usage = _empty_usage()
    for key in usage:
        usage[key] = _int(metadata.get(key))

    if not usage["total_tokens"]:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

    if not usage["estimated_tokens"]:
        chars = usage["input_chars"] + usage["response_chars"] + usage["text_chars"]
        # Four characters per token is a coarse provider-neutral estimate for audit display.
        usage["estimated_tokens"] = int((chars + 3) / 4) if chars else 0
    return usage


def _merge_usage(target: Dict[str, int], source: Dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = int(target.get(key, 0) or 0) + int(value or 0)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _elapsed_ms(started_perf: Optional[float]) -> int:
    if started_perf is None:
        return 0
    return int((time.perf_counter() - started_perf) * 1000)


def _safe_text(value: Any, limit: int) -> str:
    return str(value or "").replace("\n", " ").strip()[:limit]


def _safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    safe = {}
    for key, value in metadata.items():
        key_text = _safe_text(key, 60)
        if key_text.lower() in {"api_key", "apikey", "authorization", "token", "secret"}:
            continue
        if isinstance(value, (int, float, bool)) or value is None:
            safe[key_text] = value
        elif isinstance(value, (list, tuple, set)):
            safe[key_text] = len(value)
        elif isinstance(value, dict):
            safe[key_text] = {"keys": sorted(str(item)[:40] for item in value.keys())[:8]}
        else:
            safe[key_text] = _safe_text(value, 160)
    return safe
