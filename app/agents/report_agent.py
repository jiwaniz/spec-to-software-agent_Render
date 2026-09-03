"""Report Agent -- validation_report.md text + ZIP packaging of the full project."""

import io
import zipfile

from app.schemas import SpecOutput, GeneratedFile, ValidationReport


def build_validation_report_md(spec: SpecOutput, report: ValidationReport) -> str:
    lines = [
        f"# Validation Report -- {spec.app_name}",
        "",
        f"**Overall status:** {report.overall_status}",
        "",
        f"- Files present: {'PASS' if report.files_ok else 'FAIL'}",
        f"- Syntax errors: {len(report.syntax_errors)}",
        f"- Endpoints implemented: {report.endpoints_detected}/{report.endpoints_required}",
        f"- Tests passed: {report.tests_passed}/{report.tests_total}",
        f"- Requirement coverage: {report.requirement_coverage_pct}%",
        f"- Avg. embedding similarity: {report.avg_embedding_similarity}",
        f"- Correction cycles used: {report.correction_cycles_used}",
        "",
    ]
    if report.syntax_errors:
        lines.append("## Syntax errors")
        lines += [f"- {e}" for e in report.syntax_errors]
        lines.append("")
    if report.failed_test_names:
        lines.append("## Failed tests")
        lines += [f"- {t}" for t in report.failed_test_names]
        lines.append("")

    lines.append("## Requirement Traceability")
    for fr in spec.functional_requirements:
        eps = [ep for ep in spec.endpoints if fr.id in ep.fr_ids]
        ep_str = ", ".join(f"{e.method} {e.path}" for e in eps) or "(none)"
        lines.append(f"- **{fr.id}**: {fr.description} -> {ep_str}")

    return "\n".join(lines)


def package_zip(main_files: list[GeneratedFile], test_file: GeneratedFile, report_md: str, spec_json: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in main_files:
            zf.writestr(f.path, f.content)
        zf.writestr(test_file.path, test_file.content)
        zf.writestr("validation_report.md", report_md)
        zf.writestr("spec.json", spec_json)
    return buf.getvalue()


def run_report_agent(
    spec: SpecOutput, main_files: list[GeneratedFile], test_file: GeneratedFile, report: ValidationReport
) -> tuple[str, bytes]:
    report_md = build_validation_report_md(spec, report)
    zip_bytes = package_zip(main_files, test_file, report_md, spec.model_dump_json(indent=2))
    return report_md, zip_bytes
