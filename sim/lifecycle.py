"""Vida e morte (Fase 3): morte, funeral, luto, herança, fantasmas, ressurreição,
nascimentos e sucessão de papéis.

Tudo que é número ou texto está no YAML (`world.yaml > morte, funeral, luto,
se_morrer, sucessao, vida`; `traits.yaml > nascimento`; falas em
`data/lines/vida.yaml`). Aqui ficam só as regras genéricas:

**Morte** (`roll` + `kill`): cada causa de `morte.causas` diz QUANDO o mundo
sorteia (todo dia, no fim de uma briga, quando uma ação dá errado, perto de uma
criatura, ao ir para o Limbo) e com que chance (× `por_traco`). Ninguém morre
se a cidade já está com `limites.min_populacao` vivos ou menos (sem extinção).
A morte é permanente: `alive = False`, o corpo vai para o cemitério, todos os
vivos ganham a memória permanente `morte`, quem gostava entra em luto, o mais
próximo herda um objeto, o papel importante fica vago e o funeral é marcado.

**Funeral**: velório na Catedral, cortejo até o Cemitério, enterro, lápide.
Sempre chove (clima forçado). Cada vivo ganha um objetivo de ir (`velar`),
mais forte quanto mais gostava do morto (e o traço `vaidoso` vai para ser
visto). Na ação `velar`, cada um reage pela personalidade (falas por
personagem/traço) e pela afinidade (amigo / indiferente / inimigo). Quem passa
pelo cemitério sem estar no funeral (o Mike) também aparece no Chat.

**Luto**: intensidade = afinidade com o morto / 100 × fator do tipo de relação
(casal, filho...). Choque nas necessidades na hora; taxas e notas de ações
alteradas por `luto.dias × intensidade` dias.

**Fantasmas** e **ressurreição natural** são raros e quem os dispara é o
diretor (eventos com `especial: fantasma | ressurreicao`).

**Nascimento**: de tempos em tempos (`limites.intervalo_nascimento_dias`, mais
provável quando há vagas abertas por mortes recentes; nunca acima de
`max_populacao`) ou por comando. Traços, profissão e aparência sorteados de
`traits.yaml`; às vezes herda um objeto ou mania de um morto recente. O novo
personagem vira um YAML em `data/characters/born/` (ou `DW_BORN_DIR`).

**Sucessão**: profissão com `papel_importante` sem ninguém vivo para exercer
abre uma vaga; depois de `sucessao.papeis.<prof>.depois_horas`, alguém assume
por eleição (assembleia na Praça, cada um vota em quem mais gosta), vocação
(traços) ou sucessão (herdeiros, aprendiz, família). Quem assume ganha a
profissão, o local de trabalho e os blocos de rotina do papel (o YAML original
não muda; fica salvo no banco).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from sim import needs as needs_mod
from sim import speech
from sim.rng import weighted_choice
from sim.schemas import Character
from sim.state import CharacterState

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World

DAY = 1440


@dataclass
class LifeState:
    created: str = ""  # quando o mundo começou (a "data de nascimento" dos personagens da bible)
    deaths: list[dict] = field(default_factory=list)  # {cid, minute, ts, cause, place, by}
    births: list[dict] = field(default_factory=list)  # {cid, minute, ts, from_dead}
    graves: list[dict] = field(default_factory=list)  # {cid, born, died, cause, cause_name, epitaph, resurrected}
    funerals: list[dict] = field(default_factory=list)
    grief: dict[str, list[dict]] = field(default_factory=dict)  # quem -> [{of, until, intensity}]
    consequences: list[dict] = field(default_factory=list)  # {dead, actions, who, until}
    vacancies: list[dict] = field(default_factory=list)
    overrides: dict[str, dict] = field(default_factory=dict)  # quem assumiu um papel: profession, workplace, routine
    objects: dict[str, list[str]] = field(default_factory=dict)  # objetos herdados
    faction_leaders: dict[str, str | None] = field(default_factory=dict)  # facção -> líder atual (se mudou)
    next_born: int = 1
    next_funeral: int = 1
    ghosts: dict[str, float] = field(default_factory=dict)  # morto -> minuto da última aparição

    def to_json(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_json(cls, raw: dict) -> "LifeState":
        st = cls()
        for key, value in (raw or {}).items():
            if hasattr(st, key):
                setattr(st, key, value)
        return st


# =========================================================================== ajuda
def living(world: "World") -> list[str]:
    return sorted(cid for cid, st in world.states.items() if st.alive and not st.frozen)


def _fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso[:10]


def grief_level(world: "World", cid: str) -> float:
    """Luto mais forte agora (0..1.5)."""
    now = world.now_minutes()
    return max((g["intensity"] for g in world.life.grief.get(cid, []) if g["until"] > now), default=0.0)


def grieved_dead(world: "World", cid: str) -> str | None:
    now = world.now_minutes()
    best = max((g for g in world.life.grief.get(cid, []) if g["until"] > now), key=lambda g: g["intensity"],
               default=None)
    return best["of"] if best else None


def multipliers(world: "World", cid: str) -> tuple[dict[str, float], dict[str, float]]:
    """(taxas de necessidades, notas de ações) por causa do luto e das consequências de mortes."""
    cfg = world.data.world.grief
    rates: dict[str, float] = {}
    actions: dict[str, float] = {}
    level = grief_level(world, cid)
    if level > 0:
        for n, m in cfg.rates.items():
            rates[n] = 1 + (m - 1) * min(1.0, level)
        for a, m in cfg.actions.items():
            actions[a] = max(0.05, 1 + (m - 1) * min(1.0, level))
    now = world.now_minutes()
    for cons in world.life.consequences:
        if cons["until"] <= now or (cons["who"] and cid not in cons["who"]):
            continue
        for a, m in cons["actions"].items():
            actions[a] = actions.get(a, 1.0) * m
    return rates, actions


# ========================================================================== morte
def roll(world: "World", when: str, cid: str, *, action: str | None = None, place: str | None = None,
         by: str | None = None, factor: float = 1.0, detail: str = "") -> bool:
    """Sorteia as causas de morte do tipo `when` para `cid`. True se morreu."""
    st = world.states.get(cid)
    if st is None or not st.alive or st.frozen:
        return False
    if len(living(world)) <= world.data.world.limits.min_population:
        return False  # a cidade nunca se extingue por acaso
    place = place or st.place
    traits = set(world.traits_of(cid))
    for cause_id in sorted(world.data.world.death.causes):
        cause = world.data.world.death.causes[cause_id]
        if cause.when != when:
            continue
        if cause.actions and action not in cause.actions:
            continue
        if cause.places and place not in cause.places:
            continue
        chance = cause.chance if cause.chance is not None else world.data.world.limits.death_chance_per_day
        if when == "diario":
            chance /= 24  # sorteado de hora em hora
        for t, m in cause.by_trait.items():
            if t in traits:
                chance *= m
        if world.rng.random() < min(1.0, chance * factor):
            kill(world, cid, cause_id, place=place, by=by, detail=detail)
            return True
    return False


def kill(world: "World", cid: str, cause_id: str, *, place: str | None = None, by: str | None = None,
         detail: str = "") -> None:
    st = world.states[cid]
    if not st.alive:
        return
    cfg = world.data.world
    cause = cfg.death.causes.get(cause_id)
    cause_name = cause.name if cause else cause_id
    place = place or st.place
    if st.activity is not None or st.plan is not None:
        world.interrupt(cid)
    st.alive = False
    st.plan, st.activity = None, None
    st.jailed_until, st.limbo_until = None, None
    now = world.now_minutes()
    situation = (cause.situation if cause and cause.situation else f"morte_{cause_id}")
    world.say(cid, situation, target=by if by in world.states else None, place=place, event_type="death",
              extra={"objeto": detail or cause_name}, tags=["morte"], importance=3,
              data={"cause": cause_id, "cause_name": cause_name, "by": by, "place": place},
              fallback="{eu} morreu em {lugar}. Causa: " + cause_name + ".")
    st.place = cfg.death.body_place
    life = world.life
    life.deaths.append({"cid": cid, "minute": now, "ts": world.clock.iso(), "cause": cause_id,
                        "cause_name": cause_name, "place": place, "by": by})
    char = world.data.characters[cid]
    life.graves.append({"cid": cid, "born": char.born_at or life.created or world.clock.iso(),
                        "died": world.clock.iso(), "cause": cause_id, "cause_name": cause_name,
                        "epitaph": "", "resurrected": False})
    # o mundo esquece os planos de quem morreu
    world.goals[:] = [g for g in world.goals if g["who"] != cid]
    world.law.points.pop(cid, None)
    world.law.warrants.pop(cid, None)
    for inst in world.social.active():
        if cid in (inst.organizer, inst.partner):
            inst.status = "fracassado"
            world.remove_goals(f"{inst.kind}#{inst.id}")
    if st.spouse and st.spouse in world.states:
        world.states[st.spouse].spouse = None
    st.spouse = None
    # todo mundo lembra (quem viu, mais forte)
    witnesses = set(world.present_at(place))
    for other in living(world):
        world.remember(other, cfg.death.memory, subject=cid, object=by, place=place,
                       factor=1.0 if other in witnesses else 0.8, detail=cause_name)
    _grieve(world, cid)
    _inherit(world, cid)
    _open_vacancy(world, cid)
    _apply_consequence(world, cid)
    _schedule_funeral(world, cid)
    world.refresh_review_minutes(cid)


def _relation_kinds(world: "World", a: str, b: str) -> set[str]:
    kinds = {r.kind for r in world.data.characters[a].relations if r.with_ == b}
    kinds |= {r.kind for r in world.data.characters[b].relations if r.with_ == a}
    if world.states[a].spouse == b:
        kinds.add("casal")
    return kinds


def _grieve(world: "World", dead: str) -> None:
    cfg = world.data.world.grief
    cons = world.data.world.consequences.get(dead)
    now = world.now_minutes()
    felt = []
    for other in living(world):
        aff = world.affinity(other, dead)
        factor = max([cfg.kind_factor.get(k, 1.0) for k in _relation_kinds(world, other, dead)] or [1.0])
        if cons:
            factor *= cons.grief_factor.get(other, 1.0)
        if aff < cfg.affinity_min and factor <= 1.0:
            continue
        intensity = min(1.5, max(0.0, aff) / 100 * factor)
        if intensity <= 0.05:
            continue
        st = world.states[other]
        for n, v in cfg.shock.items():
            st.needs[n] = needs_mod.clamp(st.needs.get(n, 0) + v * min(1.0, intensity))
        world.life.grief.setdefault(other, []).append(
            {"of": dead, "until": now + cfg.days * intensity * DAY, "intensity": round(intensity, 3)})
        felt.append((intensity, other))
    # só os mais abalados aparecem no Chat (senão a cidade inteira chora ao mesmo tempo)
    for intensity, other in sorted(felt, reverse=True)[:3]:
        if intensity >= 0.4:
            world.say(other, "luto", place=world.states[other].place, event_type="grief", extra={"morto": dead},
                      tags=["morte"], importance=2, data={"dead": dead, "intensity": round(intensity, 2)},
                      fallback="{eu} fica em silêncio quando ouve falar de {morto}.")


def _objects_of(world: "World", cid: str) -> list[str]:
    char = world.data.characters[cid]
    objs = list(char.inheritance.objects) + list(world.life.objects.get(cid, []))
    if char.inherited and char.inherited.object:
        objs.append(char.inherited.object)
    return list(dict.fromkeys(objs))


def _inherit(world: "World", dead: str) -> None:
    objs = _objects_of(world, dead)
    if not objs:
        return
    alive = [c for c in living(world) if not world.states[c].away]
    if not alive:
        return
    heirs = [h for h in world.data.characters[dead].inheritance.heirs if h in alive]
    heir = heirs[0] if heirs else max(alive, key=lambda c: (world.affinity(dead, c), c))
    obj = objs[0] if heirs else world.rng.choice(objs)
    world.life.objects.setdefault(heir, []).append(obj)
    world.say(heir, "heranca", place=world.states[heir].place, event_type="inheritance",
              extra={"morto": dead, "objeto": obj}, tags=["morte"], importance=2,
              data={"dead": dead, "object": obj},
              fallback="{eu} fica com " + "{objeto}" + ", de {morto}.")


# ======================================================================== funeral
def _next_in_window(world: "World", window, earliest: float) -> float:
    now = world.now_minutes()
    offset = world.clock.minute_of_day() - (now % DAY)
    minute = int(earliest)
    for _ in range(0, DAY * 2, 5):
        if window.contains(int((minute + offset) % DAY)):
            return float(minute)
        minute += 5
    return float(earliest)


def _schedule_funeral(world: "World", dead: str) -> None:
    cfg = world.data.world.funeral
    cons = world.data.world.consequences.get(dead)
    now = world.now_minutes()
    delay = cons.funeral_delay_hours if (cons and cons.funeral_delay_hours is not None) else world.rng.uniform(*cfg.delay_hours)
    start = _next_in_window(world, cfg.window, now + delay * 60 + cfg.wake_minutes)
    wake = start - cfg.wake_minutes
    end = start + world.rng.randint(*cfg.duration_minutes)
    fid = world.life.next_funeral
    world.life.next_funeral += 1
    fun = {"id": fid, "dead": dead, "wake": wake, "start": start, "end": end, "status": "planejado",
           "attendees": [], "passers": [], "leader": None}
    world.life.funerals.append(fun)
    source = f"funeral#{fid}"
    for other in living(world):
        aff = world.affinity(other, dead)
        bonus = max(cfg.bonus_min, cfg.bonus_base + aff * cfg.bonus_per_affinity)
        if cfg.wake_minutes > 0:
            world.add_goal(who=other, action=cfg.action, place=cfg.wake_place, bonus=bonus, start=wake - 20,
                           end=start, source=source)
        world.add_goal(who=other, action=cfg.action, place=cfg.burial_place, bonus=bonus, start=start, end=end,
                       source=source)
    leader = _funeral_leader(world)
    speaker = leader or next(iter(living(world)), None)
    if speaker:
        world.say(speaker, "funeral_anuncio", place=world.states[speaker].place, event_type="funeral_planned",
                  extra={"morto": dead, "hora": world.hhmm_of(wake)}, tags=["morte"], importance=2,
                  data={"dead": dead, "funeral": fid, "wake": world.iso_of(wake), "start": world.iso_of(start)},
                  fallback="{eu} avisa: o velório de {morto} é às {hora}, na Catedral.")


def _funeral_leader(world: "World") -> str | None:
    for prof in world.data.world.funeral.leaders:
        for cid in living(world):
            st = world.states[cid]
            if world.data.characters[cid].profession == prof and not st.away and st.jailed_until is None:
                return cid
    return None


def active_funeral_at(world: "World", place: str) -> dict | None:
    """O funeral que está acontecendo AGORA neste lugar (velório ou enterro)."""
    cfg = world.data.world.funeral
    now = world.now_minutes()
    for fun in world.life.funerals:
        if fun["status"] == "terminado":
            continue
        # o velório só "acontece" a partir da hora marcada (quem chega antes espera)
        if place == cfg.wake_place and fun["wake"] <= now < fun["start"] and cfg.wake_minutes > 0:
            return fun
        if place == cfg.burial_place and fun["start"] <= now < fun["end"]:
            return fun
    return None


def update(world: "World") -> None:
    """A cada tick: fases dos funerais."""
    if not world.life.funerals:
        return
    cfg = world.data.world.funeral
    now = world.now_minutes()
    for fun in list(world.life.funerals):
        if fun["status"] == "terminado":
            continue
        dead = fun["dead"]
        if fun["status"] == "planejado" and now >= fun["wake"]:
            fun["status"] = "velorio"
            cons = world.data.world.consequences.get(dead)
            rain = world.data.world.limits.funeral_rain_minutes
            if cons and cons.rain_minutes is not None:
                rain = cons.rain_minutes
            world.weather.force(world.data.world.weather.funeral_kind, max(rain, fun["end"] - now + 15), "funeral")
            leader = _funeral_leader(world)
            fun["leader"] = leader
            speaker = leader or next(iter(living(world)), None)
            if speaker:
                world.say(speaker, "funeral_comeca", place=cfg.wake_place, event_type="funeral_started",
                          extra={"morto": dead}, tags=["morte"], importance=3,
                          data={"dead": dead, "funeral": fun["id"]},
                          fallback="Começa o velório de {morto}. Chove.")
        if fun["status"] == "velorio" and now >= fun["start"]:
            fun["status"] = "enterro"
            walkers = [c for c in world.present_at(cfg.wake_place)
                       if world.states[c].activity and world.states[c].activity.action == cfg.action]
            speaker = fun["leader"] if fun["leader"] in walkers else (walkers[0] if walkers else None)
            if speaker:
                world.say(speaker, "funeral_cortejo", place=cfg.wake_place, event_type="funeral_procession",
                          extra={"morto": dead, "convidados": world.list_names([w for w in walkers if w != speaker])},
                          tags=["morte"], importance=2, data={"dead": dead, "funeral": fun["id"], "walkers": walkers},
                          fallback="O cortejo de {morto} sai da Catedral rumo ao Cemitério.")
            for cid in walkers:  # o cortejo: quem estava no velório vai junto até o cemitério
                world.interrupt(cid)
                world.send_to(cid, cfg.action, cfg.burial_place)
        if fun["status"] == "enterro":
            for cid in world.present_at(cfg.burial_place):
                st = world.states[cid]
                act = st.activity.action if st.activity else None
                if (act != cfg.action and cid not in fun["passers"] and cid not in fun["attendees"]
                        and not world.is_asleep(cid)):
                    fun["passers"].append(cid)
                    world.say(cid, "funeral_passante", place=cfg.burial_place, event_type="speech",
                              extra={"morto": dead}, tags=["morte"], importance=1,
                              data={"dead": dead, "funeral": fun["id"]})
            if now >= fun["end"]:
                _finish_funeral(world, fun)


def joined(world: "World", fun: dict, cid: str) -> None:
    if cid not in fun["attendees"]:
        fun["attendees"].append(cid)


def _finish_funeral(world: "World", fun: dict) -> None:
    cfg = world.data.world.funeral
    fun["status"] = "terminado"
    dead = fun["dead"]
    world.remove_goals(f"funeral#{fun['id']}")
    people = [c for c in fun["attendees"] if c in world.states and world.states[c].alive]
    grave = next((g for g in reversed(world.life.graves) if g["cid"] == dead), None)
    epitaph = ""
    ctx = world._speech_ctx(dead, cfg.burial_place, None, {"morto": dead})
    line = speech.pick_line(world.data, "epitafio", ctx, world.rng, None) if "epitafio" in world.data.lines else None
    if line:
        epitaph = line
    if grave is not None:
        grave["epitaph"] = epitaph
    speaker = fun.get("leader") if fun.get("leader") in people else (people[0] if people else None)
    who = world.list_names(people) if people else "ninguém"
    text = (f"Enterram {{@{dead}}} em {{@{cfg.burial_place}}}. Estavam lá: {who}.")
    world.emit("funeral_ended", text, actors=[dead] + people, place=cfg.burial_place, tags=["morte"],
               importance=3, data={"dead": dead, "funeral": fun["id"], "attendees": people,
                                   "passers": fun["passers"]})
    if grave is not None:
        cause = grave["cause_name"]
        gtext = (f"A lápide nova no {{@{cfg.burial_place}}}: {{@{dead}}}, {_fmt_date(grave['born'])} – "
                 f"{_fmt_date(grave['died'])}. {cause[:1].upper() + cause[1:]}.")
        if epitaph:
            gtext += f" «{epitaph}»"
        world.emit("grave", gtext, actors=[dead], place=cfg.burial_place, tags=["morte"], importance=2,
                   data={"dead": dead, **{k: grave[k] for k in ("born", "died", "cause", "cause_name")},
                         "epitaph": epitaph})
    if cfg.memory:
        for cid in people:
            world.remember(cid, cfg.memory, subject=dead, place=cfg.burial_place)
    cons = world.data.world.consequences.get(dead)
    if cons and cons.text:
        narrator = speaker or next(iter(living(world)), None)
        if narrator:
            world.event_text(narrator, cons.text, "death_consequence", place=world.data.world.central_place,
                             tags=["morte"], importance=cons.importance, extra={"morto": dead},
                             data={"dead": dead})


def _apply_consequence(world: "World", dead: str) -> None:
    cons = world.data.world.consequences.get(dead)
    if cons is None:
        return
    now = world.now_minutes()
    if cons.actions:
        world.life.consequences.append({"dead": dead, "actions": dict(cons.actions), "who": list(cons.who),
                                        "until": now + cons.days * DAY})
    if cons.goal:
        g = cons.goal
        start = now + world.data.world.funeral.delay_hours[1] * 60  # depois do funeral, mais ou menos
        for cid in living(world):
            if g.who == "todos" or cid in cons.who:
                world.add_goal(who=cid, action=g.action, place=g.place, bonus=g.bonus, start=start,
                               end=start + g.hours * 60, source=f"se_morrer:{dead}")


# ================================================================== fantasmas etc.
def ghost(world: "World") -> bool:
    """Um morto aparece à noite perto de quem ele mais amava ou mais odiava."""
    now = world.now_minutes()
    alive = [c for c in living(world) if not world.states[c].away]
    options = []
    for d in world.life.deaths:
        cid = d["cid"]
        st = world.states.get(cid)
        if st is None or st.alive or now - d["minute"] < 12 * 60:
            continue
        if now - world.life.ghosts.get(cid, -1e12) < 3 * DAY:
            continue
        best = max(alive, key=lambda o: (abs(world.affinity(cid, o)), o), default=None)
        if best is not None and abs(world.affinity(cid, best)) >= 30:
            options.append((cid, best))
    if not options:
        return False
    dead, target = world.rng.choice(sorted(set(options)))
    world.life.ghosts[dead] = now
    tst = world.states[target]
    love = world.affinity(dead, target) > 0
    asleep = world.is_asleep(target)
    situation = "fantasma_sonho" if asleep else ("fantasma_amor" if love else "fantasma_odio")
    world.say(target, situation, place=tst.place, event_type="ghost", extra={"morto": dead}, tags=["misterio", "morte"],
              importance=2, data={"dead": dead, "target": target, "love": love, "dream": asleep},
              fallback="{morto} aparece para {eu} no meio da noite.")
    mem = world.data.world.life.ghost_memory
    seen = [target] + [c for c in world.present_at(tst.place) if c != target and not world.is_asleep(c)]
    for cid in seen:
        if "criaturas" in world.data.characters[cid].immunities and cid != target:
            continue
        st = world.states[cid]
        st.needs["medo"] = needs_mod.clamp(st.needs.get("medo", 0) + (25 if cid == target and love else 45))
        st.needs["fe"] = needs_mod.clamp(st.needs.get("fe", 0) + 20)
        world.remember(cid, mem, subject=dead, object=target, place=tst.place, factor=1.0 if cid == target else 0.7)
    return True


def resurrect(world: "World", cid: str, how: str = "natural", *, fear: float = 85.0,
              forget_chance: float = 0.5) -> bool:
    """O morto volta, mudado. `how`: natural (raríssimo, pelo diretor) ou criador (Fase 4:
    comando `reviver`, com `medo` e `chance_esquecer` de data/events/criador.yaml)."""
    st = world.states.get(cid)
    if st is None or st.alive:
        return False
    char = world.data.characters[cid]
    place = world.data.world.death.body_place
    st.alive = True
    st.place = place
    st.activity, st.plan = None, None
    st.needs = needs_mod.initial_needs(world.data, char)
    st.needs["medo"] = float(fear)
    st.next_review = world.now_minutes()
    trait = world.draw_new_trait(cid)
    if trait:
        st.extra_traits.append(trait)
    mine = world.memories.of(cid)
    forgot = 0
    for m in list(mine):  # volta com buracos na memória
        if not m.permanent and world.rng.random() < forget_chance:
            mine.remove(m)
            forgot += 1
    # voltou antes do próprio enterro: o funeral é cancelado
    for fun in world.life.funerals:
        if fun["dead"] == cid and fun["status"] != "terminado":
            fun["status"] = "terminado"
            fun["cancelled"] = True
            world.remove_goals(f"funeral#{fun['id']}")
    for grave in world.life.graves:
        if grave["cid"] == cid:
            grave["resurrected"] = True
    for other in world.life.grief:
        world.life.grief[other] = [g for g in world.life.grief[other] if g["of"] != cid]
    world.life.vacancies = [v for v in world.life.vacancies if not (v["dead"] == cid and v["status"] == "aberta")]
    extra = {"traco": world.data.traits[trait].name.lower()} if trait else {}
    world.say(cid, f"ressurreicao_{how}", place=place, event_type="resurrection", extra=extra,
              tags=["misterio", "morte"], importance=3, data={"how": how, "new_trait": trait, "forgot": forgot},
              fallback="{eu} se levanta da cova, sujo de terra. Voltou.")
    for prof, situation in (("padre", "ressurreicao_padre"), ("medium", "ressurreicao_medium")):
        for other in living(world):
            if other != cid and world.data.characters[other].profession == prof and not world.states[other].away:
                world.say(other, situation, place=world.states[other].place, event_type="speech",
                          extra={"morto": cid}, tags=["misterio"], importance=2, data={"about": cid})
                break
    for other in living(world):
        if other != cid:
            world.remember(other, world.data.world.life.resurrection_memory, subject=cid, place=place)
    world.refresh_review_minutes(cid)
    return True


# ===================================================================== nascimento
def hourly(world: "World") -> None:
    """De hora em hora: mortes "do dia" (velhice, acaso), nascimentos, vagas, consequências que acabaram."""
    now = world.now_minutes()
    for cid in living(world):
        roll(world, "diario", cid)
    life = world.life
    life.consequences = [c for c in life.consequences if c["until"] > now]
    for who in list(life.grief):
        life.grief[who] = [g for g in life.grief[who] if g["until"] > now]
        if not life.grief[who]:
            del life.grief[who]
    _maybe_birth(world)
    _succession_hourly(world)


def birth_chance_per_day(world: "World") -> float:
    lim = world.data.world.limits
    alive = len(living(world))
    if alive >= lim.max_population:
        return 0.0
    now = world.now_minutes()
    deaths = sum(1 for d in world.life.deaths if now - d["minute"] < 30 * DAY)
    births = sum(1 for b in world.life.births if now - b["minute"] < 30 * DAY)
    vacancies = max(0, deaths - births)
    chance = (1 / lim.birth_interval_days) * (1 + world.data.world.life.vacancy_bonus * vacancies)
    if alive < lim.min_population:
        chance *= 3
    return min(1.0, chance)


def _maybe_birth(world: "World") -> None:
    if world.rng.random() < birth_chance_per_day(world) / 24:
        birth(world)


def _draw_traits(world: "World", wanted: list[str] | None = None) -> list[str]:
    rules = world.data.traits_file.birth
    chosen = [t for t in (wanted or []) if t in world.data.traits]
    count = world.rng.randint(rules.min_traits, rules.max_traits)
    while len(chosen) < count:
        blocked = set(chosen)
        for t in chosen:
            blocked |= set(world.data.traits[t].opposites)
        options = sorted(t.id for t in world.data.traits.values()
                         if t.drawable and t.id not in blocked and not (set(t.opposites) & set(chosen)))
        if not options:
            break
        chosen.append(world.rng.choice(options))
    return chosen


def _quirk_phrase(quirk: str) -> str | None:
    """'terminar as frases com "...hehe."' -> '...hehe.' (vira bordão)."""
    m = re.search(r'"([^"]+)"', quirk)
    return m.group(1) if m else None


def birth(world: "World", traits: list[str] | None = None, reason: str = "natural") -> str | None:
    """Nasce alguém novo. Grava o YAML e põe no mundo. Devolve o id."""
    data = world.data
    rules = data.traits_file.birth
    pool = data.traits_file.appearance
    rng = world.rng
    life = world.life
    # DW_BORN_DIR vale também em tempo de execução (testes e simulações de teste)
    env = os.environ.get("DW_BORN_DIR", "").strip()
    born_dir = Path(env) if env else (Path(data.born_dir) if data.born_dir else data.root / "characters" / "born")
    n = life.next_born
    while f"born_{n}" in data.characters or (born_dir / f"born_{n}.yaml").exists():
        n += 1
    life.next_born = n + 1
    cid = f"born_{n}"
    pronoun = rng.choice(["ele", "ela"])
    name = (rules.default_name_she if pronoun == "ela" else rules.default_name).replace("{n}", str(n))
    trait_ids = _draw_traits(world, traits)
    professions = sorted(p.id for p in data.professions.values() if p.drawable)
    prof = rng.choice(professions)
    workplace = data.professions[prof].workplace
    colors = list(pool.colors)
    color = rng.choice(colors)
    second = rng.choice([c for c in colors if c != color] or colors)
    raw = {
        "id": cid,
        "nome": name,
        "pronome": pronoun,
        "papel": "Nascido no mundo · sorteado",
        "aparencia": rng.choice(pool.descriptions) if pool.descriptions else "Alguém que acabou de chegar.",
        "visual": {"cor": color, "cor_secundaria": second, "altura": round(rng.uniform(0.85, 1.15), 2),
                   "corpo": rng.choice(pool.bodies), "chapeu": rng.choice(pool.hats) if pool.hats else "nenhum",
                   "acessorio": rng.choice(pool.accessories) if pool.accessories else "nenhum"},
        "tracos": trait_ids,
        "profissao": prof,
        "casa": rules.home,
        "afinidade_padrao": rules.default_affinity,
        "nascido_em": world.clock.iso(),
    }
    if workplace:
        raw["local_trabalho"] = workplace
    raw["rotina"] = [{"das": b.start, "ate": b.end, "acao": b.action, **({"lugar": b.place} if b.place else {}),
                      "peso": b.weight} for b in rules.routine
                     if b.action != "trabalhar" or prof != "nenhuma"]
    # herança de um morto recente
    now = world.now_minutes()
    recent = [d for d in reversed(life.deaths) if now - d["minute"] < world.data.world.life.recent_dead_days * DAY
              and not world.states[d["cid"]].alive]
    from_dead = None
    if recent and rng.random() < rules.inherit_chance:
        dead = recent[0]["cid"]
        dchar = data.characters[dead]
        options = [("objeto", o) for o in _objects_of(world, dead)] + [("mania", q) for q in dchar.inheritance.quirks]
        if options:
            kind, value = rng.choice(options)
            raw["herdou"] = {"de": dead, kind: value}
            from_dead = dead
            if kind == "mania":
                phrase = _quirk_phrase(value)
                if phrase:
                    raw["bordoes"] = [phrase]
    char = Character.model_validate(raw)
    _write_born_yaml(born_dir, raw, world)
    data.characters[cid] = char
    st = CharacterState(id=cid, place=rules.appears_at, needs=needs_mod.initial_needs(data, char))
    st.next_review = now
    world.states[cid] = st
    world.refresh_review_minutes(cid)
    life.births.append({"cid": cid, "minute": now, "ts": world.clock.iso(), "from_dead": from_dead,
                        "reason": reason})
    extra = {"traco": ", ".join(data.traits[t].name.lower() for t in trait_ids),
             "objeto": data.professions[prof].name.lower()}
    world.say(cid, "nascimento", place=st.place, event_type="birth", extra=extra, tags=["nascimento"],
              importance=3, data={"traits": trait_ids, "profession": prof, "file": f"{born_dir.name}/{cid}.yaml",
                                  "inherited": raw.get("herdou"), "reason": reason},
              fallback="Nasce alguém na cidade: {eu}. Ninguém sabe de onde veio.")
    if from_dead:
        what = raw["herdou"].get("objeto") or raw["herdou"].get("mania")
        world.say(cid, "nascimento_heranca", place=st.place, event_type="inheritance",
                  extra={"morto": from_dead, "objeto": what}, tags=["nascimento", "morte"], importance=2,
                  data={"dead": from_dead, "what": what},
                  fallback="{eu} tem uma coisa de {morto}: {objeto}.")
    welcomers = [c for c in world.present_at(st.place) if c != cid and not world.is_asleep(c)]
    if welcomers:
        w = rng.choice(welcomers)
        world.say(w, "boas_vindas", target=cid, place=st.place, event_type="speech", tags=["nascimento"],
                  importance=1, data={"about": cid})
    return cid


def _write_born_yaml(folder: Path, raw: dict, world: "World") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    header = (
        "# Personagem NASCIDO no mundo (Fase 3), gerado automaticamente.\n"
        f"# Nasceu em {raw['nascido_em']} (hora do mundo).\n"
        "# Pode editar à vontade: troque o 'nome' (nada quebra), os traços, a\n"
        "# aparência e as falas. NÃO mude o 'id'. Depois rode: python -m tools.validate\n"
    )
    body = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=100)
    (folder / f"{raw['id']}.yaml").write_text(header + body, encoding="utf-8")


# ====================================================================== sucessão
def _open_vacancy(world: "World", dead: str) -> None:
    prof_id = world.data.characters[dead].profession
    prof = world.data.professions.get(prof_id)
    if prof is None or not prof.important_role:
        return
    if any(world.data.characters[c].profession == prof_id for c in living(world)):
        return  # ainda tem quem faça (os dois Técnicos)
    role = world.data.world.succession.roles.get(prof_id)
    if role is None:
        return
    now = world.now_minutes()
    world.life.vacancies.append({"profession": prof_id, "dead": dead, "since": now,
                                 "due": now + world.rng.uniform(*role.after_hours) * 60,
                                 "mode": role.mode, "status": "aberta", "assembly": None})


def _candidate_score(world: "World", cid: str, vac: dict) -> float:
    cfg = world.data.world.succession
    role = cfg.roles[vac["profession"]]
    st = world.states[cid]
    if not st.alive or st.away or st.frozen or st.jailed_until is not None:
        return 0.0
    char = world.data.characters[cid]
    current = world.data.professions.get(char.profession)
    if current and current.important_role:
        return 0.0  # ninguém larga um papel importante para pegar outro
    score = 1.0
    if cid in world.data.characters[vac["dead"]].inheritance.heirs:
        score += cfg.heir_bonus
    for k in _relation_kinds(world, cid, vac["dead"]):
        score += cfg.kind_bonus.get(k, 0.0)
    score += 2.0 * len(set(role.traits) & set(world.traits_of(cid)))
    score += max(0.0, world.affinity(cid, vac["dead"])) / 50
    return score


def _succession_hourly(world: "World") -> None:
    now = world.now_minutes()
    for vac in world.life.vacancies:
        if vac["status"] != "aberta" or now < vac["due"]:
            continue
        if any(world.data.characters[c].profession == vac["profession"] for c in living(world)):
            vac["status"] = "fechada"
            continue
        role = world.data.world.succession.roles[vac["profession"]]
        scored = sorted(((_candidate_score(world, c, vac), c) for c in living(world)), reverse=True)
        scored = [(s, c) for s, c in scored if s > 0]
        if not scored:
            continue
        if role.mode == "eleicao":
            _election(world, vac, role, scored, now)
        else:
            people = [c for _s, c in scored]
            winner = weighted_choice(world.rng, people, [s for s, _c in scored])
            assume(world, winner, vac, role.mode)


def _election(world: "World", vac: dict, role, scored, now: float) -> None:
    cfg = world.data.world.succession
    asm = vac.get("assembly")
    if asm is None:
        start, end = now + 30, now + 30 + role.duration_minutes
        candidates = [c for _s, c in scored[:3]]
        vac["assembly"] = {"start": start, "end": end, "candidates": candidates, "voters": []}
        for cid in living(world):
            world.add_goal(who=cid, action=cfg.assembly_action, place=role.place, bonus=cfg.assembly_bonus,
                           start=start - 20, end=end, source=f"eleicao#{vac['profession']}")
        world.say(candidates[0], "eleicao_convocada", place=world.states[candidates[0]].place, event_type="election",
                  extra={"morto": vac["dead"], "objeto": world.data.professions[vac["profession"]].name,
                         "convidados": world.list_names(candidates), "hora": world.hhmm_of(start)},
                  tags=["evento"], importance=2,
                  data={"profession": vac["profession"], "candidates": candidates, "phase": "called"},
                  fallback="Sem {morto}, a cidade marca uma eleição às {hora}. Candidatos: {convidados}.")
        return
    if now < asm["end"]:
        return
    world.remove_goals(f"eleicao#{vac['profession']}")
    candidates = [c for c in asm["candidates"] if world.states[c].alive]
    if not candidates:
        vac["assembly"] = None
        return
    voters = [v for v in asm["voters"] if world.states[v].alive]
    if len(voters) < 3:
        voters = living(world)
    votes = {c: 0 for c in candidates}
    for v in voters:
        choice = v if v in candidates else max(candidates, key=lambda c: (world.affinity(v, c), c))
        votes[choice] += 1
    best = max(votes.values())
    winners = sorted(c for c, n in votes.items() if n == best)
    winner = world.rng.choice(winners)
    tally = ", ".join(f"{{@{c}}} {n}" for c, n in sorted(votes.items(), key=lambda kv: -kv[1]))
    world.say(winner, "eleicao_resultado", place=role.place, event_type="election",
              extra={"objeto": tally, "convidados": world.list_names(voters)}, tags=["evento"], importance=2,
              data={"profession": vac["profession"], "votes": votes, "voters": voters, "phase": "result"},
              fallback="Fim da apuração: {objeto}. {eu} venceu.")
    assume(world, winner, vac, "eleicao")


def assembly_joined(world: "World", cid: str) -> None:
    for vac in world.life.vacancies:
        asm = vac.get("assembly")
        if vac["status"] == "aberta" and asm and cid not in asm["voters"]:
            asm["voters"].append(cid)


def assembly_active(world: "World", place: str) -> bool:
    now = world.now_minutes()
    for vac in world.life.vacancies:
        asm = vac.get("assembly")
        role = world.data.world.succession.roles.get(vac["profession"])
        if vac["status"] == "aberta" and asm and role and role.place == place and asm["start"] - 20 <= now < asm["end"]:
            return True
    return False


def role_actions(world: "World", prof: str) -> set[str]:
    return {a.id for a in world.data.actions.values() if prof in a.conditions.professions}


def assume(world: "World", cid: str, vac: dict, mode: str) -> None:
    """`cid` assume a profissão do morto: profissão, local de trabalho e a rotina do papel."""
    prof_id = vac["profession"]
    prof = world.data.professions[prof_id]
    dead = vac["dead"]
    old = world.data.characters[cid]
    dead_char = world.data.characters[dead]
    keep = {"trabalhar"} | role_actions(world, prof_id) | role_actions(world, old.profession)
    routine = [b for b in old.routine if b.action not in keep]
    routine += [b for b in dead_char.routine if b.action in ({"trabalhar"} | role_actions(world, prof_id))]
    workplace = dead_char.workplace or prof.workplace
    apply_override(world, cid, prof_id, workplace, [b.model_dump(by_alias=True) for b in routine])
    vac["status"] = "fechada"
    vac["successor"] = cid
    # quem herda o papel de líder de facção (Padre -> Igreja, Médium -> Seita) vira o líder
    for fid, leader in world.faction_leader_professions().items():
        if leader == prof_id:
            world.life.faction_leaders[fid] = cid
            world.states[cid].faction = fid
    world.say(cid, f"sucessao_{mode}", place=world.states[cid].place, event_type="succession",
              extra={"morto": dead, "objeto": prof.name}, tags=["evento"], importance=3,
              data={"profession": prof_id, "dead": dead, "mode": mode, "from": old.profession},
              fallback="{eu} agora é {objeto}, no lugar de {morto}.")


def apply_override(world: "World", cid: str, profession: str, workplace: str | None, routine: list[dict]) -> None:
    world.life.overrides[cid] = {"profession": profession, "workplace": workplace, "routine": routine}
    _apply_one(world, cid)


def _apply_one(world: "World", cid: str) -> None:
    ov = world.life.overrides.get(cid)
    char = world.data.characters.get(cid)
    if not ov or char is None or ov["profession"] not in world.data.professions:
        return
    from sim.schemas import RoutineBlock

    routine = []
    for b in ov.get("routine", []):
        try:
            block = RoutineBlock.model_validate(b)
        except Exception:
            continue
        if block.action in world.data.actions:
            routine.append(block)
    world.data.characters[cid] = char.model_copy(update={"profession": ov["profession"],
                                                          "workplace": ov.get("workplace"), "routine": routine})
    world.refresh_review_minutes(cid)


def apply_all_overrides(world: "World") -> None:
    for cid in list(world.life.overrides):
        _apply_one(world, cid)
