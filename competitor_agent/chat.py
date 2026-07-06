"""Interactive CLI chat about competitors.

Each answer is grounded in three things:
  1. The persistent knowledge base (accumulated findings).
  2. Live web search (if the backend supports it) for anything fresh.
  3. The current conversation history (so follow-ups have context).

No per-user personalization — the knowledge base is shared. Conversation memory
lives for the duration of the chat session.
"""

from __future__ import annotations

from .config import Config
from .llm import BaseLLM
from .store import Finding, KnowledgeStore

MAX_HISTORY_TURNS = 8  # how many prior turns to keep in context


def _kb_context(cfg: Config, store: KnowledgeStore, question: str) -> list[Finding]:
    """Pull relevant findings from the KB for this question."""
    found: dict[str, Finding] = {}

    # 1. Any competitor named in the question -> its recent findings.
    for comp in cfg.find_competitors_in(question):
        for f in store.findings_for(comp.name, limit=15):
            found[f.id] = f

    # 2. Keyword search on the raw question.
    for f in store.search(question, limit=15):
        found[f.id] = f

    # 3. If nothing matched, fall back to the most recent findings overall.
    if not found:
        for f in store.all_findings(limit=20):
            found[f.id] = f

    return list(found.values())[:30]


def _render_findings(cfg: Config, findings: list[Finding]) -> str:
    if not findings:
        return "(no relevant findings in the knowledge base yet)"
    lines = []
    for f in findings:
        date_str = f" ({f.event_date})" if f.event_date else ""
        src = f" [{f.source_url}]" if f.source_url else ""
        lines.append(
            f"- [{f.competitor} / {cfg.category_label(f.category)}]{date_str} "
            f"{f.title}: {f.summary}{src}"
        )
    return "\n".join(lines)


SYSTEM = (
    "You are a competitive-intelligence assistant for {company}. "
    "{company} is: {desc}\n"
    "Answer questions about its competitors clearly and factually. Prefer the "
    "provided knowledge-base findings; use web search only to fill gaps or get "
    "fresher information. Cite sources (URLs) when you rely on them. If you are "
    "unsure or lack data, say so plainly rather than guessing."
)


class ChatSession:
    def __init__(self, cfg: Config, llm: BaseLLM, store: KnowledgeStore):
        self.cfg = cfg
        self.llm = llm
        self.store = store
        self.history: list[tuple[str, str]] = []  # (role, text)
        self.system = SYSTEM.format(company=cfg.company_name, desc=cfg.company_description)

    def ask(self, question: str) -> str:
        findings = _kb_context(self.cfg, self.store, question)
        kb = _render_findings(self.cfg, findings)

        history_txt = ""
        if self.history:
            turns = self.history[-MAX_HISTORY_TURNS * 2 :]
            history_txt = "\n".join(f"{role.upper()}: {text}" for role, text in turns)

        prompt = f"""KNOWLEDGE BASE (accumulated competitor findings):
{kb}

{"CONVERSATION SO FAR:" if history_txt else ""}
{history_txt}

USER QUESTION: {question}

Answer the question. Use the knowledge base first; use web search only to fill
gaps or refresh stale info. Be concise and cite source URLs you rely on."""

        resp = self.llm.generate(
            prompt, system=self.system, use_web_search=self.llm.supports_web_search
        )
        answer = resp.text.strip()
        if resp.sources:
            cited = "\n".join(f"  - {s.title}: {s.url}" for s in resp.sources[:5])
            answer += f"\n\nSources:\n{cited}"

        self.history.append(("user", question))
        self.history.append(("assistant", answer))
        return answer
