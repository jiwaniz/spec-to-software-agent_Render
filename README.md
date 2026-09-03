# Spec-to-Software Agent

A spec-driven, multi-agent pipeline that turns a plain-English app description
into a working FastAPI + SQLite CRUD application, with generated tests, a
real validation report, and an ER diagram — via a Gradio UI.

## What it does

```
Requirement -> Specification -> Planning -> Task -> RAG Retrieval -> Coding
  -> Testing -> Validation (real pytest) -> Correction loop (max 2 cycles)
  -> Diagram -> Report -> ZIP
```

Supported domains: Inventory Management, Expense Tracking, Leave Management,
Student Registration, Library Management (small CRUD apps only, by design).

## Architecture

- **LangGraph** orchestrates 12 nodes (`app/graph_sketch.py`)
- **Groq** (free tier) is the LLM, used only where an LLM adds value:
  classifying requests, writing the structured spec, and writing the
  business logic for non-standard ("custom") endpoints
- **Jinja2 templates** deterministically generate all standard CRUD code,
  SQLAlchemy models, Pydantic schemas, and pytest tests — no LLM call
  needed for the mechanical 90% of the output
- **RAG grounding**: a hand-written bank of 5 gold-standard specs, embedded
  with `sentence-transformers`, grounds the Coding Agent's style
- **Real validation**: pytest actually runs against the generated project
  in a temp directory; failures feed back into a 2-cycle self-correction
  loop with the actual assertion error as context

See `app/agents/` for each agent and `app/templates/` for the Jinja2 templates.

## Setup

```bash
python -m venv venv
source venv/bin/activate      # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env          # add your GROQ_API_KEY
```

## Run

```bash
python ui.py
```
Opens a Gradio app at `http://127.0.0.1:7860`.

## Verify each stage (optional, no UI needed)

```bash
python -m app.agents.requirement_agent
python -m app.agents.specification_agent
python -m app.codegen.render
python test_day4_live.py    # Coding Agent, real end-to-end run
python test_day5_live.py    # Testing + Validation, real pytest
python test_day6_live.py    # Correction loop, real bug injection + fix
python -m app.agents.refinement_agent
```

## Deploy to Hugging Face Spaces

1. Create a new Space (Gradio SDK)
2. Push this repo's contents; rename `README_HF.md` -> `README.md` in the Space
3. Add `GROQ_API_KEY` as a Space secret
4. Space builds from `app.py`

## Security

Generated code is never executed inside a public deployment — validation
(including running pytest) only happens locally/server-side, and the public
UI only ever shows generated files for download, never runs arbitrary code
client-visible-side.

## Limitations (by design, not oversights)

- CRUD FastAPI + SQLite apps only, 5 supported domains
- Auth scaffold is a demo JWT flow with hardcoded credentials, template-generated
  (not LLM-improvised) specifically to avoid an LLM inventing insecure auth code
- Correction loop caps at 2 cycles
