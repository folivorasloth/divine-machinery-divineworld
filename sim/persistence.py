"""Persistência em SQLite (seção 10 de docs/arquitetura.md).

- `meta`: versão do esquema, hora do mundo, seed, estado do RNG, velocidade...
- `characters`: estado vivo de cada personagem, POR ID (o nome nunca é salvo).
- `events` (+ `event_actors`, `event_tags`): o Chat do Mundo inteiro.
- `relations`: afinidade viva por par (só os pares que mudaram desde o YAML).
- `memories` (F2): memórias de cada NPC (uma linha por memória, campos em JSON).
- `structures` (F2): resistência e assinaturas (pichações) de cada estrutura.
- O resto do estado da sociedade (leis, eventos sociais, objetivos, objetos
  roubados, visitantes recentes) vai em `meta.society` (JSON).

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
    # versão 2 (Fase 2: sociedade)
    """
    CREATE TABLE IF NOT EXISTS memories (
      id INTEGER PRIMARY KEY,
      owner TEXT NOT NULL,
      kind TEXT NOT NULL,
      data TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS memories_owner ON memories(owner);
    CREATE TABLE IF NOT EXISTS structures (
      id TEXT PRIMARY KEY,
      place TEXT NOT NULL,
      hp REAL NOT NULL,
      data TEXT NOT NULL DEFAULT '{}',
      updated_at TEXT
    );
    """,
    # versão 3 (Fase 3: vida, morte, diretor, clima)
    """
    CREATE TABLE IF NOT EXISTS graves (
      char_id TEXT PRIMARY KEY,
      born_ts TEXT, died_ts TEXT, cause TEXT, epitaph TEXT,
      data TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS director_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT, tension REAL, chosen TEXT, reason TEXT
    );
    CREATE TABLE IF NOT EXISTS weather_log (
      ts TEXT PRIMARY KEY, kind TEXT, label TEXT, temp REAL, source TEXT, forced TEXT
    );
    """,
]


class Storage:
    @classmethod
    def reader(cls, path: str | Path) -> "Storage":
        """Conexão só de leitura (Fase 4: a API lê o Chat do Mundo enquanto a simulação
        escreve; o WAL do SQLite deixa ler sem travar quem escreve). Não migra nada."""
        self = cls.__new__(cls)
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA query_only=1")
        self._dirty = False
        return self

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
                "extra_traits": json.loads(row["extra_traits"] or "[]"),
            }
        return out

    def save_character(self, cid: str, *, alive: bool, place: str, needs: dict, current: dict | None,
                       last_action: str | None, flags: dict, extra_traits: list[str] | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            """INSERT INTO characters (id, alive, place, needs, current, last_action, flags, extra_traits, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET alive=excluded.alive, place=excluded.place,
                 needs=excluded.needs, current=excluded.current, last_action=excluded.last_action,
                 flags=excluded.flags, extra_traits=excluded.extra_traits, updated_at=excluded.updated_at""",
            (cid, int(alive), place, json.dumps(needs), json.dumps(current) if current else None,
             last_action, json.dumps(flags), json.dumps(extra_traits or []), now),
        )

    # ------------------------------------------------------- memórias (F2)
    def save_memories(self, rows: list[dict]) -> None:
        """Regrava todas as memórias (são poucas: ~40 por NPC)."""
        self.conn.execute("DELETE FROM memories")
        self.conn.executemany(
            "INSERT INTO memories (id, owner, kind, data) VALUES (?, ?, ?, ?)",
            [(r["id"], r["owner"], r["kind"], json.dumps(r, ensure_ascii=False)) for r in rows],
        )

    def load_memories(self) -> list[dict]:
        return [json.loads(r["data"]) for r in self.conn.execute("SELECT data FROM memories ORDER BY id")]

    # ----------------------------------------------------- estruturas (F2)
    def save_structures(self, rows: list[dict], world_ts: str) -> None:
        for r in rows:
            self.conn.execute(
                """INSERT INTO structures (id, place, hp, data, updated_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET place=excluded.place, hp=excluded.hp, data=excluded.data,
                     updated_at=excluded.updated_at""",
                (r["id"], r["place"], r["hp"], json.dumps({"marks": r.get("marks", [])}), world_ts),
            )

    def load_structures(self) -> list[dict]:
        out = []
        for r in self.conn.execute("SELECT * FROM structures ORDER BY id"):
            out.append({"id": r["id"], "place": r["place"], "hp": r["hp"], **json.loads(r["data"])})
        return out

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
                     type: str | None = None, limit: int = 100, before_id: int | None = None,
                     after_id: int | None = None, since: str | None = None, until: str | None = None,
                     min_importance: int | None = None, exclude_types: tuple[str, ...] = ()) -> list[Event]:
        """Histórico do Chat do Mundo, mais novos primeiro (base do /api/chat da Fase 4).

        `type` aceita vários separados por vírgula; `since`/`until` são horas do MUNDO
        (ISO, comparadas como texto: o fuso é sempre o do world.yaml)."""
        sql = "SELECT * FROM events e WHERE 1=1"
        args: list = []
        if after_id:
            sql += " AND e.id > ?"
            args.append(after_id)
        if since:
            sql += " AND e.ts >= ?"
            args.append(since)
        if until:
            sql += " AND e.ts <= ?"
            args.append(until)
        if min_importance:
            sql += " AND e.importance >= ?"
            args.append(min_importance)
        for t in exclude_types:
            sql += " AND e.type != ?"
            args.append(t)
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
            types = [t.strip() for t in type.split(",") if t.strip()]
            sql += " AND e.type IN (" + ",".join("?" * len(types)) + ")"
            args += types
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

    # ------------------------------------------------------ vida e morte (F3)
    def save_graves(self, graves: list[dict]) -> None:
        """Lápides (uma por morto; a mais recente vale, se alguém morreu duas vezes)."""
        for g in graves:
            self.conn.execute(
                """INSERT INTO graves (char_id, born_ts, died_ts, cause, epitaph, data) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(char_id) DO UPDATE SET born_ts=excluded.born_ts, died_ts=excluded.died_ts,
                     cause=excluded.cause, epitaph=excluded.epitaph, data=excluded.data""",
                (g["cid"], g["born"], g["died"], g["cause"], g.get("epitaph", ""),
                 json.dumps({"cause_name": g.get("cause_name"), "resurrected": g.get("resurrected", False)},
                            ensure_ascii=False)),
            )

    def load_graves(self) -> list[dict]:
        out = []
        for r in self.conn.execute("SELECT * FROM graves ORDER BY died_ts"):
            extra = json.loads(r["data"] or "{}")
            out.append({"cid": r["char_id"], "born": r["born_ts"], "died": r["died_ts"], "cause": r["cause"],
                        "epitaph": r["epitaph"] or "", **extra})
        return out

    def log_director(self, entry: dict) -> None:
        self.conn.execute("INSERT INTO director_log (ts, tension, chosen, reason) VALUES (?, ?, ?, ?)",
                          (entry["ts"], entry["tension"], entry["chosen"], entry["reason"]))
        self._dirty = True

    def log_weather(self, ts: str, kind: str, label: str, temp, source: str, forced) -> None:
        self.conn.execute("INSERT OR REPLACE INTO weather_log (ts, kind, label, temp, source, forced) "
                          "VALUES (?, ?, ?, ?, ?, ?)", (ts, kind, label, temp, source, forced))
        self._dirty = True

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
