"""
Thin wrapper around the Groq client. Every agent should call through
these two functions rather than hitting the Groq SDK directly, so the
model name stays fixed in one place (required for a fair baseline
comparison) and streaming behaves consistently everywhere.
"""

import os
import time
from collections.abc import Generator
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

_client: Groq | None = None
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 2


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Copy .env.example to .env and add your key."
            )
        _client = Groq(api_key=api_key)
    return _client


def get_model() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def complete(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """Non-streaming call. Use for agents whose output must be parsed as one JSON blob.
    Retries on transient errors (rate limits, timeouts, connection issues)."""
    client = get_client()
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=get_model(),
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_transient = any(kw in error_str for kw in ["rate limit", "timeout", "connection", "429", "503", "502"])
            if not is_transient or attempt == _MAX_RETRIES - 1:
                raise
            wait = _RETRY_BACKOFF_SECONDS * (2 ** attempt)
            print(f"[Groq] transient error ({e}), retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})...")
            time.sleep(wait)
    raise last_error  # pragma: no cover


def stream(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Generator[str, None, None]:
    """
    Streaming call. Yields text chunks as they arrive.
    Use this for the Coding Agent so Gradio can show live progress.
    """
    client = get_client()
    completion = client.chat.completions.create(
        model=get_model(),
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        stream=True,
    )
    for chunk in completion:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


if __name__ == "__main__":
    # Quick manual test — run locally with a real GROQ_API_KEY in .env.
    # (Not run here: this sandbox has no network access to api.groq.com.)
    print("Non-streaming test:")
    print(complete("You are a helpful assistant.", "Say hello in exactly 5 words."))

    print("\nStreaming test:")
    for piece in stream("You are a helpful assistant.", "Count from 1 to 5, one number per line."):
        print(piece, end="", flush=True)
    print()
