"""PreToolUse hook: role-gate writes to repo-registry.json (CEO-owned state).

INTENT (rules.md #6): repo-registry.json is CEO-only — no SUBAGENT writes. It holds the
CEO's cross-session repo state (paths, capabilities, groups, lastSession).

WHY THIS HOOK EXISTS: the original implementation used a blanket
`permissions.deny: Write(repo-registry.json) / Edit(repo-registry.json)`. But
`permissions.deny` is role-BLIND — it blocked EVERYONE, including the CEO, which directly
contradicted the skill's own Step 1.1 ("Write repo-registry.json") and Step 2.3/4.2
(lastSession updates). The CEO could not register repos. That deny was mis-categorized as
"truly-unconditional" when the CEO is in fact the legitimate writer. Per the two-tier
design, a rule with a legitimate exception belongs in a fail-open role-gated hook, not an
unconditional deny. This hook replaces those two deny lines.

ALLOWS: the CEO main session (no agent_type) + team-overseer.
BLOCKS: every other subagent role writing repo-registry.json.

Design contract: FAIL-OPEN on any error.  exit 0 = allow; exit 2 = block.
"""
import json
import os
import sys

GATED_TOOLS = {"Write", "Edit"}
# Roles permitted to write the registry (the orchestrator tier).
ALLOWED_ROLES = {"", "goat-ceo", "team-overseer"}


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        if data.get("tool_name", "") not in GATED_TOOLS:
            return 0  # not a write tool — allow

        tool_input = data.get("tool_input", {}) or {}
        target = tool_input.get("file_path") or tool_input.get("path") or ""
        if os.path.basename(str(target)) != "repo-registry.json":
            return 0  # not the registry — allow

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if agent_type in ALLOWED_ROLES:
            return 0  # CEO / overseer — allowed (this is what the old deny wrongly blocked)

        sys.stderr.write(
            "REGISTRY GUARD: repo-registry.json is CEO-owned cross-session state. Role "
            "'{}' may not write it. Report the needed registry change to the CEO; the CEO "
            "writes the registry during Step 1 intake and lastSession updates.".format(agent_type)
        )
        return 2
    except Exception:
        return 0  # fail open — a hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
