"""
Day 6 live test -- runs the full pipeline with real Groq + real embeddings,
prints the validation report including embedding similarity, then
deliberately breaks the implementation and confirms the correction loop
detects and fixes it automatically.

Run from the project root:
    python test_day6_live.py
"""

from unittest.mock import patch

from app.agents.coding_agent import run_coding_agent, regenerate_endpoint_with_feedback
from app.agents.testing_agent import run_testing_agent
from app.agents.validation_agent import run_validation_agent_full
from app.rag.example_bank import EXAMPLE_BANK


def main():
    spec = EXAMPLE_BANK[0]

    print("=== Part 1: normal run with real Groq + real embedding similarity ===\n")
    main_files = run_coding_agent(spec)
    test_file = run_testing_agent(spec)
    report, failure_details = run_validation_agent_full(spec, main_files, test_file)
    print(report.model_dump_json(indent=2))

    print("\n=== Part 2: correction loop -- inject a deliberate bug, confirm it self-heals ===\n")
    # Force a broken implementation using AST-based replacement (robust
    # regardless of what variable names/structure the real Groq output
    # used) so this part of the test doesn't depend on regex-guessing
    # the exact shape of Groq's actual code.
    import ast
    from app.schemas import GeneratedFile

    main_file = next(f for f in main_files if f.path == "main.py")
    func_name = "get_products_low_stock"

    tree = ast.parse(main_file.content)
    func_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name),
        None,
    )
    if func_node is None or not func_node.body:
        print(f"Could not find {func_name} to inject a bug into -- skipping Part 2")
        return

    lines = main_file.content.split("\n")
    body_start = func_node.body[0].lineno - 1
    body_end = func_node.body[-1].end_lineno
    broken_body = [
        "    products = db.query(models.Product).all()",
        "    return [schemas.ProductRead.model_validate(p).model_dump() for p in products]",
    ]
    new_lines = lines[:body_start] + broken_body + lines[body_end:]
    broken_content = "\n".join(new_lines)
    ast.parse(broken_content)  # confirm the injected bug is at least syntactically valid

    broken_files = [
        GeneratedFile(path=f.path, content=broken_content) if f.path == "main.py" else f
        for f in main_files
    ]

    report2, failure_details2 = run_validation_agent_full(spec, broken_files, test_file)
    print(f"After injecting bug: {report2.overall_status}, "
          f"{report2.tests_passed}/{report2.tests_total} passed, "
          f"failed: {report2.failed_test_names}")

    if not report2.failed_test_names:
        print("Bug injection didn't actually break anything -- skipping correction test")
        return

    test_name = report2.failed_test_names[0]
    func_name = test_name[len("test_"):]
    detail = failure_details2.get(test_name, "")

    print(f"\nRunning correction with real Groq feedback for {func_name}...")
    corrected_files = regenerate_endpoint_with_feedback(spec, broken_files, func_name, detail)

    report3, _ = run_validation_agent_full(spec, corrected_files, test_file, correction_cycles_used=1)
    print(f"\nAfter correction: {report3.overall_status}, "
          f"{report3.tests_passed}/{report3.tests_total} passed")

    if report3.overall_status == "PASS":
        print("\nSUCCESS: correction loop detected and fixed the injected bug using real Groq")
    else:
        print("\nNOTE: correction didn't fully fix it this time -- Groq's fix attempt may need "
              "another cycle, which is expected behavior (capped at 2 in the real pipeline)")


if __name__ == "__main__":
    main()
