import time
from dataclasses import dataclass

import httpx

from recall.config import Config

_RETRY_STATUS = {429, 500, 502, 503, 504}


class LlmUnavailable(RuntimeError):
    """The card writer could not be reached, or refused to work.

    A distinct type so the API can answer 502 with something a student can act
    on, instead of leaking a 500 that the browser then reports as "could not
    reach the API" — which is a lie, since the API was reached fine and it was
    DeepSeek that said no.

    Carries the upstream status and nothing else. The request that failed
    contains the API key in its headers, so neither the exception nor its
    message may ever quote it.
    """

    def __init__(self, status: int | None, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


_UPSTREAM_MEANING = {
    401: "the DeepSeek API key is missing or was rejected",
    403: "the DeepSeek API key is not allowed to use this model",
    402: "the DeepSeek account is out of credit",
    400: "DeepSeek rejected the request",
}


def _unavailable(status: int | None) -> LlmUnavailable:
    meaning = _UPSTREAM_MEANING.get(status or 0)
    if meaning is None:
        meaning = ("DeepSeek is not responding" if status is None
                   else f"DeepSeek returned {status}")
    return LlmUnavailable(status, f"Cards could not be written: {meaning}.")


@dataclass(frozen=True)
class LlmResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    #: Why the model stopped. "length" means the reply was CUT OFF at the token
    #: cap, which for a json_object response means unparseable json — and the
    #: difference between "the model wrote nonsense" and "we did not let it
    #: finish" is the whole diagnosis.
    finish_reason: str = "stop"


class DeepSeekClient:
    """The only module in this package permitted to make network calls."""

    def __init__(self, cfg: Config, transport=None, sleep=time.sleep,
                 max_retries: int = 4):
        self._cfg = cfg
        self._sleep = sleep
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=cfg.base_url, timeout=120.0, transport=transport
        )

    def complete_json(self, system: str, user: str,
                      max_tokens: int | None = None) -> LlmResponse:
        payload = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        last_status = None
        for attempt in range(self._max_retries):
            resp = self._http.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._cfg.api_key}"},
                json=payload,
            )
            if resp.status_code in _RETRY_STATUS:
                last_status = resp.status_code
                self._sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code >= 400:
                raise _unavailable(resp.status_code)
            data = resp.json()
            usage = data.get("usage", {})
            choice = data["choices"][0]
            return LlmResponse(
                content=choice["message"]["content"],
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                finish_reason=choice.get("finish_reason") or "stop",
            )
        # Deliberately excludes payload and headers: the API key must never
        # reach a log line or a traceback.
        raise _unavailable(last_status)
