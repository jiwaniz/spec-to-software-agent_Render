"""
Shared utility: ask Groq for a snippet of Python code (never a full
function or file), validate it with ast.parse, retry with the error fed
back on failure. Used by the Coding Agent (Day 4, custom endpoint
bodies) and the Testing Agent (Day 5, custom endpoint test bodies) --
same reasoning both times: keep the LLM's blast radius small and easy
to validate.
"""

import ast
import json
import textwrap

from pydantic import BaseModel

from app.groq_client import complete
from app.agents.llm_json import _strip_code_fences


class CodeSnippet(BaseModel):
    body: str  # raw statements, no leading indentation, no def/decorator


def reindent_body(raw_body: str, indent: str = "    ") -> list[str]:
    """
    Shifts a code block under a wrapping `def _tmp():` by `indent`, while
    PRESERVING relative nesting (an `if` inside a `for` must stay more
    indented than the `for` line). textwrap.dedent first strips only the
    common leading whitespace shared by every line (handling any stray
    uniform indent the LLM might add), then every line gets the same base
    indent added -- never each line's OWN indentation stripped individually,
    which would flatten nested blocks and break multi-level code.
    """
    dedented = textwrap.dedent(raw_body)
    lines = dedented.split("\n")
    return [f"{indent}{line}" if line.strip() else "" for line in lines]


def validate_body_syntax(indented_lines: list[str]) -> str | None:
    """Wraps the body in a throwaway function and checks it parses."""
    reconstructed = "def _tmp():\n" + "\n".join(indented_lines) + "\n"
    try:
        ast.parse(reconstructed)
        return None
    except SyntaxError as e:
        return str(e)


def replace_function_body(source: str, func_name: str, new_body_lines: list[str]) -> str:
    """
    Replaces an EXISTING function's body (whatever it currently is -- a
    stub, a working implementation, a buggy one) with new_body_lines,
    keeping the def line and decorator untouched. Uses ast line ranges
    rather than regex, since the correction loop needs to replace
    arbitrary existing bodies, not just a known fixed stub pattern.
    """
    tree = ast.parse(source)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            target = node
            break
    if target is None:
        raise ValueError(f"Function '{func_name}' not found in source")
    if not target.body:
        raise ValueError(f"Function '{func_name}' has an empty body -- cannot locate replacement range")

    lines = source.split("\n")
    body_start_idx = target.body[0].lineno - 1
    body_end_idx = target.body[-1].end_lineno  # end_lineno is 1-indexed inclusive == exclusive slice end
    new_lines = lines[:body_start_idx] + new_body_lines + lines[body_end_idx:]
    result = "\n".join(new_lines)
    ast.parse(result)  # fail loudly here rather than downstream if something's off
    return result


def generate_code_body(
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 2,
    temperature: float = 0.2,
) -> list[str]:
    """Returns a list of already-indented (4-space) source lines, guaranteed
    to parse as a valid function body, or raises after exhausting retries."""
    last_error = None
    current_user_prompt = user_prompt

    for _ in range(max_retries + 1):
        raw = complete(system_prompt, current_user_prompt, temperature=temperature)
        cleaned = _strip_code_fences(raw)
        try:
            data = json.loads(cleaned)
            snippet = CodeSnippet.model_validate(data)
        except Exception as e:
            last_error = f"JSON/schema error: {e}"
            current_user_prompt = f"{user_prompt}\n\nYour previous response caused: {last_error}\nReturn ONLY corrected JSON."
            continue

        indented = reindent_body(snippet.body)
        syntax_error = validate_body_syntax(indented)
        if syntax_error is None:
            return indented

        last_error = f"Syntax error: {syntax_error}"
        current_user_prompt = (
            f"{user_prompt}\n\nYour previous body was:\n{snippet.body}\n\n"
            f"It caused this error: {last_error}\nFix it and return corrected JSON."
        )

    raise ValueError(f"Failed to generate valid code after {max_retries + 1} attempts: {last_error}")
