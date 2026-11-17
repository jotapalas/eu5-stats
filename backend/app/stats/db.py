"""SQLite storage for campaigns, sessions, saves and extracted statistics.

Statistics are per country, keyed by `country_id` (stable across tag changes such as ENG -> GBR);
each snapshot keeps the tag the country had in that save and the players controlling it. Countries
are labelled in query results by their *current* tag: the one in their latest processed save.

`campaign_countries` is the editable list of countries a campaign tracks. Countries played by humans
are added automatically when a save is processed; removing one only deactivates it, so data already
extracted is kept and the country is no longer extracted from saves processed afterwards.
"""
from __future__ import annotations

import json
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
CREATE TABLE IF NOT EXISTS campaign_countries (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,      -- tag the country was added with
    country_id  INTEGER,            -- NULL until a processed save resolves the tag
    active      INTEGER NOT NULL DEFAULT 1,
    player      TEXT,               -- main player shown in campaign-wide views (NULL: from saves)
    added_at    TEXT NOT NULL,
    UNIQUE (campaign_id, country_id)
);
CREATE TABLE IF NOT EXISTS country_snapshots (
    save_id    INTEGER NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    country_id INTEGER NOT NULL,
    tag        TEXT,
    players    TEXT NOT NULL,  -- JSON list of player names (empty: AI)
    PRIMARY KEY (save_id, country_id)
);
CREATE TABLE IF NOT EXISTS country_metrics (
    save_id    INTEGER NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    country_id INTEGER NOT NULL,
    metric     TEXT NOT NULL,
    value      REAL NOT NULL,
    PRIMARY KEY (save_id, country_id, metric)
);
-- The game's yearly history (historical_*) is no longer stored.
DROP TABLE IF EXISTS country_history;
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
        current = self._current_tags(db, campaign_id)
        entries = self._entries(db, campaign_id)
        out["countries"] = sorted(current.get(e["country_id"], e["tag"]) for e in entries if e["active"])
        # Main player per country (edited in the tracked list), keyed by display tag; only those set.
        out["main_players"] = {current.get(e["country_id"], e["tag"]): e["player"] for e in entries if e["player"]}
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

    # ------------------------------------------------------------------ tracked countries
    @staticmethod
    def _entries(db, campaign_id: int) -> list[sqlite3.Row]:
        return db.execute("SELECT * FROM campaign_countries WHERE campaign_id = ? ORDER BY id",
                          (campaign_id,)).fetchall()

    @staticmethod
    def _current_tags(db, campaign_id: int) -> dict[int, str]:
        """country_id -> tag in its latest processed save of the campaign."""
        out: dict[int, str] = {}
        for r in db.execute(
            """SELECT cs.country_id, cs.tag FROM country_snapshots cs JOIN saves s ON s.id = cs.save_id
               WHERE s.campaign_id = ? AND s.status = 'done' AND cs.tag IS NOT NULL
               ORDER BY s.game_hours, s.id""", (campaign_id,)):
            out[r["country_id"]] = r["tag"]
        return out

    def _label(self, db, campaign_id: int):
        """Function country_id -> display tag (current tag, else the tag it was added with)."""
        current = self._current_tags(db, campaign_id)
        added = {e["country_id"]: e["tag"] for e in self._entries(db, campaign_id) if e["country_id"] is not None}
        return lambda cid: current.get(cid) or added.get(cid) or str(cid)

    def _country_id(self, db, campaign_id: int, tag: str) -> int | None:
        """Resolve a tag to a country_id: current tag, then tag it was added with, then any past tag."""
        for cid, t in self._current_tags(db, campaign_id).items():
            if t == tag:
                return cid
        for e in self._entries(db, campaign_id):
            if e["tag"] == tag and e["country_id"] is not None:
                return e["country_id"]
        row = db.execute(
            """SELECT cs.country_id FROM country_snapshots cs JOIN saves s ON s.id = cs.save_id
               WHERE s.campaign_id = ? AND s.status = 'done' AND cs.tag = ?
               ORDER BY s.game_hours DESC, s.id DESC LIMIT 1""", (campaign_id, tag)).fetchone()
        return row[0] if row else None

    def _entry_for(self, db, campaign_id: int, tag: str) -> sqlite3.Row | None:
        cid = self._country_id(db, campaign_id, tag)
        for e in self._entries(db, campaign_id):
            if (cid is not None and e["country_id"] == cid) or (e["country_id"] is None and e["tag"] == tag):
                return e
        return None

    def tracked_countries(self, campaign_id: int) -> list[tuple[str, int | None]]:
        """Active tracked countries as (tag, country_id or None), the input of `extract`."""
        with self.connect() as db:
            return [(e["tag"], e["country_id"]) for e in self._entries(db, campaign_id) if e["active"]]

    def list_countries(self, campaign_id: int) -> list[dict]:
        with self.connect() as db:
            self._campaign(db, campaign_id)
            current = self._current_tags(db, campaign_id)
            seen: dict[int, dict] = {}
            for r in db.execute(
                f"""SELECT cs.country_id, cs.tag, cs.players, s.game_date FROM ({EFFECTIVE_SAVES}) s
                    JOIN country_snapshots cs ON cs.save_id = s.id ORDER BY s.game_hours""",
                {"campaign": campaign_id}):
                info = seen.setdefault(r["country_id"], {"tags": [], "players": [], "snapshots": 0})
                if r["tag"] and r["tag"] not in info["tags"]:
                    info["tags"].append(r["tag"])
                for p in json.loads(r["players"]):
                    if p not in info["players"]:
                        info["players"].append(p)
                info["snapshots"] += 1
                info["last_date"] = r["game_date"]
            out = []
            for e in self._entries(db, campaign_id):
                info = seen.get(e["country_id"], {}) if e["country_id"] is not None else {}
                out.append({
                    "tag": current.get(e["country_id"], e["tag"]),
                    "added_as": e["tag"],
                    "country_id": e["country_id"],
                    "active": bool(e["active"]),
                    "player": e["player"],
                    "added_at": e["added_at"],
                    "tags": info.get("tags", []),
                    "players": info.get("players", []),
                    "snapshots": info.get("snapshots", 0),
                    "last_date": info.get("last_date"),
                })
            return sorted(out, key=lambda c: (not c["active"], c["tag"]))

    def add_country(self, campaign_id: int, tag: str) -> dict:
        """Track a country from now on. Reactivates it if it was removed."""
        with self.connect() as db:
            self._campaign(db, campaign_id)
            entry = self._entry_for(db, campaign_id, tag)
            if entry is not None:
                if entry["active"]:
                    raise Conflict(f"Country {tag} is already tracked in campaign {campaign_id}")
                db.execute("UPDATE campaign_countries SET active = 1 WHERE id = ?", (entry["id"],))
            else:
                db.execute(
                    "INSERT INTO campaign_countries(campaign_id, tag, country_id, added_at) VALUES (?,?,?,?)",
                    (campaign_id, tag, self._country_id(db, campaign_id, tag), now()))
        return next(c for c in self.list_countries(campaign_id)
                    if tag in (c["tag"], c["added_as"]) or tag in c["tags"])

    def set_country_player(self, campaign_id: int, tag: str, player: str | None) -> dict:
        """Set the main player shown for a country in campaign-wide views (None: use the saves' players)."""
        player = (player or "").strip() or None
        with self.connect() as db:
            self._campaign(db, campaign_id)
            entry = self._entry_for(db, campaign_id, tag)
            if entry is None:
                raise NotFound(f"Country {tag} is not tracked in campaign {campaign_id}")
            db.execute("UPDATE campaign_countries SET player = ? WHERE id = ?", (player, entry["id"]))
            key = (entry["tag"], entry["country_id"])
        return next(c for c in self.list_countries(campaign_id) if (c["added_as"], c["country_id"]) == key)

    def remove_country(self, campaign_id: int, tag: str) -> None:
        """Stop tracking a country in saves processed from now on; extracted data is kept."""
        with self.connect() as db:
            self._campaign(db, campaign_id)
            entry = self._entry_for(db, campaign_id, tag)
            if entry is None or not entry["active"]:
                raise NotFound(f"Country {tag} is not tracked in campaign {campaign_id}")
            db.execute("UPDATE campaign_countries SET active = 0 WHERE id = ?", (entry["id"],))

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
            players = [json.loads(r[0]) for r in db.execute(
                "SELECT players FROM country_snapshots WHERE save_id = ?", (save_id,))]
            out["countries"] = len(players)
            out["players"] = sum(len(p) for p in players)
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

    def _update_tracked(self, db, campaign_id: int, stats: SaveStats) -> set[int]:
        """Resolve pending entries, auto-add played countries; returns the active country ids."""
        entries = self._entries(db, campaign_id)
        by_cid = {e["country_id"]: e for e in entries if e["country_id"] is not None}
        pending = {e["tag"]: e for e in entries if e["country_id"] is None}
        active = {cid for cid, e in by_cid.items() if e["active"]}
        for c in stats.countries:
            if c.country_id in by_cid:
                continue
            e = pending.pop(c.tag, None) if c.tag else None
            if e is not None:
                db.execute("UPDATE campaign_countries SET country_id = ? WHERE id = ?", (c.country_id, e["id"]))
                if e["active"]:
                    active.add(c.country_id)
            elif c.players:
                db.execute(
                    "INSERT INTO campaign_countries(campaign_id, tag, country_id, added_at) VALUES (?,?,?,?)",
                    (campaign_id, c.tag or str(c.country_id), c.country_id, now()))
                active.add(c.country_id)
        return active

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

            active = self._update_tracked(db, campaign_id, stats)
            db.execute("DELETE FROM country_snapshots WHERE save_id = ?", (save_id,))
            db.execute("DELETE FROM country_metrics WHERE save_id = ?", (save_id,))
            for c in stats.countries:
                if c.country_id not in active:  # played but removed from the campaign
                    continue
                db.execute("INSERT INTO country_snapshots VALUES (?, ?, ?, ?)",
                           (save_id, c.country_id, c.tag, json.dumps(c.players)))
                db.executemany("INSERT INTO country_metrics VALUES (?, ?, ?, ?)",
                               [(save_id, c.country_id, k, v) for k, v in c.metrics.items()])
            db.execute(
                """UPDATE saves SET status = 'done', error = NULL, warning = ?, processed_at = ?,
                   playthrough_id = ?, playthrough_name = ?, version = ?,
                   game_hours = ?, game_date = ? WHERE id = ?""",
                (warning, now(), stats.playthrough_id, stats.playthrough_name, stats.version,
                 stats.game_hours, stats.game_date, save_id),
            )

    # ------------------------------------------------------------------ queries
    def _resolve(self, db, campaign_id: int, tag: str) -> int:
        cid = self._country_id(db, campaign_id, tag)
        if cid is None:
            raise NotFound(f"Country {tag} not found in campaign {campaign_id}")
        return cid

    def series(self, campaign_id: int, metric: str, tag: str | None = None,
               session_id: int | None = None) -> dict[str, list]:
        with self.connect() as db:
            self._campaign(db, campaign_id)
            cid = self._resolve(db, campaign_id, tag) if tag is not None else None
            if session_id is not None:
                saves_sql = "SELECT * FROM saves WHERE session_id = :session AND status = 'done'"
            else:
                saves_sql = EFFECTIVE_SAVES
            rows = db.execute(
                f"""
                SELECT m.country_id, s.game_date, m.value
                FROM ({saves_sql}) s
                JOIN country_metrics m ON m.save_id = s.id
                WHERE m.metric = :metric AND (:cid IS NULL OR m.country_id = :cid)
                ORDER BY m.country_id, s.game_hours
                """,
                {"campaign": campaign_id, "session": session_id, "metric": metric, "cid": cid},
            ).fetchall()
            label = self._label(db, campaign_id)
            out: dict[str, list] = {}
            for r in rows:
                out.setdefault(label(r["country_id"]), []).append([r["game_date"], r["value"]])
            return dict(sorted(out.items()))

    def country_timeline(self, campaign_id: int, tag: str) -> dict:
        with self.connect() as db:
            self._campaign(db, campaign_id)
            cid = self._resolve(db, campaign_id, tag)
            snaps = db.execute(
                f"""
                SELECT s.id, s.game_date, s.session_id, cs.tag, cs.players
                FROM ({EFFECTIVE_SAVES}) s
                JOIN country_snapshots cs ON cs.save_id = s.id AND cs.country_id = :cid
                ORDER BY s.game_hours
                """,
                {"campaign": campaign_id, "cid": cid},
            ).fetchall()
            timeline = []
            for s in snaps:
                metrics = {r["metric"]: r["value"] for r in db.execute(
                    "SELECT metric, value FROM country_metrics WHERE save_id = ? AND country_id = ?",
                    (s["id"], cid))}
                timeline.append({"save_id": s["id"], "session_id": s["session_id"], "date": s["game_date"],
                                 "tag": s["tag"], "players": json.loads(s["players"]), "metrics": metrics})
            return {"tag": self._label(db, campaign_id)(cid), "country_id": cid, "timeline": timeline}

    def latest_snapshots(self, campaign_id: int) -> dict[str, dict]:
        """Latest snapshot of each country with data in the campaign."""
        with self.connect() as db:
            self._campaign(db, campaign_id)
            rows = db.execute(
                f"""
                SELECT s.id AS save_id, s.game_date, cs.country_id, cs.tag, cs.players
                FROM ({EFFECTIVE_SAVES}) s
                JOIN country_snapshots cs ON cs.save_id = s.id
                WHERE s.game_hours = (
                    SELECT MAX(s3.game_hours) FROM saves s3
                    JOIN country_snapshots cs3 ON cs3.save_id = s3.id
                    WHERE s3.campaign_id = :campaign AND s3.status = 'done'
                      AND cs3.country_id = cs.country_id)
                """,
                {"campaign": campaign_id},
            ).fetchall()
            label = self._label(db, campaign_id)
            out = {}
            for r in rows:
                metrics = {m["metric"]: m["value"] for m in db.execute(
                    "SELECT metric, value FROM country_metrics WHERE save_id = ? AND country_id = ?",
                    (r["save_id"], r["country_id"]))}
                out[label(r["country_id"])] = {"date": r["game_date"], "tag": r["tag"], "country_id": r["country_id"],
                                               "players": json.loads(r["players"]), "metrics": metrics}
            return dict(sorted(out.items()))

    def session_summary(self, session_id: int) -> dict:
        with self.connect() as db:
            session = self._session(db, session_id)
            saves = db.execute(
                "SELECT id, game_date, game_hours FROM saves WHERE session_id = ? AND status = 'done' "
                "ORDER BY game_hours, id", (session_id,)).fetchall()
            out = {"session_id": session_id, "campaign_id": session["campaign_id"],
                   "first_date": None, "last_date": None, "countries": {}, "players": {}}
            if not saves:
                return out
            first, last = saves[0], saves[-1]
            out["first_date"], out["last_date"] = first["game_date"], last["game_date"]

            def load(save_id):
                res: dict[int, dict] = {}
                for r in db.execute("SELECT country_id, metric, value FROM country_metrics WHERE save_id = ?",
                                    (save_id,)):
                    res.setdefault(r["country_id"], {})[r["metric"]] = r["value"]
                return res

            start, end = load(first["id"]), load(last["id"])
            label = self._label(db, session["campaign_id"])
            for cid in set(start) | set(end):
                s, e = start.get(cid, {}), end.get(cid, {})
                out["countries"][label(cid)] = {
                    m: {"start": s.get(m), "end": e.get(m),
                        "delta": (e[m] - s[m]) if m in s and m in e else None}
                    for m in sorted(set(s) | set(e))
                }
            out["countries"] = dict(sorted(out["countries"].items()))
            # Players as written in this session's saves (not the campaign's main player).
            for r in db.execute(
                "SELECT cs.country_id, cs.players FROM country_snapshots cs JOIN saves s ON s.id = cs.save_id "
                "WHERE s.session_id = ? AND s.status = 'done' ORDER BY s.game_hours, s.id", (session_id,)):
                names = out["players"].setdefault(label(r["country_id"]), [])
                names.extend(p for p in json.loads(r["players"]) if p not in names)
            out["players"] = dict(sorted(out["players"].items()))
            return out
