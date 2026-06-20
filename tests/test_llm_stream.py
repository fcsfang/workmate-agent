from types import SimpleNamespace

from src.LLMClient import LLMClient


class FakeCompletions:
    def __init__(self, stream_chunks, fallback_content="fallback"):
        self.stream_chunks = stream_chunks
        self.fallback_content = fallback_content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(self.stream_chunks)
        message = SimpleNamespace(content=self.fallback_content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def build_client(completions):
    client = object.__new__(LLMClient)
    client.model = "fake-model"
    client.baseUrl = "https://example.test/v1"
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client


def chunk(content):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


def test_invoke_stream_yields_string_and_content_parts():
    completions = FakeCompletions([
        chunk("第一段"),
        chunk([{"type": "text", "text": "第二段"}]),
    ])
    client = build_client(completions)

    result = list(client.invoke_stream(messages=[{"role": "user", "content": "hello"}]))

    assert result == ["第一段", "第二段"]
    assert len(completions.calls) == 1
    assert completions.calls[0]["stream"] is True


def test_invoke_stream_falls_back_when_provider_returns_no_visible_text():
    completions = FakeCompletions([chunk(None)], fallback_content="降级回复")
    client = build_client(completions)

    result = list(client.invoke_stream(messages=[{"role": "user", "content": "hello"}]))

    assert result == ["降级回复"]
    assert len(completions.calls) == 2
    assert completions.calls[0]["stream"] is True
    assert "stream" not in completions.calls[1]
