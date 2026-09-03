"""
Testing Agent -- Day 5.

Standard CRUD tests are fully deterministic (see app/codegen/context.py's
build_test_context and app/templates/test_api.py.j2) -- no LLM needed,
since the shape of a CRUD test is entirely mechanical given the spec.

The ONLY thing the LLM writes is the body of each custom endpoint's test
function (e.g. testing the low-stock filter actually filters correctly).
Same reasoning and same splice-and-validate pattern as the Coding Agent:
small blast radius, syntax-validated before acceptance, grounded by the
endpoint's actual functional requirement so the assertions test the
right thing instead of just smoke-testing a 200 status code.
"""

import ast
import re

from app.schemas import SpecOutput, GeneratedFile
from app.codegen.context import build_template_context
from app.codegen.render import render_test_file
from app.agents.code_gen_utils import generate_code_body


def _matching_acceptance_criteria(spec: SpecOutput, fr_ids: list[str]) -> str:
    matches = [fr for fr in spec.functional_requirements if fr.id in fr_ids]
    if not matches:
        return "(no matching functional requirement found)"
    return "\n".join(f"- {fr.id}: {fr.description} -- Acceptance: {fr.acceptance_criteria}" for fr in matches)


def _build_system_prompt(entity_reference: str, acceptance_criteria: str) -> str:
    return f"""You are the Testing Agent in a spec-driven FastAPI code generation pipeline.

You must write ONLY the body of one pytest test function -- not the def line,
not decorators. The following are already available at module level in the
test file, no imports needed:
  - `client`: a FastAPI TestClient wrapping the generated app
  - `TestingSessionLocal`: a SQLAlchemy sessionmaker for direct DB setup
  - `models`, `schemas`: the generated ORM models and Pydantic schemas

{entity_reference}

This test must verify the following functional requirement(s):
{acceptance_criteria}

Rules:
- Create any prerequisite test data yourself, either via `client.post(...)` if
  a create endpoint exists for that entity, or directly via a
  `TestingSessionLocal()` session and the appropriate `models.<Entity>(...)`
  if it does not.
- Call the endpoint under test using `client.<method>(...)`.
- Use plain `assert` statements to verify the response matches the
  acceptance criteria above -- check status code AND actual response content,
  not just that the call didn't error.
- Do NOT use pytest fixtures as function parameters -- do all setup inline.
- End with at least one assert statement.

Return ONLY raw JSON in this exact shape, no markdown fences, no preamble:
{{"body": "<python statements, NO leading indentation, NO def line>"}}

Use \\n to separate lines within the "body" string.
"""


def _build_entity_reference(spec: SpecOutput, entity_name: str) -> str:
    entity = next((e for e in spec.entities if e.name.lower() == entity_name.lower()), None)
    if entity is None:
        return ""
    field_lines = "\n".join(f"  - {f.name}: {f.type}" for f in entity.fields)
    create_note = (
        f"  A create endpoint EXISTS: POST /{entity.table_name}"
        if any(ep.method == "POST" and ep.path == f"/{entity.table_name}" for ep in spec.endpoints)
        else f"  NO create endpoint exists for {entity.name} -- create it directly via the ORM."
    )
    return f"Entity: {entity.name} (table: {entity.table_name})\nFields:\n{field_lines}\n{create_note}\n"


def _guess_entity(spec: SpecOutput, custom_ep: dict) -> str:
    for entity in spec.entities:
        if entity.table_name in custom_ep["path"]:
            return entity.name
    return spec.entities[0].name if spec.entities else ""


def implement_custom_endpoint_tests(spec: SpecOutput, test_file: GeneratedFile) -> GeneratedFile:
    context = build_template_context(spec)
    custom_endpoints = context["custom_endpoints"]
    if not custom_endpoints:
        return test_file

    content = test_file.content

    for ep in custom_endpoints:
        entity_name = ep.get("entity") or _guess_entity(spec, ep)
        entity_reference = _build_entity_reference(spec, entity_name)
        acceptance_criteria = _matching_acceptance_criteria(spec, ep.get("fr_ids", []))
        system_prompt = _build_system_prompt(entity_reference, acceptance_criteria)
        user_prompt = (
            f"Endpoint under test: {ep['method']} {ep['path']}\n"
            f"Description: {ep['description']}\n"
            f"Write the test function body now."
        )

        indented_body = generate_code_body(system_prompt, user_prompt)
        body_text = "\n".join(indented_body) + "\n"

        pattern = re.compile(
            rf'(def test_{re.escape(ep["func_name"])}\(\):\n)'
            rf'    raise AssertionError\("Not implemented yet -- Day 5 Testing Agent fills this in"\)\n'
        )
        new_content, count = pattern.subn(lambda m: m.group(1) + body_text, content)
        if count != 1:
            raise ValueError(
                f"Expected exactly 1 stub match for test_{ep['func_name']}, found {count}."
            )
        content = new_content

    ast.parse(content)
    return GeneratedFile(path=test_file.path, content=content)


def run_testing_agent(spec: SpecOutput) -> GeneratedFile:
    test_file = render_test_file(spec)
    return implement_custom_endpoint_tests(spec, test_file)


if __name__ == "__main__":
    from app.rag.example_bank import EXAMPLE_BANK

    spec = EXAMPLE_BANK[0]  # Inventory Management
    test_file = run_testing_agent(spec)
    print(test_file.content)
