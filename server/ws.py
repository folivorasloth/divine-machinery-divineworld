"""WebSocket: o contrato com o viewer (seção 13.3 de docs/arquitetura.md).

- `/ws?screen=<id>`: ao conectar, `hello` com o estado inicial dos lugares
  daquela tela; depois, só o que interessa a ela (eventos dos lugares dela,
  movimento, falas como balões, clima, hora, névoa, teletransporte, Aparição).
- `/ws/chat`: todos os eventos (a página do Chat do Mundo).

O `Hub.on_event` é assinante do EventBus e roda no thread da SIMULAÇÃO: ele
só monta as mensagens (rápido) e entrega ao asyncio do servidor com
`loop.call_soon_threadsafe`. Cada cliente tem uma fila; cliente lento perde
mensagens (a fila tem limite), mas nunca segura o mundo.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from server.runtime import Runtime
    from sim.events import Event

log = logging.getLogger("server.ws")

PROTOCOL = 1
HIDDEN = {"decision", "tension"}  # nunca vão para as telas nem para o chat ao vivo
QUEUE_MAX = 2000
CHARACTER_EVENTS = {"action_started", "bell", "move_arrived", "teleport_finished", "death", "birth", "resurrection",
                    "arrest", "released", "limbo_in", "limbo_out", "fight", "argument", "reconcile", "prank",
                    "slapstick", "chase", "ritual", "theft", "stare"}


@dataclass(eq=False)
class Client:
    screen: str | None  # None = Chat do Mundo (tudo)
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE_MAX))
    dropped: int = 0


class Hub:
    def __init__(self, runtime: "Runtime"):
        self.runtime = runtime
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: set[Client] = set()
        data = runtime.data
        self.screen_places = {s.id: set(s.places) for s in data.world.screens}

    # --------------------------------------------------------- clientes
    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def add(self, screen: str | None) -> Client:
        c = Client(screen=screen)
        self.clients.add(c)
        return c

    def remove(self, c: Client) -> None:
        self.clients.discard(c)

    def _deliver(self, items: list[tuple[Client, dict]]) -> None:
        for client, msg in items:
            if client not in self.clients:
                continue
            try:
                client.queue.put_nowait(msg)
            except asyncio.QueueFull:
                client.dropped += 1

    def broadcast(self, msg: dict, screens_only: bool = False) -> None:
        """Do thread do asyncio (ou de qualquer um): manda para todos."""
        items = [(c, msg) for c in list(self.clients) if not (screens_only and c.screen is None)]
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._deliver, items)

    # ------------------------------------------------- do thread do mundo
    def on_event(self, ev: "Event") -> None:
        if self.loop is None or not self.clients or ev.type in HIDDEN:
            return
        world = self.runtime.world
        evd = ev.to_dict(world.names())
        items: list[tuple[Client, dict]] = []
        derived_cache: dict[str, list[dict]] = {}
        for c in list(self.clients):
            if c.screen is None:
                items.append((c, {"type": "event", "event": evd}))
                continue
            if c.screen not in derived_cache:
                derived_cache[c.screen] = self.screen_messages(c.screen, ev, evd)
            items += [(c, m) for m in derived_cache[c.screen]]
        if items:
            self.loop.call_soon_threadsafe(self._deliver, items)

    def _relevant(self, screen: str, ev: "Event") -> bool:
        places = self.screen_places.get(screen, set())
        if ev.place is None:
            return True  # global (sistema, período, clima)
        d = ev.data
        where = {ev.place, d.get("from"), d.get("to"), d.get("from_place"), d.get("to_place")}
        if ev.type == "apparition":
            return True
        return bool(places & where)

    def screen_messages(self, screen: str, ev: "Event", evd: dict) -> list[dict]:
        """Um evento do mundo -> mensagens para a tela `screen` (contrato do viewer)."""
        if not self._relevant(screen, ev):
            return []
        world = self.runtime.world
        places = self.screen_places.get(screen, set())
        d = ev.data
        out: list[dict] = [{"type": "event", "event": evd}]
        actor = ev.actors[0] if ev.actors else None
        if ev.type == "speech" and actor:
            out.append({"type": "bubble", "id": actor, "place": ev.place, "text": evd["text_rendered"],
                        "duration_s": 4})
        elif ev.type == "move_started" and d.get("from") in places and d.get("to") in places:
            out.append({"type": "move", "id": actor, "from": d.get("from"), "to": d.get("to"),
                        "duration_s": round(d.get("minutes", 1) * 60 / max(world.speed, 0.001), 2)})
        elif ev.type in ("teleport_started", "teleport_finished"):
            if screen in (d.get("from_screen"), d.get("to_screen")):
                out.append({"type": "teleport", "phase": "start" if ev.type == "teleport_started" else "end",
                            "id": actor, "from_place": d.get("from_place"), "to_place": d.get("to_place"),
                            "from_screen": d.get("from_screen"), "to_screen": d.get("to_screen"),
                            "duration_s": d.get("duration_s")})
        elif ev.type in ("fog_on", "fog_off"):
            out.append({"type": "fog", "place": ev.place, "on": ev.type == "fog_on"})
        elif ev.type == "weather_changed":
            out.append({"type": "weather", "label": world.weather.label, "kind": world.weather.kind,
                        "forced": world.weather.now.forced})
        elif ev.type == "period_changed":
            out.append(self.clock_message())
        elif ev.type == "apparition":
            out.append({"type": "apparition", "screen": d.get("screen"), "places": d.get("places", []),
                        "duration_s": d.get("duration_s", 4)})
        if ev.type in CHARACTER_EVENTS:
            for cid in (ev.actors if ev.type == "stare" else ev.actors[:2]):
                msg = self.character_message(cid)
                if msg is not None:
                    out.append(msg)
        return out

    # ------------------------------------------------------- mensagens
    def clock_message(self) -> dict:
        snap = self.runtime.snapshot()
        return {"type": "clock", "ts": snap.get("ts"), "period": snap.get("period"),
                "is_night": snap.get("is_night"), "speed": snap.get("speed"), "paused": snap.get("paused")}

    def character_message(self, cid: str) -> dict | None:
        world = self.runtime.world
        if cid not in world.states or cid not in world.data.characters:
            return None
        st = world.states[cid]
        char = world.data.characters[cid]
        return {"type": "character", "id": cid, "name": char.name, "place": st.place, "alive": st.alive,
                "action": st.activity.action if st.activity else None, "moving": st.moving,
                "visual": char.visual.model_dump() if char.visual else None}

    def hello(self, screen: str | None) -> dict:
        """Estado inicial para uma tela (ou para o chat). Lê só o snapshot e os dados (somente leitura)."""
        rt = self.runtime
        snap = rt.snapshot()
        data = rt.data
        names = snap.get("names") or {}
        fog = set(snap.get("fog", []))
        screens = [{"id": s.id, "name": s.name, "places": list(s.places),
                    "position_cm": {"x": s.position_cm.x, "y": s.position_cm.y},
                    "size_cm": {"width": s.size_cm.width, "height": s.size_cm.height}}
                   for s in data.world.screens]
        wanted = self.screen_places.get(screen) if screen else set(data.places)
        structures = snap.get("structures", {})
        places = []
        for pid in sorted(wanted or []):
            p = data.places[pid]
            places.append({"id": pid, "name": names.get(pid, p.name), "palette": p.palette.model_dump(),
                           "sinister": p.sinister, "environment": p.environment, "fog": pid in fog,
                           "connections": [{"to": c.to, "kind": c.kind, "minutes": c.minutes} for c in p.connections],
                           "structures": [{"id": sid, "name": names.get(sid, sid), **s}
                                          for sid, s in structures.items() if s["place"] == pid]})
        chars = []
        for cid, c in (snap.get("characters") or {}).items():
            if not c["alive"] or (wanted is not None and c["place"] not in wanted):
                continue
            char = data.characters.get(cid)
            chars.append({"id": cid, "name": names.get(cid, cid), "place": c["place"], "action": c["action"],
                          "moving": c["moving"], "visual": char.visual.model_dump() if char and char.visual else None})
        return {"type": "hello", "screen": screen, "protocol": PROTOCOL,
                "world": {"ts": snap.get("ts"), "period": snap.get("period"), "is_night": snap.get("is_night"),
                          "speed": snap.get("speed"), "paused": snap.get("paused"), "weather": snap.get("weather"),
                          "tension": snap.get("tension"), "population": snap.get("population")},
                "screens": screens, "places": places, "characters": chars}
