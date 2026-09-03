"""
Live preview -- launches a generated project as a real running uvicorn
server, so the person can click through to its actual Swagger docs
instead of only downloading a ZIP.

LOCAL USE ONLY. This must never run inside the public HF Space deployment
(that would mean executing arbitrary generated code in a public-facing
environment, which the project's security stance explicitly forbids).
HF Spaces sets a SPACE_ID env var automatically -- if present, live
preview is disabled and the UI falls back to ZIP-only.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from app.schemas import GeneratedFile


def is_running_in_hf_space() -> bool:
    return bool(os.getenv("SPACE_ID"))


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop_preview(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def start_preview(main_files: list[GeneratedFile]) -> tuple[str | None, subprocess.Popen | None, str | None]:
    """
    Writes the generated project to a fresh temp dir and launches it with
    uvicorn. Returns (docs_url, process, tmp_dir) -- docs_url is None if
    preview is disabled (e.g. running inside an HF Space) or launch failed.
    """
    if is_running_in_hf_space():
        return None, None, None

    tmp_dir = tempfile.mkdtemp(prefix="spec_preview_")
    for f in main_files:
        path = os.path.join(tmp_dir, f.path)
        os.makedirs(os.path.dirname(path) or tmp_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f.content)

    port = _find_free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait briefly for the server to come up, checking the port rather than
    # a fixed sleep.
    docs_url = f"http://127.0.0.1:{port}/docs"
    for _ in range(30):  # up to ~3s
        if process.poll() is not None:
            break  # process died -- launch failed
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return docs_url, process, tmp_dir
        except OSError:
            time.sleep(0.1)

    stop_preview(process)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return None, None, None
