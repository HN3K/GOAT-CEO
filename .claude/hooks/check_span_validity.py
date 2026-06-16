"""SubagentStop hook: reviewer citation span-validator (anti-hallucination).

Adopts rubric's mechanical span-check (verify.py) for GOAT-CEO's correctness reviewers
(A/B). check_toolcall_audit.py confirms a reviewer READ files; this confirms its CITATIONS
RESOLVE — it opens each cited code span and verifies it actually exists. A reviewer that
cites a plausible-but-fabricated foo.py:213 is a hallucination vector the read-floor cannot
catch.

Mechanism: the reviewer's verdict carries `cited_spans: [{file, line, quote}]`. For each, the
hook opens <cwd>/<file> and confirms `quote` appears (whitespace-normalized, like rubric's
_normalize_ws). Any clearly-fabricated span → exit 2, blocking the reviewer's stop with the
offending citations so it must remove/correct them and re-issue.

Only gates A/B reviewers (the `"reviewer":"A"|"B"` marker). Judge/critic/Reviewer-C are exempt
(Reviewer C's spans are rubric's, already span-checked inside `rubric enforce --verify`).

Anti-false-positive guards (a wrong block would stall the pipeline):
  - parse spans ONLY from the reviewer's OWN ASSISTANT messages, never the prompt/template
    (whose schema example contains placeholder file/quote);
  - skip placeholder-looking entries (file starting with '<', quote containing '<' or empty);
  - require a substantive quote (>= MIN_QUOTE non-space chars) before judging it fabricated;
  - if extraction is ambiguous or anything errors, FAIL OPEN.

Design contract: FAIL-OPEN on any internal error. exit 0 = allow; exit 2 = BLOCK. stdlib only.
"""
import json
import os
import re
import sys

GATED_ROLES = {"team-verifier"}
REVIEWER_MARKER = re.compile(r'"reviewer"\s*:\s*"(A|B)"')
MIN_QUOTE = 12  # non-whitespace chars; below this a quote is too trivial to adjudicate
LINE_WINDOW = 3  # the cited quote must appear within cited_line ± this many lines

# A cited-span object: {"file": "...", "line": <n|null>, "quote": "..."} in any field order.
_SPAN_RE = re.compile(
    r'\{(?P<body>[^{}]*?"file"\s*:\s*"(?P<file>(?:[^"\\]|\\.)*)"[^{}]*?'
    r'"quote"\s*:\s*"(?P<quote>(?:[^"\\]|\\.)*)"[^{}]*?)\}'
)
_LINE_RE = re.compile(r'"line"\s*:\s*(\d+|null)')


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _unescape(s):
    try:
        return json.loads('"' + s + '"')
    except Exception:
        return s.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")


def _assistant_text(transcript_text):
    """Concatenate decoded text from ASSISTANT messages only (excludes the prompt/template)."""
    parts = []
    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = ev.get("role") or (ev.get("message") or {}).get("role") or ev.get("type")
        if role != "assistant":
            continue
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else ev
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", "") or "")
    return "\n".join(parts)


def _extract_spans(text):
    spans = []
    for m in _SPAN_RE.finditer(text):
        file_ = _unescape(m.group("file"))
        quote = _unescape(m.group("quote"))
        lm = _LINE_RE.search(m.group("body"))
        line = lm.group(1) if lm else None
        spans.append({"file": file_, "quote": quote, "line": line})
    return spans


def _parse_line(line):
    """Coerce the cited `line` (str/int/None/'null') to an int, or None if absent."""
    if line is None:
        return None
    try:
        if isinstance(line, str):
            line = line.strip()
            if line.lower() == "null" or line == "":
                return None
        return int(line)
    except (TypeError, ValueError):
        return None


def _quote_in_window(quote, content, cited_line, window=LINE_WINDOW):
    """True if normalized `quote` appears within cited_line ± window of `content`.

    A quote may itself span multiple lines, so we slide a window over the file and test
    each window-join against the quote. If cited_line is None/out-of-range we cannot
    line-anchor, so we fall back to whole-file containment (substring) — the placeholder
    and MIN_QUOTE guards already filter trivial quotes, and a missing line is the
    reviewer's omission, not a fabrication we can localize."""
    nq = _norm(quote)
    if not nq:
        return True  # nothing substantive to check
    lines = content.splitlines()
    if cited_line is None or cited_line < 1 or cited_line > len(lines):
        return nq in _norm(content)  # cannot anchor — fall back to anywhere-in-file
    lo = max(0, cited_line - 1 - window)
    hi = min(len(lines), cited_line - 1 + window + 1)
    window_text = "\n".join(lines[lo:hi])
    return nq in _norm(window_text)


def _is_placeholder(file_, quote):
    if not file_ or not quote:
        return True
    if file_.startswith("<") or "<path>" in file_:
        return True
    if "<" in quote and ">" in quote:  # e.g. "<exact code span>"
        return True
    if len(re.sub(r"\s+", "", quote)) < MIN_QUOTE:
        return True
    return False


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if agent_type not in GATED_ROLES:
            return 0

        tpath = data.get("agent_transcript_path", "") or data.get("transcript_path", "")
        cwd = data.get("cwd", "") or "."
        if not tpath or not os.path.exists(tpath):
            return 0  # can't validate — fail open

        full = _read(tpath)
        if full is None:
            return 0

        # Parse the reviewer's OWN assistant output only (not the echoed prompt/template).
        # Decoded here, so quotes are real (the raw transcript has them backslash-escaped).
        assistant = _assistant_text(full)

        # Only gate actual A/B reviewers — check the marker on DECODED text.
        last_msg = str(data.get("last_assistant_message", "") or "")
        if not (REVIEWER_MARKER.search(assistant) or REVIEWER_MARKER.search(last_msg)):
            return 0

        spans = _extract_spans(assistant)
        if not spans:
            # C7(a) — close the no-spans dodge. A confirmed A/B reviewer that emitted a
            # verdict but ZERO structured cited_spans is blocked: a verdict must be backed
            # by at least one checkable, line-anchored citation.
            try:
                sys.stderr.write(
                    "CITATION SPAN BLOCK: your A/B verdict carries ZERO structured cited_spans. "
                    "A correctness verdict must cite at least one concrete code span the way the "
                    "review template specifies — {\"file\": \"path\", \"line\": N, \"quote\": "
                    "\"exact code\"} — so the claim is mechanically checkable. Add the span(s) you "
                    "actually inspected and re-issue your verdict."
                )
            except Exception:
                pass  # never let an I/O failure downgrade a block to an allow
            return 2

        fabricated = []
        for sp in spans:
            f, q = sp.get("file"), sp.get("quote")
            if _is_placeholder(f, q):
                continue
            fpath = f if os.path.isabs(f) else os.path.join(cwd, f)
            content = _read(fpath)
            if content is None:
                fabricated.append("{} (cited file not found)".format(f))
                continue
            cited_line = _parse_line(sp.get("line"))
            # C7(b) — validate within the cited line window (± LINE_WINDOW), not anywhere.
            if not _quote_in_window(q, content, cited_line):
                where = (
                    "near line {} (±{})".format(cited_line, LINE_WINDOW)
                    if cited_line is not None else "anywhere in file"
                )
                fabricated.append(
                    "{}:{} — cited span not found {}: {!r}".format(
                        f, sp.get("line"), where, q[:80]
                    )
                )

        if fabricated:
            try:
                sys.stderr.write(
                    "CITATION SPAN BLOCK: your verdict cites code spans that do NOT exist in the files "
                    "(fabricated/hallucinated citations — the review equivalent of mock-only testing). "
                    "Open the real files, fix or remove these citations, and re-issue your verdict:\n- "
                    + "\n- ".join(fabricated)
                )
            except Exception:
                pass  # never let an I/O failure downgrade a block to an allow
            return 2

        return 0
    except Exception:
        return 0  # fail open — a hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
