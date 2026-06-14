"""TaskCreated hook: enforce task naming convention.

Tasks in the GOAT-CEO pipeline MUST follow the convention:
    "{repo}: Phase {N} — {name}"
e.g. "IntelligenceService: Phase 3 — Implement analytics endpoints"

This ensures the CEO can parse the shared task list reliably.

This is a SOFT gate: exit 1 (warning, not a rollback) so naming errors
don't deadlock the pipeline.  The task IS created; the CEO is warned.

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow (valid name); exit 1 = allow + warn (invalid name).
"""
import json
import re
import sys

# Pattern: "<repo>: Phase <N> — <name>" (em-dash or double-dash accepted)
VALID_NAME = re.compile(
    r"^.+:\s+Phase\s+\d+(\.\d+)?\s+(—|--)\s+.+$",
    re.IGNORECASE,
)

# Allow well-known non-pipeline task names used by the CEO itself
EXEMPT_PREFIXES = (
    "CEO:",
    "INIT:",
    "HANDOFF:",
    "ESCALATE:",
    "CLEANUP:",
)


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        task_title = (
            data.get("task_title")
            or data.get("title")
            or data.get("tool_input", {}).get("title", "")
        )

        if not task_title:
            return 0  # can't check — fail open

        for prefix in EXEMPT_PREFIXES:
            if task_title.startswith(prefix):
                return 0  # exempt

        if not VALID_NAME.match(task_title):
            sys.stderr.write(
                "TASK NAMING WARNING: task '{}' does not follow the required "
                "convention '{{repo}}: Phase {{N}} — {{name}}'. "
                "The task has been created but the CEO's task-list parser may "
                "not recognize it. Rename if this is a pipeline phase task.".format(
                    task_title
                )
            )
            return 1  # soft warn — allow the task to be created

        return 0
    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
