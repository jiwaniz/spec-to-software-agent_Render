"""
Day 5 live test -- runs the FULL pipeline (Coding Agent -> Testing Agent ->
Validation Agent) using your real Groq key, actually executes pytest
against the generated project, and prints the validation report.

Run from the project root:
    python test_day5_live.py
"""

from app.agents.coding_agent import run_coding_agent
from app.agents.testing_agent import run_testing_agent
from app.agents.validation_agent import run_validation_agent
from app.rag.example_bank import EXAMPLE_BANK


def main():
    spec = EXAMPLE_BANK[0]  # Inventory Management -- has the low-stock custom endpoint
    print(f"Testing domain: {spec.domain}\n")

    print("--- Coding Agent (real Groq call) ---")
    main_files = run_coding_agent(spec)
    print(f"Generated {len(main_files)} files")

    print("\n--- Testing Agent (real Groq call for custom endpoint test) ---")
    test_file = run_testing_agent(spec)
    print("Generated tests/test_api.py")

    print("\n--- Validation Agent (running real pytest) ---")
    report = run_validation_agent(spec, main_files, test_file)

    print("\n=== VALIDATION REPORT ===")
    print(report.model_dump_json(indent=2))

    print()
    if report.overall_status == "PASS":
        print(f"PASS -- {report.tests_passed}/{report.tests_total} tests passed, "
              f"{report.requirement_coverage_pct}% requirement coverage")
    else:
        print(f"Status: {report.overall_status} -- {report.tests_passed}/{report.tests_total} tests passed")
        if report.syntax_errors:
            print("Syntax errors:", report.syntax_errors)


if __name__ == "__main__":
    main()
