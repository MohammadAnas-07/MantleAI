"""Agent demo: one Planner + Reviewer run with a REAL model, through the running API.

Not part of pytest. It makes real, paid API calls with the key you saved in Mantle. It creates a
project with 2 approved requirements, starts a plan run for the first one, waits for it, and
prints the plan and the review. It approves nothing: the run stays "waiting_for_approval", so
nothing reaches project memory. Approve or reject it yourself in /docs if you want.

Start the API first (backend, venv active): `uvicorn app.main:app`. Then:

    python scripts/agent_demo.py --model gemini/gemini-3.8-flash

Options: --api (default http://127.0.0.1:8000), --force (run above AGENT_RUN_COST_LIMIT_USD).
"""

import argparse
import sys
import textwrap
import time
from typing import Any

import httpx

REQUIREMENTS = [
    (
        "Users can reset a forgotten password",
        "A user who forgot their password gets an email with a link that works once and "
        "expires after 30 minutes. The link sets a new password.",
    ),
    (
        "Accounts lock after repeated failed logins",
        "After 5 failed logins in 15 minutes the account is locked for 15 minutes. The user "
        "sees a clear message.",
    ),
]


def fail(response: httpx.Response) -> None:
    try:
        error = response.json()["error"]
        message = f"{error['code']}: {error['message']}"
    except (ValueError, KeyError):
        message = response.text[:300]
    raise SystemExit(f"{response.request.method} {response.request.url.path} -> "
                     f"{response.status_code} {message}")  # fmt: skip


def call(client: httpx.Client, method: str, path: str, **kwargs: Any) -> Any:
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        fail(response)
    return response.json()


def model_id(client: httpx.Client, name: str) -> str:
    models = call(client, "GET", "/api/v1/models")
    for model in models:
        if model["litellm_model"] == name or model["id"] == name:
            if model["kind"] != "chat":
                raise SystemExit(f"{name} is not a chat model.")
            return str(model["id"])
    known = ", ".join(m["litellm_model"] for m in models if m["kind"] == "chat")
    raise SystemExit(f"Unknown model {name!r}. Chat models: {known}")


def wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(text, width=96, initial_indent=indent, subsequent_indent=indent)


def print_plan(result: dict[str, Any]) -> None:
    plan = result.get("plan", {})
    print("\nPLAN")
    for i, task in enumerate(plan.get("tasks", [])):
        deps = f" (after {', '.join(map(str, task['depends_on']))})" if task["depends_on"] else ""
        dup = " [possible duplicate]" if task.get("possible_duplicate_of") else ""
        print(f"  task {i} [{task['priority']}] {task['title']}{deps}{dup}")
        if task.get("description"):
            print(wrap(task["description"], "      "))
        for criterion in task.get("acceptance_criteria", []):
            print(wrap(f"- {criterion}", "      "))
    for i, decision in enumerate(plan.get("decisions", [])):
        print(f"  decision {i}: {decision['title']}")
        print(wrap(f"what: {decision['what']}", "      "))
        if decision.get("why"):
            print(wrap(f"why: {decision['why']}", "      "))
        if decision.get("alternatives"):
            print(wrap(f"alternatives: {decision['alternatives']}", "      "))
    for name in ("assumptions", "risks", "open_questions"):
        for item in plan.get(name, []):
            print(wrap(f"{name[:-1].replace('_', ' ')}: {item}", "  "))


def print_review(result: dict[str, Any]) -> None:
    review = result.get("review", {})
    print(f"\nREVIEW (verdict: {review.get('verdict')})")
    for finding in review.get("findings", []):
        refs = ", ".join(finding["refers_to"]) or "-"
        print(f"  [{finding['severity']}] {finding['explanation']} (refers to {refs})")
        if finding.get("suggestion"):
            print(wrap(f"suggestion: {finding['suggestion']}", "      "))


def print_steps(run: dict[str, Any]) -> None:
    """One line per step: attempts (2 = one retry after an invalid answer), tokens, cost."""
    print("\nSTEPS")
    for step in run["steps"]:
        retries = step["attempts"] - 1
        print(f"  {step['agent']} ({step['prompt_version']}): {step['status']}, "
              f"{retries} retr{'y' if retries == 1 else 'ies'}, "
              f"{step['input_tokens']} in / {step['output_tokens']} out tokens, "
              f"${step['cost_usd']}, {step['latency_ms']} ms"
              + (f", error {step['error']}" if step["error"] else ""))  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="litellm model name or model id")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--force", action="store_true", help="run above the cost limit")
    parser.add_argument("--timeout", type=float, default=600, help="seconds to wait")
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=60) as client:
        chosen = model_id(client, args.model)
        project = call(client, "POST", "/api/v1/projects", json={
            "name": f"Agent demo {time.strftime('%Y-%m-%d %H:%M')}",
            "description": "A small web shop with email and password accounts.",
        })  # fmt: skip
        print(f"project {project['id']}")
        requirement_ids = []
        for title, body in REQUIREMENTS:
            item = call(client, "POST", f"/api/v1/projects/{project['id']}/memory", json={
                "kind": "requirement", "title": title, "body": body, "status": "approved",
                "priority": "must",
            })  # fmt: skip
            requirement_ids.append(item["id"])
        run = call(client, "POST", f"/api/v1/projects/{project['id']}/agent-runs", json={
            "run_type": "plan", "model_id": chosen, "requirement_id": requirement_ids[0],
            "force": args.force,
        })  # fmt: skip
        estimate = run["estimate"]
        print(f"run {run['id']} queued; estimate {estimate['input_tokens']} in / "
              f"{estimate['output_tokens']} out tokens, ${estimate['cost_usd']}")  # fmt: skip

        deadline = time.monotonic() + args.timeout
        while run["status"] in ("queued", "running"):
            if time.monotonic() > deadline:
                raise SystemExit(f"Timed out; the run is still {run['status']}.")
            time.sleep(2)
            run = call(client, "GET", f"/api/v1/agent-runs/{run['id']}")
            print(f"  status {run['status']}, steps done: {len(run['steps'])}")

        print_steps(run)
        if run["status"] == "failed":
            raise SystemExit(f"Run failed: {run['error']}: {run['error_message']}")
        print_plan(run["result"])
        print_review(run["result"])
        for warning in run["warnings"]:
            print(f"warning: {warning}")
        print(f"\ntokens {run['input_tokens']} in / {run['output_tokens']} out, "
              f"cost ${run['cost_usd']}")  # fmt: skip
        print(f"Nothing was approved. The run is {run['status']}: approve or reject it with "
              f"POST /api/v1/agent-runs/{run['id']}/approve or /reject.")  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
