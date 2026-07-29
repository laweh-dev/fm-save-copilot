"""API key and model config resolution.

Resolution order (first hit wins):
  1. --config path if given
  2. ./config.yaml
  3. ANTHROPIC_API_KEY env var
  4. .env file

If none found, the caller runs in free mode (no LLM narrative).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from dotenv import dotenv_values

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 12000


@dataclass
class Config:
    api_key: Optional[str]
    model: str
    max_tokens: int

    @property
    def free_mode(self) -> bool:
        return not self.api_key


def _load_yaml(path: Path) -> Optional[Config]:
    if not path.exists():
        return None
    with path.open("r") as f:
        data = yaml.safe_load(f) or {}
    anthropic_cfg = data.get("anthropic") or {}
    api_key = anthropic_cfg.get("api_key")
    if not api_key:
        return None
    return Config(
        api_key=api_key,
        model=anthropic_cfg.get("model", DEFAULT_MODEL),
        max_tokens=anthropic_cfg.get("max_tokens", DEFAULT_MAX_TOKENS),
    )


def load_config(config_path: Optional[str] = None) -> Config:
    """Resolve the API key using the documented precedence order."""

    if config_path:
        cfg = _load_yaml(Path(config_path))
        if cfg:
            return cfg

    cfg = _load_yaml(Path("config.yaml"))
    if cfg:
        return cfg

    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return Config(api_key=env_key, model=DEFAULT_MODEL, max_tokens=DEFAULT_MAX_TOKENS)

    dotenv_path = Path(".env")
    if dotenv_path.exists():
        values = dotenv_values(dotenv_path)
        dotenv_key = values.get("ANTHROPIC_API_KEY")
        if dotenv_key:
            return Config(api_key=dotenv_key, model=DEFAULT_MODEL, max_tokens=DEFAULT_MAX_TOKENS)

    return Config(api_key=None, model=DEFAULT_MODEL, max_tokens=DEFAULT_MAX_TOKENS)
