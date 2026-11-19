"""Checks on the app as it really starts, in a fresh interpreter (the test process itself has
already imported every model, which would hide a missing import)."""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def run(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_running_app_registers_every_table() -> None:
    # Regression: usage_records.agent_run_id references agent_runs; if the workflow models are
    # not imported, the first usage row fails with "could not find table 'agent_runs'".
    out = run(
        "import app.main; from app.db.base import Base; "
        "print(len(Base.metadata.tables), 'agent_runs' in Base.metadata.tables)"
    )
    assert out == "24 True"


def test_every_write_endpoint_takes_a_json_body() -> None:
    # Regression: POST /credentials/{id}/test had no body, so /docs sent no Content-Type and the
    # JSON-only middleware (rule 29) answered 415. A JSON body makes /docs send the header.
    from app.main import app

    missing = [
        f"{method.upper()} {path}"
        for path, operations in app.openapi()["paths"].items()
        for method, operation in operations.items()
        if method in {"post", "put", "patch"}
        and "application/json" not in operation.get("requestBody", {}).get("content", {})
    ]
    assert missing == []


def test_app_start_does_not_import_litellm() -> None:
    assert run("import sys, app.main; print('litellm' in sys.modules)") == "False"
