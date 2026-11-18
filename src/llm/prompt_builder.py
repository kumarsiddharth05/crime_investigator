"""Prompt builder for LLM analysis queries.

Constructs provider-agnostic system and task prompts, incorporating
structured case context while guaranteeing that no binary images,
image paths, or base64 payloads reach the language model.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

PERMITTED_TIER_B_TYPES: frozenset[str] = frozenset({
    "spatial_inconsistency",
    "timeline_contradiction",
    "contextual_contradiction",
})

PROHIBITED_IMAGE_KEYS: frozenset[str] = frozenset({
    "image",
    "image_bytes",
    "bytes",
    "data",
    "base64",
    "b64",
    "image_path",
    "file_path",
    "url",
    "image_url",
    "thumbnail",
})

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts" / "v1"


def sanitize_case_context(data: Any) -> Any:
    """Recursively strip prohibited image/binary/path fields from case context.
    
    Preserves all legitimate structural case data including references,
    text notes, detection metadata, summaries, dimensions, and timeline entries.
    """
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for key, value in data.items():
            if key in PROHIBITED_IMAGE_KEYS:
                continue
            cleaned[key] = sanitize_case_context(value)
        return cleaned
    if isinstance(data, list):
        return [sanitize_case_context(item) for item in data]
    return data


def load_prompt_text(filename: str) -> str:
    """Load prompt file from the prompts/v1 directory."""
    path = PROMPTS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()


class PromptBundle:
    """Container for assembled system prompt, task prompt, and sanitized case context."""

    def __init__(
        self,
        assigned_analysis_type: str,
        system_prompt: str,
        task_prompt: str,
        sanitized_context: dict[str, Any],
    ) -> None:
        self.assigned_analysis_type = assigned_analysis_type
        self.system_prompt = system_prompt
        self.task_prompt = task_prompt
        self.sanitized_context = sanitized_context

    @property
    def user_prompt(self) -> str:
        """Compose the user prompt containing task instructions and JSON case context."""
        context_json = json.dumps(self.sanitized_context, indent=2, ensure_ascii=False)
        return (
            f"=== TASK INSTRUCTION: {self.assigned_analysis_type} ===\n\n"
            f"{self.task_prompt}\n\n"
            f"=== CASE CONTEXT (DATA ONLY) ===\n\n"
            f"{context_json}\n\n"
            f"=== END OF CASE CONTEXT ===\n"
            f"Return strict JSON matching the schema defined in the system prompt."
        )

    def to_openai_messages(self) -> list[dict[str, str]]:
        """Return messages list suitable for OpenAI chat completions."""
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_prompt},
        ]

    def to_anthropic_payload(self, max_tokens: int = 4096) -> dict[str, Any]:
        """Return parameters suitable for Anthropic messages API."""
        return {
            "system": self.system_prompt,
            "messages": [{"role": "user", "content": self.user_prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }

    def to_gemini_payload(self) -> dict[str, Any]:
        """Return parameters suitable for Gemini generateContent API."""
        return {
            "system_instruction": {"parts": [{"text": self.system_prompt}]},
            "contents": [{"parts": [{"text": self.user_prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }


def build_prompt(
    case_context: dict[str, Any],
    assigned_analysis_type: str,
) -> PromptBundle:
    """Validate analysis type, sanitize context, and build prompt bundle.
    
    Raises:
        ValueError: If assigned_analysis_type is not one of the permitted Tier B types.
    """
    if assigned_analysis_type not in PERMITTED_TIER_B_TYPES:
        raise ValueError(
            f"Invalid assigned_analysis_type: {assigned_analysis_type!r}. "
            f"Must be one of: {sorted(PERMITTED_TIER_B_TYPES)}"
        )

    system_prompt = load_prompt_text("system.md")
    task_prompt = load_prompt_text(f"{assigned_analysis_type}.md")
    sanitized_context = sanitize_case_context(copy.deepcopy(case_context))

    return PromptBundle(
        assigned_analysis_type=assigned_analysis_type,
        system_prompt=system_prompt,
        task_prompt=task_prompt,
        sanitized_context=sanitized_context,
    )
