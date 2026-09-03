"""
Task Agent -- Day 3.

Also deterministic. Produces an ordered, dependency-tagged task list
straight from the spec, mainly for the traceability display in the UI
(Day 8) rather than for driving any actual generation logic.
"""

from app.schemas import SpecOutput, TaskOutput, TaskItem
from app.codegen.context import build_template_context


def run_task_agent(spec: SpecOutput) -> TaskOutput:
    context = build_template_context(spec)
    tasks: list[TaskItem] = []

    tasks.append(TaskItem(id="T1", description="Set up database engine and SQLAlchemy models"))
    tasks.append(TaskItem(id="T2", description="Define Pydantic request/response schemas", depends_on=["T1"]))
    tasks.append(TaskItem(id="T3", description="Implement CRUD service functions", depends_on=["T2"]))
    tasks.append(TaskItem(id="T4", description="Wire standard CRUD endpoints in main.py", depends_on=["T3"]))

    next_id = 5
    custom_task_ids = []
    for ep in context["custom_endpoints"]:
        task_id = f"T{next_id}"
        tasks.append(TaskItem(
            id=task_id,
            description=f"Implement custom endpoint: {ep['method']} {ep['path']} -- {ep['description']}",
            depends_on=["T4"],
        ))
        custom_task_ids.append(task_id)
        next_id += 1

    auth_task_id = None
    if spec.auth_enabled:
        auth_task_id = f"T{next_id}"
        tasks.append(TaskItem(id=auth_task_id, description="Add JWT auth scaffold and protect flagged endpoints", depends_on=["T1"]))
        next_id += 1

    test_depends = ["T4"] + custom_task_ids + ([auth_task_id] if auth_task_id else [])
    tasks.append(TaskItem(id=f"T{next_id}", description="Write pytest test suite from functional requirements", depends_on=test_depends))

    return TaskOutput(tasks=tasks)


if __name__ == "__main__":
    from app.rag.example_bank import EXAMPLE_BANK

    result = run_task_agent(EXAMPLE_BANK[0])
    print(result.model_dump_json(indent=2))
