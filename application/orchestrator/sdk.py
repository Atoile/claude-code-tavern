"""Claude Agent SDK spawn helper.

One async function — spawn_agent — wraps claude_agent_sdk.query() with the
defaults the Tavern orchestrator needs:
- model selection by short name ("sonnet" | "haiku")
- cwd locked to repo root
- bypassPermissions so the agent never blocks on tool prompts
- setting_sources=[] (empty list, NOT None) so claude CLI does not load
  user/project/local settings (.claude/settings.json) NOR project memory
  files (CLAUDE.md, CLAUDE.overwrite.md). NOTE: setting_sources=None makes
  the SDK skip the --setting-sources flag entirely, which leaves the CLI
  on its own default (which DOES auto-load CLAUDE.md and persona hooks).
  Passing an empty list forces the CLI into clean-slate mode — no hooks,
  no project memory, no persona contamination. Agents see only what the
  orchestrator's prompt explicitly puts in their context.
- live progress indicators streamed to stdout so a long-running agent doesn't
  look like it's silently hanging.
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    UserMessage,
)

from .env import MODEL_MAP

REPO = Path(__file__).resolve().parents[2]
DEFAULT_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]


SESSION_LOG_DIR = Path.home() / ".claude" / "projects" / "D--AI-Tavern"


class SpawnResult:
    def __init__(self, text: str, is_error: bool, usage: dict[str, Any] | None,
                 cost_usd: float | None, num_turns: int, duration_ms: int,
                 session_id: str | None):
        self.text = text
        self.is_error = is_error
        self.usage = usage
        self.cost_usd = cost_usd
        self.num_turns = num_turns
        self.duration_ms = duration_ms
        self.session_id = session_id

    @property
    def session_log_path(self) -> str | None:
        if not self.session_id:
            return None
        return str(SESSION_LOG_DIR / f"{self.session_id}.jsonl")

    def __repr__(self) -> str:
        return (f"<SpawnResult session={self.session_id} turns={self.num_turns} "
                f"error={self.is_error} cost=${self.cost_usd}>")


def _short(text: str, n: int = 110) -> str:
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    return text[: n - 1] + "..."


def _format_tool(name: str, ti: dict[str, Any]) -> str:
    if name == "Read":
        return f"Read {_basename(ti.get('file_path', '?'))}"
    if name == "Write":
        return f"Write {_basename(ti.get('file_path', '?'))}"
    if name == "Edit":
        return f"Edit {_basename(ti.get('file_path', '?'))}"
    if name == "Bash":
        cmd = ti.get("command", "")
        return f"Bash: {_short(cmd, 90)}"
    if name == "Glob":
        return f"Glob {ti.get('pattern', '?')}"
    if name == "Grep":
        return f"Grep {_short(ti.get('pattern', '?'), 60)}"
    return f"{name}: {_short(str(ti), 80)}"


def _basename(p: str) -> str:
    p = p.replace("\\", "/")
    return p.rsplit("/", 1)[-1] if "/" in p else p


def _emit(label: str, line: str, quiet: bool) -> None:
    if quiet:
        return
    print(f"  [{label}] {line}", flush=True)


async def spawn_agent(
    prompt: str,
    model: str = "sonnet",
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
    label: str = "agent",
    quiet: bool = False,
    thinking_budget: int | str | None = None,
    dialogue_id: str | None = None,
) -> SpawnResult:
    """One-shot stateless subagent. Streams progress; returns final text + metadata.

    thinking_budget:
      None         — leave the model's default (some models think anyway).
      "off" or 0   — EXPLICITLY disabled — guarantees zero thinking blocks.
      int (>0)     — extended thinking with a fixed token budget cap. Predictable
                     ceiling on per-spawn reasoning spend.
      "adaptive"   — adaptive thinking. Model self-sizes how much it needs per
                     turn; pays only for what's used. Best for variable-difficulty
                     spawns (planner, handler) where easy rounds use little and
                     hard rounds get the headroom they need.

    Thinking is most cost-effective on Sonnet (heavy reasoners). Haiku has
    smaller thinking budgets and benefits less per-token, but still works.
    """
    if model not in MODEL_MAP:
        raise ValueError(f"model must be 'sonnet' or 'haiku', got {model!r}")

    thinking_cfg = None
    if thinking_budget == "off" or thinking_budget == 0:
        thinking_cfg = {"type": "disabled"}
    elif thinking_budget == "adaptive":
        thinking_cfg = {"type": "adaptive"}
    elif isinstance(thinking_budget, int) and thinking_budget > 0:
        thinking_cfg = {"type": "enabled", "budget_tokens": thinking_budget}

    options = ClaudeAgentOptions(
        model=MODEL_MAP[model],
        cwd=str(REPO),
        allowed_tools=allowed_tools if allowed_tools is not None else DEFAULT_TOOLS,
        permission_mode="bypassPermissions",
        setting_sources=[],  # empty list, not None — see module docstring
        max_turns=max_turns,
        thinking=thinking_cfg,
        # --no-session-persistence: tells claude CLI not to persist this spawn's
        # session to ~/.claude/projects/D--AI-Tavern/<session-id>.jsonl. Each
        # queue run spawns 4-10 agents; persisting them all clutters the user's
        # local session picker (/resume) with hundreds of orchestrator entries.
        # The orchestrator's own thinking_log.jsonl + per-task queue.json error
        # field cover post-mortem needs without the noise. Only works in --print
        # mode, which the SDK uses by default. To re-enable for debugging a
        # specific spawn, drop this flag from extra_args.
        extra_args={"no-session-persistence": None},
    )

    if not quiet:
        if thinking_cfg:
            thinking_str = f" thinking={thinking_budget}"
        else:
            thinking_str = ""
        print(f"  [{label}] >> spawning ({model}) tools={allowed_tools or DEFAULT_TOOLS}{thinking_str}",
              flush=True)
    t0 = time.monotonic()
    last_progress = t0

    text = ""
    is_error = False
    usage: dict[str, Any] | None = None
    cost: float | None = None
    turns = 0
    duration_ms = 0
    tool_count = 0
    thinking_blocks = 0
    thinking_chars = 0
    captured_thinking: list[dict[str, str]] = []
    captured_text: list[dict[str, str]] = []
    text_chars = 0
    captured_tools: list[dict[str, Any]] = []
    tool_input_chars = 0
    read_paths_seen: list[str] = []
    session_id: str | None = None

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            if session_id is None and getattr(msg, "session_id", None):
                session_id = msg.session_id
                _emit(label, f"session={session_id}", quiet)
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    tool_count += 1
                    # Tool call arg payloads count as output tokens — especially
                    # Write/Edit calls with multi-KB content. Capture the input
                    # size + summary so the user can see where output spend went
                    # beyond text/thinking blocks. Detect duplicate Reads (same
                    # path read multiple times in one spawn = forgetfulness =
                    # waste).
                    input_serialized = json.dumps(block.input, ensure_ascii=False)
                    input_size = len(input_serialized)
                    tool_input_chars += input_size
                    summary = _format_tool(block.name, block.input)
                    record = {
                        "name": block.name,
                        "summary": summary,
                        "input_size_chars": input_size,
                    }
                    if block.name == "Read":
                        path = block.input.get("file_path", "")
                        if path in read_paths_seen:
                            record["duplicate_read"] = True
                        else:
                            read_paths_seen.append(path)
                    elif block.name == "Write":
                        # Surface the content size separately — this is usually
                        # 90%+ of a Write's tool-call cost.
                        content = block.input.get("content", "")
                        record["content_size_chars"] = len(content)
                    captured_tools.append(record)
                    _emit(label, f"* {summary}", quiet)
                    last_progress = time.monotonic()
                elif isinstance(block, ThinkingBlock):
                    thinking_blocks += 1
                    thinking_chars += len(block.thinking)
                    # Drop signature (Anthropic's authenticity proof, ~200 chars
                    # of base64) — pure clutter for human-readable debugging
                    # logs and useless without the SDK to verify it.
                    captured_thinking.append({"thinking": block.thinking})
                    _emit(label, f"~ thinking ({len(block.thinking)} chars)", quiet)
                    last_progress = time.monotonic()
                elif isinstance(block, TextBlock):
                    txt = block.text.strip()
                    if txt:
                        # Capture the FULL text block for the spawn log so the
                        # user can see every commentary token the agent spent
                        # outside of tool calls (narration, summaries, etc.).
                        # The output discipline directive is supposed to keep
                        # this minimal; the log shows where it fails.
                        captured_text.append({"text": block.text})
                        text_chars += len(block.text)
                        _emit(label, f"> {_short(txt, 130)}", quiet)
                        last_progress = time.monotonic()
        elif isinstance(msg, SystemMessage):
            # SystemMessage subtypes: init, etc. Mostly noise — emit only errors.
            if msg.subtype == "error":
                _emit(label, f"! system: {_short(str(msg.data), 120)}", quiet)
        elif isinstance(msg, UserMessage):
            # User messages within an agent session = tool results being fed back.
            # Don't echo them — they're loud and we already printed the tool call.
            pass
        elif isinstance(msg, ResultMessage):
            text = msg.result or ""
            is_error = bool(msg.is_error)
            usage = msg.usage
            cost = msg.total_cost_usd
            turns = msg.num_turns
            duration_ms = msg.duration_ms
            if not session_id and getattr(msg, "session_id", None):
                session_id = msg.session_id

    elapsed = time.monotonic() - t0
    if not quiet:
        cost_str = f"${cost:.4f}" if cost is not None else "-"
        usage_str = ""
        if usage:
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            usage_str = f" tok_in={in_tok} tok_out={out_tok}"
        thinking_str = ""
        if thinking_blocks:
            thinking_str = f" think_blocks={thinking_blocks} think_chars={thinking_chars}"
        status = "[FAIL]" if is_error else "[OK]"
        sid_str = f" session={session_id}" if session_id else ""
        print(
            f"  [{label}] {status} — {elapsed:.1f}s, {turns} turn(s), "
            f"{tool_count} tool call(s), cost={cost_str}{usage_str}{thinking_str}{sid_str}",
            flush=True,
        )
        # Session log path on error — but with --no-session-persistence the
        # log isn't actually written. Print it conditionally so the message
        # only appears when there's something to read.
        if is_error and session_id:
            log_path = SESSION_LOG_DIR / f"{session_id}.jsonl"
            if log_path.exists():
                print(f"  [{label}] log: {log_path}", flush=True)

    # Persist captured thinking + text blocks to a per-dialogue JSONL log so
    # the user can retrospect what each agent reasoned about AND every output
    # token it spent on commentary outside tool calls. One JSONL line per
    # spawn, append-only across rounds. Manual cleanup if the file grows.
    if dialogue_id and (captured_thinking or captured_text or captured_tools):
        log_path = REPO / "infrastructure" / "dialogues" / dialogue_id / "thinking_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Token-spend totals from the SDK's billing dict, surfaced at the top
        # for grep/jq-friendly reporting. tok_in / tok_out are the authoritative
        # billed counts; the per-section *_chars fields are estimates of
        # where the spend went (×~4 chars/token).
        in_tok = (usage or {}).get("input_tokens", 0)
        out_tok = (usage or {}).get("output_tokens", 0)
        cache_read = (usage or {}).get("cache_read_input_tokens", 0)
        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "label": label,
            "model": model,
            "session_id": session_id,
            "duration_ms": duration_ms,
            "is_error": is_error,
            "tok_in": in_tok,
            "tok_out": out_tok,
            "cache_read_tok_in": cache_read,
            "cost_usd": cost,
            # Output-spend breakdown (chars; rough indicator of where tok_out went)
            "thinking_block_count": thinking_blocks,
            "thinking_total_chars": thinking_chars,
            "text_block_count": len(captured_text),
            "text_total_chars": text_chars,
            "tool_call_count": tool_count,
            "tool_input_total_chars": tool_input_chars,
            # Detail arrays
            "thinking_blocks": captured_thinking,
            "text_blocks": captured_text,
            "tool_calls": captured_tools,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return SpawnResult(
        text=text, is_error=is_error, usage=usage,
        cost_usd=cost, num_turns=turns, duration_ms=duration_ms,
        session_id=session_id,
    )
