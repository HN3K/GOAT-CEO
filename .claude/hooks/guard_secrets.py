"""PreToolUse hook (Write|Edit): belt-and-suspenders secret-file + read-only-path guard.

INTENT: defense in depth on top of the settings.json permissions.deny secret-file globs
(C14). permissions.deny is the primary, role-blind block; this hook catches secret-bearing
paths a glob deny might miss (case folding, odd separators, relative-vs-absolute) and adds
a capability that a static deny list cannot express: per-session READ-ONLY reference-repo
protection (C17).

Two independent reasons to BLOCK a Write/Edit (exit 2):

  1. SECRET-BEARING PATH (C14). The target basename / path matches a known secret pattern:
     .env and any .env.* variant, .npmrc, .pypirc, secrets.json, *.pem, *.key, *.crt,
     *.p12, *.pfx, id_rsa*, .aws/credentials, a bare "credentials" file, and
     appsettings.*.json. This mirrors (and slightly extends) the settings.json deny globs.

  2. READ-ONLY REFERENCE PATH (C17). An OPTIONAL file
     agent-workspace/READONLY-PATHS.json gives read-only reference repos a real path-level
     write block. The CEO generates it at intake when a repo is registered read-only.

         Schema:
             {
               "paths": [
                 "<abs-or-repo-relative directory>",
                 ...
               ]
             }

     Each entry is a directory (absolute, or relative to the GOAT-CEO project root). Any
     Write/Edit whose target resolves UNDER one of these directories is blocked. If the
     file is absent or malformed, this check is skipped silently (the secret check still
     runs).

Design contract: FAIL-OPEN on any error.  exit 0 = allow; exit 2 = block.
A hook bug must never block legitimate work.
"""
import fnmatch
import json
import os
import sys

GATED_TOOLS = {"Write", "Edit"}

# Secret-bearing path patterns, matched (case-insensitively) against both the full
# normalized path and the basename. fnmatch globs; "*" does not cross "/" here only because
# we also test the basename, so e.g. "*.pem" matches any .pem regardless of directory.
SECRET_BASENAME_GLOBS = [
    ".env",
    ".env.*",
    ".npmrc",
    ".pypirc",
    "secrets.json",
    "*.pem",
    "*.key",
    "*.crt",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "appsettings.*.json",
]

# Non-secret .env template files that are routinely committed — never block these (F4).
ENV_TEMPLATE_ALLOW = {".env.example", ".env.sample", ".env.template", ".env.dist"}

# Path-fragment patterns matched against the whole normalized (forward-slash) path.
SECRET_PATH_GLOBS = [
    "*/.aws/credentials",
    "*.aws/credentials",
]


def _norm(p: str) -> str:
    """Normalize to forward slashes, lower-cased, for matching."""
    return str(p).replace("\\", "/").lower()


def _matches_secret(target: str) -> bool:
    norm = _norm(target)
    base = os.path.basename(norm)
    if base in ENV_TEMPLATE_ALLOW:
        return False  # .env.example/.sample/.template/.dist are templates, not secrets
    for glob in SECRET_BASENAME_GLOBS:
        if fnmatch.fnmatch(base, glob):
            return True
    for glob in SECRET_PATH_GLOBS:
        if fnmatch.fnmatch(norm, glob):
            return True
    return False


def _project_root() -> str:
    # .claude/hooks/guard_secrets.py -> project root is two dirs up from .claude
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )


def _readonly_paths(root: str):
    """Load agent-workspace/READONLY-PATHS.json. Returns list of absolute dir paths.
    Absent/malformed -> []."""
    cfg = os.path.join(root, "agent-workspace", "READONLY-PATHS.json")
    if not os.path.isfile(cfg):
        return []
    try:
        with open(cfg, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []
    paths = data.get("paths") if isinstance(data, dict) else None
    if not isinstance(paths, list):
        return []
    out = []
    for entry in paths:
        if not isinstance(entry, str) or not entry.strip():
            continue
        p = entry.strip()
        if not os.path.isabs(p):
            p = os.path.join(root, p)
        out.append(os.path.normcase(os.path.abspath(p)))
    return out


def _under_readonly(target: str, ro_dirs) -> str:
    """Return the matched read-only dir if target resolves under one, else ''."""
    if not ro_dirs:
        return ""
    abs_target = os.path.normcase(os.path.abspath(target))
    for d in ro_dirs:
        # containment: target == d, or target startswith d + os.sep
        if abs_target == d or abs_target.startswith(d + os.sep):
            return d
    return ""


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        if data.get("tool_name", "") not in GATED_TOOLS:
            return 0  # not a write tool — allow

        tool_input = data.get("tool_input", {}) or {}
        target = tool_input.get("file_path") or tool_input.get("path") or ""
        if not target:
            return 0  # nothing to evaluate — allow

        # Anchor a RELATIVE target to the payload cwd (the agent's repo/worktree) before
        # any path-based check — falling back to the hook process cwd only if the payload
        # omits cwd. The read-only dirs are anchored to the project root, so resolving a
        # relative target against the process cwd would compare inconsistent bases and a
        # write under a read-only reference path could slip the containment check.
        cwd = data.get("cwd", "") or ""
        resolved_target = target
        if not os.path.isabs(target):
            base = cwd or os.getcwd()
            resolved_target = os.path.join(base, target)

        # (1) secret-bearing path (basename/glob based — independent of cwd resolution)
        if _matches_secret(target):
            sys.stderr.write(
                "SECRETS GUARD: refusing Write/Edit to '{}' — it matches a secret-bearing "
                "file pattern (.env*/.npmrc/.pypirc/secrets.json/*.pem/*.key/*.crt/*.p12/"
                "*.pfx/id_rsa*/.aws/credentials/appsettings.*.json). Secret files must never "
                "be written by an agent. If this is a false positive, the CEO can adjust the "
                "settings.json deny globs and this hook.".format(target)
            )
            return 2

        # (2) read-only reference path (C17, optional) — use the cwd-anchored target
        root = _project_root()
        matched = _under_readonly(resolved_target, _readonly_paths(root))
        if matched:
            sys.stderr.write(
                "SECRETS GUARD: refusing Write/Edit to '{}' — it resolves under a read-only "
                "reference path declared in agent-workspace/READONLY-PATHS.json ('{}'). "
                "Read-only reference repos may not be modified. Report needed changes to the "
                "CEO.".format(target, matched)
            )
            return 2

        return 0
    except Exception:
        return 0  # fail open — a hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
