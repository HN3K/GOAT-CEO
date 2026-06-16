"""LLM client — subscription-billed via the Claude Code CLI (`claude -p`).

Injectable ``LLMClient`` protocol so review is testable offline (``ScriptedClient``).
``ClaudeCLIClient`` bills to the Claude Code subscription: it strips
``ANTHROPIC_API_KEY``/``ANTHROPIC_AUTH_TOKEN`` from the subprocess env (their presence
silently switches to paid-API billing) and never uses ``--bare`` (which forces
API-key auth). Pattern proven in the Research System.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

STRONG, MID, CHEAP = "strong", "mid", "cheap"
_CLI_ALIASES = {STRONG: "opus", MID: "sonnet", CHEAP: "haiku"}


@dataclass
class LLMResponse:
    text: str
    model: str
    cost_usd: float | None = None


class LLMClient(Protocol):
    def generate(self, *, system: str, prompt: str, model: str) -> LLMResponse: ...


@dataclass
class ScriptedClient:
    """Deterministic fake. Queue of responses, or a (system, prompt)->str router."""

    responses: list[str] = field(default_factory=list)
    router: Callable[[str, str], str] | None = None
    calls: list[dict] = field(default_factory=list)

    def generate(self, *, system: str, prompt: str, model: str = MID) -> LLMResponse:
        self.calls.append({"system": system, "prompt": prompt, "model": model})
        if self.router is not None:
            return LLMResponse(self.router(system, prompt), model)
        if self.responses:
            return LLMResponse(self.responses.pop(0), model)
        return LLMResponse("", model)


class ClaudeCLIClient:
    """Subscription-billed via `claude -p`. Prompt piped on stdin; retries transient failures."""

    def __init__(self, claude_bin: str = "claude", *, timeout: float = 180.0,
                 retries: int = 2, backoff: float = 2.0) -> None:
        self.claude_bin = claude_bin
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def _sleep(self, seconds: float) -> None:  # seam for tests
        import time

        time.sleep(seconds)

    def generate(self, *, system: str, prompt: str, model: str = MID) -> LLMResponse:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._once(system=system, prompt=prompt, model=model)
            except Exception as exc:  # noqa: BLE001 - retry any transient CLI failure
                last = exc
                if attempt < self.retries:
                    self._sleep(self.backoff * (attempt + 1))
        raise RuntimeError(f"`claude -p` failed after {self.retries + 1} attempts: {last}")

    def _once(self, *, system: str, prompt: str, model: str) -> LLMResponse:
        import json
        import os
        import subprocess

        alias = _CLI_ALIASES.get(model, model)
        args = [self.claude_bin, "-p", "--model", alias, "--output-format", "json"]
        if system:
            args += ["--system-prompt", system]
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)        # force subscription billing
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        proc = subprocess.run(args, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", timeout=self.timeout, env=env)
        if proc.returncode != 0:
            raise RuntimeError(f"exit {proc.returncode}: {proc.stderr.strip()[:300]}")
        data = json.loads(proc.stdout)
        return LLMResponse(text=data.get("result", ""), model=alias,
                           cost_usd=data.get("total_cost_usd"))
