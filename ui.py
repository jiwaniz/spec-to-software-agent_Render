"""
Gradio UI -- Day 8. Entry point: `python ui.py`.

Wraps the LangGraph pipeline (app/graph_sketch.py) with a browser UI:
input box, auth toggle, Generate button, tabs for Spec/Plan/Code/Tests/
Validation/Diagram, a refinement chat, and a ZIP download.
"""

import json
import os
import tempfile

import gradio as gr

from app.graph_sketch import build_graph
from app.live_preview import start_preview, stop_preview, is_running_in_hf_space

_GRAPH = build_graph()

SUPPORTED_DOMAINS = [
    "Inventory Management", "Expense Tracking", "Leave Management",
    "Student Registration", "Library Management",
]


def _format_code_tab(generated_files: list[dict]) -> str:
    parts = []
    for f in generated_files:
        parts.append(f"### `{f['path']}`\n```python\n{f['content']}\n```")
    return "\n\n".join(parts)


def _zip_to_tempfile(zip_bytes: bytes, app_name: str) -> str:
    path = os.path.join(tempfile.gettempdir(), f"{app_name}.zip")
    with open(path, "wb") as fh:
        fh.write(zip_bytes)
    return path


def _preview_html(docs_url: str | None) -> str:
    if is_running_in_hf_space():
        return "<i>Live preview is only available when running locally (disabled in this public deployment for security).</i>"
    if docs_url is None:
        return "<i>Live preview failed to start -- check the terminal for errors. The ZIP download still works.</i>"
    return f'<a href="{docs_url}" target="_blank">Open live API docs -> {docs_url}</a>'


def _launch_and_stop_old(main_files: list[dict], state: dict) -> str:
    from app.schemas import GeneratedFile
    stop_preview(state.get("preview_process"))
    files = [GeneratedFile.model_validate(f) for f in main_files]
    docs_url, process, tmp_dir = start_preview(files)
    state["preview_process"] = process
    state["preview_tmp_dir"] = tmp_dir
    return _preview_html(docs_url)


def generate(requirement: str, auth_enabled: bool, state: dict):
    if not requirement.strip():
        return ("Please enter a requirement.", "", "", "", "", None, "", state)

    try:
        result = _GRAPH.invoke({"raw_requirement": requirement, "auth_enabled": auth_enabled})
    except Exception as e:
        err = f"**Something went wrong generating your project:**\n\n```\n{e}\n```\n\nTry again, or simplify the request."
        return (err, "", "", "", "", None, "", state)

    state["last_state"] = result

    if not result.get("requirement", {}).get("in_scope", False):
        reason = result.get("requirement", {}).get("rejection_reason", "Out of scope.")
        return (f"**Rejected:** {reason}", "", "", "", "", None, "", state)

    spec_md = f"```json\n{json.dumps(result['spec'], indent=2)}\n```"
    plan_md = f"```json\n{json.dumps(result['plan'], indent=2)}\n```"
    code_md = _format_code_tab(result["generated_files"])
    test_md = f"```python\n{result['test_file']['content']}\n```"
    validation_md = (
        f"```json\n{json.dumps(result['validation'], indent=2)}\n```\n\n"
        f"### Diagram\n```mermaid\n{result['diagram']}\n```"
    )
    zip_path = _zip_to_tempfile(result["zip_bytes"], result["spec"]["app_name"])
    preview_html = _launch_and_stop_old(result["generated_files"], state)

    return (spec_md, plan_md, code_md, test_md, validation_md, zip_path, preview_html, state)


def refine(message: str, history: list, state: dict):
    prior = state.get("last_state")
    if prior is None or not prior.get("spec"):
        history = history + [(message, "Generate a project first before refining it.")]
        return history, state, "", "", "", "", "", None

    try:
        new_state = dict(prior)
        new_state["refinement_message"] = message

        from app.graph_sketch import (
            refinement_node, planning_node, task_node, retrieval_node,
            coding_node, testing_node, validation_node, diagram_node, report_node,
        )
        s = refinement_node(new_state)
        s = planning_node(s); s = task_node(s); s = retrieval_node(s); s = coding_node(s)
        s = testing_node(s); s = validation_node(s)
        cycles = 0
        while s.get("validation", {}).get("overall_status") != "PASS" and cycles < 2:
            from app.graph_sketch import correction_node
            s = correction_node(s); s = validation_node(s); cycles += 1
        s = diagram_node(s); s = report_node(s)
    except Exception as e:
        history = history + [(message, f"Refinement failed: {e}")]
        return history, state, "", "", "", "", "", None

    state["last_state"] = s
    reply = s.get("refinement_patch", {}).get("notes", "Updated.")
    history = history + [(message, reply)]

    spec_md = f"```json\n{json.dumps(s['spec'], indent=2)}\n```"
    plan_md = f"```json\n{json.dumps(s['plan'], indent=2)}\n```"
    code_md = _format_code_tab(s["generated_files"])
    test_md = f"```python\n{s['test_file']['content']}\n```"
    validation_md = f"```json\n{json.dumps(s['validation'], indent=2)}\n```"
    preview_html = _launch_and_stop_old(s["generated_files"], state)

    return history, state, spec_md, plan_md, code_md, test_md, validation_md, preview_html


with gr.Blocks(title="Spec-to-Software Agent") as demo:
    gr.Markdown("# Spec-to-Software Agent\nDescribe a small CRUD app. Supported domains: "
                + ", ".join(SUPPORTED_DOMAINS))

    session_state = gr.State({})

    with gr.Row():
        requirement_box = gr.Textbox(label="Describe your app", scale=4,
                                      placeholder="Build an inventory API with products, categories, and low-stock alerts.")
        auth_checkbox = gr.Checkbox(label="Add JWT auth", scale=1)
    generate_btn = gr.Button("Generate", variant="primary")

    with gr.Tabs():
        with gr.Tab("Spec"):
            spec_out = gr.Markdown()
        with gr.Tab("Plan"):
            plan_out = gr.Markdown()
        with gr.Tab("Code"):
            code_out = gr.Markdown()
        with gr.Tab("Tests"):
            test_out = gr.Markdown()
        with gr.Tab("Validation + Diagram"):
            validation_out = gr.Markdown()

    download_out = gr.File(label="Download project ZIP")
    preview_out = gr.HTML(label="Live preview (local only)")

    gr.Markdown("## Refine")
    chatbot = gr.Chatbot(label="Refinement chat")
    refine_box = gr.Textbox(label="e.g. 'add an email field to Category'")
    refine_btn = gr.Button("Send")

    generate_btn.click(
        generate,
        inputs=[requirement_box, auth_checkbox, session_state],
        outputs=[spec_out, plan_out, code_out, test_out, validation_out, download_out, preview_out, session_state],
    )
    refine_btn.click(
        refine,
        inputs=[refine_box, chatbot, session_state],
        outputs=[chatbot, session_state, spec_out, plan_out, code_out, test_out, validation_out, preview_out],
    )

if __name__ == "__main__":
    demo.launch()
