"""Tests for provider-agnostic LLM client, prompt builder, and response normalization.

All tests run completely offline with mocked transport calls.
No live API keys or external network connections are required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import pytest
import httpx
from google.genai.errors import APIError

from src.llm import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    LLMAuthenticationError,
    LLMClient,
    LLMConfigurationError,
    LLMConfig,
    LLMRateLimitError,
    LLMResponse,
    LLMTransportError,
    build_prompt,
    call_llm,
    sanitize_case_context,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "cases"

VALID_SUGGESTION_PAYLOAD = {
    "suggestions": [
        {
            "type": "spatial_inconsistency",
            "severity": "medium",
            "summary": "Note places E1 near door while map summary places it near window.",
            "evidence_refs": ["notes.N1", "evidence.E1"],
            "reasoning": "N1 states evidence is near entrance, but map positions it across the room.",
            "suggested_action": "Verify physical placement of E1 against photo P1.",
        }
    ]
}

VALID_EMPTY_PAYLOAD = {"suggestions": []}


class MockGeminiUsage:
    def __init__(self, prompt: int = 200, completion: int = 50, total: int = 250):
        self.total_input_tokens = prompt
        self.total_output_tokens = completion
        self.total_tokens = total


class MockGeminiInteraction:
    def __init__(self, output_text: str, model: str = "gemini-3.8-flash", usage: Any = None):
        self.output_text = output_text
        self.model = model
        self.usage = usage or MockGeminiUsage()


class MockGenAIClient:
    def __init__(self, create_fn: Any):
        self.interactions = MagicMock()
        self.interactions.create = create_fn


@pytest.fixture
def sample_case_context() -> dict[str, Any]:
    c0_path = FIXTURES_DIR / "C0.json"
    return json.loads(c0_path.read_text(encoding="utf-8"))


# --- 1. Configuration Tests ---

def test_unsupported_provider():
    with pytest.raises(LLMConfigurationError, match="Unsupported LLM provider"):
        LLMConfig(provider="cohere", model="command-r", api_key="dummy-key")


def test_missing_provider(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(LLMConfigurationError, match="provider must be explicitly configured"):
        LLMConfig(provider=None, model="gpt-4o", api_key="dummy-key")


def test_missing_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(LLMConfigurationError, match="model must be explicitly configured"):
        LLMConfig(provider="openai", model=None, api_key="dummy-key")


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError, match="API key missing"):
        LLMConfig(provider="openai", model="gpt-4o", api_key=None)


def test_temperature_and_timeout():
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")
    assert config.temperature == DEFAULT_TEMPERATURE == 0.0
    assert config.timeout == DEFAULT_TIMEOUT_SECONDS == 20.0


# --- 2. Prompt Builder Tests ---

def test_prompt_builder_loads_prompts(sample_case_context):
    bundle = build_prompt(sample_case_context, "spatial_inconsistency")
    assert "You are a case analyst assistant" in bundle.system_prompt
    assert "spatial_inconsistency" in bundle.task_prompt
    assert "C-2026-001" in bundle.user_prompt
    assert bundle.assigned_analysis_type == "spatial_inconsistency"


def test_prompt_builder_invalid_type(sample_case_context):
    with pytest.raises(ValueError, match="Invalid assigned_analysis_type"):
        build_prompt(sample_case_context, "invalid_analysis_type")


def test_prompt_builder_sanitizes_images(sample_case_context):
    polluted_context = json.loads(json.dumps(sample_case_context))
    polluted_context["photos"][0]["image_bytes"] = "BINARY_DATA_HERE"
    polluted_context["photos"][0]["base64"] = "data:image/png;base64,iVBORw0KGgoAAAANS..."
    polluted_context["photos"][0]["file_path"] = "/tmp/evidence_photo.jpg"
    polluted_context["photos"][0]["url"] = "https://example.com/photo.jpg"

    bundle = build_prompt(polluted_context, "spatial_inconsistency")
    user_prompt = bundle.user_prompt

    assert "BINARY_DATA_HERE" not in user_prompt
    assert "image_bytes" not in user_prompt
    assert "base64" not in user_prompt
    assert "file_path" not in user_prompt
    assert "https://example.com/photo.jpg" not in user_prompt

    # Verify legitimate structured data is fully preserved
    assert "living_room" in user_prompt
    assert "knife" in user_prompt
    assert "photos.P1.d1" in user_prompt
    assert "bloody kitchen knife" in user_prompt


# --- 3. Provider Adapters & Normalization Tests ---

def test_openai_success_and_normalization(sample_case_context):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-openai-test"
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o"
        assert body["temperature"] == 0.0
        assert body["response_format"] == {"type": "json_object"}
        assert len(body["messages"]) == 2
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {"message": {"content": json.dumps(VALID_SUGGESTION_PAYLOAD)}}
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 45,
                    "total_tokens": 165,
                },
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-openai-test")

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert isinstance(result, LLMResponse)
    assert result.status == "success"
    assert result.error is None
    assert len(result.suggestions) == 1
    assert result.provider == "openai"
    assert result.model == "gpt-4o-2024-08-06"
    assert result.attempts == 1
    assert result.latency_ms >= 0.0
    assert result.usage == {
        "prompt_tokens": 120,
        "completion_tokens": 45,
        "total_tokens": 165,
    }


def test_gemini_success_and_normalization(sample_case_context):
    def mock_create(**kwargs):
        assert kwargs["model"] == "gemini-3.8-flash"
        assert kwargs["generation_config"]["temperature"] == 0.0
        assert kwargs["generation_config"]["thinking_level"] == "low"
        assert kwargs["response_format"] == {"type": "text", "mime_type": "application/json"}
        assert "system_instruction" in kwargs
        assert isinstance(kwargs["input"], str)
        return MockGeminiInteraction(
            output_text=json.dumps(VALID_SUGGESTION_PAYLOAD),
            model="gemini-3.8-flash",
            usage=MockGeminiUsage(prompt=200, completion=50, total=250),
        )

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert result.status == "success"
    assert result.error is None
    assert len(result.suggestions) == 1
    assert result.provider == "gemini"
    assert result.model == "gemini-3.8-flash"
    assert result.usage == {
        "prompt_tokens": 200,
        "completion_tokens": 50,
        "total_tokens": 250,
    }


def test_anthropic_success_and_normalization(sample_case_context):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "anthropic-test-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        body = json.loads(request.content)
        assert body["model"] == "claude-3-5-sonnet-20241022"
        assert body["max_tokens"] == 4096
        assert body["temperature"] == 0.0
        assert "system" in body
        assert body["messages"][0]["role"] == "user"
        return httpx.Response(
            200,
            json={
                "model": "claude-3-5-sonnet-20241022",
                "content": [{"type": "text", "text": json.dumps(VALID_SUGGESTION_PAYLOAD)}],
                "usage": {
                    "input_tokens": 150,
                    "output_tokens": 60,
                },
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        api_key="anthropic-test-key",
    )

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert result.status == "success"
    assert result.error is None
    assert len(result.suggestions) == 1
    assert result.provider == "anthropic"
    assert result.model == "claude-3-5-sonnet-20241022"
    assert result.usage == {
        "prompt_tokens": 150,
        "completion_tokens": 60,
        "total_tokens": 210,
    }


# --- 4. Distinguishing Genuine Empty Results vs Schema Failures ---

def test_genuine_empty_result_is_valid(sample_case_context):
    """Confirm a genuine valid empty response {'suggestions': []} is marked as successful."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(VALID_EMPTY_PAYLOAD)}}
                ]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert result.status == "success"
    assert result.error is None
    assert result.suggestions == []
    assert result["suggestions"] == []
    # Pipeline can unambiguously recognize success
    assert result["status"] == "success"


def test_exhausted_schema_retries_distinguishable_from_empty(sample_case_context):
    """Confirm exhausted retries produce an explicitly failed result that cannot be confused with valid empty."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Malformed Non-JSON Output"}}]},
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 3  # initial + 2 retries
    assert result.status == "schema_fail"
    assert result.error == "schema_fail"
    assert result["status"] == "schema_fail"
    assert result["error"] == "schema_fail"
    assert result.suggestions == []

    # Downstream pipeline check cannot confuse this with genuine empty success:
    assert result["status"] != "success"
    assert result["error"] is not None


# --- 5. Multi-turn Provider Message Conversion on Retries ---

def test_gemini_retry_message_conversion(sample_case_context):
    """Verify Gemini multi-turn role conversation conversion on retries."""
    call_count = 0

    def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            assert isinstance(kwargs["input"], str)
            return MockGeminiInteraction(output_text="Not valid JSON")
        # Attempt 2 has multi-turn history passed as list of contents
        input_data = kwargs["input"]
        assert isinstance(input_data, list)
        assert len(input_data) == 3
        assert input_data[0]["role"] == "user"
        assert input_data[1]["role"] == "model"
        assert input_data[1]["parts"][0]["text"] == "Not valid JSON"
        assert input_data[2]["role"] == "user"
        assert "failed validation" in input_data[2]["parts"][0]["text"]
        return MockGeminiInteraction(output_text=json.dumps(VALID_SUGGESTION_PAYLOAD))

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 2
    assert result.status == "success"
    assert len(result.suggestions) == 1


def test_anthropic_retry_message_conversion(sample_case_context):
    """Verify Anthropic multi-turn role conversation conversion ('user' -> 'assistant' -> 'user')."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content)
        if call_count == 1:
            assert len(body["messages"]) == 1
            assert body["messages"][0]["role"] == "user"
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "Not JSON"}]},
            )
        # Attempt 2
        assert len(body["messages"]) == 3
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][1]["role"] == "assistant"
        assert body["messages"][1]["content"] == "Not JSON"
        assert body["messages"][2]["role"] == "user"
        assert "failed validation" in body["messages"][2]["content"]
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": json.dumps(VALID_SUGGESTION_PAYLOAD)}]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        api_key="anthropic-test-key",
    )

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 2
    assert result.status == "success"
    assert len(result.suggestions) == 1


# --- 6. Retry on Schema Failure & Controlled Errors ---

def test_retry_on_schema_failure(sample_case_context):
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Valid JSON but missing required "suggestions" container
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps({"findings": []})}}]},
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(VALID_SUGGESTION_PAYLOAD)}}
                ]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 2
    assert result.status == "success"
    assert len(result.suggestions) == 1


def test_transport_error_handling(sample_case_context):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMTransportError, match="HTTP 502"):
            client.analyze_case(sample_case_context, "spatial_inconsistency")


def test_auth_error_handling(sample_case_context):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized: Invalid API key")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMAuthenticationError, match="Authentication failed \\(401\\)"):
            client.analyze_case(sample_case_context, "spatial_inconsistency")


def test_rate_limit_error_handling(sample_case_context):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit exceeded")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMRateLimitError, match="Rate limit exceeded \\(429\\)"):
            client.analyze_case(sample_case_context, "spatial_inconsistency")


# --- 7. Gemini Interactions API Dedicated Tests ---

def test_gemini_markdown_fence_cleaning(sample_case_context):
    """Verify JSON wrapped in markdown code fences is cleaned and parsed."""
    fenced_output = f"```json\n{json.dumps(VALID_SUGGESTION_PAYLOAD)}\n```"
    mock_client = MockGenAIClient(lambda **kwargs: MockGeminiInteraction(output_text=fenced_output))
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert result.status == "success"
    assert len(result.suggestions) == 1


def test_gemini_interactions_schema_failure_exhausted(sample_case_context):
    """Verify exhausted retries on invalid schema returns schema_fail status."""
    call_count = 0

    def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return MockGeminiInteraction(output_text=json.dumps({"invalid_root": True}))

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 3
    assert result.status == "schema_fail"
    assert result.error == "schema_fail"
    assert result.suggestions == []


def test_gemini_rate_limit_error_handling(sample_case_context):
    """Verify HTTP 429 / RESOURCE_EXHAUSTED maps to LLMRateLimitError."""
    def mock_create(**kwargs):
        raise APIError(429, {"error": {"message": "Rate limit exceeded for gemini-3.8-flash"}})

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        with pytest.raises(LLMRateLimitError, match="Rate limit exceeded"):
            client.analyze_case(sample_case_context, "spatial_inconsistency")


def test_gemini_auth_error_handling(sample_case_context):
    """Verify HTTP 401 / 403 maps to LLMAuthenticationError."""
    def mock_create(**kwargs):
        raise APIError(401, {"error": {"message": "API key not valid"}})

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        with pytest.raises(LLMAuthenticationError, match="Authentication failed"):
            client.analyze_case(sample_case_context, "spatial_inconsistency")


def test_gemini_transport_error_handling(sample_case_context):
    """Verify 5xx or network errors map to LLMTransportError."""
    def mock_create(**kwargs):
        raise APIError(500, {"error": {"message": "Internal error"}})

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        with pytest.raises(LLMTransportError, match="Gemini transport error"):
            client.analyze_case(sample_case_context, "spatial_inconsistency")


def test_gemini_missing_api_key(monkeypatch):
    """Verify missing Gemini API key raises LLMConfigurationError."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError, match="API key missing for provider 'gemini'"):
        LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key=None)


def test_gemini_dry_run_offline_no_network(sample_case_context):
    """Verify dry_run mode makes zero network requests and requires no API key."""
    # Top-level call_llm
    messages = [
        {"role": "system", "content": "You are a test assistant"},
        {"role": "user", "content": "Analyze case"},
    ]
    res1 = call_llm(messages, dry_run=True)
    assert res1["status"] == "success"
    assert res1["suggestions"] == []
    assert res1["latency_ms"] == 0.0

    # Client call_llm and analyze_case
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="dummy-key")
    with LLMClient(config=config) as client:
        res2 = client.call_llm(messages, dry_run=True)
        assert res2.status == "success"
        assert res2.suggestions == []
        assert res2.latency_ms == 0.0

        res3 = client.analyze_case(sample_case_context, "spatial_inconsistency", dry_run=True)
        assert res3.status == "success"
        assert res3.suggestions == []
        assert res3.latency_ms == 0.0


def test_gemini_usage_metadata_extraction(sample_case_context):
    """Verify exact token usage counts are preserved without fabrication."""
    usage_obj = MockGeminiUsage(prompt=312, completion=88, total=400)
    mock_client = MockGenAIClient(lambda **kwargs: MockGeminiInteraction(
        output_text=json.dumps(VALID_SUGGESTION_PAYLOAD),
        usage=usage_obj,
    ))
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert result.usage["prompt_tokens"] == 312
    assert result.usage["completion_tokens"] == 88
    assert result.usage["total_tokens"] == 400


def test_call_llm_public_api():
    """Verify call_llm public function signature and dispatch."""
    mock_create = MagicMock(return_value=MockGeminiInteraction(
        output_text=json.dumps(VALID_SUGGESTION_PAYLOAD),
        usage=MockGeminiUsage(prompt=50, completion=20, total=70),
    ))
    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    messages = [
        {"role": "system", "content": "System prompt here"},
        {"role": "user", "content": "User prompt here"},
    ]

    with LLMClient(config=config, genai_client=mock_client) as client:
        resp = client.call_llm(messages, dry_run=False)

    assert isinstance(resp, dict)
    assert resp["status"] == "success"
    assert len(resp["suggestions"]) == 1
    assert resp["usage"]["prompt_tokens"] == 50
    assert resp["usage"]["completion_tokens"] == 20


def test_429_fails_fast_no_retry(sample_case_context):
    """Verify HTTP 429 raises LLMRateLimitError after exactly one invocation without retrying."""
    call_count = 0

    def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        raise APIError(429, {"error": {"message": "Rate limit exceeded", "code": "too_many_requests"}})

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        with pytest.raises(LLMRateLimitError):
            client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 1


def test_503_fails_fast_no_retry(sample_case_context):
    """Verify HTTP 503 raises LLMTransportError after exactly one invocation without retrying."""
    call_count = 0

    def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        raise APIError(503, {"error": {"message": "Service unavailable", "code": "service_unavailable"}})

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        with pytest.raises(LLMTransportError):
            client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 1


def test_client_constructor_retry_options():
    """Verify genai.Client constructor is called with attempts=1 retry configuration."""
    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.interactions.create.return_value = MockGeminiInteraction(
            output_text=json.dumps(VALID_SUGGESTION_PAYLOAD)
        )
        mock_client_cls.return_value = mock_instance

        config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")
        client = LLMClient(config=config)
        messages = [{"role": "user", "content": "Analyze"}]
        client.call_llm(messages, dry_run=False)

        assert mock_client_cls.called
        call_kwargs = mock_client_cls.call_args.kwargs
        http_options = call_kwargs.get("http_options", {})
        # Per SDK preflight: retry_options MUST live inside http_options
        assert "retry_options" in http_options, (
            "retry_options must be nested inside http_options; "
            "the SDK does not accept it as a top-level client kwarg."
        )
        retry_opts = http_options["retry_options"]
        # retry_opts is a dict as passed by the client; attempts must be 1
        assert isinstance(retry_opts, dict), (
            f"expected dict, got {type(retry_opts).__name__}"
        )
        assert retry_opts.get("attempts") == 1, (
            f"expected attempts=1, got {retry_opts.get('attempts')}"
        )
        # Regression guard: must NOT also be passed at top level
        assert "retry_options" not in call_kwargs, (
            "retry_options must not be passed at top level; "
            "only inside http_options."
        )


def test_client_create_call_passes_timeout_and_no_continuation():
    """Verify interactions.create is called with timeout=20.0 and automatic_continuation=False."""
    captured_kwargs = {}

    def mock_create(**kwargs):
        captured_kwargs.update(kwargs)
        return MockGeminiInteraction(output_text=json.dumps(VALID_SUGGESTION_PAYLOAD))

    mock_client = MockGenAIClient(mock_create)
    config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key")

    with LLMClient(config=config, genai_client=mock_client) as client:
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User prompt"},
        ]
        resp = client.call_llm(messages, dry_run=False)

    assert resp["status"] == "success"
    assert captured_kwargs.get("timeout") == 20.0
    assert isinstance(captured_kwargs.get("timeout"), float)
    assert captured_kwargs.get("automatic_continuation") is False


def test_http_options_timeout_is_milliseconds():
    """Verify genai.Client http_options timeout is passed in milliseconds (20000)."""
    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.interactions.create.return_value = MockGeminiInteraction(
            output_text=json.dumps(VALID_SUGGESTION_PAYLOAD)
        )
        mock_client_cls.return_value = mock_instance

        config = LLMConfig(provider="gemini", model="gemini-3.8-flash", api_key="gemini-test-key", timeout=20.0)
        client = LLMClient(config=config)
        messages = [{"role": "user", "content": "Analyze"}]
        client.call_llm(messages, dry_run=False)

        assert mock_client_cls.called
        call_kwargs = mock_client_cls.call_args.kwargs
        http_options = call_kwargs.get("http_options", {})
        assert http_options.get("timeout") == 20000


# --- 8. OpenRouter Provider Tests ---

def test_openrouter_config_and_env_resolution(monkeypatch):
    """Verify OpenRouter provider, model, and OPENROUTER_API_KEY resolution."""
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-testkey")

    config = LLMConfig()
    assert config.provider == "openrouter"
    assert config.model == "meta-llama/llama-3.3-70b-instruct"
    assert config.api_key == "sk-or-v1-testkey"


def test_openrouter_missing_model_raises_error(monkeypatch):
    """Selecting OpenRouter without an explicit model produces a controlled configuration error."""
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    with pytest.raises(LLMConfigurationError, match="LLM model must be explicitly configured"):
        LLMConfig(provider="openrouter", model="")


def test_openrouter_missing_api_key_raises_error(monkeypatch):
    """Missing OpenRouter API key produces the expected controlled configuration error."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError, match="API key missing for provider 'openrouter'"):
        LLMConfig(provider="openrouter", model="meta-llama/llama-3.3-70b-instruct", api_key="")


def test_openrouter_request_dispatch_and_normalization(sample_case_context):
    """OpenRouter dispatch uses correct endpoint, auth header, model, and structured JSON payload."""
    recorded_requests = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-or-v1-test"
        assert request.headers["content-type"] == "application/json"
        body = json.loads(request.content)
        assert body["model"] == "anthropic/claude-3.5-sonnet"
        assert body["temperature"] == 0.0
        assert body["response_format"] == {"type": "json_object"}
        assert len(body["messages"]) >= 2
        return httpx.Response(
            200,
            json={
                "id": "gen-12345",
                "model": "anthropic/claude-3.5-sonnet",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(VALID_SUGGESTION_PAYLOAD),
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 45,
                    "total_tokens": 165,
                },
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(
        provider="openrouter",
        model="anthropic/claude-3.5-sonnet",
        api_key="sk-or-v1-test",
    )

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert len(recorded_requests) == 1
    assert result.status == "success"
    assert result.error is None
    assert result.provider == "openrouter"
    assert result.model == "anthropic/claude-3.5-sonnet"
    assert len(result.suggestions) == 1
    assert result.usage == {
        "prompt_tokens": 120,
        "completion_tokens": 45,
        "total_tokens": 165,
    }


def test_openrouter_rate_limit_error_handling(sample_case_context):
    """OpenRouter HTTP 429 maps to LLMRateLimitError identifying OpenRouter as provider."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit exceeded on OpenRouter")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openrouter", model="meta-llama/llama-3-8b", api_key="sk-or-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMRateLimitError) as exc_info:
            client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert "openrouter" in str(exc_info.value).lower()
    assert "429" in str(exc_info.value)


def test_openrouter_auth_error_handling(sample_case_context):
    """OpenRouter HTTP 401/403 maps to LLMAuthenticationError identifying OpenRouter."""
    for status_code in (401, 403):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, text="Invalid OpenRouter key")

        transport = httpx.MockTransport(mock_handler)
        http_client = httpx.Client(transport=transport)
        config = LLMConfig(provider="openrouter", model="meta-llama/llama-3-8b", api_key="sk-or-test")

        with LLMClient(config=config, http_client=http_client) as client:
            with pytest.raises(LLMAuthenticationError) as exc_info:
                client.analyze_case(sample_case_context, "spatial_inconsistency")

        assert "openrouter" in str(exc_info.value).lower()
        assert str(status_code) in str(exc_info.value)


def test_openrouter_transport_error_handling(sample_case_context):
    """OpenRouter HTTP 500 maps to LLMTransportError identifying OpenRouter."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error from upstream")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openrouter", model="meta-llama/llama-3-8b", api_key="sk-or-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMTransportError) as exc_info:
            client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert "openrouter" in str(exc_info.value).lower()
    assert "500" in str(exc_info.value)


# --- 9. Application-Level Attempt Control Tests ---

def test_max_attempts_one_makes_exactly_one_call(sample_case_context):
    """With max_attempts=1, a malformed response results in exactly one application-level call."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openrouter", model="test-model", api_key="sk-or-test")

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.call_llm(
            [{"role": "user", "content": "Analyze"}],
            dry_run=False,
            max_attempts=1,
        )

    assert call_count == 1
    assert result.status == "schema_fail"
    assert result.attempts == 1


def test_default_max_attempts_is_three(sample_case_context):
    """Without an explicit parameter, the existing default of three total attempts is preserved."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "broken"}}]})

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openrouter", model="test-model", api_key="sk-or-test")

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.call_llm(
            [{"role": "user", "content": "Analyze"}],
            dry_run=False,
        )

    assert call_count == 3
    assert result.status == "schema_fail"
    assert result.attempts == 3


@pytest.mark.parametrize("invalid_val", [0, -1, -5])
def test_max_attempts_zero_or_negative_rejected(invalid_val):
    """max_attempts <= 0 is rejected with LLMConfigurationError."""
    config = LLMConfig(provider="openrouter", model="test-model", api_key="sk-or-test")
    client = LLMClient(config=config)
    with pytest.raises(LLMConfigurationError, match="max_attempts must be a positive integer"):
        client.call_llm([{"role": "user", "content": "Analyze"}], max_attempts=invalid_val)


@pytest.mark.parametrize("invalid_val", [True, False])
def test_max_attempts_boolean_rejected(invalid_val):
    """A boolean value is rejected with LLMConfigurationError."""
    config = LLMConfig(provider="openrouter", model="test-model", api_key="sk-or-test")
    client = LLMClient(config=config)
    with pytest.raises(LLMConfigurationError, match="max_attempts must be a positive integer"):
        client.call_llm([{"role": "user", "content": "Analyze"}], max_attempts=invalid_val)


@pytest.mark.parametrize("invalid_val", [1.0, 2.5, "3", None])
def test_max_attempts_non_integer_rejected(invalid_val):
    """A float or other non-integer value is rejected with LLMConfigurationError."""
    config = LLMConfig(provider="openrouter", model="test-model", api_key="sk-or-test")
    client = LLMClient(config=config)
    with pytest.raises(LLMConfigurationError, match="max_attempts must be a positive integer"):
        client.call_llm([{"role": "user", "content": "Analyze"}], max_attempts=invalid_val)


# --- 10. HTTP Transport & Status Retry Behavior Tests ---

def test_http_500_handled_once_no_http_retry(sample_case_context):
    """HTTP 500 status response is handled once without HTTP-level retrying."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openrouter", model="test-model", api_key="sk-or-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMTransportError):
            client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 1


def test_http_429_handled_once_no_http_retry(sample_case_context):
    """HTTP 429 status response is handled once without HTTP-level retrying."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, text="Too Many Requests")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openrouter", model="test-model", api_key="sk-or-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMRateLimitError):
            client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 1


def test_genuine_transport_connection_error_no_retry(sample_case_context):
    """httpx.ConnectError raises LLMTransportError with exactly one transport attempt."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Failed to establish a new connection: [Errno 111] Connection refused")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="openrouter", model="test-model", api_key="sk-or-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMTransportError) as exc_info:
            client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert call_count == 1
    assert "transport error" in str(exc_info.value).lower()
    assert "connection refused" in str(exc_info.value).lower()


# --- 10. Groq Provider Integration Tests ---

def test_groq_config_and_env_resolution(monkeypatch):
    """Groq provider and model configure correctly via arguments or environment variables."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key-12345")

    config = LLMConfig()
    assert config.provider == "groq"
    assert config.model == "openai/gpt-oss-120b"
    assert config.api_key == "gsk-test-key-12345"


def test_groq_default_model_resolution(monkeypatch):
    """Groq provider defaults to openai/gpt-oss-120b when LLM_MODEL is unset."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key-12345")

    config = LLMConfig()
    assert config.provider == "groq"
    assert config.model == "openai/gpt-oss-120b"
    assert config.api_key == "gsk-test-key-12345"


def test_groq_missing_api_key_raises_error(monkeypatch):
    """Missing Groq API key raises LLMConfigurationError."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError, match="API key missing for provider 'groq'"):
        LLMConfig(provider="groq", model="openai/gpt-oss-120b", api_key="")


def test_groq_request_dispatch_and_normalization(sample_case_context):
    """Groq call dispatches to Groq chat completions endpoint with normalized response."""
    recorded_requests = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer gsk-groq-test"
        assert request.headers["content-type"] == "application/json"

        body = json.loads(request.content)
        assert body["model"] == "openai/gpt-oss-120b"
        assert body["temperature"] == 0.0
        assert body["response_format"] == {"type": "json_object"}
        assert len(body["messages"]) >= 2
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-groq-123",
                "object": "chat.completion",
                "model": "openai/gpt-oss-120b",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(VALID_SUGGESTION_PAYLOAD),
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 150,
                    "completion_tokens": 40,
                    "total_tokens": 190,
                },
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(
        provider="groq",
        model="openai/gpt-oss-120b",
        api_key="gsk-groq-test",
    )

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert len(recorded_requests) == 1
    assert result.status == "success"
    assert result.error is None
    assert result.provider == "groq"
    assert result.model == "openai/gpt-oss-120b"
    assert len(result.suggestions) == 1
    assert result.usage == {
        "prompt_tokens": 150,
        "completion_tokens": 40,
        "total_tokens": 190,
    }


def test_groq_rate_limit_error_handling(sample_case_context):
    """Groq HTTP 429 maps to LLMRateLimitError identifying Groq as provider."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit reached for Groq organization")

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="groq", model="openai/gpt-oss-120b", api_key="gsk-groq-test")

    with LLMClient(config=config, http_client=http_client) as client:
        with pytest.raises(LLMRateLimitError) as exc_info:
            client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert "groq" in str(exc_info.value).lower()
    assert "429" in str(exc_info.value)





