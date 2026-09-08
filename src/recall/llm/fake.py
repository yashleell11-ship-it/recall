from recall.llm.client import LlmResponse


class FakeLlmClient:
    """Test double. Returns queued response bodies in order."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str,
                      max_tokens: int | None = None) -> LlmResponse:
        self.calls.append((system, user))
        if not self._responses:
            raise AssertionError("FakeLlmClient ran out of queued responses")
        return LlmResponse(self._responses.pop(0), prompt_tokens=10,
                           completion_tokens=20)
