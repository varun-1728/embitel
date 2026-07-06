"""Configuration loading: merges config.yaml with environment (.env) secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Project root = parent of this package directory.
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DB_PATH = ROOT / "data" / "knowledge.db"

# Load .env once at import time so os.getenv works everywhere.
load_dotenv(ROOT / ".env")


@dataclass
class Competitor:
    name: str
    aliases: list[str] = field(default_factory=list)

    def matches(self, text: str) -> bool:
        """True if this competitor is mentioned in `text` (case-insensitive)."""
        lowered = text.lower()
        names = [self.name] + self.aliases
        return any(n.lower() in lowered for n in names)


@dataclass
class Config:
    raw: dict[str, Any]

    # --- company ---
    @property
    def company_name(self) -> str:
        return self.raw["company"]["name"]

    @property
    def company_description(self) -> str:
        return " ".join(self.raw["company"]["description"].split())

    # --- competitors ---
    @property
    def competitors(self) -> list[Competitor]:
        return [
            Competitor(name=c["name"], aliases=c.get("aliases") or [])
            for c in self.raw["competitors"]
        ]

    def find_competitors_in(self, text: str) -> list[Competitor]:
        return [c for c in self.competitors if c.matches(text)]

    # --- categories ---
    @property
    def categories(self) -> list[dict[str, str]]:
        return self.raw["categories"]

    def category_label(self, key: str) -> str:
        for c in self.categories:
            if c["key"] == key:
                return c["label"]
        return key.title()

    @property
    def category_keys(self) -> list[str]:
        return [c["key"] for c in self.categories]

    # --- research ---
    @property
    def lookback_days(self) -> int:
        return int(self.raw["research"]["lookback_days"])

    @property
    def max_findings_per_competitor(self) -> int:
        return int(self.raw["research"]["max_findings_per_competitor"])

    # --- report ---
    @property
    def report_recipients(self) -> list[str]:
        return list(self.raw["report"]["recipients"])

    @property
    def report_subject_prefix(self) -> str:
        return self.raw["report"]["subject_prefix"]

    @property
    def report_window_days(self) -> int:
        return int(self.raw["report"]["window_days"])

    # --- LLM ---
    @property
    def provider(self) -> str:
        return os.getenv("LLM_PROVIDER", "gemini").strip().lower()

    def model_for(self, provider: str) -> str:
        return self.raw.get("models", {}).get(provider, "")

    # --- secrets (from env) ---
    @staticmethod
    def env(key: str, default: str | None = None) -> str | None:
        return os.getenv(key, default)


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found at {path}. Copy config.yaml from the repo."
        )
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(raw=raw)
