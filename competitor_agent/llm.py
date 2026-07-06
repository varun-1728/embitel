"""Provider-agnostic LLM adapter.

Default backend is Google Gemini (free tier) with Google Search grounding, which
gives us live web search for free. Swap to Claude or Groq by setting
LLM_PROVIDER in .env — no other code changes needed.

Every backend implements .generate(prompt, system, use_web_search) and returns
an LLMResponse with .text and .sources.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .config import Config


@dataclass
class Source:
    title: str
    url: str


@dataclass
class LLMResponse:
    text: str
    sources: list[Source] = field(default_factory=list)


class LLMError(RuntimeError):
    pass


class RateLimitError(LLMError):
    """Raised when the provider quota / rate limit is exhausted (HTTP 429)."""


# Cap on how long we'll block waiting out a rate limit before giving up. Short
# per-minute throttles (~60s) are worth waiting; a daily-quota reset is not.
_MAX_RETRY_WAIT = 65


def _parse_retry_delay(err) -> float | None:
    """Pull the server-suggested retry delay (seconds) from a 429 error, if any."""
    m = re.search(r"ret[rR]y[dD]elay['\"]?\s*[:=]\s*['\"]?(\d+)", str(err))
    return float(m.group(1)) if m else None


class BaseLLM:
    supports_web_search: bool = False

    def generate(
        self, prompt: str, system: str | None = None, use_web_search: bool = False
    ) -> LLMResponse:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Gemini (default)
# --------------------------------------------------------------------------- #
class GeminiLLM(BaseLLM):
    supports_web_search = True

    def __init__(self, cfg: Config):
        api_key = cfg.env("GEMINI_API_KEY")
        if not api_key or api_key == "your-gemini-key-here":
            raise LLMError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and put it in .env"
            )
        try:
            from google import genai  # type: ignore
        except ImportError as e:
            raise LLMError(
                "google-genai is not installed. Run: pip install -r requirements.txt"
            ) from e

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = cfg.model_for("gemini") or "gemini-2.5-flash"

    def generate(
        self, prompt: str, system: str | None = None, use_web_search: bool = False
    ) -> LLMResponse:
        from google.genai import types  # type: ignore

        tools = None
        if use_web_search:
            tools = [types.Tool(google_search=types.GoogleSearch())]

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tools,
        )
        attempts = 0
        while True:
            try:
                resp = self._client.models.generate_content(
                    model=self._model, contents=prompt, config=config
                )
                break
            except Exception as e:  # noqa: BLE001 - surface provider errors cleanly
                is_429 = getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)
                if is_429:
                    delay = _parse_retry_delay(e)
                    # Retry once for a short throttle; otherwise report as rate limit.
                    if delay is not None and delay <= _MAX_RETRY_WAIT and attempts < 1:
                        attempts += 1
                        time.sleep(delay + 1)
                        continue
                    raise RateLimitError(
                        "Gemini quota/rate limit hit (HTTP 429). Free tier allows "
                        "~20 requests/day for gemini-2.5-flash. Wait for the daily "
                        "reset or reduce usage."
                    ) from e
                raise LLMError(f"Gemini request failed: {e}") from e

        return LLMResponse(text=resp.text or "", sources=self._extract_sources(resp))

    @staticmethod
    def _extract_sources(resp) -> list[Source]:
        sources: list[Source] = []
        try:
            for cand in resp.candidates or []:
                meta = getattr(cand, "grounding_metadata", None)
                if not meta:
                    continue
                for chunk in getattr(meta, "grounding_chunks", None) or []:
                    web = getattr(chunk, "web", None)
                    if web and getattr(web, "uri", None):
                        sources.append(
                            Source(title=getattr(web, "title", "") or web.uri, url=web.uri)
                        )
        except Exception:  # noqa: BLE001 - grounding metadata is best-effort
            pass
        # De-dup by url, keep order.
        seen, out = set(), []
        for s in sources:
            if s.url not in seen:
                seen.add(s.url)
                out.append(s)
        return out


# --------------------------------------------------------------------------- #
# Claude (swappable)
# --------------------------------------------------------------------------- #
class ClaudeLLM(BaseLLM):
    supports_web_search = True

    def __init__(self, cfg: Config):
        api_key = cfg.env("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set (needed for LLM_PROVIDER=claude).")
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise LLMError("anthropic not installed. Run: pip install anthropic") from e

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = cfg.model_for("claude") or "claude-sonnet-5"

    def generate(
        self, prompt: str, system: str | None = None, use_web_search: bool = False
    ) -> LLMResponse:
        tools = []
        if use_web_search:
            tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system or "",
                tools=tools,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"Claude request failed: {e}") from e

        text_parts, sources = [], []
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            # web_search results surface as tool result blocks with citations;
            # citations (if present) are attached to text blocks.
            for cit in getattr(block, "citations", None) or []:
                url = getattr(cit, "url", None)
                if url:
                    sources.append(Source(title=getattr(cit, "title", "") or url, url=url))
        return LLMResponse(text="".join(text_parts), sources=sources)


# --------------------------------------------------------------------------- #
# Groq (swappable, no web search)
# --------------------------------------------------------------------------- #
class GroqLLM(BaseLLM):
    supports_web_search = False

    def __init__(self, cfg: Config):
        api_key = cfg.env("GROQ_API_KEY")
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set (needed for LLM_PROVIDER=groq).")
        try:
            from groq import Groq  # type: ignore
        except ImportError as e:
            raise LLMError("groq not installed. Run: pip install groq") from e

        self._client = Groq(api_key=api_key)
        self._model = cfg.model_for("groq") or "llama-3.3-70b-versatile"

    def generate(
        self, prompt: str, system: str | None = None, use_web_search: bool = False
    ) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = self._client.chat.completions.create(
                model=self._model, messages=messages
            )
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"Groq request failed: {e}") from e
        return LLMResponse(text=resp.choices[0].message.content or "")


_PROVIDERS = {"gemini": GeminiLLM, "claude": ClaudeLLM, "groq": GroqLLM}


def build_llm(cfg: Config) -> BaseLLM:
    provider = cfg.provider
    cls = _PROVIDERS.get(provider)
    if not cls:
        raise LLMError(
            f"Unknown LLM_PROVIDER '{provider}'. Choose one of: {', '.join(_PROVIDERS)}"
        )
    return cls(cfg)
