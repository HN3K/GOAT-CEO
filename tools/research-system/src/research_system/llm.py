"""LLM client abstraction shared by Answer (P2), Verify (P3), Synthesize (P5).

The pipeline talks to an injectable ``LLMClient`` so every stage is testable
offline with ``ScriptedClient`` and the backend is swappable. Two live backends:

- ``ClaudeCLIClient`` — billed to the user's **Claude Code subscription** via the
  ``claude -p`` CLI (OAuth auth). This is the default for live runs. We strip
  ``ANTHROPIC_API_KEY``/``ANTHROPIC_AUTH_TOKEN`` from the subprocess env because
  their presence silently switches billing to the pay-per-token API. NB: the CLI
  ``--bare`` flag must NOT be used — it forces API-key auth and ignores OAuth.
- ``AnthropicClient`` — pay-per-token Anthropic API (needs ANTHROPIC_API_KEY).

Stages pass a TIER token (DESIGN §6: cheap for open-book extraction, strong for
reasoning); each client resolves the tier to a concrete model. Verification uses
a different tier/model than generation (P6 finding on judge self-preference bias).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

# DESIGN §6 model TIERS — semantic tokens resolved to concrete models per client.
STRONG = "strong"
MID = "mid"
CHEAP = "cheap"

# tier -> Anthropic API model id (env's model list)
_API_IDS = {
    STRONG: "claude-opus-4-8",
    MID: "claude-sonnet-4-6",
    CHEAP: "claude-haiku-4-5-20251001",
}
# tier -> claude CLI alias (latest model in that tier)
_CLI_ALIASES = {STRONG: "opus", MID: "sonnet", CHEAP: "haiku"}


def resolve_model(tier_or_model: str, mapping: dict[str, str]) -> str:
    """Resolve a tier token to a concrete model; pass through unknown values."""
    return mapping.get(tier_or_model, tier_or_model)


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None      # populated by ClaudeCLIClient (subscription cost report)


class LLMClient(Protocol):
    def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


class AnthropicClient:
    """Live client over the Anthropic SDK. Requires ANTHROPIC_API_KEY (or api_key)."""

    def __init__(self, api_key: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def generate(self, *, system, prompt, model, max_tokens=2048, temperature=0.0) -> LLMResponse:
        resolved = resolve_model(model, _API_IDS)
        msg = self._client.messages.create(
            model=resolved,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )
        return LLMResponse(
            text=text,
            model=resolved,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
        )


class ClaudeCLIClient:
    """Subscription-billed client via the ``claude -p`` headless CLI (OAuth auth).

    The user prompt is piped via stdin (no argv length limit — answer prompts can
    embed whole documents). The system prompt and model are passed as flags.
    ``temperature``/``max_tokens`` are accepted for interface parity but the CLI
    does not expose them, so they are ignored (model defaults apply).
    """

    def __init__(
        self,
        claude_bin: str = "claude",
        *,
        timeout: float = 180.0,
        force_subscription: bool = True,
        extra_args: list[str] | None = None,
        retries: int = 2,
        backoff: float = 2.0,
    ) -> None:
        self.claude_bin = claude_bin
        self.timeout = timeout
        self.force_subscription = force_subscription
        self.extra_args = extra_args or []
        self.retries = retries
        self.backoff = backoff

    def _sleep(self, seconds: float) -> None:  # seam for tests
        import time

        time.sleep(seconds)

    def _build_args(self, *, system: str, model: str) -> list[str]:
        alias = resolve_model(model, _CLI_ALIASES)
        args = [self.claude_bin, "-p", "--model", alias, "--output-format", "json"]
        if system:
            args += ["--system-prompt", system]
        return args + self.extra_args

    def _build_env(self) -> dict[str, str]:
        import os

        env = dict(os.environ)
        if self.force_subscription:
            # Their presence flips billing from subscription OAuth to the paid API.
            env.pop("ANTHROPIC_API_KEY", None)
            env.pop("ANTHROPIC_AUTH_TOKEN", None)
        return env

    def generate(self, *, system, prompt, model, max_tokens=2048, temperature=0.0) -> LLMResponse:
        """Run `claude -p` with retries on transient failures (exit!=0, timeout,
        unparseable output) — a single hiccup shouldn't abort a long batch run."""
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._generate_once(system=system, prompt=prompt, model=model)
            except Exception as exc:  # noqa: BLE001 - retry any transient CLI failure
                last_err = exc
                if attempt < self.retries:
                    self._sleep(self.backoff * (attempt + 1))
        raise RuntimeError(f"`claude -p` failed after {self.retries + 1} attempts: {last_err}")

    def _generate_once(self, *, system, prompt, model) -> LLMResponse:
        import json
        import subprocess

        args = self._build_args(system=system, model=model)
        proc = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.timeout,
            env=self._build_env(),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"`claude -p` failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}"
            )
        data = json.loads(proc.stdout)
        usage = data.get("usage") or {}
        return LLMResponse(
            text=data.get("result", ""),
            model=resolve_model(model, _CLI_ALIASES),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cost_usd=data.get("total_cost_usd"),
        )


@dataclass
class CostTracker:
    """Wraps any ``LLMClient`` and accumulates cost/token/call totals.

    Used by the tier sweep (P7) to quantify "X% cheaper at equal faithfulness".
    Costs are populated by ``ClaudeCLIClient`` (subscription cost report); with a
    fake client they stay zero.
    """

    inner: LLMClient
    total_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    n_calls: int = 0

    def generate(self, **kwargs) -> LLMResponse:
        resp = self.inner.generate(**kwargs)
        self.n_calls += 1
        if resp.cost_usd:
            self.total_cost_usd += resp.cost_usd
        if resp.input_tokens:
            self.input_tokens += resp.input_tokens
        if resp.output_tokens:
            self.output_tokens += resp.output_tokens
        return resp


@dataclass
class ScriptedClient:
    """Deterministic fake LLM.

    Provide either a queue of ``responses`` (returned FIFO) or a ``router``
    callable ``(system, prompt) -> str``. Records every call in ``calls``.
    """

    responses: list[str] = field(default_factory=list)
    router: Callable[[str, str], str] | None = None
    calls: list[dict] = field(default_factory=list)

    def generate(self, *, system, prompt, model, max_tokens=2048, temperature=0.0) -> LLMResponse:
        self.calls.append({"system": system, "prompt": prompt, "model": model})
        if self.router is not None:
            return LLMResponse(text=self.router(system, prompt), model=model)
        if self.responses:
            return LLMResponse(text=self.responses.pop(0), model=model)
        return LLMResponse(text="", model=model)
