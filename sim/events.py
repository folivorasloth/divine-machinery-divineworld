"""Eventos do mundo e o barramento (EventBus).

Tudo que acontece vira um `Event` (formato na seção 8 de docs/arquitetura.md),
publicado no `EventBus`. Os assinantes (SQLite, terminal, e na Fase 4 o
WebSocket e o MQTT) rodam no thread da simulação e precisam ser rápidos.

`text` guarda tokens de id (`{@clown}`); o nome atual só entra na saída
(`to_dict(names)` -> `text_rendered`). Assim renomear muda até o histórico.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sim import text as text_mod

log = logging.getLogger(__name__)

# Tipos da Fase 1 (as próximas fases acrescentam; ver arquitetura, seção 8)
EVENT_TYPES = {
    "system",
    "period_changed",
    "decision",  # só debug: não vai para o SQLite nem para o MQTT
    "action_started",
    "action_finished",
    "speech",
    "move_started",
    "move_arrived",
    "teleport_started",
    "teleport_finished",
    "bell",
}
# Fase 3 (lista completa na seção 8 de docs/arquitetura.md)
EVENT_TYPES |= {
    "death", "grief", "inheritance", "funeral_planned", "funeral_started", "funeral_procession", "funeral_ended",
    "grave", "death_consequence", "ghost", "resurrection", "birth", "succession", "election",
    "creature_spawned", "creature_gone", "creature_fight", "weather_changed", "fog_on", "fog_off",
    "director_event", "tension",
}
# Fase 4: o Criador (comandos, ordens do Chefe, vozes da Médium), o olhar e a Aparição
EVENT_TYPES |= {"creator_command", "creator_order", "creator_voice", "stare", "apparition"}

# tipos que não são gravados no banco (muito volume, só para depuração)
NOT_PERSISTED = {"decision"}


@dataclass
class Event:
    type: str
    ts: str  # tempo do MUNDO (ISO com fuso)
    text: str = ""
    actors: list[str] = field(default_factory=list)  # actors[0] = quem faz
    place: str | None = None
    tags: list[str] = field(default_factory=list)
    importance: int = 0
    data: dict = field(default_factory=dict)
    id: int = 0
    real_ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def render(self, names: Mapping[str, str]) -> str:
        return text_mod.render(self.text, names)

    def to_dict(self, names: Mapping[str, str] | None = None) -> dict:
        out = {
            "id": self.id,
            "ts": self.ts,
            "real_ts": self.real_ts,
            "type": self.type,
            "tags": list(self.tags),
            "importance": self.importance,
            "actors": list(self.actors),
            "place": self.place,
            "text": self.text,
            "data": dict(self.data),
        }
        if names is not None:
            out["text_rendered"] = self.render(names)
        return out


Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> None:
        self._subscribers.append(fn)

    def unsubscribe(self, fn: Subscriber) -> None:
        if fn in self._subscribers:
            self._subscribers.remove(fn)

    def publish(self, event: Event) -> None:
        for fn in list(self._subscribers):
            try:
                fn(event)
            except Exception:  # um assinante quebrado não pode parar o mundo
                log.exception("assinante do EventBus falhou com o evento %s", event.type)
