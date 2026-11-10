"""Eventos sociais organizados pelos NPCs (festa, rave, rodeio, casamento,
procissão, mutirão). Os tipos ficam em `data/events/*.yaml > eventos_sociais`.

Ciclo de vida (nada é roteirizado: quem organiza, quando, onde, quem vai e se
dá certo saem das necessidades, traços e afinidades):

1. **ideia** (de hora em hora): para cada tipo sem evento em andamento e fora
   do cooldown, cada NPC que bate com `organizadores` e tem as `vontade` altas
   tem `chance_por_hora` de tomar a iniciativa;
2. **planejado**: marca o lugar e a hora (`antecedencia_horas`, dentro de
   `comeca_entre`) e convida os `max_convidados` de quem gosta mais
   (afinidade >= `convite_afinidade_min`). Cada convidado ganha um objetivo:
   a nota da `acao` naquele lugar e hora é multiplicada por `bonus`;
3. **na hora**: se houver `quorum` pessoas no lugar, começa; se não houver
   até 45 minutos depois, **fracassa** (memória `memoria_fracasso` para quem
   organizou);
4. **termina** depois de `duracao_horas`: quem participou ganha a memória
   `memoria` e gosta um pouco mais de quem organizou. Casamento: os dois
   viram cônjuges.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from sim.schemas import SocialEventDef

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World

TOLERANCE_MINUTES = 45  # quanto tempo o organizador espera o quórum
ARRIVE_BEFORE_MINUTES = 30  # o objetivo começa um pouco antes (para dar tempo de chegar)


@dataclass
class SocialInstance:
    id: int
    kind: str
    organizer: str
    place: str
    start: float  # minuto absoluto do mundo
    end: float
    guests: list[str] = field(default_factory=list)
    partner: str | None = None
    status: str = "planejado"  # planejado | acontecendo | terminado | fracassado
    participants: list[str] = field(default_factory=list)


class SocialEvents:
    def __init__(self) -> None:
        self.instances: list[SocialInstance] = []
        self.cooldown_until: dict[str, float] = {}
        self.next_id = 1

    def active(self) -> list[SocialInstance]:
        return [i for i in self.instances if i.status in ("planejado", "acontecendo")]

    def to_json(self) -> dict:
        return {"instances": [asdict(i) for i in self.active()], "cooldown_until": self.cooldown_until,
                "next_id": self.next_id}

    def load(self, raw: dict) -> None:
        self.instances = [SocialInstance(**i) for i in raw.get("instances", [])]
        self.cooldown_until = dict(raw.get("cooldown_until", {}))
        self.next_id = int(raw.get("next_id", 1))


# ------------------------------------------------------------------ ideia
def _can_organize(world: "World", sev: SocialEventDef, cid: str) -> bool:
    char = world.data.characters[cid]
    st = world.states[cid]
    if not st.alive or st.frozen or st.away or st.jailed_until is not None:
        return False
    if cid in sev.excluded:
        return False
    rule = sev.organizers
    ok = (cid in rule.characters or bool(set(rule.traits) & set(world.traits_of(cid)))
          or char.profession in rule.professions or (char.group in rule.groups if char.group else False)
          or (st.faction in rule.factions if st.faction else False))
    if not ok:
        return False
    return all(st.needs.get(n, 0) >= v for n, v in sev.desire.items())


def _partner(world: "World", sev: SocialEventDef, cid: str) -> str | None:
    if sev.partner_affinity_min is None:
        return None
    best, value = None, sev.partner_affinity_min
    for other in sorted(world.states):
        o = world.states[other]
        if other == cid or not o.alive or o.away or o.spouse or world.states[cid].spouse or other in sev.excluded:
            continue
        kinds = {r.kind for r in world.data.characters[cid].relations if r.with_ == other}
        kinds |= {r.kind for r in world.data.characters[other].relations if r.with_ == cid}
        if kinds & set(sev.partner_forbidden_kinds):
            continue
        mutual = min(world.affinity(cid, other), world.affinity(other, cid))
        if mutual >= value:
            best, value = other, mutual
    return best


def _next_start(world: "World", sev: SocialEventDef, earliest: float) -> float | None:
    """Primeiro minuto >= earliest dentro de `comeca_entre` (no máximo 24 h à frente)."""
    now = world.now_minutes()
    offset = world.clock.minute_of_day() - (now % 1440)  # fuso: minuto do dia = (abs + offset) % 1440
    minute = int(earliest)
    for _ in range(0, 1440, 5):
        if sev.start_window.contains(int((minute + offset) % 1440)):
            return float(minute)
        minute += 5
    return None


def plan_hourly(world: "World") -> None:
    state = world.social
    now = world.now_minutes()
    busy_organizers = {i.organizer for i in state.active()}
    for sid in sorted(world.data.social_events):
        sev = world.data.social_events[sid]
        if any(i.kind == sid for i in state.active()) or state.cooldown_until.get(sid, 0) > now:
            continue
        if not world.data.actions.get(sev.action) or not world.data.actions[sev.action].active:
            continue
        place = sev.place
        if sev.where == "dano":
            place, damage = world.structures.worst()
            if place is None or damage < 100 - world.data.world.structures.damaged_below:
                continue
        for cid in sorted(world.states):
            if cid in busy_organizers or not _can_organize(world, sev, cid):
                continue
            partner = _partner(world, sev, cid)
            if sev.partner_affinity_min is not None and partner is None:
                continue
            if world.rng.random() >= sev.chance_per_hour:
                continue
            lead = world.rng.uniform(*sev.lead_hours) * 60
            start = _next_start(world, sev, now + lead)
            if start is None:
                continue
            duration = world.rng.uniform(*sev.duration_hours) * 60
            _plan(world, sev, cid, place, start, start + duration, partner)
            busy_organizers.add(cid)
            break


def _plan(world: "World", sev: SocialEventDef, organizer: str, place: str, start: float, end: float,
          partner: str | None) -> None:
    state = world.social
    candidates = []
    for other in sorted(world.states):
        o = world.states[other]
        if other in (organizer, partner) or not o.alive or o.frozen or o.away:
            continue
        aff = world.affinity(organizer, other)
        if aff >= sev.invite_affinity_min:
            candidates.append((-aff, other))
    guests = [c for _a, c in sorted(candidates)[: sev.max_guests]]
    inst = SocialInstance(id=state.next_id, kind=sev.id, organizer=organizer, place=place, start=start, end=end,
                          guests=guests, partner=partner)
    state.next_id += 1
    state.instances.append(inst)
    state.cooldown_until[sev.id] = start + sev.cooldown_hours * 60
    for who in [organizer] + ([partner] if partner else []) + guests:
        bonus = sev.bonus * (1.5 if who in (organizer, partner) else 1.0)
        world.add_goal(who=who, action=sev.action, place=place, bonus=bonus,
                       start=start - ARRIVE_BEFORE_MINUTES, end=end, source=f"{sev.id}#{inst.id}")
    world.event_text(organizer, world.rng.choice(sev.texts.planned), "social_event_planned", place=place,
                     target=partner, tags=sev.tags, importance=1,
                     extra={"evento": sev.name, "hora": world.hhmm_of(start), "convidados": world.list_names(guests)},
                     data={"social_event": sev.id, "instance": inst.id, "organizer": organizer, "guests": guests,
                           "partner": partner, "start": world.iso_of(start)})


# ------------------------------------------------------------- cada tick
def update(world: "World") -> None:
    now = world.now_minutes()
    for inst in list(world.social.active()):
        sev = world.data.social_events.get(inst.kind)
        if sev is None:
            inst.status = "fracassado"
            continue
        present = world.present_at(inst.place)
        if inst.status == "planejado" and now >= inst.start:
            if len(present) >= sev.quorum and (inst.organizer in present or now >= inst.start + 15):
                inst.status = "acontecendo"
                inst.participants = sorted(set(present))
                world.event_text(inst.organizer, world.rng.choice(sev.texts.started), "social_event_started",
                                 place=inst.place, target=inst.partner, tags=sev.tags, importance=sev.importance,
                                 extra={"evento": sev.name, "convidados": world.list_names(
                                     [p for p in inst.participants if p not in (inst.organizer, inst.partner)])},
                                 data={"social_event": sev.id, "instance": inst.id, "present": len(present),
                                       "participants": inst.participants})
            elif now >= inst.start + TOLERANCE_MINUTES:
                _fail(world, sev, inst, present)
        elif inst.status == "acontecendo":
            for cid in present:
                if cid not in inst.participants:
                    inst.participants.append(cid)
            if now >= inst.end:
                _finish(world, sev, inst)


def _fail(world: "World", sev: SocialEventDef, inst: SocialInstance, present: list[str]) -> None:
    inst.status = "fracassado"
    world.remove_goals(f"{sev.id}#{inst.id}")
    world.event_text(inst.organizer, world.rng.choice(sev.texts.failed), "social_event_ended", place=inst.place,
                     target=inst.partner, tags=sev.tags, importance=1, extra={"evento": sev.name},
                     data={"social_event": sev.id, "instance": inst.id, "result": "fracasso", "present": len(present)})
    if sev.failure_memory:
        world.remember(inst.organizer, sev.failure_memory, subject=inst.organizer, object=None, place=inst.place)
        st = world.states[inst.organizer]
        st.needs["raiva"] = min(100.0, st.needs.get("raiva", 0) + 20)
        for g in inst.guests:
            if g not in present:
                world.change_affinity(inst.organizer, g, -4)  # "ninguém veio"


def _finish(world: "World", sev: SocialEventDef, inst: SocialInstance) -> None:
    inst.status = "terminado"
    world.remove_goals(f"{sev.id}#{inst.id}")
    people = sorted(set(inst.participants))
    world.event_text(inst.organizer, world.rng.choice(sev.texts.ended), "social_event_ended", place=inst.place,
                     target=inst.partner, tags=sev.tags, importance=sev.importance,
                     extra={"evento": sev.name, "convidados": world.list_names(
                         [p for p in people if p not in (inst.organizer, inst.partner)])},
                     data={"social_event": sev.id, "instance": inst.id, "result": "sucesso",
                           "participants": people})
    for cid in people:
        if sev.memory:
            world.remember(cid, sev.memory, subject=inst.organizer, object=inst.partner, place=inst.place)
        if cid != inst.organizer:
            world.change_affinity(cid, inst.organizer, 3)
    if inst.partner:
        world.states[inst.organizer].spouse = inst.partner
        world.states[inst.partner].spouse = inst.organizer
