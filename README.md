# Embitel Competitor Intelligence Agent

Tracks Embitel's competitors in the automotive space — new technologies, hiring,
acquisitions, partnerships, and other developments — and surfaces the intel two ways:

1. **Interactive CLI chat** — ask questions, get contextualized answers grounded in
   an accumulated knowledge base + live web search.
2. **Weekly email report** — a concise briefing emailed to your team's Gmail inboxes.

The "brain" is a swappable LLM backend, defaulting to **Google Gemini** (free tier)
with **Google Search grounding** for live web search. Swap to Claude or Groq by
changing one line in `.env`.

---

## How it works

```
                  ┌─────────────────────────────────────────┐
                  │        LLM adapter (llm.py)             │
                  │  gemini (default) │ claude │ groq        │
                  │  + live web search (Google grounding)   │
                  └───────────────┬─────────────────────────┘
                                  │
        refresh / weekly          │            chat / report
   ┌──────────────────────────────┼──────────────────────────────┐
   │                              ▼                               │
   │   research.py  ──►  SQLite knowledge base (store.py)  ◄── chat.py
   │   (gather intel)         data/knowledge.db            (Q&A + memory)
   │                              │                               │
   │                              ▼                               │
   │                        report.py ──► emailer.py (Gmail SMTP) │
   └──────────────────────────────────────────────────────────────┘
```

The **knowledge base is shared** (not per-user): everything the agent gathers is
stored once and used by both chat and the weekly report. Chat also keeps
**conversation memory** within a session so follow-up questions work.

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
# if your system blocks it (PEP 668), use:
# pip install --user --break-system-packages -r requirements.txt
```

**2. Get a free Gemini API key** at <https://aistudio.google.com/apikey>

**3. Configure secrets**

```bash
cp .env.example .env
# then edit .env and fill in:
#   GEMINI_API_KEY       (from step 2)
#   GMAIL_ADDRESS        (the account the report is sent FROM)
#   GMAIL_APP_PASSWORD   (see below)
```

**Gmail App Password:** the report sends over Gmail SMTP using an *App Password*,
not your normal password. Enable 2-Step Verification on the account, then create one
at <https://myaccount.google.com/apppasswords> and paste it into `.env`.

**4. Choose who/what to track** — edit `config.yaml`:
- `competitors:` — the companies to monitor (add/remove freely)
- `report.recipients:` — the Gmail addresses that receive the weekly report
- `categories:`, `research.lookback_days`, `report.window_days` — tune as needed

---

## Usage

```bash
# Populate / refresh the knowledge base (runs web search per competitor)
python main.py refresh                     # all competitors
python main.py refresh --competitor KPIT   # just one

# Interactive chat
python main.py chat

# Weekly report
python main.py report                      # preview in terminal
python main.py report --save preview.html  # save an HTML preview to open in a browser
python main.py report --send               # email it to configured recipients

# Full weekly job (refresh everything, then build + email) — for cron
python main.py weekly

# Housekeeping
python main.py competitors                 # list tracked competitors
python main.py stats                       # knowledge-base stats
```

Open `preview.html` in a browser to see the exact email format.

---

## Scheduling the weekly report

The repo ships a **portable installer** that sets up a systemd user timer
(Mondays 08:00, with catch-up if the machine was off at that time). It detects
the project path and Python automatically, so it works for **any user on any
machine** — no hardcoded paths.

```bash
./install_schedule.sh                      # default: Mondays 08:00
./install_schedule.sh "Fri *-*-* 09:30:00" # custom time (systemd OnCalendar format)
```

Manage it:

```bash
systemctl --user list-timers embitel-weekly.timer   # next run / status
systemctl --user start embitel-weekly.service       # run once now (test)
journalctl --user -u embitel-weekly.service          # logs
./uninstall_schedule.sh                              # remove the schedule
```

> **Catch-up:** the missed run fires shortly after you next log in. For an
> always-on / headless box that should run without anyone logging in, also run
> `sudo loginctl enable-linger $USER`.
>
> **Laptop note:** plain `cron` does NOT catch up on missed runs — that's why we
> use a systemd timer with `Persistent=true`. If your machine has no systemd,
> fall back to cron: `0 8 * * 1  cd /path/to/embitel && ./run_weekly.sh`.

### Handing this project to someone else

The schedule lives in the user's home (`~/.config/systemd/user/`), and secrets
live in `.env` — neither travels with the folder. So a new person needs to:

1. `pip install -r requirements.txt` (or the `--user --break-system-packages` form)
2. `cp .env.example .env` and add their own `GEMINI_API_KEY` + Gmail credentials
3. Edit `config.yaml` recipients/competitors as desired
4. Run `./install_schedule.sh` to set up their own weekly timer

That's it — the scripts figure out their paths automatically.

---

## Switching LLM backend

In `.env`, set `LLM_PROVIDER` to `gemini` (default), `claude`, or `groq`, and provide
the matching key (`ANTHROPIC_API_KEY` / `GROQ_API_KEY`). Install the extra package if
needed (`pip install anthropic` or `pip install groq`). No other changes required.

> Note: Groq has no built-in web search, so with it the agent relies on model
> knowledge only — Gemini (default) and Claude both do live web search.

---

## Project layout

| File | Purpose |
|------|---------|
| `config.yaml` | What to track — competitors, categories, recipients, models |
| `.env` | Secrets — API key, Gmail credentials |
| `competitor_agent/config.py` | Config + env loading |
| `competitor_agent/llm.py` | Provider-agnostic LLM adapter (Gemini/Claude/Groq) |
| `competitor_agent/store.py` | SQLite knowledge base (findings, dedup, queries) |
| `competitor_agent/research.py` | Gathers intel via web search, parses, stores |
| `competitor_agent/chat.py` | Interactive Q&A with KB retrieval + memory |
| `competitor_agent/report.py` | Weekly report generation (text + HTML) |
| `competitor_agent/emailer.py` | Gmail SMTP delivery |
| `competitor_agent/cli.py` | Command-line interface |
| `main.py` | Entry point |
