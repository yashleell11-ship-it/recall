import time
from dataclasses import dataclass

import httpx

from recall.config import Config

_RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class LlmResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int


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

    def complete_json(self, system: str, user: str) -> LlmResponse:
        payload = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
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
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            return LlmResponse(
                content=data["choices"][0]["message"]["content"],
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
        # Deliberately excludes payload and headers: the API key must never
        # reach a log line or a traceback.
        raise RuntimeError(
            f"DeepSeek request failed after {self._max_retries} attempts "
            f"(last status {last_status})"
        )
