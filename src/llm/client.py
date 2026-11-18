"""Provider-agnostic LLM client implementation.

Provides a unified interface to OpenAI, Gemini, and Anthropic with:
- Fixed temperature 0.0 and timeout 20.0 seconds
- Explicit model configuration (no stale defaults)
- Structured JSON output mode across providers
- Controlled retries (up to 2 retries, 3 total attempts) for schema/parsing errors
- Normalized response container distinguishing genuine empty results from schema failures
- Consistent token usage, latency, model identity, and raw response normalization
- Non-retryable controlled exceptions for transport, auth, and rate limit errors
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from src.llm.prompt_builder import PromptBundle, build_prompt

SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"openai", "gemini", "anthropic"})
REQUIRED_SUGGESTION_KEYS: frozenset[str] = frozenset({
    "type",
    "severity",
    "summary",
    "evidence_refs",
    "reasoning",
    "suggested_action",
})

DEFAULT_TIMEOUT_SECONDS: float = 20.0
DEFAULT_TEMPERATURE: float = 0.0


# --- Exception Hierarchy ---

class LLMClientError(Exception):
    """Base exception for all LLM client errors."""


class LLMConfigurationError(LLMClientError, ValueError):
    """Raised when provider, model, or API key configuration is missing or invalid."""


class LLMTransportError(LLMClientError):
    """Raised on network failures, timeouts, connection drops, or HTTP 5xx errors."""


class LLMAuthenticationError(LLMClientError):
    """Raised when provider authentication fails (HTTP 401 / 403)."""


class LLMRateLimitError(LLMClientError):
    """Raised when provider rate limit or quota is exceeded (HTTP 429)."""


# --- Configuration ---

class LLMConfig:
    """Explicit configuration for the LLM client."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> None:
        self.provider = (provider or os.environ.get("LLM_PROVIDER", "")).strip().lower()
        self.model = (model or os.environ.get("LLM_MODEL", "")).strip()
        self.timeout = float(timeout)
        self.temperature = float(temperature)

        if not self.provider:
            raise LLMConfigurationError(
                "LLM provider must be explicitly configured via provider argument or LLM_PROVIDER."
            )
        if self.provider not in SUPPORTED_PROVIDERS:
            raise LLMConfigurationError(
                f"Unsupported LLM provider: {self.provider!r}. Must be one of: {sorted(SUPPORTED_PROVIDERS)}"
            )

        if not self.model:
            raise LLMConfigurationError(
                "LLM model must be explicitly configured via model argument or LLM_MODEL."
            )

        # Determine API key based on provider
        resolved_key = api_key
        if not resolved_key:
            env_var_map = {
                "openai": "OPENAI_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
            }
            env_var = env_var_map.get(self.provider)
            if env_var:
                resolved_key = os.environ.get(env_var)

        if not resolved_key or not resolved_key.strip():
            raise LLMConfigurationError(
                f"API key missing for provider '{self.provider}'. "
                f"Set via api_key argument or environment variable."
            )
        self.api_key = resolved_key.strip()


# --- Normalized Response Container ---

class LLMResponse(dict):
    """Normalized response dictionary returned by LLMClient.analyze_case.

    Explicitly differentiates between a successful analysis (including genuine empty suggestions)
    and a terminal schema failure.
    """

    @property
    def suggestions(self) -> list[dict[str, Any]]:
        return self.get("suggestions", [])

    @property
    def status(self) -> str:
        return self.get("status", "")

    @property
    def error(self) -> str | None:
        return self.get("error")

    @property
    def raw_response(self) -> str:
        return self.get("raw_response", "")

    @property
    def provider(self) -> str:
        return self.get("provider", "")

    @property
    def model(self) -> str:
        return self.get("model", "")

    @property
    def attempts(self) -> int:
        return self.get("attempts", 1)

    @property
    def latency_ms(self) -> float:
        return self.get("latency_ms", 0.0)

    @property
    def usage(self) -> dict[str, int]:
        return self.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})


# --- Response Shape Validation ---

def validate_response_shape(raw_text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Validate JSON parsing and basic suggestion container shape.

    Does not duplicate the 7 downstream validator checks; verifies only
    envelope integrity and required field presence.
    """
    try:
        data = json.loads(raw_text)
    except Exception as exc:
        return None, f"JSON parse failure: {exc}"

    if not isinstance(data, dict):
        return None, "Root response must be a JSON object"

    if "suggestions" not in data or not isinstance(data["suggestions"], list):
        return None, "Missing top-level 'suggestions' list"

    for idx, item in enumerate(data["suggestions"]):
        if not isinstance(item, dict):
            return None, f"Suggestion item at index {idx} must be a JSON object"
        missing = REQUIRED_SUGGESTION_KEYS - item.keys()
        if missing:
            return None, f"Suggestion item at index {idx} missing keys: {sorted(missing)}"
        if not isinstance(item.get("evidence_refs"), list):
            return None, f"Suggestion item at index {idx} 'evidence_refs' must be a list"

    return data, None


# --- Provider Adapters & Client ---

class LLMClient:
    """Provider-agnostic LLM client with isolated adapters, normalization, and controlled retries."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config or LLMConfig()
        self._http_client = http_client or httpx.Client(timeout=self.config.timeout)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http_client.close()

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def analyze_case(
        self,
        case_context: dict[str, Any],
        assigned_analysis_type: str,
    ) -> LLMResponse:
        """Execute one analysis invocation with controlled retries on schema failure.

        Returns:
            LLMResponse containing normalized fields:
            - suggestions: list[dict]
            - status: "success" | "schema_fail"
            - error: None | "schema_fail"
            - raw_response: str
            - provider: str
            - model: str
            - attempts: int
            - latency_ms: float
            - usage: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        """
        bundle = build_prompt(case_context, assigned_analysis_type)

        history: list[tuple[str, str]] = []  # list of (assistant_raw, user_correction)
        max_attempts = 3
        start_time = time.perf_counter()

        last_raw_text = ""
        last_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        last_model = self.config.model

        for attempt in range(1, max_attempts + 1):
            raw_text, usage, model_name = self._dispatch_call(bundle, history)
            last_raw_text = raw_text
            last_usage = usage
            if model_name:
                last_model = model_name

            parsed_data, err_msg = validate_response_shape(raw_text)

            if parsed_data is not None:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return LLMResponse({
                    "suggestions": parsed_data["suggestions"],
                    "status": "success",
                    "error": None,
                    "raw_response": raw_text,
                    "provider": self.config.provider,
                    "model": last_model,
                    "attempts": attempt,
                    "latency_ms": latency_ms,
                    "usage": last_usage,
                })

            if attempt < max_attempts:
                correction = (
                    f"Your previous response failed validation: {err_msg}. "
                    f"Return ONLY valid JSON with top-level 'suggestions' list, "
                    f"where each suggestion contains: type, severity, summary, "
                    f"evidence_refs, reasoning, suggested_action."
                )
                history.append((raw_text, correction))

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return LLMResponse({
            "suggestions": [],
            "status": "schema_fail",
            "error": "schema_fail",
            "raw_response": last_raw_text,
            "provider": self.config.provider,
            "model": last_model,
            "attempts": max_attempts,
            "latency_ms": latency_ms,
            "usage": last_usage,
        })

    def _dispatch_call(
        self,
        bundle: PromptBundle,
        history: list[tuple[str, str]],
    ) -> tuple[str, dict[str, int], str]:
        """Route call to the provider-specific isolated handler.

        Returns:
            tuple of (raw_text, normalized_usage, model_name)
        """
        if self.config.provider == "openai":
            return self._call_openai(bundle, history)
        if self.config.provider == "gemini":
            return self._call_gemini(bundle, history)
        if self.config.provider == "anthropic":
            return self._call_anthropic(bundle, history)
        raise LLMConfigurationError(f"Unsupported provider: {self.config.provider}")

    def _handle_http_errors(self, response: httpx.Response) -> None:
        """Map HTTP error status codes to controlled exceptions."""
        status = response.status_code
        if status in (401, 403):
            raise LLMAuthenticationError(
                f"Authentication failed ({status}) for provider '{self.config.provider}': {response.text}"
            )
        if status == 429:
            raise LLMRateLimitError(
                f"Rate limit exceeded (429) for provider '{self.config.provider}': {response.text}"
            )
        if status >= 400:
            raise LLMTransportError(
                f"HTTP {status} error from provider '{self.config.provider}': {response.text}"
            )

    # --- OpenAI Adapter ---

    def _call_openai(
        self, bundle: PromptBundle, history: list[tuple[str, str]]
    ) -> tuple[str, dict[str, int], str]:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        messages: list[dict[str, str]] = [
            {"role": "system", "content": bundle.system_prompt},
            {"role": "user", "content": bundle.user_prompt},
        ]
        for assistant_reply, user_retry in history:
            messages.append({"role": "assistant", "content": assistant_reply})
            messages.append({"role": "user", "content": user_retry})

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"},
        }

        try:
            res = self._http_client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
            raise LLMTransportError(f"OpenAI transport error: {exc}") from exc

        self._handle_http_errors(res)

        try:
            body = res.json()
            raw_text = str(body["choices"][0]["message"]["content"])
            model_name = str(body.get("model", self.config.model))
            usage_data = body.get("usage", {})
            usage = {
                "prompt_tokens": int(usage_data.get("prompt_tokens", 0)),
                "completion_tokens": int(usage_data.get("completion_tokens", 0)),
                "total_tokens": int(usage_data.get("total_tokens", 0)),
            }
            return raw_text, usage, model_name
        except Exception as exc:
            raise LLMTransportError(f"Unexpected response structure from OpenAI: {exc}") from exc

    # --- Gemini Adapter ---

    def _call_gemini(
        self, bundle: PromptBundle, history: list[tuple[str, str]]
    ) -> tuple[str, dict[str, int], str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config.model}:generateContent"
        headers = {
            "x-goog-api-key": self.config.api_key,
            "Content-Type": "application/json",
        }
        contents: list[dict[str, Any]] = [
            {"role": "user", "parts": [{"text": bundle.user_prompt}]}
        ]
        for assistant_reply, user_retry in history:
            contents.append({"role": "model", "parts": [{"text": assistant_reply}]})
            contents.append({"role": "user", "parts": [{"text": user_retry}]})

        # Sends system_instruction, contents, temperature 0.0, and responseMimeType
        payload = {
            "system_instruction": {"parts": [{"text": bundle.system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": self.config.temperature,
                "responseMimeType": "application/json",
            },
        }

        try:
            res = self._http_client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
            raise LLMTransportError(f"Gemini transport error: {exc}") from exc

        self._handle_http_errors(res)

        try:
            body = res.json()
            raw_text = str(body["candidates"][0]["content"]["parts"][0]["text"])
            model_name = str(body.get("modelVersion", self.config.model))
            meta = body.get("usageMetadata", {})
            prompt_tokens = int(meta.get("promptTokenCount", 0))
            completion_tokens = int(meta.get("candidatesTokenCount", 0))
            total_tokens = int(meta.get("totalTokenCount", prompt_tokens + completion_tokens))
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
            return raw_text, usage, model_name
        except Exception as exc:
            raise LLMTransportError(f"Unexpected response structure from Gemini: {exc}") from exc

    # --- Anthropic Adapter ---

    def _call_anthropic(
        self, bundle: PromptBundle, history: list[tuple[str, str]]
    ) -> tuple[str, dict[str, int], str]:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        messages: list[dict[str, str]] = [
            {"role": "user", "content": bundle.user_prompt}
        ]
        for assistant_reply, user_retry in history:
            messages.append({"role": "assistant", "content": assistant_reply})
            messages.append({"role": "user", "content": user_retry})

        payload = {
            "model": self.config.model,
            "max_tokens": 4096,
            "system": bundle.system_prompt,
            "messages": messages,
            "temperature": self.config.temperature,
        }

        try:
            res = self._http_client.post(url, headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
            raise LLMTransportError(f"Anthropic transport error: {exc}") from exc

        self._handle_http_errors(res)

        try:
            body = res.json()
            raw_text = str(body["content"][0]["text"])
            model_name = str(body.get("model", self.config.model))
            usage_data = body.get("usage", {})
            prompt_tokens = int(usage_data.get("input_tokens", 0))
            completion_tokens = int(usage_data.get("output_tokens", 0))
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }
            return raw_text, usage, model_name
        except Exception as exc:
            raise LLMTransportError(f"Unexpected response structure from Anthropic: {exc}") from exc
