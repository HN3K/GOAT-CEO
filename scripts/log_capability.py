#!/usr/bin/env python3
"""Append-only audit logs for the GOAT-CEO optional capabilities (INTEGRATION layer).

The vendored tools (`tools/rubric/`, `tools/research-system/`) are re-vendored from upstream and
must NOT be edited in place, so this logger lives at the GOAT-CEO integration layer and records the
*outcomes* of invoking them:

  - logs/rubric-enforcement.jsonl — every time rubric ENFORCED a standard: a blocking violation it
    caught / healed / degraded that would otherwise have broken the rules/conventions.
  - logs/research.jsonl          — every research action (capture / run / benchmark) and its outcome.

Both live under logs/ (gitignored) — a local audit trail, never published, consistent with keeping a
user's code/standards activity off the public repo.

WRITE:
  python scripts/log_capability.py rubric --source <gate|heal-gate|reviewer-c|features> \
      --action <blocked|healed|degraded|violation|pass> [--repo PATH] [--rules a,b] \
      [--files x,y] [--detail "..."]
  python scripts/log_capability.py research --action <capture|run|benchmark> --subject SLUG \
      [--question "..."] [--verdicts "supported=5,overreach=1"] [--sources N] [--detail "..."]

SHOW:
  python scripts/log_capability.py show rubric   [--n 20]
  python scripts/log_capability.py show research [--n 20]

Design contract: FAIL-OPEN / non-fatal — logging must NEVER break the caller. Any error exits 0.
Dependency-free (stdlib only).
"""
import argparse
import datetime
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(REPO_ROOT, "logs")
LOG_FILES = {
    "rubric": os.path.join(LOG_DIR, "rubric-enforcement.jsonl"),
    "research": os.path.join(LOG_DIR, "research.jsonl"),
}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _split_csv(value):
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _parse_verdicts(value):
    out = {}
    for pair in _split_csv(value):
        if "=" in pair:
            k, v = pair.split("=", 1)
            try:
                out[k.strip()] = int(v.strip())
            except ValueError:
                out[k.strip()] = v.strip()
    return out


def cmd_rubric(a):
    rec = {
        "ts": _now(), "log": "rubric-enforcement", "source": a.source, "action": a.action,
        "repo": a.repo or "", "rules": _split_csv(a.rules), "files": _split_csv(a.files),
    }
    if a.detail:
        rec["detail"] = a.detail
    _append(LOG_FILES["rubric"], rec)
    print("logged rubric-enforcement: {} via {} ({} rule(s), {} file(s))".format(
        a.action, a.source, len(rec["rules"]), len(rec["files"])))
    return 0


def cmd_research(a):
    rec = {"ts": _now(), "log": "research", "action": a.action, "subject": a.subject or ""}
    if a.question:
        rec["question"] = a.question
    if a.verdicts:
        rec["verdicts"] = _parse_verdicts(a.verdicts)
    if a.sources is not None:
        rec["sources"] = a.sources
    if a.detail:
        rec["detail"] = a.detail
    _append(LOG_FILES["research"], rec)
    print("logged research: {} {}".format(a.action, rec["subject"]))
    return 0


def cmd_show(a):
    path = LOG_FILES.get(a.which)
    if not path or not os.path.exists(path):
        print("(no {} log yet — {})".format(a.which, path or "?"))
        return 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError:
        print("(could not read {})".format(path))
        return 0
    tail = lines[-max(1, a.n):]
    print("{} — last {} of {} entries:".format(path, len(tail), len(lines)))
    for ln in tail:
        try:
            r = json.loads(ln)
        except ValueError:
            print("  " + ln)
            continue
        if a.which == "rubric":
            extra = []
            if r.get("rules"):
                extra.append("rules=" + ",".join(r["rules"]))
            if r.get("files"):
                extra.append("files=" + ",".join(r["files"]))
            print("  {}  [{}] {}{}{}".format(
                r.get("ts", "?"), r.get("source", "?"), r.get("action", "?"),
                ("  " + r.get("repo", "") if r.get("repo") else ""),
                ("  " + " ".join(extra) if extra else "")))
        else:
            v = r.get("verdicts")
            vstr = ("  verdicts=" + ",".join("{}:{}".format(k, n) for k, n in v.items())) if v else ""
            print("  {}  [{}] {}{}{}".format(
                r.get("ts", "?"), r.get("action", "?"), r.get("subject", ""),
                ("  q=\"{}\"".format(r["question"][:60]) if r.get("question") else ""), vstr))
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="log_capability.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rubric", help="log a rubric enforcement event")
    r.add_argument("--source", default="features")
    r.add_argument("--action", required=True)
    r.add_argument("--repo", default="")
    r.add_argument("--rules", default="")
    r.add_argument("--files", default="")
    r.add_argument("--detail", default="")
    r.set_defaults(func=cmd_rubric)

    s = sub.add_parser("research", help="log a research action")
    s.add_argument("--action", required=True)
    s.add_argument("--subject", default="")
    s.add_argument("--question", default="")
    s.add_argument("--verdicts", default="")
    s.add_argument("--sources", type=int, default=None)
    s.add_argument("--detail", default="")
    s.set_defaults(func=cmd_research)

    sh = sub.add_parser("show", help="print the tail of a log")
    sh.add_argument("which", choices=["rubric", "research"])
    sh.add_argument("--n", type=int, default=20)
    sh.set_defaults(func=cmd_show)
    return p


def main():
    try:
        args = build_parser().parse_args()
        return args.func(args) or 0
    except SystemExit:
        # argparse error — surface usage but never hard-fail a pipeline step.
        return 0
    except Exception as exc:  # pragma: no cover - defensive, logging must never break a caller
        try:
            sys.stderr.write("log_capability: non-fatal error: {}\n".format(exc))
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
