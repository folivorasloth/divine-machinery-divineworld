"""API HTTP + WebSocket (FastAPI) — seção 13.2/13.3 de docs/arquitetura.md.

    GET  /api/state                 hora, período, clima, tensão, população, pausado
    GET  /api/characters            lista (id, nome, lugar, ação, vivo)
    GET  /api/characters/{id}       ficha viva (igual ao comando `quem`)
    GET  /api/places                lugares + quem está lá + névoa + tela + estruturas
    GET  /api/screens               telas do world.yaml
    GET  /api/chat?character=&place=&tag=&type=&since=&until=&min_importance=&limit=&before_id=&after_id=
    GET  /api/timeline?min_importance=2&limit=50     grandes acontecimentos
    GET  /api/meta                  o que os filtros do Chat precisam (nomes, lugares, categorias, tipos)
    POST /api/commands              {"cmd": "chefe", "arg": "reconstruam a ferraria"} -> 202
    GET  /api/commands[/{id}]       comandos recentes e o resultado de cada um
    GET  /health                    a simulação está viva?
    GET  /chat                      a página do Chat do Mundo (viewer/chat.html)
    WS   /ws?screen=<id>            telas;  WS /ws/chat: Chat do Mundo ao vivo

A API nunca mexe no estado vivo: lê o snapshot (cópia sob lock), lê o SQLite
numa conexão só de leitura e manda comandos pela fila do mundo.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.runtime import Runtime
from sim.commands import CREATOR_COMMANDS
from sim.events import EVENT_TYPES

log = logging.getLogger("server.app")

VIEWER_DIR = Path(__file__).resolve().parent.parent / "viewer"
READ_COMMANDS = {"status", "quem"}
WAIT_SECONDS = 5.0


class CommandIn(BaseModel):
    cmd: str
    arg: str = ""
    id: str | None = None


def _event_json(ev, names: dict) -> dict:
    return ev.to_dict(names)


def create_app(runtime: Runtime | None = None, runtime_factory=None, start: bool = True) -> FastAPI:
    """`runtime` pronto (testes) ou `runtime_factory()` chamado ao subir (python -m server)."""
    holder: dict = {"rt": runtime}

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        rt = holder["rt"] or runtime_factory()
        holder["rt"] = rt
        rt.hub.attach_loop(asyncio.get_running_loop())
        if start and not rt.alive:
            rt.start()
        ticker = asyncio.create_task(_clock_loop(rt))
        try:
            yield
        finally:
            ticker.cancel()
            if start:
                await asyncio.to_thread(rt.stop)

    app = FastAPI(title="Divine Machinery — o Mundo Vivo", version="0.4", lifespan=lifespan)

    def rt() -> Runtime:
        r = holder["rt"]
        if r is None:  # pragma: no cover
            raise HTTPException(503, "o mundo ainda está acordando")
        return r

    async def wait(fut, seconds: float = WAIT_SECONDS):
        try:
            return await asyncio.wait_for(asyncio.wrap_future(fut), seconds)
        except asyncio.TimeoutError:
            return None

    # ------------------------------------------------------------- estado
    @app.get("/health")
    def health():
        r = rt()
        snap = r.snapshot()
        return {"ok": r.alive and r.error is None, "simulating": r.alive, "ticks": snap.get("ticks"),
                "ts": snap.get("ts"), "error": repr(r.error) if r.error else None,
                "mqtt": r.mqtt.summary() if r.mqtt else {"ativo": False},
                "llm": r.world.llm.summary() if r.world.llm else {"ativo": False}}

    @app.get("/api/state")
    def state():
        snap = rt().snapshot()
        names = snap.get("names") or {}
        chars = snap.get("characters") or {}
        return {"ts": snap.get("ts"), "period": snap.get("period"), "is_night": snap.get("is_night"),
                "speed": snap.get("speed"), "paused": snap.get("paused"), "weather": snap.get("weather"),
                "tension": snap.get("tension"), "population": snap.get("population"),
                "fog": snap.get("fog", []), "creatures": snap.get("creatures", []),
                "dead": sorted(names.get(c, c) for c, v in chars.items() if not v["alive"]),
                "seed": snap.get("seed"), "ticks": snap.get("ticks")}

    @app.get("/api/characters")
    def characters():
        r = rt()
        snap = r.snapshot()
        names = snap.get("names") or {}
        out = []
        for cid, c in sorted((snap.get("characters") or {}).items()):
            char = r.data.characters.get(cid)
            out.append({"id": cid, "name": names.get(cid, cid), "place": c["place"],
                        "place_name": names.get(c["place"], c["place"]), "action": c["action"], "alive": c["alive"],
                        "moving": c["moving"], "jailed": c["jailed"], "away": c["away"], "faction": c["faction"],
                        "profession": char.profession if char else None})
        return out

    @app.get("/api/characters/{cid}")
    async def character(cid: str):
        r = rt()
        if cid not in (r.snapshot().get("characters") or {}):
            raise HTTPException(404, f"personagem '{cid}' não existe")
        res = await wait(r.command("quem", cid))
        if res is None:
            raise HTTPException(504, "a simulação não respondeu a tempo")
        return res.get("sheet", res)

    @app.get("/api/places")
    def places():
        r = rt()
        snap = r.snapshot()
        names = snap.get("names") or {}
        fog = set(snap.get("fog", []))
        who: dict[str, list[str]] = {}
        for cid, c in (snap.get("characters") or {}).items():
            if c["alive"] and not c["away"]:
                who.setdefault(c["place"], []).append(cid)
        out = []
        for pid, p in r.data.places.items():
            out.append({"id": pid, "name": names.get(pid, p.name), "screen": r.data.screen_of(pid),
                        "fog": pid in fog, "sinister": p.sinister, "environment": p.environment,
                        "people": sorted(who.get(pid, [])),
                        "structures": [{"id": sid, "name": names.get(sid, sid), **s}
                                       for sid, s in (snap.get("structures") or {}).items() if s["place"] == pid]})
        return out

    @app.get("/api/screens")
    def screens():
        r = rt()
        fog = set(r.snapshot().get("fog", []))
        return [{"id": s.id, "name": s.name, "places": list(s.places),
                 "position_cm": {"x": s.position_cm.x, "y": s.position_cm.y},
                 "size_cm": {"width": s.size_cm.width, "height": s.size_cm.height},
                 "offline": bool(set(s.places) & fog) and set(s.places) <= fog}
                for s in r.data.world.screens]

    @app.get("/api/meta")
    def meta():
        r = rt()
        names = r.names()
        return {"name": r.data.world.name,
                "characters": [{"id": c, "name": names.get(c, c)} for c in sorted(r.world.states)],
                "places": [{"id": p, "name": names.get(p, pl.name)} for p, pl in sorted(r.data.places.items())],
                "categories": [{"id": k, "name": v.name} for k, v in r.data.world.chat_categories.items()],
                "types": sorted(EVENT_TYPES - {"decision"}),
                "commands": list(r.world.COMMANDS)}

    # --------------------------------------------------------------- chat
    @app.get("/api/chat")
    def chat(character: str | None = None, place: str | None = None, tag: str | None = None,
             type: str | None = None, since: str | None = None, until: str | None = None,
             min_importance: int | None = None, limit: int = Query(100, ge=1, le=1000),
             before_id: int | None = None, after_id: int | None = None, include_moves: bool = False):
        r = rt()
        exclude = ("tension",) if include_moves else ("tension", "move_started", "move_arrived")
        reader = r.reader()
        try:
            events = reader.query_events(character=character, place=place, tag=tag, type=type, since=since,
                                         until=until, min_importance=min_importance, limit=limit,
                                         before_id=before_id, after_id=after_id, exclude_types=exclude)
        finally:
            reader.conn.close()
        names = r.names()
        return {"events": [_event_json(e, names) for e in events], "count": len(events)}

    @app.get("/api/timeline")
    def timeline(min_importance: int = Query(2, ge=0, le=3), limit: int = Query(50, ge=1, le=500),
                 before_id: int | None = None):
        r = rt()
        reader = r.reader()
        try:
            events = reader.query_events(min_importance=min_importance, limit=limit, before_id=before_id,
                                         exclude_types=("tension", "speech", "action_finished"))
        finally:
            reader.conn.close()
        names = r.names()
        return {"events": [_event_json(e, names) for e in events]}

    # ----------------------------------------------------------- comandos
    @app.post("/api/commands", status_code=202)
    async def post_command(body: CommandIn):
        r = rt()
        known = set(r.world.COMMANDS)
        if body.cmd not in known:
            raise HTTPException(400, f"comando desconhecido '{body.cmd}'. Comandos: {', '.join(sorted(known))}")
        cid = body.id or uuid.uuid4().hex[:10]
        fut = r.command(body.cmd, body.arg, cid)
        res = await wait(fut, WAIT_SECONDS if body.cmd in READ_COMMANDS else 2.0)
        payload = {"id": cid, "cmd": body.cmd, "arg": body.arg,
                   "status": "feito" if res is not None else "na_fila", "result": res}
        return JSONResponse(payload, status_code=202)

    @app.get("/api/commands")
    def commands_log():
        return list(rt().world.command_log)[-50:][::-1]

    @app.get("/api/commands/{cid}")
    def command_result(cid: str):
        for entry in reversed(list(rt().world.command_log)):
            if entry["id"] == cid:
                return entry
        raise HTTPException(404, "comando não encontrado (ainda na fila, ou muito antigo)")

    # ---------------------------------------------------------- páginas
    @app.get("/")
    def root():
        return RedirectResponse("/chat")

    @app.get("/chat")
    def chat_page():
        return FileResponse(VIEWER_DIR / "chat.html", media_type="text/html")

    if VIEWER_DIR.is_dir():
        app.mount("/viewer", StaticFiles(directory=VIEWER_DIR, html=True), name="viewer")

    # ---------------------------------------------------------- WebSocket
    async def pump(ws: WebSocket, screen: str | None):
        r = rt()
        client = r.hub.add(screen)
        try:
            await ws.send_json(r.hub.hello(screen))

            async def reader():
                while True:
                    msg = await ws.receive_json()
                    kind = msg.get("type") if isinstance(msg, dict) else None
                    if kind == "ping":
                        await client.queue.put({"type": "pong"})
                    elif kind == "resync":
                        await client.queue.put(r.hub.hello(screen))

            task = asyncio.create_task(reader())
            try:
                while True:
                    get = asyncio.create_task(client.queue.get())
                    done, _pending = await asyncio.wait({get, task}, return_when=asyncio.FIRST_COMPLETED)
                    if task in done:
                        get.cancel()
                        task.result()  # levanta a desconexão
                        break
                    await ws.send_json(get.result())
            finally:
                task.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            r.hub.remove(client)

    @app.websocket("/ws")
    async def ws_screen(ws: WebSocket, screen: str | None = None):
        await ws.accept()
        r = rt()
        if screen is not None and screen not in r.hub.screen_places:
            await ws.send_json({"type": "error", "message": f"tela '{screen}' não existe",
                                "screens": sorted(r.hub.screen_places)})
            await ws.close()
            return
        await pump(ws, screen)

    @app.websocket("/ws/chat")
    async def ws_chat(ws: WebSocket):
        await ws.accept()
        await pump(ws, None)

    return app


async def _clock_loop(rt: Runtime) -> None:
    """A cada 5 s reais, a hora do mundo para as telas (dia/noite)."""
    while True:
        await asyncio.sleep(5)
        if rt.hub.clients:
            rt.hub.broadcast(rt.hub.clock_message(), screens_only=True)
