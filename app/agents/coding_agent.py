"""
Coding Agent -- Day 4.

Day 3's templates already generate 100% of the file structure and every
standard CRUD route deterministically. The ONLY thing left for the LLM
to write is the body of each "custom" endpoint (things like a low-stock
filter that don't fit the standard CRUD shape).

Design choices, deliberately:
- We ask the LLM for ONLY the function body, not the whole file or even
  the whole function. The decorator, signature, and route wiring were
  already generated correctly and tested in Day 3 -- there's no reason
  to let the LLM touch them and risk breaking something that works.
- The body is spliced into main.py via a regex scoped to that specific
  function's unique name, so this can never accidentally corrupt an
  unrelated part of the file.
- Every generated body is validated with ast.parse before being
  accepted; on failure we retry with the error fed back to the LLM,
  same self-correction pattern as llm_json.py.
- RAG retrieval (Day 1's app/rag/retrieval.py) pulls the closest
  gold-standard example spec as grounding context, mainly to keep
  naming/style conventions consistent with the rest of the bank.
"""

import ast
import re

from app.schemas import SpecOutput, GeneratedFile
from app.codegen.context import build_template_context
from app.codegen.render import render_project
from app.agents.code_gen_utils import generate_code_body
from app.rag.retrieval import retrieve, spec_to_text


def _build_entity_reference(spec: SpecOutput, entity_name: str) -> str:
    """Describes one entity's fields and available service functions, so the
    LLM references real names instead of hallucinating them."""
    entity = next((e for e in spec.entities if e.name.lower() == entity_name.lower()), None)
    if entity is None:
        return ""

    var_name = entity.name.lower()
    field_lines = "\n".join(f"  - {f.name}: {f.type}" for f in entity.fields)
    return (
        f"Entity: {entity.name} (table: {entity.table_name})\n"
        f"Fields:\n{field_lines}\n"
        f"Available service functions (already implemented, import as `services`):\n"
        f"  - services.get_{var_name}_list(db, skip=0, limit=100) -> list[models.{entity.name}]\n"
        f"  - services.get_{var_name}(db, {var_name}_id) -> models.{entity.name} | None\n"
        f"Available schema for serialization (import as `schemas`):\n"
        f"  - schemas.{entity.name}Read.model_validate(obj).model_dump()\n"
    )


def _build_system_prompt(entity_reference: str, grounding_text: str) -> str:
    return f"""You are the Coding Agent in a spec-driven FastAPI code generation pipeline.

You must write ONLY the body of one FastAPI route function -- not the decorator,
not the function signature, not imports. The function already has:
  - A `db: Session` parameter (SQLAlchemy session, already injected)
  - Access to already-imported modules: `models`, `schemas`, `services`

{entity_reference}

IMPORTANT: The route decorator does NOT set a response_model. You MUST return
JSON-serializable data -- either plain dicts, or convert ORM objects using
`schemas.<Entity>Read.model_validate(obj).model_dump()` for each item. Returning
raw SQLAlchemy ORM objects directly will fail to serialize.

For reference, here is a similar gold-standard spec from this project's domain
(for naming/style consistency only -- it does not contain code):
{grounding_text}

Return ONLY raw JSON in this exact shape, no markdown fences, no preamble:
{{"body": "<python statements, one responsibility, NO leading indentation, NO def/decorator, must end with a return statement>"}}

Use \\n to separate lines within the "body" string.
"""


def _guess_entity(spec: SpecOutput, custom_ep: dict) -> str:
    """Fallback if an endpoint's entity field is empty -- match by path segment."""
    for entity in spec.entities:
        if entity.table_name in custom_ep["path"]:
            return entity.name
    return spec.entities[0].name if spec.entities else ""


def implement_custom_endpoints(spec: SpecOutput, files: list[GeneratedFile]) -> list[GeneratedFile]:
    """
    Takes the Day 3 rendered files and replaces every LLM_IMPLEMENT stub in
    main.py with a real, syntax-validated function body.
    """
    context = build_template_context(spec)
    custom_endpoints = context["custom_endpoints"]
    if not custom_endpoints:
        return files  # nothing to do

    grounding_examples = retrieve(spec, top_k=1)
    grounding_text = spec_to_text(grounding_examples[0]) if grounding_examples else "(none found)"

    main_file = next(f for f in files if f.path == "main.py")
    main_content = main_file.content

    for ep in custom_endpoints:
        entity_name = ep.get("entity") or _guess_entity(spec, ep)
        entity_reference = _build_entity_reference(spec, entity_name)
        system_prompt = _build_system_prompt(entity_reference, grounding_text)
        user_prompt = (
            f"Endpoint: {ep['method']} {ep['path']}\n"
            f"Description: {ep['description']}\n"
            f"Write the function body now."
        )

        indented_body = generate_code_body(system_prompt, user_prompt)
        body_text = "\n".join(indented_body) + "\n"

        pattern = re.compile(
            rf'(def {re.escape(ep["func_name"])}\([^\n]*\):\n)'
            rf'    raise HTTPException\(status_code=501, detail="Not implemented yet -- Day 4 Coding Agent fills this in"\)\n'
        )
        new_content, count = pattern.subn(lambda m: m.group(1) + body_text, main_content)
        if count != 1:
            raise ValueError(
                f"Expected exactly 1 stub match for {ep['func_name']}, found {count}. "
                "Splice pattern may be out of sync with the current template."
            )
        main_content = new_content

    # Final whole-file syntax check before accepting the patched main.py
    ast.parse(main_content)

    return [
        GeneratedFile(path=f.path, content=main_content) if f.path == "main.py" else f
        for f in files
    ]


def run_coding_agent(spec: SpecOutput) -> list[GeneratedFile]:
    files = render_project(spec)
    return implement_custom_endpoints(spec, files)


def regenerate_endpoint_with_feedback(
    spec: SpecOutput,
    main_files: list[GeneratedFile],
    func_name: str,
    failure_detail: str,
) -> list[GeneratedFile]:
    """
    Day 6 correction loop: regenerates ONE specific custom endpoint's body
    using the actual pytest failure text as feedback, rather than blindly
    regenerating from scratch (which could easily repeat the same mistake
    or introduce a different one with no signal about what was wrong).

    Splices into the EXISTING main.py content (not a fresh render), so
    every other endpoint's already-correct implementation is left untouched.
    """
    context = build_template_context(spec)
    custom_ep = next((ep for ep in context["custom_endpoints"] if ep["func_name"] == func_name), None)
    if custom_ep is None:
        raise ValueError(f"No custom endpoint found with func_name={func_name}")

    main_file = next(f for f in main_files if f.path == "main.py")
    current_body = _extract_current_body(main_file.content, func_name)

    entity_name = custom_ep.get("entity") or _guess_entity(spec, custom_ep)
    entity_reference = _build_entity_reference(spec, entity_name)
    grounding_examples = retrieve(spec, top_k=1)
    grounding_text = spec_to_text(grounding_examples[0]) if grounding_examples else "(none found)"

    system_prompt = _build_system_prompt(entity_reference, grounding_text)
    user_prompt = (
        f"Endpoint: {custom_ep['method']} {custom_ep['path']}\n"
        f"Description: {custom_ep['description']}\n\n"
        f"Your PREVIOUS implementation was:\n{current_body}\n\n"
        f"That implementation FAILED its test with this error:\n{failure_detail}\n\n"
        f"Fix the implementation so the test passes. Write the corrected function body now."
    )

    indented_body = generate_code_body(system_prompt, user_prompt)

    tree = ast.parse(main_file.content)
    func_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name),
        None,
    )
    if func_node is None or not func_node.body:
        raise ValueError(f"Could not locate function {func_name} in main.py to replace during correction")

    lines = main_file.content.split("\n")
    body_start = func_node.body[0].lineno - 1       # 0-indexed
    body_end = func_node.body[-1].end_lineno         # 1-indexed inclusive -> valid as exclusive slice end
    new_lines = lines[:body_start] + indented_body + lines[body_end:]
    new_content = "\n".join(new_lines)

    ast.parse(new_content)

    return [
        GeneratedFile(path=f.path, content=new_content) if f.path == "main.py" else f
        for f in main_files
    ]


def _locate_function_body_range(content: str, func_name: str) -> tuple[int, int]:
    """Returns (body_start, body_end) as 0-indexed line-slice bounds for a
    function's body (excluding the def line), via AST -- reused by both
    the correction loop and anything else that needs to reliably replace
    a function's body regardless of its exact original code style."""
    tree = ast.parse(content)
    func_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name),
        None,
    )
    if func_node is None or not func_node.body:
        raise ValueError(f"Could not locate function {func_name} in content")
    body_start = func_node.body[0].lineno - 1
    body_end = func_node.body[-1].end_lineno
    return body_start, body_end


def _extract_current_body(main_content: str, func_name: str) -> str:
    tree = ast.parse(main_content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            source = ast.get_source_segment(main_content, node)
            return source or "(source unavailable)"
    return "(function not found)"


if __name__ == "__main__":
    from app.rag.example_bank import EXAMPLE_BANK

    spec = EXAMPLE_BANK[0]  # Inventory Management -- has one custom endpoint: low-stock
    files = run_coding_agent(spec)
    main_file = next(f for f in files if f.path == "main.py")
    print(main_file.content)
