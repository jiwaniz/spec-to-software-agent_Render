"""
Requirement Agent — Day 2.

Two-stage guardrail:
1. Keyword check (free, instant) — catches obvious out-of-scope asks
   (React frontend, Docker, GraphQL, etc.) before spending a Groq call.
2. LLM classification (only if step 1 passes) — confirms it's a plain
   CRUD app, picks the closest supported domain, extracts an app_name,
   and detects if the user is asking for authentication.
"""

from app.schemas import RequirementOutput
from app.agents.llm_json import call_llm_for_json

SUPPORTED_DOMAINS = [
    "Inventory Management",
    "Expense Tracking",
    "Leave Management",
    "Student Registration",
    "Library Management",
]

# Anything matching these = auto-reject, no LLM call needed.
OUT_OF_SCOPE_KEYWORDS = [
    "react", "vue", "angular", "next.js", "frontend framework",
    "docker", "kubernetes", "microservice", "kafka", "redis", "celery",
    "graphql", "mongodb", "postgres", "postgresql", "mysql",
    "oauth", "social login", "google login", "payment", "stripe",
    "websocket", "real-time chat", "live chat",
    "machine learning model", "image recognition", "computer vision",
    "file upload", "image upload", "video upload",
    "email sending", "sms", "notification service",
    "mobile app", "flutter", "ios app", "android app",
]


def _keyword_reject(text: str) -> str | None:
    lowered = text.lower()
    for kw in OUT_OF_SCOPE_KEYWORDS:
        if kw in lowered:
            return kw
    return None


SYSTEM_PROMPT = f"""You are the Requirement Agent in a spec-driven software generation pipeline.

The pipeline ONLY supports generating small Python FastAPI + SQLite CRUD applications.
Supported domains are: {", ".join(SUPPORTED_DOMAINS)}.

Given a user's free-text app description, decide:
- in_scope: true only if this is a plain CRUD API that reasonably fits one of the
  supported domains (or a close variant of one). False for anything requiring a
  frontend framework, a different database, real-time features, file/image handling,
  external payment/auth providers, ML models, or mobile apps.
- rejection_reason: null if in_scope is true, otherwise a short plain-English reason
- app_name: a short, filesystem-safe, snake_case app name (e.g. "expense_tracker")
- domain: pick the closest match from the supported domains list above
- auth_enabled: true if the user explicitly asked for login/authentication/user accounts

Return JSON matching this exact structure:
{{
  "in_scope": bool,
  "rejection_reason": string or null,
  "app_name": string,
  "domain": string,
  "raw_description": string (echo the user's original text back),
  "auth_enabled": bool
}}
"""


def run_requirement_agent(raw_description: str) -> RequirementOutput:
    keyword_hit = _keyword_reject(raw_description)
    if keyword_hit:
        return RequirementOutput(
            in_scope=False,
            rejection_reason=(
                f"Request mentions '{keyword_hit}', which is outside this tool's scope "
                f"(Python FastAPI + SQLite CRUD apps only)."
            ),
            app_name="rejected",
            domain="N/A",
            raw_description=raw_description,
            auth_enabled=False,
        )

    result = call_llm_for_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=f"User's app description:\n{raw_description}",
        model=RequirementOutput,
    )
    return result  # type: ignore[return-value]


if __name__ == "__main__":
    # Manual tests — run locally with GROQ_API_KEY set.
    test_cases = [
        "Build an inventory management API with products, categories, and low-stock alerts.",
        "Build me a React dashboard with a Node.js backend and MongoDB.",
        "I need an expense tracker with login so users only see their own expenses.",
    ]
    for case in test_cases:
        print(f"\n--- Input: {case}")
        result = run_requirement_agent(case)
        print(result.model_dump_json(indent=2))
