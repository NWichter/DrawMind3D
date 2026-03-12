"""LLM client using OpenRouter (OpenAI-compatible API) with retry logic."""

from __future__ import annotations

import base64
import json
import logging
import re
import time

from drawmind.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, VISION_MODEL, TEXT_MODEL

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds
MAX_DELAY = 30.0


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
                "No OPENROUTER_API_KEY configured. "
                "Get one at https://openrouter.ai/keys"
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
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })
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
                return response.choices[0].message.content

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                status = getattr(e, "status_code", None) or getattr(e, "code", None)

                # Determine if retryable
                retryable = (
                    status in (429, 500, 502, 503, 504)
                    or "rate" in err_str
                    or "timeout" in err_str
                    or "connection" in err_str
                    or "server" in err_str
                )

                if not retryable or attempt == MAX_RETRIES - 1:
                    logger.error(f"LLM request failed (attempt {attempt + 1}): {e}")
                    raise

                delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
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

        response = self.complete(json_prompt, model=model, images=images, system=system)

        # Robust code fence stripping
        text = response.strip()

        # Remove ```json ... ``` or ``` ... ``` blocks
        fence_pattern = re.compile(r'^```(?:json)?\s*\n?(.*?)\n?\s*```$', re.DOTALL)
        match = fence_pattern.match(text)
        if match:
            text = match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}\nRaw: {text[:500]}")
            raise ValueError(f"LLM did not return valid JSON: {e}") from e


# Singleton instance
_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
