"""LLM client using OpenRouter (OpenAI-compatible API) with retry logic."""

from __future__ import annotations

import base64
import json
import logging
import re
import time

from openai import APIConnectionError, APITimeoutError

from drawmind.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    VISION_MODEL,
    TEXT_MODEL,
    LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 3
JSON_RETRIES = 2
BASE_DELAY = 1.0  # seconds
MAX_DELAY = 30.0


class EmptyCompletion(RuntimeError):
    """The provider answered successfully but sent no content."""


class NotJSON(ValueError):
    """The answer arrived but is not JSON. `raw` holds it for the caller."""

    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def _require_content(response) -> str:
    """Return the completion text, or raise if the provider sent nothing.

    An empty body arrives as a normal 200 response, so without this check it
    travels on as an unparseable answer instead of being retried.
    """
    choices = getattr(response, "choices", None)
    if not choices:
        raise EmptyCompletion("provider returned no choices")

    content = choices[0].message.content
    if content and content.strip():
        return content

    reason = getattr(choices[0], "finish_reason", None) or "unknown"
    raise EmptyCompletion(f"provider returned empty content (finish_reason={reason})")


class LLMClient:
    """LLM client via OpenRouter - access Claude, GPT-4o, Llama etc. through one API."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None and OPENROUTER_API_KEY:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=OPENROUTER_API_KEY,
                timeout=LLM_TIMEOUT_SECONDS,
                # This class runs its own retry loop; leaving the SDK's on
                # would multiply the attempts and the worst-case wait.
                max_retries=0,
            )
        return self._client

    @property
    def available(self) -> bool:
        return bool(OPENROUTER_API_KEY)

    def complete(
        self,
        prompt: str,
        model: str | None = None,
        images: list[bytes] | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        """Send a completion request via OpenRouter with automatic retry.

        Retries on rate-limit (429), server errors (5xx), and transient
        network failures using exponential backoff.

        Args:
            prompt: The user prompt
            model: OpenRouter model ID (e.g. "anthropic/claude-sonnet-4-20250514")
            images: Optional list of PNG image bytes for vision
            system: Optional system prompt
            max_tokens: Maximum response tokens
            temperature: Sampling temperature

        Returns:
            The model's text response
        """
        if not self.client:
            raise RuntimeError(
                "No OPENROUTER_API_KEY configured. Get one at https://openrouter.ai/keys"
            )

        model = model or (VISION_MODEL if images else TEXT_MODEL)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        # Build user message content
        content = []
        if images:
            for img in images:
                b64 = base64.b64encode(img).decode()
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
        content.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": content})

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return _require_content(response)

            except Exception as e:
                last_error = e
                status = getattr(e, "status_code", None)

                # Decided by type and status only: matching words in the
                # message would retry a 400 that merely mentions "generate".
                retryable = isinstance(
                    e, (EmptyCompletion, APIConnectionError, APITimeoutError)
                ) or status in (408, 429, 500, 502, 503, 504)

                if not retryable or attempt == MAX_RETRIES - 1:
                    logger.error(f"LLM request failed (attempt {attempt + 1}): {e}")
                    raise

                delay = min(BASE_DELAY * (2**attempt), MAX_DELAY)
                logger.warning(
                    f"LLM request failed (attempt {attempt + 1}/{MAX_RETRIES}), "
                    f"retrying in {delay:.1f}s: {e}"
                )
                time.sleep(delay)

        raise last_error  # Should not reach here, but safety net

    def complete_json(
        self,
        prompt: str,
        model: str | None = None,
        images: list[bytes] | None = None,
        system: str | None = None,
    ) -> dict | list:
        """Send a request expecting JSON output.

        Wraps the prompt to request JSON and parses the response.
        Handles various code-fence formats in the response.
        """
        json_prompt = (
            f"{prompt}\n\n"
            "IMPORTANT: Respond with valid JSON only, no markdown formatting or code blocks."
        )

        # complete() retries transport failures; an answer that arrives but
        # carries no JSON is a separate failure and needs its own attempt.
        for attempt in range(JSON_RETRIES):
            try:
                return self._complete_json_once(
                    json_prompt, model=model, images=images, system=system
                )
            except EmptyCompletion as e:
                if attempt == JSON_RETRIES - 1:
                    raise
                logger.warning(f"Empty JSON body (attempt {attempt + 1}/{JSON_RETRIES}): {e}")
                time.sleep(BASE_DELAY)

        raise EmptyCompletion("provider returned no JSON body")

    def _complete_json_once(
        self,
        json_prompt: str,
        model: str | None = None,
        images: list[bytes] | None = None,
        system: str | None = None,
    ) -> dict | list:
        response = self.complete(json_prompt, model=model, images=images, system=system)

        # Robust code fence stripping
        text = response.strip()

        # Remove ```json ... ``` or ``` ... ``` blocks
        fence_pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)
        match = fence_pattern.match(text)
        if match:
            text = match.group(1).strip()

        if not text:
            # An empty fence is the same failure as an empty body, and the
            # retry loop handles it — but only if it is raised as one.
            raise EmptyCompletion("provider returned an empty JSON body")

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}\nRaw response: {response[:500]}")
            raise NotJSON(f"LLM did not return valid JSON: {e}", response) from e


# Singleton instance
_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
