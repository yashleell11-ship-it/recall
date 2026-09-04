import httpx
import pytest

from recall.config import load_config
from recall.llm.client import DeepSeekClient
from recall.llm.fake import FakeLlmClient

CFG = load_config({"DEEPSEEK_API_KEY": "sk-test"})


def _ok(content):
    def handler(request):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 22},
        })
    return httpx.MockTransport(handler)


def test_complete_json_returns_content_and_tokens():
    client = DeepSeekClient(CFG, transport=_ok('{"cards": []}'))
    resp = client.complete_json("sys", "user")
    assert resp.content == '{"cards": []}'
    assert resp.prompt_tokens == 11
    assert resp.completion_tokens == 22


def test_request_sends_auth_and_json_mode():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    DeepSeekClient(CFG, transport=httpx.MockTransport(handler)).complete_json("s", "u")
    assert seen["auth"] == "Bearer sk-test"
    assert "json_object" in seen["body"]


def test_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    client = DeepSeekClient(CFG, transport=httpx.MockTransport(handler),
                            sleep=lambda _s: None)
    assert client.complete_json("s", "u").content == "{}"
    assert calls["n"] == 3


def test_gives_up_after_max_retries():
    client = DeepSeekClient(CFG,
                            transport=httpx.MockTransport(lambda r: httpx.Response(503)),
                            sleep=lambda _s: None)
    with pytest.raises(RuntimeError):
        client.complete_json("s", "u")


def test_api_key_never_appears_in_error():
    client = DeepSeekClient(CFG,
                            transport=httpx.MockTransport(lambda r: httpx.Response(503)),
                            sleep=lambda _s: None)
    with pytest.raises(RuntimeError) as exc:
        client.complete_json("s", "u")
    assert "sk-test" not in str(exc.value)


def test_fake_client_returns_queued_responses_in_order():
    fake = FakeLlmClient(['{"a": 1}', '{"b": 2}'])
    assert fake.complete_json("s", "u1").content == '{"a": 1}'
    assert fake.complete_json("s", "u2").content == '{"b": 2}'
    assert fake.calls == [("s", "u1"), ("s", "u2")]
