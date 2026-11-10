"""Persistência em SQLite (seção 10 de docs/arquitetura.md).

- `meta`: versão do esquema, hora do mundo, seed, estado do RNG, velocidade...
- `characters`: estado vivo de cada personagem, POR ID (o nome nunca é salvo).
- `events` (+ `event_actors`, `event_tags`): o Chat do Mundo inteiro.
- `relations`: afinidade viva por par (só os pares que mudaram desde o YAML).

Migrações simples: uma lista de SQL por versão; o banco guarda a versão em
`meta.schema_version` e aplica só as que faltam.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sim.events import NOT_PERSISTED, Event

MIGRATIONS: list[str] = [
    # versão 1 (Fase 1)
    """
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS characters (
      id TEXT PRIMARY KEY,
      alive INTEGER NOT NULL DEFAULT 1,
      place TEXT NOT NULL,
      needs TEXT NOT NULL,
      current TEXT,
      last_action TEXT,
      extra_traits TEXT NOT NULL DEFAULT '[]',
      flags TEXT NOT NULL DEFAULT '{}',
      born_at TEXT, died_at TEXT, death_cause TEXT,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY,
      ts TEXT NOT NULL, real_ts TEXT NOT NULL,
      type TEXT NOT NULL, importance INTEGER NOT NULL DEFAULT 0,
      place TEXT, text TEXT, data TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS event_actors (event_id INTEGER, char_id TEXT, role INTEGER,
      PRIMARY KEY (event_id, char_id));
    CREATE TABLE IF NOT EXISTS event_tags (event_id INTEGER, tag TEXT, PRIMARY KEY (event_id, tag));
    CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
    CREATE INDEX IF NOT EXISTS actors_char ON event_actors(char_id);
    CREATE TABLE IF NOT EXISTS relations (a TEXT, b TEXT, affinity REAL NOT NULL, updated_at TEXT,
      PRIMARY KEY (a, b));
    """,
]


class Storage:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._dirty = False
        self._migrate()

    # ------------------------------------------------------------- esquema
    def _migrate(self) -> None:
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        version = int(self.get_meta("schema_version", "0"))
        for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
            self.conn.executescript(sql)
            self.set_meta("schema_version", str(i))
        self.conn.commit()

    @property
    def schema_version(self) -> int:
        return int(self.get_meta("schema_version", "0"))

    # ---------------------------------------------------------------- meta
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def has_world(self) -> bool:
        return self.get_meta("world_time") is not None

    # ---------------------------------------------------------- personagens
    def load_characters(self) -> dict[str, dict]:
        rows = self.conn.execute("SELECT * FROM characters").fetchall()
        out = {}
        for row in rows:
            out[row["id"]] = {
                "alive": bool(row["alive"]),
                "place": row["place"],
                "needs": json.loads(row["needs"]),
                "current": json.loads(row["current"]) if row["current"] else None,
                "last_action": row["last_action"],
                "flags": json.loads(row["flags"]),
            }
        return out

    def save_character(self, cid: str, *, alive: bool, place: str, needs: dict, current: dict | None,
                       last_action: str | None, flags: dict) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            """INSERT INTO characters (id, alive, place, needs, current, last_action, flags, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET alive=excluded.alive, place=excluded.place,
                 needs=excluded.needs, current=excluded.current, last_action=excluded.last_action,
                 flags=excluded.flags, updated_at=excluded.updated_at""",
            (cid, int(alive), place, json.dumps(needs), json.dumps(current) if current else None,
             last_action, json.dumps(flags), now),
        )

    # -------------------------------------------------------------- relações
    def load_relations(self) -> dict[tuple[str, str], float]:
        rows = self.conn.execute("SELECT a, b, affinity FROM relations").fetchall()
        return {(r["a"], r["b"]): r["affinity"] for r in rows}

    def save_relation(self, a: str, b: str, affinity: float, world_ts: str) -> None:
        self.conn.execute(
            """INSERT INTO relations (a, b, affinity, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(a, b) DO UPDATE SET affinity=excluded.affinity, updated_at=excluded.updated_at""",
            (a, b, affinity, world_ts),
        )

    # --------------------------------------------------------------- eventos
    def insert_event(self, ev: Event) -> None:
        if ev.type in NOT_PERSISTED:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO events (id, ts, real_ts, type, importance, place, text, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ev.id, ev.ts, ev.real_ts, ev.type, ev.importance, ev.place, ev.text,
             json.dumps(ev.data, ensure_ascii=False)),
        )
        for role, cid in enumerate(dict.fromkeys(ev.actors)):
            self.conn.execute("INSERT OR IGNORE INTO event_actors VALUES (?, ?, ?)", (ev.id, cid, role))
        for tag in dict.fromkeys(ev.tags):
            self.conn.execute("INSERT OR IGNORE INTO event_tags VALUES (?, ?)", (ev.id, tag))
        self._dirty = True

    def query_events(self, *, character: str | None = None, place: str | None = None, tag: str | None = None,
                     type: str | None = None, limit: int = 100, before_id: int | None = None) -> list[Event]:
        """Histórico do Chat do Mundo, mais novos primeiro (base do /api/chat da Fase 4)."""
        sql = "SELECT * FROM events e WHERE 1=1"
        args: list = []
        if character:
            sql += " AND EXISTS (SELECT 1 FROM event_actors a WHERE a.event_id = e.id AND a.char_id = ?)"
            args.append(character)
        if place:
            sql += " AND e.place = ?"
            args.append(place)
        if tag:
            sql += " AND EXISTS (SELECT 1 FROM event_tags t WHERE t.event_id = e.id AND t.tag = ?)"
            args.append(tag)
        if type:
            sql += " AND e.type = ?"
            args.append(type)
        if before_id:
            sql += " AND e.id < ?"
            args.append(before_id)
        sql += " ORDER BY e.id DESC LIMIT ?"
        args.append(limit)
        out = []
        for row in self.conn.execute(sql, args).fetchall():
            actors = [r["char_id"] for r in self.conn.execute(
                "SELECT char_id FROM event_actors WHERE event_id = ? ORDER BY role", (row["id"],))]
            tags = [r["tag"] for r in self.conn.execute("SELECT tag FROM event_tags WHERE event_id = ?", (row["id"],))]
            out.append(Event(type=row["type"], ts=row["ts"], text=row["text"] or "", actors=actors,
                             place=row["place"], tags=tags, importance=row["importance"],
                             data=json.loads(row["data"]), id=row["id"], real_ts=row["real_ts"]))
        return out

    def count_events(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    # --------------------------------------------------------------- geral
    def commit(self) -> None:
        self.conn.commit()
        self._dirty = False

    def commit_if_dirty(self) -> None:
        if self._dirty:
            self.commit()

    def close(self) -> None:
        try:
            self.conn.commit()
        finally:
            self.conn.close()
