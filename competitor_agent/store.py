"""SQLite-backed persistent knowledge base of competitor findings.

Shared (not per-user). Both the CLI chat and the weekly report read from here.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id           TEXT PRIMARY KEY,       -- content hash, for dedup
    competitor   TEXT NOT NULL,
    category     TEXT NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    source_url   TEXT,
    event_date   TEXT,                   -- YYYY-MM-DD (approx, from source)
    created_at   TEXT NOT NULL           -- ISO8601 when we stored it
);
CREATE INDEX IF NOT EXISTS idx_findings_competitor ON findings(competitor);
CREATE INDEX IF NOT EXISTS idx_findings_created ON findings(created_at);

CREATE TABLE IF NOT EXISTS research_runs (
    competitor   TEXT PRIMARY KEY,
    last_run_at  TEXT NOT NULL,
    finding_count INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class Finding:
    id: str
    competitor: str
    category: str
    title: str
    summary: str
    source_url: str
    event_date: str
    created_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id(competitor: str, title: str, source_url: str) -> str:
    key = f"{competitor.lower()}|{title.lower().strip()}|{(source_url or '').lower()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class KnowledgeStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as c:
            c.executescript(SCHEMA)

    # ------------------------------------------------------------------ #
    def add_finding(
        self,
        competitor: str,
        category: str,
        title: str,
        summary: str,
        source_url: str = "",
        event_date: str = "",
    ) -> bool:
        """Insert a finding. Returns True if new, False if it was a duplicate."""
        fid = _make_id(competitor, title, source_url)
        with self._conn() as c:
            exists = c.execute("SELECT 1 FROM findings WHERE id=?", (fid,)).fetchone()
            if exists:
                return False
            c.execute(
                """INSERT INTO findings
                   (id, competitor, category, title, summary, source_url, event_date, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (fid, competitor, category, title, summary, source_url, event_date, _now_iso()),
            )
        return True

    def record_run(self, competitor: str, finding_count: int):
        with self._conn() as c:
            c.execute(
                """INSERT INTO research_runs (competitor, last_run_at, finding_count)
                   VALUES (?,?,?)
                   ON CONFLICT(competitor) DO UPDATE SET
                     last_run_at=excluded.last_run_at,
                     finding_count=excluded.finding_count""",
                (competitor, _now_iso(), finding_count),
            )

    # ------------------------------------------------------------------ #
    def _rows_to_findings(self, rows) -> list[Finding]:
        return [Finding(**dict(r)) for r in rows]

    def recent_findings(self, days: int, competitor: str | None = None) -> list[Finding]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        q = "SELECT * FROM findings WHERE created_at >= ?"
        params: list = [cutoff]
        if competitor:
            q += " AND competitor = ?"
            params.append(competitor)
        q += " ORDER BY competitor, category, created_at DESC"
        with self._conn() as c:
            return self._rows_to_findings(c.execute(q, params).fetchall())

    def findings_for(self, competitor: str, limit: int = 25) -> list[Finding]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM findings WHERE competitor=? ORDER BY created_at DESC LIMIT ?",
                (competitor, limit),
            ).fetchall()
        return self._rows_to_findings(rows)

    def search(self, term: str, limit: int = 25) -> list[Finding]:
        like = f"%{term}%"
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM findings
                   WHERE competitor LIKE ? OR title LIKE ? OR summary LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (like, like, like, limit),
            ).fetchall()
        return self._rows_to_findings(rows)

    def all_findings(self, limit: int = 500) -> list[Finding]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM findings ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return self._rows_to_findings(rows)

    def stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            by_comp = c.execute(
                "SELECT competitor, COUNT(*) n FROM findings GROUP BY competitor ORDER BY n DESC"
            ).fetchall()
            runs = c.execute(
                "SELECT competitor, last_run_at FROM research_runs"
            ).fetchall()
        return {
            "total": total,
            "by_competitor": {r["competitor"]: r["n"] for r in by_comp},
            "last_runs": {r["competitor"]: r["last_run_at"] for r in runs},
        }
