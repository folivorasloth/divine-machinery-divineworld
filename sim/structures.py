"""Construções e objetos com estado (seção 11 de docs/arquitetura.md).

Cada lugar pode ter `estruturas` no YAML (ex.: a bigorna da Ferraria, os muros
das Casas). Cada uma tem resistência 0..100:

    inteiro     resistência >= estruturas.danificado_abaixo (70)
    danificado  entre 0 e isso
    destruido   0

Brigas, `quebrar`, pichações e acidentes tiram resistência; `construir`
(ação com `conserta`) devolve. O que é destruído só volta se alguém quiser
consertar (ou se o Chefe mandar). Pichação deixa uma "assinatura" (`marks`):
o Fiscal que passar pelo lugar descobre quem foi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sim.loader import WorldData


@dataclass
class Structure:
    id: str
    place: str
    hp: float = 100.0
    # assinaturas deixadas (pichação): [[quem, infração], ...]
    marks: list[list[str]] = field(default_factory=list)


def state_of(hp: float, damaged_below: float) -> str:
    if hp <= 0:
        return "destruido"
    if hp < damaged_below:
        return "danificado"
    return "inteiro"


STATE_NAMES = {"inteiro": "inteiro", "danificado": "danificado", "destruido": "destruído"}


class Structures:
    def __init__(self, data: WorldData):
        self.data = data
        self.items: dict[str, Structure] = {}
        for pid, place in data.places.items():
            for sdef in place.structures:
                self.items[sdef.id] = Structure(id=sdef.id, place=pid)

    @property
    def damaged_below(self) -> float:
        return self.data.world.structures.damaged_below

    def at(self, place: str) -> list[Structure]:
        return [s for s in self.items.values() if s.place == place]

    def state(self, sid: str) -> str:
        return state_of(self.items[sid].hp, self.damaged_below)

    def damage_at(self, place: str) -> float:
        """Quanto o lugar está estragado: 100 - a menor resistência (0 = tudo inteiro)."""
        here = self.at(place)
        return max((100 - s.hp for s in here), default=0.0)

    def worst(self) -> tuple[str | None, float]:
        """(lugar, dano) do pior estrago do mundo."""
        best_place, best = None, 0.0
        for s in self.items.values():
            if 100 - s.hp > best:
                best_place, best = s.place, 100 - s.hp
        return best_place, best

    def change(self, sid: str, delta: float) -> tuple[str, str]:
        """Muda a resistência; devolve (estado_antes, estado_depois)."""
        s = self.items[sid]
        before = self.state(sid)
        s.hp = max(0.0, min(100.0, s.hp + delta))
        return before, self.state(sid)

    # --------------------------------------------------------- persistência
    def rows(self) -> list[dict]:
        return [asdict(s) for s in self.items.values()]

    def load(self, rows: list[dict]) -> None:
        for row in rows:
            if row["id"] in self.items:  # estrutura que saiu do YAML é ignorada
                s = self.items[row["id"]]
                s.hp = row["hp"]
                s.marks = row.get("marks", [])
