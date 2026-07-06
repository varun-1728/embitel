"""Gather competitor intelligence via the LLM's live web search and store it.

For each competitor we ask the model to find recent developments across the
configured categories, return them as structured JSON, and we dedup + persist.
"""

from __future__ import annotations

import json
import re

from .config import Competitor, Config
from .llm import BaseLLM
from .store import KnowledgeStore

_JSON_BLOCK = re.compile(r"\[.*\]", re.DOTALL)


def _extract_json_array(text: str) -> list[dict]:
    """Best-effort parse of a JSON array from an LLM response."""
    if not text:
        return []
    # Strip code fences, then try the whole string and the first [...] block.
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    candidates = [cleaned]
    match = _JSON_BLOCK.search(cleaned)
    if match:
        candidates.append(match.group())
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    return []


def _research_prompt(cfg: Config, competitor: Competitor) -> str:
    cats = "\n".join(f'  - "{c["key"]}": {c["label"]}' for c in cfg.categories)
    return f"""You are a competitive-intelligence analyst for {cfg.company_name}.
{cfg.company_name} is: {cfg.company_description}

Use web search to find NOTABLE, RECENT developments (within the last {cfg.lookback_days} days)
about the competitor "{competitor.name}" that are relevant to the automotive
software / product-engineering space.

Track these categories (use the exact key on the left):
{cats}

Return ONLY a JSON array (no prose, no markdown) of up to {cfg.max_findings_per_competitor}
objects. Each object must have exactly these fields:
  "category":   one of the category keys above
  "title":      short headline (max ~15 words)
  "summary":    2-3 sentence factual summary of what happened and why it matters to {cfg.company_name}
  "source_url": the URL you found it at (or "" if unknown)
  "event_date": approximate date as YYYY-MM-DD (or "" if unknown)

Only include real, specific, verifiable developments. If you find nothing notable,
return an empty array []. Do not invent news."""


def research_competitor(
    cfg: Config, llm: BaseLLM, store: KnowledgeStore, competitor: Competitor
) -> dict:
    """Research one competitor, store findings, return a summary dict."""
    system = "You are a precise competitive-intelligence analyst. You never fabricate facts."
    resp = llm.generate(
        _research_prompt(cfg, competitor),
        system=system,
        use_web_search=llm.supports_web_search,
    )
    items = _extract_json_array(resp.text)

    valid_keys = set(cfg.category_keys)
    new_count = 0
    for it in items:
        category = str(it.get("category", "other")).strip().lower()
        if category not in valid_keys:
            category = "other"
        title = str(it.get("title", "")).strip()
        summary = str(it.get("summary", "")).strip()
        if not title or not summary:
            continue
        source_url = str(it.get("source_url", "")).strip()
        # If the model omitted a URL, fall back to the first grounding source.
        if not source_url and resp.sources:
            source_url = resp.sources[0].url
        event_date = str(it.get("event_date", "")).strip()
        if store.add_finding(
            competitor.name, category, title, summary, source_url, event_date
        ):
            new_count += 1

    store.record_run(competitor.name, new_count)
    return {
        "competitor": competitor.name,
        "returned": len(items),
        "new": new_count,
        "web_search": llm.supports_web_search,
    }


def refresh_all(
    cfg: Config, llm: BaseLLM, store: KnowledgeStore, only: str | None = None
):
    """Research every competitor (or one, if `only` is given). Yields per-competitor results."""
    competitors = cfg.competitors
    if only:
        competitors = [c for c in competitors if c.matches(only)]
        if not competitors:
            raise ValueError(f"No configured competitor matches '{only}'.")
    for comp in competitors:
        yield research_competitor(cfg, llm, store, comp)
