"""
Shared helper: call Groq, expect JSON back, validate it against a Pydantic
model. Every structured agent (Requirement, Specification, Planning, ...)
should go through this rather than parsing JSON by hand — keeps the
"self-correction on bad output" logic in one place.
"""

import json
import re
from pydantic import BaseModel, ValidationError

from app.groq_client import complete

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    """LLMs love wrapping JSON in ```json ... ``` even when told not to. Strip it."""
    return _JSON_FENCE_RE.sub("", text).strip()


def call_llm_for_json(
    system_prompt: str,
    user_prompt: str,
    model: type[BaseModel],
    max_retries: int = 2,
    temperature: float = 0.2,
) -> BaseModel:
    """
    Calls Groq, parses the response as JSON, validates against `model`.
    On failure (bad JSON or schema mismatch), re-prompts once with the
    error message included so the LLM can fix its own output.
    """
    full_system_prompt = (
        f"{system_prompt}\n\n"
        "Respond with ONLY raw JSON. No markdown code fences, no preamble, "
        "no explanation before or after the JSON."
    )

    last_error: str | None = None
    current_user_prompt = user_prompt

    for attempt in range(max_retries + 1):
        raw = complete(full_system_prompt, current_user_prompt, temperature=temperature)
        cleaned = _strip_code_fences(raw)

        try:
            data = json.loads(cleaned)
            return model.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)
            current_user_prompt = (
                f"{user_prompt}\n\n"
                f"Your previous response caused this error:\n{last_error}\n\n"
                f"Your previous response was:\n{cleaned}\n\n"
                "Fix the issue and return ONLY corrected, valid JSON matching the required schema."
            )

    raise ValueError(
        f"LLM failed to produce valid {model.__name__} after {max_retries + 1} attempts. "
        f"Last error: {last_error}"
    )
