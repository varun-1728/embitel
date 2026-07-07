"""Translate the `schedule:` config into scheduler-specific strings.

- systemd timers use an OnCalendar string.
- Windows Task Scheduler (schtasks) uses a /SC + /D + /ST triple.

Keeping the translation here (Python) means both the bash and PowerShell
installers stay dumb — they just ask this module what to schedule.
"""

from __future__ import annotations

from .config import Config

_DAYS = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu",
         "fri": "Fri", "sat": "Sat", "sun": "Sun"}
# schtasks day codes.
_WIN_DAYS = {"mon": "MON", "tue": "TUE", "wed": "WED", "thu": "THU",
             "fri": "FRI", "sat": "SAT", "sun": "SUN"}


def _sched(cfg: Config) -> dict:
    return cfg.raw.get("schedule", {}) or {}


def _time(cfg: Config) -> tuple[str, str]:
    t = str(_sched(cfg).get("time", "08:00")).strip()
    hh, _, mm = t.partition(":")
    hh = f"{int(hh):02d}"
    mm = f"{int(mm or 0):02d}"
    return hh, mm


def _interval(cfg: Config) -> str:
    return str(_sched(cfg).get("interval", "weekly")).strip().lower()


def _day(cfg: Config) -> str:
    return str(_sched(cfg).get("day", "Mon")).strip().lower()[:3]


def oncalendar(cfg: Config) -> str:
    """Build a systemd OnCalendar= value from config."""
    override = str(_sched(cfg).get("oncalendar", "")).strip()
    if override:
        return override

    hh, mm = _time(cfg)
    interval = _interval(cfg)
    if interval == "daily":
        return f"*-*-* {hh}:{mm}:00"
    if interval == "monthly":
        dom = int(_sched(cfg).get("day_of_month", 1))
        return f"*-*-{dom:02d} {hh}:{mm}:00"
    # default: weekly
    day = _DAYS.get(_day(cfg), "Mon")
    return f"{day} *-*-* {hh}:{mm}:00"


def schtasks_args(cfg: Config) -> str:
    """Build the Windows schtasks /SC ... /ST HH:MM fragment from config."""
    hh, mm = _time(cfg)
    interval = _interval(cfg)
    if interval == "daily":
        return f"/SC DAILY /ST {hh}:{mm}"
    if interval == "monthly":
        dom = int(_sched(cfg).get("day_of_month", 1))
        return f"/SC MONTHLY /D {dom} /ST {hh}:{mm}"
    day = _WIN_DAYS.get(_day(cfg), "MON")
    return f"/SC WEEKLY /D {day} /ST {hh}:{mm}"


def human(cfg: Config) -> str:
    hh, mm = _time(cfg)
    interval = _interval(cfg)
    if interval == "daily":
        return f"every day at {hh}:{mm}"
    if interval == "monthly":
        dom = int(_sched(cfg).get("day_of_month", 1))
        return f"day {dom} of each month at {hh}:{mm}"
    return f"every {_DAYS.get(_day(cfg), 'Mon')} at {hh}:{mm}"
