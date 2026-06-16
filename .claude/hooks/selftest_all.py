"""GOAT-CEO hook self-test suite (C10) — the engine behind /goat-doctor.

Crafts JSON payloads, invokes each hook as a subprocess with that payload on
stdin, and ASSERTS the exit code — proving each gate actually BLOCKS (exit 2) or
ALLOWS (exit 0). Prints one PASS/FAIL/SKIP line per check and exits non-zero if
any check fails.

SAFETY: agent-workspace/ holds real artifacts. Every workspace mutation goes
through `workspace_file()`, which backs up the existing file (if any), writes the
fixture, yields, and then RESTORES the original (or deletes the fixture if there
was none) in a finally block — so the suite leaves agent-workspace byte-identical
to how it found it. A protected-files integrity check runs at the end.

Run:  python .claude/hooks/selftest_all.py
"""
import atexit
import contextlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time


def _rmtree(path):
    """rmtree that survives Windows read-only files (git marks .git/objects
    read-only, and shutil.rmtree can't unlink those without clearing the bit)."""
    def _onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_onerror)

# selftest is in .claude/hooks/, so repo root = three dirs up.
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")

# Files in agent-workspace that must survive the suite byte-for-byte if present.
PROTECTED = [
    "MISSION.md",
    "ASSESSMENT.md",
    "STATUS.md",
    "IMPLEMENTATION-MANIFEST.json",
    "BASELINE.txt",
    "AGENT-START-TIMES.json",
    "HOOK-FAILURES.jsonl",
]

PYEXE = sys.executable or "python"

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
_PASS = 0
_FAIL = 0
_SKIP = 0


def record_pass(label):
    global _PASS
    _PASS += 1
    print("PASS " + label)


def record_fail(label, expected, got, extra=""):
    global _FAIL
    _FAIL += 1
    msg = "FAIL {} (expected {} got {})".format(label, expected, got)
    if extra:
        msg += " :: " + extra
    print(msg)


def record_skip(label, reason):
    global _SKIP
    _SKIP += 1
    print("SKIP {} ({})".format(label, reason))


# ---------------------------------------------------------------------------
# Subprocess hook runner
# ---------------------------------------------------------------------------
def run_hook(hook_name, payload, env_extra=None):
    """Invoke .claude/hooks/<hook_name> with `payload` (dict or str) on stdin.

    Returns (returncode, stdout, stderr).
    """
    path = os.path.join(HOOKS_DIR, hook_name)
    if isinstance(payload, (dict, list)):
        stdin = json.dumps(payload)
    else:
        stdin = payload
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [PYEXE, path],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    return proc.returncode, proc.stdout, proc.stderr


def assert_exit(label, hook_name, payload, expected, env_extra=None):
    """Run a hook and assert its exit code equals `expected`. Records PASS/FAIL."""
    try:
        rc, out, err = run_hook(hook_name, payload, env_extra=env_extra)
    except Exception as exc:  # pragma: no cover
        record_fail(label, expected, "EXC", str(exc))
        return False
    if rc == expected:
        record_pass(label)
        return True
    tail = (err or out or "").strip().replace("\n", " ")[:200]
    record_fail(label, expected, rc, tail)
    return False


# ---------------------------------------------------------------------------
# Workspace fixture context manager (backup + restore — byte-safe)
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def workspace_file(name, content):
    """Write a fixture into agent-workspace/<name>, restoring prior state after.

    Backs up an existing file to a temp location; on exit restores it byte-for-byte
    (or deletes the fixture if there was no original). content may be str (written
    utf-8) or dict/list (json-dumped).
    """
    os.makedirs(WORKSPACE, exist_ok=True)
    target = os.path.join(WORKSPACE, name)
    had_original = os.path.exists(target)
    backup = None
    if had_original:
        fd, backup = tempfile.mkstemp(prefix="goat_selftest_bak_")
        os.close(fd)
        shutil.copy2(target, backup)
    try:
        if isinstance(content, (dict, list)):
            data = json.dumps(content)
        else:
            data = content
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(data)
        yield target
    finally:
        if had_original:
            shutil.copy2(backup, target)
            try:
                os.remove(backup)
            except OSError:
                pass
        else:
            if os.path.exists(target):
                try:
                    os.remove(target)
                except OSError:
                    pass


@contextlib.contextmanager
def workspace_absent(name):
    """Ensure agent-workspace/<name> is absent for the body, restoring it after."""
    target = os.path.join(WORKSPACE, name)
    had_original = os.path.exists(target)
    backup = None
    if had_original:
        fd, backup = tempfile.mkstemp(prefix="goat_selftest_bak_")
        os.close(fd)
        shutil.copy2(target, backup)
        os.remove(target)
    try:
        yield
    finally:
        if had_original:
            shutil.copy2(backup, target)
            try:
                os.remove(backup)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Temp git repo helpers
# ---------------------------------------------------------------------------
def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
    )


def make_temp_git_repo():
    """Create a temp git repo with one commit. Returns (path, head_sha)."""
    tmp = tempfile.mkdtemp(prefix="goat_selftest_repo_")
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "selftest@example.com")
    _git(tmp, "config", "user.name", "selftest")
    # Disable fsmonitor/untracked-cache so git leaves no background daemon holding
    # an open handle on the temp dir (which would block rmtree on Windows).
    _git(tmp, "config", "core.fsmonitor", "false")
    _git(tmp, "config", "core.untrackedCache", "false")
    with open(os.path.join(tmp, "seed.txt"), "w", encoding="utf-8") as fh:
        fh.write("seed\n")
    _git(tmp, "add", "seed.txt")
    _git(tmp, "commit", "-q", "-m", "seed")
    head = _git(tmp, "rev-parse", "HEAD").stdout.strip()
    return tmp, head


_TMP_DIRS = []


def cleanup_tmp():
    # On Windows, git may briefly hold a handle (index/fsmonitor) after the last
    # subprocess returns, so an inline rmtree can leave the dir behind in %TEMP%.
    # Retry with a short backoff; anything still locked is swept at process exit
    # (by which point all git children are gone) via the atexit hook below.
    for d in list(_TMP_DIRS):
        for _ in range(5):
            if not os.path.isdir(d):
                break
            _rmtree(d)
            if not os.path.isdir(d):
                break
            time.sleep(0.1)


@atexit.register
def _final_sweep():
    """Last-chance cleanup of any temp git repos/files still locked when the
    inline cleanup ran. At interpreter exit all git subprocesses have exited, so
    their handles are released and rmtree succeeds — keeps %TEMP% clean across
    repeated /goat-doctor runs."""
    for d in list(_TMP_DIRS):
        if os.path.isdir(d):
            _rmtree(d)
    for f in list(_TMP_FILES):
        try:
            os.remove(f)
        except OSError:
            pass


def temp_jsonl(lines):
    """Write a JSONL transcript file from `lines` (list of dicts). Returns its path."""
    fd, path = tempfile.mkstemp(prefix="goat_selftest_tx_", suffix=".jsonl")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")
    _TMP_FILES.append(path)
    return path


_TMP_FILES = []


def cleanup_tmp_files():
    for f in _TMP_FILES:
        try:
            os.remove(f)
        except OSError:
            pass


def assistant_msg(text):
    """A JSONL transcript line representing an assistant text message."""
    return {"role": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": text}]}}


def tool_use_msg(name, tool_input):
    """A JSONL transcript line representing an assistant tool_use block."""
    return {"role": "assistant", "message": {"role": "assistant",
            "content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


# ===========================================================================
# CHECK GROUPS
# ===========================================================================
def check_A_fail_open():
    """Every *.py hook (except selftest_all.py and _strict.py) must fail OPEN on
    empty {} and garbage stdin, with no traceback in stderr."""
    skip = {"selftest_all.py", "_strict.py"}
    hooks = sorted(
        f for f in os.listdir(HOOKS_DIR)
        if f.endswith(".py") and f not in skip
    )
    for hook in hooks:
        # empty {}
        rc, out, err = run_hook(hook, "{}")
        if rc == 0 and "Traceback" not in err:
            record_pass("A.fail-open empty {} :: " + hook)
        else:
            record_fail("A.fail-open empty {} :: " + hook, 0, rc,
                        "Traceback" if "Traceback" in err else err.strip()[:160])
        # garbage
        rc, out, err = run_hook(hook, "not json###")
        if rc == 0 and "Traceback" not in err:
            record_pass("A.fail-open garbage :: " + hook)
        else:
            record_fail("A.fail-open garbage :: " + hook, 0, rc,
                        "Traceback" if "Traceback" in err else err.strip()[:160])


def check_B_stop_file():
    with workspace_file("STOP", "stop"):
        assert_exit("B.stop-file present blocks Bash", "check_stop_file.py",
                    {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}, 2)
    with workspace_absent("STOP"):
        assert_exit("B.stop-file absent allows", "check_stop_file.py",
                    {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}, 0)


def check_C_git_commit():
    block = [
        ("git add -A", "git add -A"),
        ("git -C /other/repo add -A", "git -C /other add -A"),
        ("git add :/", "git add :/"),
        ("git add -u", "git add -u"),
        ("git add *", "git add *"),
        ("git add -- .", "git add -- ."),
        ("git add .", "git add ."),
        # ceo-commit.sh substring must NOT wave a chained sweep past the guard.
        ("echo ceo-commit.sh && git add -A", "ceo-commit substring + chained sweep"),
        ("ceo-commit.sh x; git add -A", "ceo-commit substring + ; sweep"),
        # QUOTED sweep selectors (the shell strips the quotes; git sweeps anyway).
        ('git add "."', 'quoted "."'),
        ("git add './'", "quoted './'"),
        ('git add ":/"', 'quoted ":/"'),
        ('git add "-A"', 'quoted "-A"'),
        ('git add -- "."', 'quoted -- "."'),
    ]
    for cmd, label in block:
        assert_exit("C.block " + label, "guard_git_commit.py",
                    {"tool_name": "Bash", "tool_input": {"command": cmd}}, 2)
    allow = [
        ("git add path/to/file.py", "git add path/to/file.py"),
        ("git add .claude/settings.json", "git add .claude/settings.json"),
        ("git add ./src/foo.py", "git add ./src/foo.py"),
        ("git add .gitignore", "git add .gitignore (dotfile, not sweep)"),
        ('git add "my file.py"', 'quoted normal path'),
        ('bash .claude/hooks/ceo-commit.sh "m" .claude/settings.json',
         "clean ceo-commit.sh invocation"),
        ("git commit -m x", "raw git commit (warn-only)"),
        ("git push", "raw git push (warn-only)"),
    ]
    for cmd, label in allow:
        assert_exit("C.allow " + label, "guard_git_commit.py",
                    {"tool_name": "Bash", "tool_input": {"command": cmd}}, 0)


def check_D_secrets():
    block = [".env", ".env.local", "secrets.json", "id_rsa", "foo.pem", "bar.key"]
    for p in block:
        assert_exit("D.block " + p, "guard_secrets.py",
                    {"tool_name": "Write", "tool_input": {"file_path": p}}, 2)
    allow = ["src/main.py", "README.md"]
    for p in allow:
        assert_exit("D.allow " + p, "guard_secrets.py",
                    {"tool_name": "Write", "tool_input": {"file_path": p}}, 0)


def check_E_test_gate():
    tmp, _ = make_temp_git_repo()
    _TMP_DIRS.append(tmp)
    failing = {
        "workingDirectory": tmp,
        "commands": [{"name": "fail", "command": PYEXE + ' -c "import sys;sys.exit(1)"',
                      "timeoutSeconds": 30, "required": True}],
    }
    passing = {
        "workingDirectory": tmp,
        "commands": [{"name": "ok",
                      "command": PYEXE + ' -c "print(\'5 passed\')"',
                      "timeoutSeconds": 30, "required": True}],
    }
    with workspace_file("TEST-CONFIG.json", failing):
        assert_exit("E.test-gate failing cmd blocks", "check_test_gate.py",
                    {"agent_type": "team-implementer", "cwd": tmp}, 2)
    with workspace_file("TEST-CONFIG.json", passing):
        assert_exit("E.test-gate passing cmd allows", "check_test_gate.py",
                    {"agent_type": "team-implementer", "cwd": tmp}, 0)
    # No config: ensure neither TEST-CONFIG.json nor TEST-COMMAND.txt present.
    with workspace_absent("TEST-CONFIG.json"):
        with workspace_absent("TEST-COMMAND.txt"):
            assert_exit("E.test-gate no-config allows (non-strict)", "check_test_gate.py",
                        {"agent_type": "team-implementer", "cwd": tmp}, 0)
            assert_exit("E.test-gate no-config blocks (STRICT)", "check_test_gate.py",
                        {"agent_type": "team-implementer", "cwd": tmp}, 2,
                        env_extra={"GOAT_CEO_STRICT": "1"})


def check_F_artifacts():
    sid = "selftest-impl-sid"
    # (1) implementer, startHead == HEAD, clean tree -> BLOCK
    tmp, head = make_temp_git_repo()
    _TMP_DIRS.append(tmp)
    with workspace_file("AGENT-START-TIMES.json", {sid + "_startHead": head}):
        assert_exit("F.impl clean+startHead==HEAD blocks", "check_artifacts.py",
                    {"agent_type": "team-implementer", "cwd": tmp,
                     "session_id": sid, "agent_transcript_path": ""}, 2)
        # (2) same baseline but with an uncommitted change -> ALLOW
        with open(os.path.join(tmp, "newfile.txt"), "w", encoding="utf-8") as fh:
            fh.write("dirty\n")
        assert_exit("F.impl uncommitted change allows", "check_artifacts.py",
                    {"agent_type": "team-implementer", "cwd": tmp,
                     "session_id": sid, "agent_transcript_path": ""}, 0)
    # (3) implementer, NO AGENT-START-TIMES (unknown baseline) -> ALLOW (fail-open)
    tmp2, _ = make_temp_git_repo()
    _TMP_DIRS.append(tmp2)
    with workspace_absent("AGENT-START-TIMES.json"):
        # also avoid IMPLEMENTER-RESULT evidence interfering — none exists by default
        assert_exit("F.impl unknown baseline allows", "check_artifacts.py",
                    {"agent_type": "team-implementer", "cwd": tmp2,
                     "session_id": "no-baseline-sid", "agent_transcript_path": ""}, 0)
    # (4) verifier with verdict in transcript -> ALLOW
    tx_pass = temp_jsonl([assistant_msg('Result: {"verdict":"PASS"}')])
    # REVIEW-LOG.md must be absent so the verdict source is purely the transcript.
    with workspace_absent("REVIEW-LOG.md"):
        assert_exit("F.verifier verdict-in-transcript allows", "check_artifacts.py",
                    {"agent_type": "team-verifier", "cwd": ".",
                     "agent_transcript_path": tx_pass}, 0)
        # (5) verifier with no verdict -> BLOCK
        tx_none = temp_jsonl([assistant_msg("I looked at the code and it seems fine.")])
        assert_exit("F.verifier no-verdict blocks", "check_artifacts.py",
                    {"agent_type": "team-verifier", "cwd": ".",
                     "agent_transcript_path": tx_none}, 2)
    # (6) architect with PLAN.md -> ALLOW; without -> BLOCK
    with workspace_file("PLAN.md", "# plan\nstuff"):
        assert_exit("F.architect with PLAN.md allows", "check_artifacts.py",
                    {"agent_type": "team-architect", "cwd": "."}, 0)
    with workspace_absent("PLAN.md"):
        assert_exit("F.architect without PLAN.md blocks", "check_artifacts.py",
                    {"agent_type": "team-architect", "cwd": "."}, 2)
    # (7) anti-stale: a STALE IMPLEMENTER-RESULT (different sessionId, endHead != current
    #     HEAD) must NOT clear a no-op implementer (clean tree, HEAD == startHead) -> BLOCK.
    tmp3, head3 = make_temp_git_repo()
    _TMP_DIRS.append(tmp3)
    sid3 = "selftest-impl-sid-3"
    stale_result = {
        "sessionId": "OTHER-OLD-SESSION", "batchId": "old-batch",
        "startHead": "0" * 40, "endHead": "a" * 40,
        "changedFiles": ["src/old.py"],
    }
    with workspace_file("AGENT-START-TIMES.json", {sid3 + "_startHead": head3}):
        with workspace_absent("IMPLEMENTATION-MANIFEST.json"):
            with workspace_file("IMPLEMENTER-RESULT.stale.json", stale_result):
                assert_exit("F.impl stale result still blocks", "check_artifacts.py",
                            {"agent_type": "team-implementer", "cwd": tmp3,
                             "session_id": sid3, "agent_transcript_path": ""}, 2)
            # (8) a CURRENT-RUN result (sessionId matches) clears a clean no-op tree -> ALLOW.
            current_result = {
                "sessionId": sid3, "batchId": "cur",
                "startHead": head3, "endHead": "f" * 40,
                "changedFiles": ["src/new.py"],
            }
            with workspace_file("IMPLEMENTER-RESULT.current.json", current_result):
                assert_exit("F.impl current-run result allows", "check_artifacts.py",
                            {"agent_type": "team-implementer", "cwd": tmp3,
                             "session_id": sid3, "agent_transcript_path": ""}, 0)
    # (9) same-session stale: the result's sessionId MATCHES the run, but its startHead is
    #     stale and endHead != current HEAD -> still BLOCK. sessionId is no longer a binder,
    #     so an earlier batch of the same long-running session can't clear a no-op.
    tmp4, head4 = make_temp_git_repo()
    _TMP_DIRS.append(tmp4)
    sid4 = "selftest-impl-sid-4"
    same_session_stale = {
        "sessionId": sid4, "batchId": "earlier-batch",
        "startHead": "0" * 40, "endHead": "b" * 40,  # stale startHead; endHead != HEAD
        "changedFiles": ["src/earlier.py"],
    }
    with workspace_file("AGENT-START-TIMES.json", {sid4 + "_startHead": head4}):
        with workspace_absent("IMPLEMENTATION-MANIFEST.json"):
            with workspace_file("IMPLEMENTER-RESULT.samesession.json", same_session_stale):
                assert_exit("F.impl same-session stale result blocks", "check_artifacts.py",
                            {"agent_type": "team-implementer", "cwd": tmp4,
                             "session_id": sid4, "agent_transcript_path": ""}, 2)


def check_G_review_gate():
    # Gate fires for team-verifier (TaskCompleted). Iteration absent == 1 (within cap).
    payload = {"agent_type": "team-verifier"}
    # (1) JUDGE-VERDICT.json PASS -> ALLOW. REVIEW-ITERATION must be absent (==1).
    with workspace_absent("REVIEW-ITERATION.txt"):
        with workspace_absent("REVIEW-LOG.md"):
            with workspace_file("JUDGE-VERDICT.json",
                                {"role": "judge", "verdict": "PASS"}):
                assert_exit("G.judge PASS allows", "check_review_gate.py", payload, 0)
            # (3) JUDGE-VERDICT.json FAIL -> BLOCK
            with workspace_file("JUDGE-VERDICT.json",
                                {"role": "judge", "verdict": "FAIL"}):
                assert_exit("G.judge FAIL blocks", "check_review_gate.py", payload, 2)
            # (4) judge PASS but NON-EMPTY blockingFindingsRemaining -> BLOCK (contradictory)
            with workspace_file("JUDGE-VERDICT.json",
                                {"role": "judge", "verdict": "PASS",
                                 "blockingFindingsRemaining": ["critical issue still open"]}):
                assert_exit("G.judge PASS+blockers blocks", "check_review_gate.py", payload, 2)
        # (2) REVIEW-LOG.md with only a non-judge PASS, no JUDGE-VERDICT.json -> BLOCK
        review_log = '```json\n{"verdict": "PASS", "reviewer": "A"}\n```\n'
        with workspace_absent("JUDGE-VERDICT.json"):
            with workspace_file("REVIEW-LOG.md", review_log):
                assert_exit("G.non-judge PASS blocks", "check_review_gate.py", payload, 2)


def check_H_span_validity():
    # Build a temp file with a known line the reviewer can cite.
    tmp = tempfile.mkdtemp(prefix="goat_selftest_src_")
    _TMP_DIRS.append(tmp)
    src_rel = "module.py"
    lines = [
        "import os\n",                               # line 1
        "import sys\n",                              # line 2
        "# pad\n",                                   # line 3
        "# pad\n",                                   # line 4
        "# pad\n",                                   # line 5
        "# pad\n",                                   # line 6
        "# pad\n",                                   # line 7
        "# pad\n",                                   # line 8
        "# pad\n",                                   # line 9
        "def compute(x):\n",                         # line 10
        "    return x * 42 + special_constant\n",    # line 11 (the quote)
        "# trailing\n",                              # line 12
    ]
    with open(os.path.join(tmp, src_rel), "w", encoding="utf-8") as fh:
        fh.writelines(lines)

    # (1) reviewer A with a verdict but ZERO cited_spans -> BLOCK
    tx_nospan = temp_jsonl([assistant_msg(
        'My verdict: {"reviewer":"A","verdict":"FAIL"} — no spans here.'
    )])
    assert_exit("H.reviewer A zero spans blocks", "check_span_validity.py",
                {"agent_type": "team-verifier", "cwd": tmp,
                 "agent_transcript_path": tx_nospan}, 2)

    # (2) reviewer A with a cited_span whose quote matches the real line -> ALLOW
    good_span = ('{"reviewer":"A","verdict":"PASS","cited_spans":['
                 '{"file":"module.py","line":11,'
                 '"quote":"return x * 42 + special_constant"}]}')
    tx_good = temp_jsonl([assistant_msg("Here is my review " + good_span)])
    assert_exit("H.reviewer A valid span allows", "check_span_validity.py",
                {"agent_type": "team-verifier", "cwd": tmp,
                 "agent_transcript_path": tx_good}, 0)

    # (3) reviewer A citing text NOT at the cited line -> BLOCK
    bad_span = ('{"reviewer":"A","verdict":"FAIL","cited_spans":['
                '{"file":"module.py","line":1,'
                '"quote":"return x * 42 + special_constant"}]}')
    tx_bad = temp_jsonl([assistant_msg("Review with wrong line " + bad_span)])
    assert_exit("H.reviewer A wrong-line span blocks", "check_span_validity.py",
                {"agent_type": "team-verifier", "cwd": tmp,
                 "agent_transcript_path": tx_bad}, 2)

    # (4) reviewer A span with NO line anchor (line:null) -> BLOCK. The quote DOES exist
    #     in the file, so this only blocks because A/B spans must be line-anchored (no
    #     whole-file-substring fallback for the gate).
    noline_span = ('{"reviewer":"A","verdict":"PASS","cited_spans":['
                   '{"file":"module.py","line":null,'
                   '"quote":"return x * 42 + special_constant"}]}')
    tx_noline = temp_jsonl([assistant_msg("Review missing line " + noline_span)])
    assert_exit("H.reviewer A missing-line span blocks", "check_span_validity.py",
                {"agent_type": "team-verifier", "cwd": tmp,
                 "agent_transcript_path": tx_noline}, 2)

    # (5) valid span in QUOTE-before-FILE order -> ALLOW. Field-order-agnostic extraction;
    #     previously a file-before-quote regex missed this and false-blocked as "zero spans".
    qf_span = ('{"reviewer":"A","verdict":"PASS","cited_spans":['
               '{"quote":"return x * 42 + special_constant","line":11,'
               '"file":"module.py"}]}')
    tx_qf = temp_jsonl([assistant_msg("Quote-first span " + qf_span)])
    assert_exit("H.reviewer A quote-first span allows", "check_span_validity.py",
                {"agent_type": "team-verifier", "cwd": tmp,
                 "agent_transcript_path": tx_qf}, 0)


def check_I_partition():
    disjoint = {"batches": [
        {"id": "b1", "files": ["src/a.py", "src/b.py"]},
        {"id": "b2", "files": ["src/c.py", "src/d.py"]},
    ]}
    overlap = {"batches": [
        {"id": "b1", "files": ["src/a.py", "src/shared.py"]},
        {"id": "b2", "files": ["src/shared.py", "src/d.py"]},
    ]}
    payload = {"agent_type": "team-architect"}
    with workspace_file("IMPLEMENTATION-MANIFEST.json", disjoint):
        assert_exit("I.disjoint manifest allows", "check_partition.py", payload, 0)
    with workspace_file("IMPLEMENTATION-MANIFEST.json", overlap):
        assert_exit("I.overlapping manifest blocks", "check_partition.py", payload, 2)


def check_J_phase_gate():
    # PHASE-GATES.json maps role -> required sentinels. A non-CEO role with a
    # required *.GATE sentinel MISSING -> BLOCK; with the sentinel present -> ALLOW.
    gate_map = {"team-implementer": ["SELFTEST.GATE"]}
    payload = {"tool_name": "Write", "agent_type": "team-implementer",
               "tool_input": {"file_path": "src/x.py"}}
    with workspace_file("PHASE-GATES.json", gate_map):
        with workspace_absent("SELFTEST.GATE"):
            assert_exit("J.missing gate sentinel blocks", "check_phase_gate.py",
                        payload, 2)
        with workspace_file("SELFTEST.GATE", "ok"):
            assert_exit("J.present gate sentinel allows", "check_phase_gate.py",
                        payload, 0)


def check_K_read_audit():
    """Reviewer read-audit (C6): the diff-tie must use the changed-set fallback chain.

    The changed set here comes from a central IMPLEMENTER-RESULT*.json `changedFiles`
    (the head of the fallback chain). A reviewer whose 5 reads miss the changed set is
    BLOCKED; one whose reads cover it is ALLOWED."""
    changed = ["src/a.py", "src/b.py", "src/c.py"]
    result = {"sessionId": "k", "batchId": "k", "startHead": "0" * 40,
              "endHead": "1" * 40, "changedFiles": changed}
    verdict = assistant_msg('My verdict: {"reviewer":"A","verdict":"PASS"}')
    # (1) 5 reads but only 1 in the changed set -> BLOCK (fails the diff-tie floor).
    miss_paths = ["src/a.py", "docs/x.md", "docs/y.md", "README.md", "other/z.py"]
    tx_miss = temp_jsonl([tool_use_msg("Read", {"file_path": p}) for p in miss_paths]
                         + [verdict])
    # (2) reads the 3 changed files + 2 others -> ALLOW.
    hit_paths = ["src/a.py", "src/b.py", "src/c.py", "README.md", "other/z.py"]
    tx_hit = temp_jsonl([tool_use_msg("Read", {"file_path": p}) for p in hit_paths]
                        + [verdict])
    # Remove any real manifest so the result file is the deterministic changed-set source.
    with workspace_absent("IMPLEMENTATION-MANIFEST.json"):
        with workspace_file("IMPLEMENTER-RESULT.ktest.json", result):
            assert_exit("K.read-audit misses changed set blocks", "check_toolcall_audit.py",
                        {"agent_type": "team-verifier", "cwd": ".",
                         "agent_transcript_path": tx_miss}, 2)
            assert_exit("K.read-audit covers changed set allows", "check_toolcall_audit.py",
                        {"agent_type": "team-verifier", "cwd": ".",
                         "agent_transcript_path": tx_hit}, 0)


def check_L_commit_wrappers():
    """Commit wrappers reject the full sweep set (aligned with guard_git_commit.py).

    Runs the wrapper(s) in a THROWAWAY git repo so a hypothetical validation miss can
    only touch that repo, never the real one. Best-effort: SKIP if the interpreter is
    not on PATH (the suite must run on any OS)."""
    tmp, _ = make_temp_git_repo()
    _TMP_DIRS.append(tmp)
    forbidden = [".", "./", "-A", "--all", "-u", "--update", "*", ":", ":/"]

    def _run_wrapper(label_prefix, argv_prefix, script):
        if not os.path.exists(script):
            record_skip(label_prefix + " commit wrapper", "wrapper missing")
            return
        for ps in forbidden:
            try:
                proc = subprocess.run(
                    argv_prefix + [script, "selftest-should-not-commit", ps],
                    capture_output=True, text=True, cwd=tmp,
                )
            except Exception as exc:  # pragma: no cover
                record_fail(label_prefix + " blocks " + ps, 1, "EXC", str(exc))
                continue
            if proc.returncode == 1:
                record_pass(label_prefix + " blocks " + ps)
            else:
                tail = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:160]
                record_fail(label_prefix + " blocks " + ps, 1, proc.returncode, tail)

    sh = shutil.which("bash")
    if sh:
        _run_wrapper("L.sh", [sh], os.path.join(HOOKS_DIR, "ceo-commit.sh"))
    else:
        record_skip("L.sh commit wrapper", "bash not on PATH")

    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh:
        _run_wrapper("L.ps1", [pwsh, "-NoProfile", "-File"],
                     os.path.join(HOOKS_DIR, "ceo-commit.ps1"))
    else:
        record_skip("L.ps1 commit wrapper", "powershell not on PATH")


# ===========================================================================
# Integrity verification of protected files
# ===========================================================================
def snapshot_protected():
    snap = {}
    for name in PROTECTED:
        p = os.path.join(WORKSPACE, name)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                snap[name] = fh.read()
    return snap


def verify_protected(before):
    """Confirm protected files are byte-intact and still present. Returns True/False."""
    ok = True
    for name, data in before.items():
        p = os.path.join(WORKSPACE, name)
        if not os.path.exists(p):
            print("INTEGRITY FAIL: protected file vanished: " + name)
            ok = False
            continue
        with open(p, "rb") as fh:
            now = fh.read()
        if now != data:
            print("INTEGRITY FAIL: protected file changed: " + name)
            ok = False
    if ok:
        print("INTEGRITY OK: {} protected file(s) byte-intact.".format(len(before)))
    return ok


@contextlib.contextmanager
def preserve_failures_log():
    """Hooks legitimately APPEND to agent-workspace/HOOK-FAILURES.jsonl during the
    run (e.g. check_test_gate's degraded-allow path calls log_failopen). It is a
    protected file, so snapshot it and restore byte-for-byte afterward."""
    p = os.path.join(WORKSPACE, "HOOK-FAILURES.jsonl")
    had = os.path.exists(p)
    backup = None
    if had:
        fd, backup = tempfile.mkstemp(prefix="goat_selftest_bak_")
        os.close(fd)
        shutil.copy2(p, backup)
    try:
        yield
    finally:
        if had:
            shutil.copy2(backup, p)
            try:
                os.remove(backup)
            except OSError:
                pass
        elif os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def sweep_stale_temp():
    """Delete temp dirs/files left by PRIOR selftest runs. On Windows git can hold
    a handle on a temp repo until its process fully exits, so the current run's own
    inline + atexit cleanup may not catch everything. Those handles ARE released by
    the next run, so we sweep leftovers at startup — keeping %TEMP% from growing
    across repeated /goat-doctor invocations."""
    import glob as _g
    root = tempfile.gettempdir()
    for pat in ("goat_selftest_repo_*", "goat_selftest_src_*",
                "goat_selftest_tx_*", "goat_selftest_bak_*"):
        for path in _g.glob(os.path.join(root, pat)):
            if os.path.isdir(path):
                _rmtree(path)
            else:
                try:
                    os.remove(path)
                except OSError:
                    pass


def main():
    sweep_stale_temp()
    before = snapshot_protected()
    try:
      with preserve_failures_log():
        check_A_fail_open()
        check_B_stop_file()
        check_C_git_commit()
        check_D_secrets()
        check_E_test_gate()
        check_F_artifacts()
        check_G_review_gate()
        check_H_span_validity()
        check_I_partition()
        check_J_phase_gate()
        check_K_read_audit()
        check_L_commit_wrappers()
    finally:
        cleanup_tmp_files()
        cleanup_tmp()

    integrity_ok = verify_protected(before)

    print("")
    print("{} passed, {} failed, {} skipped".format(_PASS, _FAIL, _SKIP))
    if not integrity_ok:
        print("PROTECTED-FILE INTEGRITY CHECK FAILED")
    sys.exit(1 if (_FAIL or not integrity_ok) else 0)


if __name__ == "__main__":
    main()
