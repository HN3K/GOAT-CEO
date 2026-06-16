"""LLM client abstraction: tier resolution, scripted fake, subscription CLI client."""

import json
import subprocess

import pytest

from research_system.llm import (
    _API_IDS,
    _CLI_ALIASES,
    CHEAP,
    ClaudeCLIClient,
    ScriptedClient,
    resolve_model,
)


class FakeProc:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_resolve_model_tiers_and_passthrough():
    assert resolve_model(CHEAP, _API_IDS) == "claude-haiku-4-5-20251001"
    assert resolve_model(CHEAP, _CLI_ALIASES) == "haiku"
    assert resolve_model("some-custom-id", _CLI_ALIASES) == "some-custom-id"


def test_scripted_router_and_queue():
    c = ScriptedClient(router=lambda s, p: "ECHO:" + p)
    assert c.generate(system="x", prompt="hi", model="m").text == "ECHO:hi"
    assert c.calls[0]["prompt"] == "hi"

    q = ScriptedClient(responses=["a", "b"])
    assert q.generate(system="", prompt="", model="m").text == "a"
    assert q.generate(system="", prompt="", model="m").text == "b"
    assert q.generate(system="", prompt="", model="m").text == ""  # exhausted


def test_cli_client_args_stdin_and_billing_safety(monkeypatch):
    captured = {}

    def fake_run(args, **kw):
        captured["args"] = args
        captured["input"] = kw.get("input")
        captured["env"] = kw.get("env")
        return FakeProc(json.dumps(
            {"result": "the answer", "total_cost_usd": 0.012,
             "usage": {"input_tokens": 10, "output_tokens": 5}}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-stripped")

    resp = ClaudeCLIClient().generate(system="SYS", prompt="USERPROMPT", model=CHEAP)
    assert resp.text == "the answer"
    assert (resp.input_tokens, resp.output_tokens) == (10, 5)
    assert resp.cost_usd == 0.012

    a = captured["args"]
    assert a[:2] == ["claude", "-p"]
    assert a[a.index("--model") + 1] == "haiku"
    assert a[a.index("--system-prompt") + 1] == "SYS"
    assert a[a.index("--output-format") + 1] == "json"
    assert "--bare" not in a                       # would break subscription OAuth
    assert captured["input"] == "USERPROMPT"        # large prompt via stdin, not argv
    assert "ANTHROPIC_API_KEY" not in captured["env"]  # billing-safety: forced to subscription


def test_cli_client_raises_after_retries_exhausted(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: FakeProc("", returncode=1, stderr="boom"))
    c = ClaudeCLIClient(retries=0)  # no retries -> raise immediately
    with pytest.raises(RuntimeError, match="claude -p"):
        c.generate(system="", prompt="x", model=CHEAP)


def test_cli_client_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky_run(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeProc("", returncode=1, stderr="transient")   # first attempt fails
        return FakeProc(json.dumps({"result": "ok"}))               # retry succeeds

    monkeypatch.setattr(subprocess, "run", flaky_run)
    c = ClaudeCLIClient(retries=2)
    monkeypatch.setattr(c, "_sleep", lambda s: None)                 # no real backoff delay
    resp = c.generate(system="", prompt="x", model=CHEAP)
    assert resp.text == "ok"
    assert calls["n"] == 2
