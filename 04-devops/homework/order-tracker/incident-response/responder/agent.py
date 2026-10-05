"""Start the coding agent in headless mode and record what it says."""

import json
import os
import shlex
import subprocess
from pathlib import Path


# Tools the agent may use without asking: read and edit the repo, run the tests,
# rebuild and inspect the app container, and query the app and telemetry backends.
ALLOWED_TOOLS = [
    "Read", "Grep", "Glob", "Edit", "Write",
    "Bash(uv run --frozen pytest:*)",
    "Bash(docker compose up:*)",
    "Bash(docker compose ps:*)",
    "Bash(docker compose logs:*)",
    "Bash(curl:*)",
    "Bash(git diff:*)",
    "Bash(git status:*)",
    "Bash(git log:*)",
]
DEFAULT_COMMAND = [
    "claude", "-p",
    "--output-format", "stream-json", "--verbose",
    "--permission-mode", "acceptEdits",
    # No MCP servers: the agent only needs the repo, the shell, and the local backends.
    "--strict-mcp-config",
    "--allowedTools", *ALLOWED_TOOLS,
]
TIMEOUT_SECONDS = int(os.getenv("RESPONDER_AGENT_TIMEOUT", "1800"))


def agent_command():
    """RESPONDER_AGENT_COMMAND overrides the default; the prompt is passed on stdin."""
    override = os.getenv("RESPONDER_AGENT_COMMAND")
    return shlex.split(override) if override else DEFAULT_COMMAND


def build_prompt(incident_dir: Path, repo_dir: Path, is_test: bool):
    incident = incident_dir.relative_to(repo_dir)
    if is_test:
        return f"""You are the on-call responder for Order Tracker. An alert arrived, but it is a
test notification (it has the label test="true"). There is no incident to fix.

Read {incident}/summary.md to confirm the alert reached you, then reply with a short
confirmation. Do not change any files. End your answer with one line that starts
with "RESULT:".
"""
    return f"""You are the on-call responder for Order Tracker, the service in this repository.
Grafana fired an alert, and the evidence is saved in {incident}/:

- summary.md: the alert, the affected endpoint, time window, and the key errors
- alert.json: the raw Grafana webhook
- metrics.json, logs.json, traces.json, traces/: the telemetry around the alert

Work through it:

1. Read the evidence and find the root cause in the code. Stack traces and the
   failing order IDs are in logs.json and traces.json.
2. If the cause is a clear bug with a small, safe fix: add a regression test in
   tests/, fix the code, and run `uv run --frozen pytest -q` until it passes.
3. Rebuild and restart the app with `docker compose up --build -d --wait app`.
4. Verify by repeating the failing request against http://localhost:8000 and
   checking that it no longer returns a 5xx.
5. Write {incident}/report.md with: root cause, evidence, the fix (files changed),
   test results, and verification.

If you cannot find the cause, the fix is not small and safe, or verification
fails, do not deploy. Write report.md explaining what you found and what a
developer should look at, and say that you are escalating.

Do not commit, push, or delete data. End your answer with one line that starts
with "RESULT:" and says fixed, escalated, or no action needed.
"""


def run_agent(incident_dir: Path, repo_dir: Path, is_test: bool):
    """Run the agent to completion; write prompt.md, agent.jsonl, agent.stderr.log, and response.md."""
    prompt = build_prompt(incident_dir, repo_dir, is_test)
    (incident_dir / "prompt.md").write_text(prompt)
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)  # allow starting from a shell that runs inside Claude Code
    transcript = incident_dir / "agent.jsonl"
    try:
        with transcript.open("w") as stdout, (incident_dir / "agent.stderr.log").open("w") as stderr:
            process = subprocess.run(
                agent_command(), input=prompt, text=True, cwd=repo_dir, env=env,
                stdout=stdout, stderr=stderr, timeout=TIMEOUT_SECONDS,
            )
        returncode = process.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        returncode = None
        (incident_dir / "response.md").write_text(f"The agent did not finish: {type(exc).__name__}: {exc}\n")
        return returncode
    (incident_dir / "response.md").write_text(final_answer(transcript.read_text()) + "\n")
    return returncode


def final_answer(output):
    """The `result` event of stream-json output, or the raw output for other agents."""
    for line in reversed(output.splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            return event.get("result") or json.dumps(event)
    return output.strip()
