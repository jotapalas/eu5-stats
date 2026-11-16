"""SQLite storage for campaigns, sessions, saves and extracted statistics."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .extract import SaveStats

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    name        TEXT,
    played_on   TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saves (
    id               INTEGER PRIMARY KEY,
    session_id       INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    campaign_id      INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    sha256           TEXT NOT NULL,
    file_name        TEXT,
    playthrough_id   TEXT,
    playthrough_name TEXT,
    version          TEXT,
    game_hours       INTEGER,
    game_date        TEXT,
    status           TEXT NOT NULL,  -- pending | processing | done | error
    error            TEXT,
    warning          TEXT,
    uploaded_at      TEXT NOT NULL,
    processed_at     TEXT,
    UNIQUE (campaign_id, sha256)
);
CREATE INDEX IF NOT EXISTS saves_status ON saves(status);
CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    UNIQUE (campaign_id, name)
);
CREATE TABLE IF NOT EXISTS player_snapshots (
    save_id    INTEGER NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    player_id  INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    country_id INTEGER NOT NULL,
    tag        TEXT,
    PRIMARY KEY (save_id, player_id)
);
CREATE TABLE IF NOT EXISTS metrics (
    save_id   INTEGER NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    metric    TEXT NOT NULL,
    value     REAL NOT NULL,
    PRIMARY KEY (save_id, player_id, metric)
);
CREATE TABLE IF NOT EXISTS country_history (
    save_id INTEGER NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    metric  TEXT NOT NULL,
    year    INTEGER NOT NULL,
    value   REAL NOT NULL,
    PRIMARY KEY (save_id, tag, metric, year)
);
"""

# Processed saves that count for campaign-wide series: when several saves share a game
# date, the most recently uploaded one wins.
EFFECTIVE_SAVES = """
SELECT s.* FROM saves s
WHERE s.campaign_id = :campaign AND s.status = 'done'
  AND s.id = (SELECT MAX(s2.id) FROM saves s2
              WHERE s2.campaign_id = s.campaign_id AND s2.status = 'done'
                AND s2.game_hours = s.game_hours)
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        try:
            with db:  # commit / rollback
                yield db
        finally:
            db.close()

    # ------------------------------------------------------------------ campaigns
    def create_campaign(self, name: str, description: str | None) -> dict:
        with self.connect() as db:
            try:
                cur = db.execute(
                    "INSERT INTO campaigns(name, description, created_at) VALUES (?, ?, ?)",
                    (name, description, now()),
                )
            except sqlite3.IntegrityError as e:
                raise Conflict(f"A campaign named {name!r} already exists") from e
            return self._campaign(db, cur.lastrowid)

    def _campaign(self, db, campaign_id: int) -> dict:
        row = db.execute(
            """
            SELECT c.*,
              (SELECT COUNT(*) FROM sessions WHERE campaign_id = c.id) AS sessions,
              (SELECT COUNT(*) FROM saves WHERE campaign_id = c.id) AS saves,
              (SELECT COUNT(*) FROM saves WHERE campaign_id = c.id AND status = 'done') AS saves_done,
              (SELECT COUNT(*) FROM saves WHERE campaign_id = c.id AND status IN ('pending','processing')) AS saves_pending,
              (SELECT COUNT(*) FROM saves WHERE campaign_id = c.id AND status = 'error') AS saves_error,
              (SELECT game_date FROM saves WHERE campaign_id = c.id AND status = 'done'
                 ORDER BY game_hours ASC LIMIT 1) AS first_date,
              (SELECT game_date FROM saves WHERE campaign_id = c.id AND status = 'done'
                 ORDER BY game_hours DESC LIMIT 1) AS last_date
            FROM campaigns c WHERE c.id = ?
            """,
            (campaign_id,),
        ).fetchone()
        if row is None:
            raise NotFound(f"Campaign {campaign_id} not found")
        out = dict(row)
        out["players"] = [r["name"] for r in db.execute(
            "SELECT name FROM players WHERE campaign_id = ? ORDER BY name", (campaign_id,))]
        return out

    def get_campaign(self, campaign_id: int) -> dict:
        with self.connect() as db:
            return self._campaign(db, campaign_id)

    def list_campaigns(self) -> list[dict]:
        with self.connect() as db:
            ids = [r["id"] for r in db.execute("SELECT id FROM campaigns ORDER BY id")]
            return [self._campaign(db, i) for i in ids]

    def update_campaign(self, campaign_id: int, name: str | None, description: str | None) -> dict:
        with self.connect() as db:
            self._campaign(db, campaign_id)
            try:
                if name is not None:
                    db.execute("UPDATE campaigns SET name = ? WHERE id = ?", (name, campaign_id))
                if description is not None:
                    db.execute("UPDATE campaigns SET description = ? WHERE id = ?", (description, campaign_id))
            except sqlite3.IntegrityError as e:
                raise Conflict(f"A campaign named {name!r} already exists") from e
            return self._campaign(db, campaign_id)

    def delete_campaign(self, campaign_id: int) -> None:
        with self.connect() as db:
            c = self._campaign(db, campaign_id)
            if c["sessions"]:
                raise Conflict("Campaign has sessions; delete them first")
            db.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))

    # ------------------------------------------------------------------ sessions
    def create_session(self, campaign_id: int, name: str | None, played_on: str | None,
                       notes: str | None) -> int:
        with self.connect() as db:
            self._campaign(db, campaign_id)
            cur = db.execute(
                "INSERT INTO sessions(campaign_id, name, played_on, notes, created_at) VALUES (?,?,?,?,?)",
                (campaign_id, name, played_on, notes, now()),
            )
            return cur.lastrowid

    def _session(self, db, session_id: int) -> dict:
        row = db.execute(
            """
            SELECT se.*,
              (SELECT game_date FROM saves WHERE session_id = se.id AND status = 'done'
                 ORDER BY game_hours ASC LIMIT 1) AS first_date,
              (SELECT game_date FROM saves WHERE session_id = se.id AND status = 'done'
                 ORDER BY game_hours DESC LIMIT 1) AS last_date
            FROM sessions se WHERE se.id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise NotFound(f"Session {session_id} not found")
        out = dict(row)
        counts = {r["status"]: r["n"] for r in db.execute(
            "SELECT status, COUNT(*) AS n FROM saves WHERE session_id = ? GROUP BY status", (session_id,))}
        out["saves_by_status"] = counts
        out["saves"] = sum(counts.values())
        return out

    def get_session(self, session_id: int, with_saves: bool = True) -> dict:
        with self.connect() as db:
            out = self._session(db, session_id)
            if with_saves:
                out["save_list"] = [dict(r) for r in db.execute(
                    "SELECT * FROM saves WHERE session_id = ? ORDER BY game_hours IS NULL, game_hours, id",
                    (session_id,))]
            return out

    def list_sessions(self, campaign_id: int) -> list[dict]:
        with self.connect() as db:
            self._campaign(db, campaign_id)
            ids = [r["id"] for r in db.execute(
                "SELECT id FROM sessions WHERE campaign_id = ? ORDER BY id", (campaign_id,))]
            return [self._session(db, i) for i in ids]

    def delete_session(self, session_id: int) -> list[str]:
        """Delete a session and its saves. Returns sha256s no longer referenced anywhere."""
        with self.connect() as db:
            self._session(db, session_id)
            shas = [r["sha256"] for r in db.execute(
                "SELECT sha256 FROM saves WHERE session_id = ?", (session_id,))]
            db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            # Players that no longer appear in any save of the campaign.
            db.execute("DELETE FROM players WHERE id NOT IN (SELECT player_id FROM player_snapshots)")
            return [s for s in shas if db.execute(
                "SELECT 1 FROM saves WHERE sha256 = ? LIMIT 1", (s,)).fetchone() is None]

    # ------------------------------------------------------------------ saves
    def add_save(self, session_id: int, sha256: str, file_name: str,
                 status: str = "pending", error: str | None = None) -> dict:
        """Register a save in a session. Returns {id, file, status} ('duplicate' if already in the campaign)."""
        with self.connect() as db:
            session = self._session(db, session_id)
            existing = db.execute(
                "SELECT id, session_id FROM saves WHERE campaign_id = ? AND sha256 = ?",
                (session["campaign_id"], sha256),
            ).fetchone()
            if existing:
                return {"id": existing["id"], "file": file_name, "status": "duplicate",
                        "session_id": existing["session_id"]}
            cur = db.execute(
                """INSERT INTO saves(session_id, campaign_id, sha256, file_name, status, error, uploaded_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (session_id, session["campaign_id"], sha256, file_name, status, error, now()),
            )
            return {"id": cur.lastrowid, "file": file_name, "status": status, "session_id": session_id}

    def get_save(self, save_id: int) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM saves WHERE id = ?", (save_id,)).fetchone()
            if row is None:
                raise NotFound(f"Save {save_id} not found")
            out = dict(row)
            out["players"] = db.execute(
                "SELECT COUNT(*) FROM player_snapshots WHERE save_id = ?", (save_id,)).fetchone()[0]
            return out

    def claim_next_pending(self) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM saves WHERE status = 'pending' ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE saves SET status = 'processing' WHERE id = ?", (row["id"],))
            return dict(row)

    def reset_processing(self) -> None:
        """On startup: saves left 'processing' by a crash go back to 'pending'."""
        with self.connect() as db:
            db.execute("UPDATE saves SET status = 'pending' WHERE status = 'processing'")

    def mark_pending(self, *, save_id: int | None = None, campaign_id: int | None = None) -> int:
        with self.connect() as db:
            if save_id is not None:
                if db.execute("SELECT 1 FROM saves WHERE id = ?", (save_id,)).fetchone() is None:
                    raise NotFound(f"Save {save_id} not found")
                cur = db.execute(
                    "UPDATE saves SET status = 'pending', error = NULL WHERE id = ?", (save_id,))
            else:
                self._campaign(db, campaign_id)
                cur = db.execute(
                    "UPDATE saves SET status = 'pending', error = NULL WHERE campaign_id = ?", (campaign_id,))
            return cur.rowcount

    def mark_error(self, save_id: int, error: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE saves SET status = 'error', error = ?, processed_at = ? WHERE id = ?",
                       (error, now(), save_id))

    def store_stats(self, save_id: int, stats: SaveStats) -> None:
        """Replace everything extracted from a save (idempotent, used for reprocessing)."""
        with self.connect() as db:
            save = db.execute("SELECT * FROM saves WHERE id = ?", (save_id,)).fetchone()
            if save is None:
                raise NotFound(f"Save {save_id} not found")
            campaign_id = save["campaign_id"]

            others = {r[0] for r in db.execute(
                "SELECT DISTINCT playthrough_id FROM saves WHERE campaign_id = ? AND id != ? "
                "AND playthrough_id IS NOT NULL", (campaign_id, save_id))}
            warning = None
            if others and stats.playthrough_id not in others:
                warning = (f"Save belongs to playthrough {stats.playthrough_id}, other saves in this "
                           f"campaign belong to {sorted(others)}")

            db.execute("DELETE FROM player_snapshots WHERE save_id = ?", (save_id,))
            db.execute("DELETE FROM metrics WHERE save_id = ?", (save_id,))
            db.execute("DELETE FROM country_history WHERE save_id = ?", (save_id,))
            for p in stats.players:
                db.execute("INSERT OR IGNORE INTO players(campaign_id, name) VALUES (?, ?)",
                           (campaign_id, p.name))
                player_id = db.execute("SELECT id FROM players WHERE campaign_id = ? AND name = ?",
                                       (campaign_id, p.name)).fetchone()[0]
                db.execute("INSERT INTO player_snapshots VALUES (?, ?, ?, ?)",
                           (save_id, player_id, p.country_id, p.tag))
                db.executemany("INSERT INTO metrics VALUES (?, ?, ?, ?)",
                               [(save_id, player_id, k, v) for k, v in p.metrics.items()])
            db.executemany("INSERT INTO country_history VALUES (?, ?, ?, ?, ?)",
                           [(save_id, tag, m, y, v) for tag, m, y, v in stats.history])
            db.execute(
                """UPDATE saves SET status = 'done', error = NULL, warning = ?, processed_at = ?,
                   playthrough_id = ?, playthrough_name = ?, version = ?,
                   game_hours = ?, game_date = ? WHERE id = ?""",
                (warning, now(), stats.playthrough_id, stats.playthrough_name, stats.version,
                 stats.game_hours, stats.game_date, save_id),
            )

    # ------------------------------------------------------------------ queries
    def series(self, campaign_id: int, metric: str, player: str | None = None,
               session_id: int | None = None) -> dict[str, list]:
        with self.connect() as db:
            self._campaign(db, campaign_id)
            if session_id is not None:
                saves_sql = "SELECT * FROM saves WHERE session_id = :session AND status = 'done'"
            else:
                saves_sql = EFFECTIVE_SAVES
            rows = db.execute(
                f"""
                SELECT p.name, s.game_date, m.value
                FROM ({saves_sql}) s
                JOIN metrics m ON m.save_id = s.id
                JOIN players p ON p.id = m.player_id
                WHERE m.metric = :metric AND (:player IS NULL OR p.name = :player)
                ORDER BY p.name, s.game_hours
                """,
                {"campaign": campaign_id, "session": session_id, "metric": metric, "player": player},
            ).fetchall()
            out: dict[str, list] = {}
            for r in rows:
                out.setdefault(r["name"], []).append([r["game_date"], r["value"]])
            return out

    def player_timeline(self, campaign_id: int, name: str) -> list[dict]:
        with self.connect() as db:
            self._campaign(db, campaign_id)
            pid = db.execute("SELECT id FROM players WHERE campaign_id = ? AND name = ?",
                             (campaign_id, name)).fetchone()
            if pid is None:
                raise NotFound(f"Player {name!r} not found in campaign {campaign_id}")
            snaps = db.execute(
                f"""
                SELECT s.id, s.game_date, s.session_id, ps.tag, ps.country_id
                FROM ({EFFECTIVE_SAVES}) s
                JOIN player_snapshots ps ON ps.save_id = s.id AND ps.player_id = :player
                ORDER BY s.game_hours
                """,
                {"campaign": campaign_id, "player": pid[0]},
            ).fetchall()
            out = []
            for s in snaps:
                metrics = {r["metric"]: r["value"] for r in db.execute(
                    "SELECT metric, value FROM metrics WHERE save_id = ? AND player_id = ?",
                    (s["id"], pid[0]))}
                out.append({"save_id": s["id"], "session_id": s["session_id"], "date": s["game_date"],
                            "tag": s["tag"], "country_id": s["country_id"], "metrics": metrics})
            return out

    def latest_snapshots(self, campaign_id: int) -> dict[str, dict]:
        """Latest snapshot of each player in the campaign."""
        with self.connect() as db:
            self._campaign(db, campaign_id)
            rows = db.execute(
                f"""
                SELECT p.name, s.id AS save_id, s.game_date, ps.tag, ps.player_id
                FROM ({EFFECTIVE_SAVES}) s
                JOIN player_snapshots ps ON ps.save_id = s.id
                JOIN players p ON p.id = ps.player_id
                WHERE s.game_hours = (
                    SELECT MAX(s3.game_hours) FROM saves s3
                    JOIN player_snapshots ps3 ON ps3.save_id = s3.id
                    WHERE s3.campaign_id = :campaign AND s3.status = 'done'
                      AND ps3.player_id = ps.player_id)
                ORDER BY p.name
                """,
                {"campaign": campaign_id},
            ).fetchall()
            out = {}
            for r in rows:
                metrics = {m["metric"]: m["value"] for m in db.execute(
                    "SELECT metric, value FROM metrics WHERE save_id = ? AND player_id = ?",
                    (r["save_id"], r["player_id"]))}
                out[r["name"]] = {"date": r["game_date"], "tag": r["tag"], "metrics": metrics}
            return out

    def session_summary(self, session_id: int) -> dict:
        with self.connect() as db:
            session = self._session(db, session_id)
            saves = db.execute(
                "SELECT id, game_date, game_hours FROM saves WHERE session_id = ? AND status = 'done' "
                "ORDER BY game_hours, id", (session_id,)).fetchall()
            out = {"session_id": session_id, "campaign_id": session["campaign_id"],
                   "first_date": None, "last_date": None, "players": {}}
            if not saves:
                return out
            first, last = saves[0], saves[-1]
            out["first_date"], out["last_date"] = first["game_date"], last["game_date"]

            def load(save_id):
                res: dict[str, dict] = {}
                for r in db.execute(
                    """SELECT p.name, m.metric, m.value FROM metrics m
                       JOIN players p ON p.id = m.player_id WHERE m.save_id = ?""", (save_id,)):
                    res.setdefault(r["name"], {})[r["metric"]] = r["value"]
                return res

            start, end = load(first["id"]), load(last["id"])
            for name in sorted(set(start) | set(end)):
                s, e = start.get(name, {}), end.get(name, {})
                out["players"][name] = {
                    m: {"start": s.get(m), "end": e.get(m),
                        "delta": (e[m] - s[m]) if m in s and m in e else None}
                    for m in sorted(set(s) | set(e))
                }
            return out

    def history(self, campaign_id: int, metric: str) -> dict:
        """Yearly series kept by the game (historical_*), per tag; the latest save wins per year."""
        with self.connect() as db:
            self._campaign(db, campaign_id)
            rows = db.execute(
                f"""
                SELECT h.tag, h.year, h.value
                FROM country_history h JOIN ({EFFECTIVE_SAVES}) s ON s.id = h.save_id
                WHERE h.metric = :metric
                  AND s.game_hours = (
                      SELECT MAX(s2.game_hours) FROM country_history h2
                      JOIN saves s2 ON s2.id = h2.save_id
                      WHERE s2.campaign_id = :campaign AND s2.status = 'done'
                        AND h2.tag = h.tag AND h2.metric = h.metric AND h2.year = h.year)
                ORDER BY h.tag, h.year
                """,
                {"campaign": campaign_id, "metric": metric},
            ).fetchall()
            series: dict[str, list] = {}
            for r in rows:
                series.setdefault(r["tag"], []).append([r["year"], r["value"]])
            players: dict[str, list] = {}
            for r in db.execute(
                """SELECT DISTINCT ps.tag, p.name FROM player_snapshots ps
                   JOIN players p ON p.id = ps.player_id
                   JOIN saves s ON s.id = ps.save_id
                   WHERE s.campaign_id = ? AND ps.tag IS NOT NULL ORDER BY p.name""", (campaign_id,)):
                players.setdefault(r["tag"], []).append(r["name"])
            return {"series": series, "players": players}
