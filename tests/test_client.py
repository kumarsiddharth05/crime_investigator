"""Tests for provider-agnostic LLM client, prompt builder, and response normalization.

All tests run completely offline with mocked transport calls.
No live API keys or external network connections are required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest
import httpx

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
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert "models/gemini-1.5-pro:generateContent" in str(request.url)
        assert request.headers["x-goog-api-key"] == "gemini-test-key"
        body = json.loads(request.content)
        assert body["generationConfig"]["temperature"] == 0.0
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "system_instruction" in body
        assert body["contents"][0]["role"] == "user"
        return httpx.Response(
            200,
            json={
                "modelVersion": "gemini-1.5-pro-002",
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(VALID_SUGGESTION_PAYLOAD)}]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 200,
                    "candidatesTokenCount": 50,
                    "totalTokenCount": 250,
                },
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="gemini", model="gemini-1.5-pro", api_key="gemini-test-key")

    with LLMClient(config=config, http_client=http_client) as client:
        result = client.analyze_case(sample_case_context, "spatial_inconsistency")

    assert result.status == "success"
    assert result.error is None
    assert len(result.suggestions) == 1
    assert result.provider == "gemini"
    assert result.model == "gemini-1.5-pro-002"
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
    """Verify Gemini multi-turn role conversation conversion ('user' -> 'model' -> 'user')."""
    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content)
        if call_count == 1:
            assert len(body["contents"]) == 1
            assert body["contents"][0]["role"] == "user"
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": "Not valid JSON"}]}}
                    ]
                },
            )
        # Attempt 2 has multi-turn history
        assert len(body["contents"]) == 3
        assert body["contents"][0]["role"] == "user"
        assert body["contents"][1]["role"] == "model"
        assert body["contents"][1]["parts"][0]["text"] == "Not valid JSON"
        assert body["contents"][2]["role"] == "user"
        assert "failed validation" in body["contents"][2]["parts"][0]["text"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(VALID_SUGGESTION_PAYLOAD)}]
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    config = LLMConfig(provider="gemini", model="gemini-1.5-pro", api_key="gemini-test-key")

    with LLMClient(config=config, http_client=http_client) as client:
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
