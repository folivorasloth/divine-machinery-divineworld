"""Criaturas noturnas e as da Sala do Servidor (Fase 3).

O bestiário fica em `data/events/creatures.yaml` (chave `criaturas:`). Regras:

- **aparecer** (de hora em hora): cada criatura comum, nos `periodos` dela (à
  noite), tem `chance_por_hora` de aparecer num dos `lugares` (no máximo
  `criaturas.max_ao_mesmo_tempo` no mundo, e uma de cada tipo por vez). Fica
  `duracao_minutos` e some (ou some de manhã, quando acaba o período).
- **enquanto está lá**: o lugar fica mais perigoso (`perigo` soma ao perigo do
  lugar: os NPCs evitam ir, e quem está lá tende a sair); quem está no lugar
  ganha `medo` (na hora em que ela aparece e metade a cada hora), e sorteia a
  causa de morte `quando: criatura` do world.yaml. Quem tem a imunidade
  `criaturas` (o Mike) não sente nada.
- **enfrentar**: a ação `enfrentar` (só vale onde há criatura) termina com
  `chance_vencer` de espantar a criatura (×1.5 para as `especialistas`); se
  perder, leva um susto e sorteia a morte por criatura.
- **homelab**: criaturas com `homelab: true` não aparecem sozinhas. Quando um
  serviço real cai (`homelab/servicos/<nome>` = down, ou o comando
  `homelab <nome> down`), uma delas aparece na Sala do Servidor e chama as
  `chama_profissoes` (os Técnicos) com um objetivo de enfrentá-la. Só some
  quando o serviço volta (`up`): o problema real é que manda.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from sim.schemas import CreatureDef

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World


@dataclass
class ActiveCreature:
    uid: int
    kind: str
    place: str
    start: float  # minuto absoluto
    end: float | None  # None = só some por regra (homelab)
    service: str | None = None
    fought_by: list[str] | None = None


class Creatures:
    def __init__(self) -> None:
        self.active: list[ActiveCreature] = []
        self.next_uid = 1

    def to_json(self) -> dict:
        return {"active": [asdict(c) for c in self.active], "next_uid": self.next_uid}

    def load(self, raw: dict) -> None:
        self.active = [ActiveCreature(**c) for c in raw.get("active", [])]
        self.next_uid = int(raw.get("next_uid", 1))

    def at(self, place: str) -> list[ActiveCreature]:
        return [c for c in self.active if c.place == place]

    def danger_at(self, world: "World", place: str) -> float:
        return sum(world.data.creatures[c.kind].danger for c in self.at(place) if c.kind in world.data.creatures)


def _immune(world: "World", cid: str) -> bool:
    return "criaturas" in world.data.characters[cid].immunities


def _say(world: "World", cre: CreatureDef, which: str, place: str, actor: str | None, ac: ActiveCreature,
         event_type: str, importance: int, extra_data: dict | None = None) -> None:
    options = getattr(cre.texts, which) or cre.texts.appears
    witnesses = [c for c in world.present_at(place) if not world.is_asleep(c)]
    who = actor or (world.rng.choice(witnesses) if witnesses else None)
    if who is None:  # ninguém por perto: só textos que não precisam de {eu}
        options = [t for t in options if "{eu}" not in t] or [f"Alguma coisa estranha acontece em {{lugar}}: {cre.name}."]
    template = world.rng.choice(options)
    data = {"creature": cre.id, "instance": ac.uid, "service": ac.service, **(extra_data or {})}
    if who is None:
        # ninguém por perto: o mundo narra sozinho (sem {eu})
        from sim import text as text_mod

        txt = text_mod.fill(template, {"lugar": place, "objeto": ac.service or cre.name})
        world.emit(event_type, txt, place=place, tags=["misterio"], importance=importance, data=data)
        return
    world.event_text(who, template, event_type, place=place, tags=["misterio"], importance=importance,
                     extra={"objeto": ac.service or cre.name}, data=data)


def spawn(world: "World", kind: str, place: str | None = None, service: str | None = None,
          reason: str = "noite") -> ActiveCreature | None:
    cre = world.data.creatures.get(kind)
    if cre is None:
        return None
    state = world.creatures
    place = place or world.rng.choice(sorted(cre.places))
    now = world.now_minutes()
    end = None if cre.homelab else now + world.rng.randint(*cre.duration_minutes)
    ac = ActiveCreature(uid=state.next_uid, kind=kind, place=place, start=now, end=end, service=service)
    state.next_uid += 1
    state.active.append(ac)
    _say(world, cre, "appears", place, None, ac, "creature_spawned", cre.importance, {"reason": reason})
    _frighten(world, cre, place, cre.fear)
    for cid in world.present_at(place):
        if not _immune(world, cid) and not world.is_asleep(cid):
            world.remember(cid, world.data.world.creatures.memory, subject=None, place=place, detail=cre.name)
    if cre.goal_professions:
        for cid, st in world.states.items():
            if st.alive and world.data.characters[cid].profession in cre.goal_professions:
                world.add_goal(who=cid, action=world.data.world.creatures.fight_action, place=place,
                               bonus=cre.goal_bonus, start=now, end=now + 7 * 24 * 60,
                               source=f"criatura#{ac.uid}")
    world.refresh_blocked()
    return ac


def _frighten(world: "World", cre: CreatureDef, place: str, amount: float) -> None:
    for cid in world.present_at(place):
        if _immune(world, cid):
            continue
        st = world.states[cid]
        st.needs["medo"] = min(100.0, st.needs.get("medo", 0) + amount)


def leave(world: "World", ac: ActiveCreature, how: str = "some", by: str | None = None) -> None:
    if ac not in world.creatures.active:
        return
    world.creatures.active.remove(ac)
    world.remove_goals(f"criatura#{ac.uid}")
    cre = world.data.creatures.get(ac.kind)
    if cre is not None:
        which = "beaten" if how == "vencida" else "leaves"
        _say(world, cre, which, ac.place, by if how == "vencida" else None, ac, "creature_gone",
             2 if how == "vencida" else 1,
             {"how": how, "by": by})
    if how in ("vencida", "resolvida") and by:
        world.remember_scene(world.data.world.creatures.win_memory, subject=by, place=ac.place,
                             detail=cre.name if cre else ac.kind)
    world.refresh_blocked()


def update(world: "World") -> None:
    """A cada tick: criaturas que passaram do tempo (ou cujo período acabou) vão embora."""
    if not world.creatures.active:
        return
    now = world.now_minutes()
    period = world.clock.period()
    for ac in list(world.creatures.active):
        cre = world.data.creatures.get(ac.kind)
        if cre is None:
            world.creatures.active.remove(ac)
            continue
        if ac.end is not None and (now >= ac.end or (cre.periods and period not in cre.periods)):
            leave(world, ac)


def hourly(world: "World") -> None:
    """De hora em hora: sustos e perigo para quem está perto, e novas aparições."""
    state = world.creatures
    for ac in list(state.active):
        cre = world.data.creatures.get(ac.kind)
        if cre is None:
            continue
        _frighten(world, cre, ac.place, cre.fear / 2)
        for cid in world.present_at(ac.place):
            if not _immune(world, cid):
                if world.lifecycle_roll("criatura", cid, place=ac.place, by_creature=ac):
                    break  # uma vítima por hora já é desgraça suficiente
    limit = world.data.world.creatures.max_active
    period = world.clock.period()
    for kind in sorted(world.data.creatures):
        if len(state.active) >= limit:
            return
        cre = world.data.creatures[kind]
        if cre.homelab or cre.chance_per_hour <= 0 or any(a.kind == kind for a in state.active):
            continue
        if cre.periods and period not in cre.periods:
            continue
        if world.rng.random() < cre.chance_per_hour:
            places = [p for p in sorted(cre.places) if p not in world.blocked_places]
            if places:
                spawn(world, kind, world.rng.choice(places))


def fight(world: "World", cid: str, place: str) -> None:
    """Fim da ação `enfrentar`: espanta a criatura, ou leva a pior."""
    here = world.creatures.at(place)
    if not here:
        return
    ac = here[0]
    cre = world.data.creatures.get(ac.kind)
    if cre is None:
        return
    chance = cre.win_chance
    if world.data.characters[cid].profession in cre.experts:
        chance = min(0.95, chance * 1.5)
    if world.rng.random() < chance:
        if cre.homelab:
            # o problema é real: dá para segurar a criatura, não para sumir com ela
            world.event_text(cid, world.rng.choice(cre.texts.beaten or cre.texts.leaves), "creature_fight",
                             place=place, tags=["misterio", "trabalho"], importance=1,
                             extra={"objeto": ac.service or cre.name},
                             data={"creature": cre.id, "instance": ac.uid, "won": True, "service": ac.service})
            st = world.states[cid]
            st.needs["medo"] = max(0.0, st.needs.get("medo", 0) - 10)
            return
        leave(world, ac, "vencida", by=cid)
        return
    st = world.states[cid]
    st.needs["medo"] = min(100.0, st.needs.get("medo", 0) + 35)
    if cre.texts.attack:
        world.event_text(cid, world.rng.choice(cre.texts.attack), "creature_fight", place=place,
                         tags=["misterio"], importance=1, extra={"objeto": ac.service or cre.name},
                         data={"creature": cre.id, "instance": ac.uid, "won": False})
    world.lifecycle_roll("criatura", cid, place=place, by_creature=ac, factor=3.0)


def homelab(world: "World", service: str, status: str) -> None:
    """Um serviço real do homelab mudou de estado (down/degraded/up)."""
    status = status.lower().strip()
    current = [a for a in world.creatures.active if a.service == service]
    if status in ("down", "degraded", "offline", "erro", "error"):
        if current:
            return
        kinds = sorted(k for k, c in world.data.creatures.items() if c.homelab)
        if not kinds:
            return
        spawn(world, world.rng.choice(kinds), service=service, reason="homelab")
    elif status in ("up", "ok", "online"):
        for ac in current:
            cre = world.data.creatures.get(ac.kind)
            profs = cre.goal_professions if cre else []
            fixer = next((c for c in world.present_at(ac.place) if world.data.characters[c].profession in profs), None)
            leave(world, ac, "resolvida" if fixer else "some", by=fixer)
