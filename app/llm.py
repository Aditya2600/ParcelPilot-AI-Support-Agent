from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any, Callable

import httpx


logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """The planner model could not be reached or returned an unusable reply.

    Raised rather than silently degrading: an agent that quietly stops planning
    and starts guessing is worse than one that says it is unavailable.
    """


# No real endpoint as a source default -- this must come from MEDHA_BASE_URL
# (see .env.example / docker-compose.yml). Left as a harmless local placeholder
# rather than raising here, so importing the app without that env var set still
# works (e.g. the deterministic, non-live_llm test suite, which never depends on
# this value resolving to anything reachable).
DEFAULT_BASE_URL = "http://localhost:8001/v1"
DEFAULT_MODEL = "Medha"

# Transient failures worth one interactive-friendly retry burst. Anything else
# (400/401/403/404/422/...) is a deterministic client error that a retry can
# never fix, so it is raised immediately instead of being retried.
RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})

MAX_RETRIES = 2          # retries after the initial attempt (3 attempts total)
BASE_DELAY_SECONDS = 0.5  # retry 1 ~0.5s, retry 2 ~1.0s (exponential, base*2**n)
JITTER_FRACTION = 0.2     # +/- up to 20% of the computed delay


def _backoff_delay(retry_index: int, rand_fn: Callable[[float, float], float]) -> float:
    """retry_index is 0 for the first retry, 1 for the second, ..."""
    base = BASE_DELAY_SECONDS * (2 ** retry_index)
    jitter = base * JITTER_FRACTION
    return max(0.0, rand_fn(base - jitter, base + jitter))


class MedhaClient:
    """Minimal client for the Medha OpenAI-compatible (vLLM) endpoint.

    The server runs without `--enable-auto-tool-choice`, so the native
    `tools` parameter is rejected. We drive tool calls through constrained
    JSON decoding instead (`response_format: json_schema`), which vLLM
    enforces at the token level via guided decoding. The model therefore
    cannot emit a tool name outside the allowed enum or a malformed call.

    Retries live entirely inside this one HTTP call (`complete_json` ->
    `_post_with_retry`). Nothing above this client -- tool execution,
    escalation staging, confirmation, database writes -- is inside the retry
    loop, so a transient inference hiccup can never cause one of those to run
    twice.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 90.0,
        max_retries: int = MAX_RETRIES,
        sleep_fn: Callable[[float], None] = time.sleep,
        rand_fn: Callable[[float, float], float] = random.uniform,
    ):
        self.base_url = (base_url or os.getenv("MEDHA_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.api_key = api_key or os.getenv("MEDHA_API_KEY", "changeme")
        self.model = model or os.getenv("MEDHA_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep_fn
        self._rand = rand_fn

    def _post_with_retry(self, payload: dict[str, Any]) -> httpx.Response:
        attempts = self.max_retries + 1
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # Transient connection-level failure: reset, refused, DNS
                # blip, read timeout, ... Worth retrying.
                last_exc = exc
                error_type = type(exc).__name__
                if attempt >= attempts:
                    logger.error(
                        "medha_inference_retry_exhausted attempt=%d/%d error_type=%s",
                        attempt, attempts, error_type,
                    )
                    raise LLMUnavailable(f"Could not reach the planner model: {error_type}") from exc
                delay = _backoff_delay(attempt - 1, self._rand)
                logger.warning(
                    "medha_inference_retry attempt=%d/%d error_type=%s retry_delay_s=%.3f",
                    attempt, attempts, error_type, delay,
                )
                self._sleep(delay)
                continue

            if response.status_code == 200:
                return response

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt >= attempts:
                    logger.error(
                        "medha_inference_retry_exhausted attempt=%d/%d status=%d",
                        attempt, attempts, response.status_code,
                    )
                    raise LLMUnavailable(
                        f"Planner model returned HTTP {response.status_code} after {attempts} attempts"
                    )
                delay = _backoff_delay(attempt - 1, self._rand)
                logger.warning(
                    "medha_inference_retry attempt=%d/%d status=%d retry_delay_s=%.3f",
                    attempt, attempts, response.status_code, delay,
                )
                self._sleep(delay)
                continue

            # Deterministic client/server error (400/401/403/404/422/...):
            # a retry cannot change the outcome, so fail immediately.
            raise LLMUnavailable(f"Planner model returned HTTP {response.status_code}: {response.text[:300]}")

        # Unreachable in practice: the loop above always returns or raises.
        if last_exc is not None:
            raise LLMUnavailable(f"Could not reach the planner model: {last_exc}") from last_exc
        raise LLMUnavailable("Planner model could not return a response")

    def complete_json(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        schema_name: str = "step",
        max_tokens: int = 700,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Return one schema-conforming JSON object from the model."""
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        response = self._post_with_retry(payload)

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMUnavailable(f"Unexpected planner response shape: {exc}") from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            # Guided decoding makes this rare; it still happens if the reply is
            # truncated by max_tokens mid-object.
            raise LLMUnavailable(f"Planner returned non-JSON content: {content[:200]}") from exc

        if not isinstance(parsed, dict):
            raise LLMUnavailable("Planner returned JSON that was not an object.")
        return parsed
