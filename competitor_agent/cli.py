"""Command-line interface for the Embitel Competitor Intelligence Agent.

Commands:
  chat                 Interactive Q&A about competitors.
  refresh [--competitor NAME]
                       Gather fresh intel via web search into the knowledge base.
  report [--send] [--save FILE]
                       Build the weekly report; preview, save, or email it.
  weekly               Refresh all competitors, then build + email the report
                       (this is what you put on a cron for Mondays).
  competitors          List configured competitors.
  stats                Show knowledge-base statistics.
"""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .llm import LLMError, build_llm
from .store import KnowledgeStore

try:
    from rich.console import Console
    from rich.markdown import Markdown

    _console = Console()

    def out(msg=""):
        _console.print(msg)

    def rule(title=""):
        _console.rule(title)

    def md(text):
        _console.print(Markdown(text))
except ImportError:  # graceful fallback if rich isn't installed
    def out(msg=""):
        print(msg)

    def rule(title=""):
        print("\n" + "=" * 60 + (f" {title} " if title else ""))

    def md(text):
        print(text)


def _bootstrap(need_llm: bool = True):
    """Load config + store. Build the LLM only when the command needs it."""
    cfg = load_config()
    store = KnowledgeStore()
    llm = None
    if need_llm:
        try:
            llm = build_llm(cfg)
        except LLMError as e:
            out(f"[LLM setup error] {e}")
            sys.exit(1)
    return cfg, store, llm


# --------------------------------------------------------------------------- #
def cmd_chat(args):
    from .chat import ChatSession

    cfg, store, llm = _bootstrap()
    session = ChatSession(cfg, llm, store)
    stats = store.stats()

    rule(f"{cfg.company_name} Competitor Intelligence — Chat")
    out(f"Provider: {cfg.provider} | Knowledge base: {stats['total']} findings")
    if stats["total"] == 0:
        out("Knowledge base is empty. Run `python main.py refresh` to populate it.")
    out("Ask about competitors. Type 'exit' or Ctrl-D to quit.\n")

    while True:
        try:
            question = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            out("\nBye.")
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", ":q"}:
            out("Bye.")
            break
        try:
            answer = session.ask(question)
        except LLMError as e:
            out(f"[error] {e}")
            continue
        out("")
        md(answer)
        out("")


def cmd_refresh(args):
    from .research import refresh_all

    cfg, store, llm = _bootstrap()
    if not llm.supports_web_search:
        out(f"[warn] provider '{cfg.provider}' has no web search; results rely on model knowledge only.")
    target = args.competitor or "all competitors"
    out(f"Refreshing intel for {target} (provider: {cfg.provider})...\n")
    try:
        for res in refresh_all(cfg, llm, store, only=args.competitor):
            out(f"  • {res['competitor']}: {res['new']} new / {res['returned']} returned")
    except (LLMError, ValueError) as e:
        out(f"[error] {e}")
        sys.exit(1)
    out("\nDone.")


def cmd_report(args):
    from .report import build_report

    cfg, store, llm = _bootstrap()
    out("Building weekly report...\n")
    try:
        report = build_report(cfg, llm, store)
    except LLMError as e:
        out(f"[error] {e}")
        sys.exit(1)

    rule(report.subject)
    md(report.executive_summary)
    out(f"\n({report.finding_count} findings in the last {cfg.report_window_days} days)")
    if report.summary_is_fallback:
        out("[note] LLM summary unavailable (rate limit) — used an auto-generated summary.")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(report.html_body)
        out(f"\nSaved HTML preview to {args.save}")

    if args.send:
        from .emailer import EmailError, send_report

        try:
            sent = send_report(
                cfg, report.subject, report.text_body, report.html_body
            )
            out(f"\nEmailed report to: {', '.join(sent)}")
        except EmailError as e:
            out(f"\n[email error] {e}")
            sys.exit(1)
    else:
        out("\n(use --send to email it, --save FILE.html to save a preview)")


def cmd_weekly(args):
    """Full weekly job: refresh everything, then build + send. For cron."""
    from .report import build_report
    from .research import refresh_all

    cfg, store, llm = _bootstrap()
    out("[weekly] Refreshing all competitors...")
    try:
        for res in refresh_all(cfg, llm, store):
            out(f"  • {res['competitor']}: {res['new']} new")
    except LLMError as e:
        out(f"[weekly] refresh error: {e}")
        sys.exit(1)

    out("[weekly] Building report...")
    report = build_report(cfg, llm, store)
    if report.summary_is_fallback:
        out("[weekly] LLM summary unavailable (rate limit) — used auto-generated summary.")

    from .emailer import EmailError, send_report

    try:
        sent = send_report(cfg, report.subject, report.text_body, report.html_body)
        out(f"[weekly] Sent to: {', '.join(sent)}")
    except EmailError as e:
        out(f"[weekly] email error: {e}")
        sys.exit(1)


def cmd_competitors(args):
    cfg, _, _ = _bootstrap(need_llm=False)
    rule("Tracked competitors")
    for c in cfg.competitors:
        alias = f"  (aka {', '.join(c.aliases)})" if c.aliases else ""
        out(f"  • {c.name}{alias}")


def cmd_stats(args):
    cfg, store, _ = _bootstrap(need_llm=False)
    s = store.stats()
    rule("Knowledge base stats")
    out(f"Total findings: {s['total']}\n")
    for comp, n in s["by_competitor"].items():
        last = s["last_runs"].get(comp, "never")
        out(f"  • {comp}: {n} findings (last refresh: {last})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="competitor-agent",
        description="Embitel Competitor Intelligence Agent",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("chat", help="Interactive Q&A about competitors").set_defaults(func=cmd_chat)

    r = sub.add_parser("refresh", help="Gather fresh intel into the knowledge base")
    r.add_argument("--competitor", help="Only refresh this competitor (name or alias)")
    r.set_defaults(func=cmd_refresh)

    rep = sub.add_parser("report", help="Build the weekly report")
    rep.add_argument("--send", action="store_true", help="Email it to configured recipients")
    rep.add_argument("--save", metavar="FILE", help="Save HTML preview to FILE")
    rep.set_defaults(func=cmd_report)

    sub.add_parser("weekly", help="Refresh all + email report (for cron)").set_defaults(func=cmd_weekly)
    sub.add_parser("competitors", help="List tracked competitors").set_defaults(func=cmd_competitors)
    sub.add_parser("stats", help="Knowledge base statistics").set_defaults(func=cmd_stats)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
