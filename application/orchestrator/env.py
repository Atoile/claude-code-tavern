"""Environment + overwrite config loader.

Reads .env.local (or .env.example fallback) and CLAUDE.overwrite.md once at
orchestrator startup and exposes a typed TavernConfig dataclass. The orchestrator
is one process per "run queue" invocation, so this is genuinely fresh every run
without any caching games.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@dataclass
class TavernConfig:
    mode: str = "dev"
    planner: str = "sonnet"
    turns: str = "sequential"
    verbatim: str = "off"
    chat_mode: str = "normal"
    narrator_voice: str = "neutral"
    voice_engine: str = "off"
    voice_engine_url: str = ""

    has_overwrite: bool = False
    overwrite_text: str = ""
    has_phase_3b: bool = False
    has_phase_4b: bool = False
    raw_env: dict[str, str] = field(default_factory=dict[str, str])

    @property
    def planner_model(self) -> str:
        return MODEL_MAP[self.planner]


MODEL_MAP = {
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}

_ENV_LINE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        m = _ENV_LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        out[key] = val
    return out


def load_config() -> TavernConfig:
    env_path = REPO / ".env.local"
    if not env_path.exists():
        env_path = REPO / ".env.example"
    raw: dict[str, str] = {}
    if env_path.exists():
        raw = _parse_env(env_path.read_text(encoding="utf-8"))

    overwrite_path = REPO / "CLAUDE.overwrite.md"
    has_overwrite = overwrite_path.exists()
    overwrite_text = overwrite_path.read_text(encoding="utf-8") if has_overwrite else ""

    cfg = TavernConfig(
        mode=raw.get("TAVERN_MODE", "dev"),
        planner=raw.get("TAVERN_PLANNER", "sonnet"),
        turns=raw.get("TAVERN_TURNS", "sequential"),
        verbatim=raw.get("TAVERN_VERBATIM", "off"),
        chat_mode=raw.get("TAVERN_CHAT_MODE", "normal"),
        narrator_voice=raw.get("TAVERN_NARRATOR_VOICE", "neutral"),
        voice_engine=raw.get("VITE_VOICE_ENGINE", "off"),
        voice_engine_url=raw.get("VITE_VOICE_ENGINE_URL", ""),
        has_overwrite=has_overwrite,
        overwrite_text=overwrite_text,
        has_phase_3b="Phase 3b" in overwrite_text,
        has_phase_4b="Phase 4b" in overwrite_text,
        raw_env=raw,
    )
    if cfg.planner not in MODEL_MAP:
        raise ValueError(f"TAVERN_PLANNER must be 'sonnet' or 'haiku', got {cfg.planner!r}")
    return cfg
