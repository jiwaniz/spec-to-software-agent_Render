"""
Streamlit UI -- alternative to ui.py (Gradio). Same backend pipeline
(app/graph_sketch.py), different frontend framework, for deployment on
Streamlit Community Cloud.

Run locally: streamlit run streamlit_app.py
"""

import json
import zipfile
import io

import streamlit as st

from app.graph_sketch import build_graph

st.set_page_config(page_title="Spec-to-Software Agent", layout="wide")

if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
if "result" not in st.session_state:
    st.session_state.result = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

SUPPORTED_DOMAINS = [
    "Inventory Management", "Expense Tracking", "Leave Management",
    "Student Registration", "Library Management",
]

st.title("Spec-to-Software Agent")
st.caption("Describe a small CRUD app. Supported domains: " + ", ".join(SUPPORTED_DOMAINS))

col1, col2 = st.columns([4, 1])
with col1:
    requirement = st.text_input(
        "Describe your app",
        placeholder="Build an inventory API with products, categories, and low-stock alerts.",
    )
with col2:
    auth_enabled = st.checkbox("Add JWT auth")

if st.button("Generate", type="primary"):
    if not requirement.strip():
        st.warning("Please enter a requirement.")
    else:
        with st.spinner("Generating..."):
            try:
                result = st.session_state.graph.invoke(
                    {"raw_requirement": requirement, "auth_enabled": auth_enabled}
                )
                st.session_state.result = result
                st.session_state.chat_history = []
            except Exception as e:
                st.error(f"Something went wrong: {e}")
                st.session_state.result = None

result = st.session_state.result

if result is not None:
    if not result.get("requirement", {}).get("in_scope", False):
        reason = result.get("requirement", {}).get("rejection_reason", "Out of scope.")
        st.error(f"Rejected: {reason}")
    else:
        tabs = st.tabs(["Spec", "Plan", "Code", "Tests", "Validation + Diagram"])

        with tabs[0]:
            st.json(result["spec"])
        with tabs[1]:
            st.json(result["plan"])
        with tabs[2]:
            for f in result["generated_files"]:
                with st.expander(f["path"]):
                    st.code(f["content"], language="python")
        with tabs[3]:
            st.code(result["test_file"]["content"], language="python")
        with tabs[4]:
            st.json(result["validation"])
            st.markdown("### Diagram")
            st.code(result["diagram"], language="text")

        # ZIP download
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in result["generated_files"]:
                zf.writestr(f["path"], f["content"])
            zf.writestr(result["test_file"]["path"], result["test_file"]["content"])
            zf.writestr("validation_report.md", result.get("report_md", ""))
        st.download_button(
            "Download project ZIP", buf.getvalue(),
            file_name=f"{result['spec']['app_name']}.zip",
        )

        st.markdown("## Refine")
        for msg, reply in st.session_state.chat_history:
            with st.chat_message("user"):
                st.write(msg)
            with st.chat_message("assistant"):
                st.write(reply)

        refine_msg = st.chat_input("e.g. 'add an email field to Category'")
        if refine_msg:
            from app.graph_sketch import (
                refinement_node, planning_node, task_node, retrieval_node,
                coding_node, testing_node, validation_node, correction_node,
                diagram_node, report_node,
            )
            with st.spinner("Refining..."):
                try:
                    s = dict(result)
                    s["refinement_message"] = refine_msg
                    s = refinement_node(s)
                    s = planning_node(s); s = task_node(s); s = retrieval_node(s)
                    s = coding_node(s); s = testing_node(s); s = validation_node(s)
                    cycles = 0
                    while s.get("validation", {}).get("overall_status") != "PASS" and cycles < 2:
                        s = correction_node(s); s = validation_node(s); cycles += 1
                    s = diagram_node(s); s = report_node(s)
                    st.session_state.result = s
                    reply = s.get("refinement_patch", {}).get("notes", "Updated.")
                    st.session_state.chat_history.append((refine_msg, reply))
                    st.rerun()
                except Exception as e:
                    st.session_state.chat_history.append((refine_msg, f"Refinement failed: {e}"))
                    st.rerun()
