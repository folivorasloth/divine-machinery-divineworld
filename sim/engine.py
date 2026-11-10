"""O mundo: junta dados, estado, relógio, Utility AI, eventos e persistência.

Uso típico (é o que `python -m tools.run` faz):

    data = load_data_or_raise("data")
    world = World(data, Storage("var/world.sqlite"), speed=600)
    world.bus.subscribe(print_event)
    world.run(until=world.clock.now + timedelta(days=1))   # ou fast=True
    world.close()

Ordem de um tick (seção 4.1 de docs/arquitetura.md):
  1. drenar comandos            2. avançar o relógio (period_changed)
  3. necessidades               4. ações em andamento (terminar as que acabaram)
  5. movimento (chegadas, túneis)
  6. sistemas: solturas (prisão/Limbo), eventos sociais (começo/fim/fracasso);
     de hora em hora: memórias decaem, afinidades voltam devagar, pontos da lei
     somem, facções, ideias de eventos sociais
  7. decisões dos livres + reavaliação de quem está ocupado (interrupção)
  8. salvar no SQLite a cada `salvar_a_cada_minutos`
Só o thread da simulação mexe no estado. API/CLI/MQTT só põem comandos na fila.

A sociedade (Fase 2) mora em módulos próprios — `memory`, `relations`,
`gossip`, `law`, `factions`, `structures`, `social_events` — e este arquivo
só liga os pontos: quando uma ação começa ou termina, o que muda no mundo.

Fase 3: `lifecycle` (morte, funeral, luto, nascimentos, sucessão, fantasmas),
`creatures`, `weather`, `screens` (névoa) e `director` (tensão e eventos).
O `World` trabalha numa CÓPIA rasa dos dados (`self.data.characters` é um
dicionário só dele): nascimentos e sucessões mudam essa cópia, nunca o
`WorldData` de quem chamou (nem os YAML originais).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from datetime import datetime, timedelta

from sim import commands as commands_mod
from sim import creatures as creatures_mod
from sim import llm as llm_mod
from sim import factions as factions_mod
from sim import lifecycle
from sim import gossip as gossip_mod
from sim import law as law_mod
from sim import needs as needs_mod
from sim import rng as rng_mod
from sim import social_events as social_mod
from sim import presence as presence_mod
from sim import speech, utility
from sim import text as text_mod
from sim.clock import WorldClock
from sim.director import Director
from sim.events import Event, EventBus
from sim.loader import WorldData
from sim.memory import Memories, Memory
from sim.pathfinding import passable, path_from, shortest_paths
from sim.persistence import Storage
from sim.relations import Relations
from sim.screens import Screens
from sim.schemas import Action, time_to_minutes
from sim.state import Activity, CharacterState, MoveStep, Plan
from sim.structures import STATE_NAMES, Structures
from sim.weather import Weather

log = logging.getLogger("sim.engine")

IDLE = "_parado"  # "ação" interna: ficar parado quando nada vale a pena
IDLE_MINUTES = 10
MAX_CATCHUP_TICKS = 600  # no tempo real, no máximo isso de ticks atrasados por rodada
VISITORS_KEEP_MINUTES = 24 * 60  # quem passou por cada lugar (para suspeitar de sumiços)


@dataclass
class Command:
    cmd: str
    arg: str = ""
    id: str = ""
    # Fase 4: dados extras (comandos internos: resposta do LLM...) e um
    # concurrent.futures.Future que recebe o resultado (a API espera por ele)
    payload: dict | None = None
    reply: Any = None


class World:
    def __init__(
        self,
        data: WorldData,
        storage: Storage | None = None,
        *,
        seed: int | None = None,
        speed: float | None = None,
        start: datetime | None = None,
        weather_fetcher=None,
    ):
        # cópia rasa: nascimentos e sucessões mudam só o dicionário deste mundo
        data = dataclasses.replace(data, characters=dict(data.characters))
        self.data = data
        self.storage = storage
        self.bus = EventBus()
        self.commands: queue.Queue[Command] = queue.Queue()
        self._lock = threading.Lock()
        self._snapshot: dict = {}
        self.paused = False
        self.stop_requested = False
        self.ticks = 0
        self._last_event_id = 0
        self.realtime = False  # True só em run(fast=False): libera o clima real (Open-Meteo)
        self.frozen_rows: dict[str, dict] = {}
        # Fase 2: a sociedade
        self.relations = Relations(data)
        self.memories = Memories(data.world.memory)
        self.structures = Structures(data)
        self.law = law_mod.Law()
        self.social = social_mod.SocialEvents()
        self.goals: list[dict] = []  # objetivos temporários (convites, ordens do Chefe, diretor)
        self.stolen: list[dict] = []  # objetos roubados (e onde foram parar)
        self.visitors: dict[str, list[list]] = {}  # lugar -> [[minuto, id], ...]
        self.relation_marks: list[list[str]] = []  # [a, b, "inimigos"|"amigos"] já anunciados
        self._next_hourly: float | None = None
        # Fase 3
        self.life = lifecycle.LifeState()
        self.screens = Screens()
        self.creatures = creatures_mod.Creatures()
        self.director = Director()
        self.director.watched = set(data.world.director.event_weights)
        self.blocked_places: frozenset[str] = frozenset()
        self._mult_cache: dict[str, tuple[dict, dict]] = {}
        # Fase 4: o Criador, o LLM opcional (o servidor liga) e o histórico dos comandos
        self.llm: llm_mod.LLM | None = None
        self.command_log: deque[dict] = deque(maxlen=100)
        self._command_seq = 0

        if storage is not None:
            self.bus.subscribe(storage.insert_event)
        self.bus.subscribe(lambda ev: self.director.observe(self, ev))

        resumed = storage is not None and storage.has_world()
        self.resumed = resumed
        society = {}
        if resumed:
            saved_seed = int(storage.get_meta("seed"))
            self.rng, self.seed = rng_mod.make_rng(saved_seed)
            rng_mod.load_state(self.rng, storage.get_meta("rng_state"))
            self.clock = WorldClock(data.world.clock, datetime.fromisoformat(storage.get_meta("world_time")))
            self.speed = speed if speed is not None else float(storage.get_meta("speed", data.world.clock.multiplier))
            self.paused = storage.get_meta("paused", "0") == "1"
            self._last_event_id = int(storage.get_meta("last_event_id", "0"))
            self.relations.values = storage.load_relations()
            self.memories.load(storage.load_memories(), int(storage.get_meta("next_memory_id", "1")))
            self.structures.load(storage.load_structures())
            society = json.loads(storage.get_meta("society", "{}"))
        else:
            self.rng, self.seed = rng_mod.make_rng(seed if seed is not None else data.world.seed)
            self.clock = WorldClock(data.world.clock, start or WorldClock.parse_start(data.world.clock, None))
            self.speed = speed if speed is not None else data.world.clock.multiplier
        self.law.load(society.get("law", {}))
        self.social.load(society.get("social", {}))
        self.goals = society.get("goals", [])
        self.stolen = society.get("stolen", [])
        self.visitors = society.get("visitors", {})
        self.relation_marks = society.get("relation_marks", [])
        self._next_hourly = society.get("next_hourly")
        if self._next_hourly is None:
            self._next_hourly = self._now_minutes() + 60
        self.life = lifecycle.LifeState.from_json(society.get("life", {}))
        if not self.life.created:
            self.life.created = self.clock.iso()
        self.weather = Weather(self, fetcher=weather_fetcher)
        self.weather.load(society.get("weather", {}))
        self.screens.load(society.get("screens", {}))
        self.creatures.load(society.get("creatures", {}))
        self.director.load(society.get("director", {}))
        self.creator = commands_mod.CreatorState.from_json(society.get("creator"))

        self.states: dict[str, CharacterState] = {}
        self._review_minutes: dict[str, set[int]] = {}
        self._load_characters()
        lifecycle.apply_all_overrides(self)
        self.refresh_blocked()
        factions_mod.init_membership(self)
        self._period = self.clock.period()
        self._next_save = self._now_minutes() + data.world.storage.save_every_minutes

        if resumed:
            self.emit("system", "O mundo acorda de onde parou.", tags=["sistema"],
                      data={"seed": self.seed, "resumed": True})
        else:
            self.emit("system", "O mundo começa.", tags=["sistema"], importance=1,
                      data={"seed": self.seed, "resumed": False})
        for cid in self.frozen_rows:
            self.emit("system", f"'{cid}' está no banco mas não existe mais em data/characters: ficou congelado.",
                      tags=["sistema"], data={"frozen": cid})
        self.save()
        self._update_snapshot()

    # ===================================================================== setup
    def _load_characters(self) -> None:
        rows = self.storage.load_characters() if self.storage else {}
        for cid, char in self.data.characters.items():
            row = rows.pop(cid, None)
            if row is None:  # personagem novo: entra em casa, com as necessidades iniciais
                st = CharacterState(id=cid, place=char.home, needs=needs_mod.initial_needs(self.data, char))
                st.faction = char.faction
                # casal do YAML (relação "tipo: casal") já é casado
                st.spouse = next((r.with_ for r in char.relations if r.kind == "casal"), None)
            else:
                place = row["place"] if row["place"] in self.data.places else char.home
                st = CharacterState(id=cid, place=place, needs=row["needs"], alive=row["alive"],
                                    last_action=row["last_action"])
                # necessidade nova no world.yaml: entra com o valor inicial
                for nid, value in needs_mod.initial_needs(self.data, char).items():
                    st.needs.setdefault(nid, value)
                flags = row["flags"]
                st.cooldowns = flags.get("cooldowns", {})
                st.recent_lines = flags.get("recent_lines", [])
                st.faction = flags.get("faction", char.faction)
                st.jailed_until = flags.get("jailed_until")
                st.limbo_until = flags.get("limbo_until")
                st.spouse = flags.get("spouse")
                st.prev_place = flags.get("prev_place")
                st.extra_traits = [t for t in row.get("extra_traits", []) if t in self.data.traits]
                try:
                    st.restore_current(row["current"])
                except (TypeError, KeyError):
                    st.activity, st.plan = None, None
                if st.activity and st.activity.action not in self.data.actions and st.activity.action != IDLE:
                    st.activity = None
                if st.plan and st.plan.action not in self.data.actions:
                    st.plan = None
            if row is None:
                self._start_asleep_if_bedtime(st)
                # espalha as reavaliações para não acontecerem todas no mesmo tick
                st.next_review = self._now_minutes() + self.rng.uniform(0, self.data.world.decision.reevaluate_minutes)
            else:
                st.next_review = row["flags"].get("next_review", self._now_minutes())
                st.pending_review = row["flags"].get("pending_review", False)
            self.states[cid] = st
            self._review_minutes[cid] = self._trigger_minutes(char)
        self.frozen_rows = rows  # sobraram: estão no banco mas não no YAML (não apaga nada)

    def _start_asleep_if_bedtime(self, st: CharacterState) -> None:
        """Mundo NOVO criado no meio da noite: quem tem um bloco de rotina de dormir
        (ação com `dormindo: true`) valendo agora já começa dormindo em casa, até o
        fim do bloco. Evita a cidade inteira acordada às 3h no primeiro dia."""
        char = self.data.characters[st.id]
        minute = self.clock.minute_of_day()
        for block in utility.active_routine(char, minute):
            action = self.data.actions.get(block.action)
            if not (action and action.active and action.sleeping):
                continue
            place = block.place or char.home
            if action.conditions.own_place == "casa":
                place = char.home
            end = time_to_minutes(block.end)
            remaining = (end - minute) % 1440 or 1
            st.place = place
            st.activity = Activity(action=action.id, place=place, duration=float(remaining))
            return

    def _trigger_minutes(self, char) -> set[int]:
        """Minutos do dia em que o personagem reavalia na hora, mesmo ocupado: começo
        de cada bloco da rotina e começo das janelas `horarios` das ações. É assim que
        o Padre larga o trabalho exatamente quando abre a janela do sino."""
        minutes = {time_to_minutes(b.start) % 1440 for b in char.routine}
        for action in self.data.actions.values():
            if action.active and action.conditions.hours:
                if action.conditions.professions and char.profession not in action.conditions.professions:
                    continue
                if action.conditions.characters and char.id not in action.conditions.characters:
                    continue
                minutes |= {time_to_minutes(w.start) % 1440 for w in action.conditions.hours}
        return minutes

    # ================================================================ utilidades
    def _now_minutes(self) -> float:
        return self.clock.now.timestamp() / 60.0

    now_minutes = _now_minutes

    def iso_of(self, minute: float) -> str:
        return datetime.fromtimestamp(minute * 60, self.clock.tz).isoformat(timespec="seconds")

    def hhmm_of(self, minute: float) -> str:
        return datetime.fromtimestamp(minute * 60, self.clock.tz).strftime("%H:%M")

    def names(self) -> dict[str, str]:
        return self.data.names()

    @property
    def affinities(self) -> dict[tuple[str, str], float]:
        return self.relations.values

    def affinity(self, a: str, b: str) -> float:
        return self.relations.get(a, b)

    def change_affinity(self, a: str, b: str, delta: float) -> None:
        before, after = self.relations.change(a, b, delta)
        if before == after:
            return
        cfg = self.data.world.relations
        initial = self.relations.initial(a, b)
        mark = None
        if after <= cfg.enemies_below < before and initial > cfg.enemies_below:
            mark = "inimigos"
        elif after >= cfg.friends_above > before and initial < cfg.friends_above:
            mark = "amigos"
        if mark and [a, b, mark] not in self.relation_marks:
            self.relation_marks.append([a, b, mark])
            self.say(a, "virou_inimigo" if mark == "inimigos" else "virou_amigo", target=b,
                     place=self.states[a].place, event_type="relation_changed", importance=1,
                     tags=["briga" if mark == "inimigos" else "conversa"],
                     data={"affinity": round(after, 1), "initial": initial, "mark": mark},
                     fallback="{eu} e {outro} agora são " + mark + ".")

    def traits_of(self, cid: str) -> list[str]:
        return self.data.all_traits(cid, self.states[cid].extra_traits if cid in self.states else [])

    def is_asleep(self, cid: str) -> bool:
        st = self.states[cid]
        act = self.data.actions.get(st.activity.action) if st.activity else None
        return bool(act and act.sleeping)

    def emit(self, type: str, text: str = "", *, actors=(), place=None, tags=(), importance=0, data=None) -> Event:
        self._last_event_id += 1
        ev = Event(type=type, ts=self.clock.iso(), text=text, actors=list(actors), place=place,
                   tags=list(tags), importance=importance, data=dict(data or {}), id=self._last_event_id)
        self.bus.publish(ev)
        return ev

    def _recall(self, cid: str, target: str | None):
        def recall(kinds: list[str]) -> str | None:
            mem = self.memories.strongest(cid, kinds=kinds, involving=target)
            if mem is None:
                return None
            return self.memories.phrase(mem, "lembranca")
        return recall

    def _speech_ctx(self, cid: str, place: str, target: str | None = None,
                    extra: dict | None = None) -> speech.SpeechContext:
        st = self.states[cid]
        extra = dict(extra or {})
        genders = {"eu": self.data.characters[cid].pronoun}
        if target in self.data.characters:
            genders["outro"] = self.data.characters[target].pronoun
        if extra.get("terceiro") in self.data.characters:
            genders["terceiro"] = self.data.characters[extra["terceiro"]].pronoun
        return speech.SpeechContext(
            speaker=cid, place=place, period=self.clock.period(), hour=extra.pop("hora", None) or self.clock.hhmm(),
            period_name=self.clock.period_name(), weather=self.weather_label,
            mood=needs_mod.mood(self.data, st.needs), needs=st.needs, target=target,
            extra=extra, genders=genders, recall=self._recall(cid, target),
            weather_kind=self.weather.kind, dead=extra.get("morto"),
        )

    def say(self, speaker: str, situation: str, *, target: str | None = None, place: str | None = None,
            event_type: str = "speech", extra: dict | None = None, tags=(), importance: int = 0,
            data: dict | None = None, fallback: str | None = None) -> Event | None:
        """Uma fala/narração de uma situação de data/lines (ou `fallback` se não houver)."""
        place = place or self.states[speaker].place
        ctx = self._speech_ctx(speaker, place, target, extra)
        line = speech.pick_line(self.data, situation, ctx, self.rng, self.states[speaker].recent_lines)
        if line is None and fallback:
            line = speech.fill_narration(self.data, fallback, ctx, self.rng)
        if line is None:
            return None
        actors = [speaker] + ([target] if target else [])
        edata = {"situation": situation, **(data or {})}
        ocfg = self.data.world.ollama
        if importance >= ocfg.min_importance and situation in ocfg.situations and self.llm_usable():
            # Fase 4: o LLM reescreve a fala num thread próprio; ela sai quando ele
            # responder (ou o template, se falhar). O mundo não espera.
            payload = {"event_type": event_type, "line": line, "actors": actors, "place": place,
                       "tags": list(tags), "importance": importance, "data": edata}
            prompt = llm_mod.build_prompt(self, speaker, situation, line, place, target)

            def done(answer, payload=payload):
                self.submit_internal("_llm_fala", {**payload, "llm": answer})

            if self.llm.rewrite(prompt, done):
                return None
        return self.emit(event_type, line, actors=actors, place=place, tags=tags, importance=importance,
                         data=edata)

    narrate = say

    def event_text(self, actor: str, template: str, event_type: str, *, place: str, target: str | None = None,
                   tags=(), importance: int = 0, extra: dict | None = None, data: dict | None = None) -> Event:
        ctx = self._speech_ctx(actor, place, target, extra)
        text = speech.fill_narration(self.data, template, ctx, self.rng)
        actors = [actor] + ([target] if target else [])
        return self.emit(event_type, text, actors=actors, place=place, tags=tags, importance=importance, data=data)

    def list_names(self, ids: list[str]) -> str:
        tokens = ["{@" + i + "}" for i in ids]
        if not tokens:
            return "ninguém"
        if len(tokens) == 1:
            return tokens[0]
        return ", ".join(tokens[:-1]) + " e " + tokens[-1]

    def _present(self) -> dict[str, list[str]]:
        present: dict[str, list[str]] = {}
        for cid, st in self.states.items():
            if st.alive and not st.frozen and not st.moving and not st.away:
                present.setdefault(st.place, []).append(cid)
        return present

    def present_at(self, place: str) -> list[str]:
        return sorted(cid for cid, st in self.states.items()
                      if st.alive and not st.frozen and not st.moving and not st.away and st.place == place)

    def decision_context(self) -> utility.DecisionContext:
        return utility.DecisionContext(
            data=self.data, minute_of_day=self.clock.minute_of_day(), hour=self.clock.hour_float(),
            period=self.clock.period(), is_night=self.clock.is_night(), now_minutes=self._now_minutes(),
            states=self.states, present=self._present(), affinity=self.affinity, world=self, goals=self.goals,
            blocked=self.blocked_places, tension=self.director.tension,
        )

    def _living(self) -> list[CharacterState]:
        return [st for st in self.states.values() if st.alive and not st.frozen and not st.away]

    # ------------------------------------------------------------- memórias
    def remember(self, owner: str, kind: str, *, subject: str | None, object: str | None = None,
                 place: str | None = None, factor: float = 1.0, heard_from: str | None = None,
                 distorted: bool = False, detail: str = "", secret: bool = False) -> tuple[Memory | None, bool]:
        st = self.states.get(owner)
        if st is None or not st.alive or kind not in self.data.world.memory.kinds:
            return None, False
        mem, new = self.memories.form(owner, kind, subject=subject, object=object, place=place, ts=self.clock.iso(),
                                      minute=self._now_minutes(), factor=factor, heard_from=heard_from,
                                      distorted=distorted, detail=detail, secret=secret)
        if mem is not None and new and subject and subject != owner:
            k = self.data.world.memory.kinds[kind]
            self.change_affinity(owner, subject, k.affinity * factor)
        return mem, new

    def remember_scene(self, kind: str, *, subject: str | None, object: str | None = None, place: str,
                       detail: str = "", witnesses: bool = True) -> None:
        """Quem fez, com quem foi e quem estava acordado no lugar (testemunhas) lembram."""
        involved = [c for c in (subject, object) if c]
        for cid in dict.fromkeys(involved):
            self.remember(cid, kind, subject=subject, object=object, place=place, detail=detail)
        if not witnesses:
            return
        factor = self.data.world.memory.witness_factor
        for cid in self.present_at(place):
            if cid not in involved and not self.is_asleep(cid):
                self.remember(cid, kind, subject=subject, object=object, place=place, detail=detail, factor=factor)

    def gossip_value(self, speaker: str, listener: str) -> float:
        return gossip_mod.best(self, speaker, listener)[1]

    def report_value(self, cid: str) -> float:
        return law_mod.best_report(self, cid)[1]

    # ------------------------------------------------------------- objetivos
    def add_goal(self, *, who: str | None, action: str, place: str | None, bonus: float, start: float,
                 end: float, source: str, penalty: bool = False) -> None:
        goal = {"who": who, "action": action, "place": place, "bonus": bonus, "start": start,
                "end": end, "source": source}
        if penalty:  # bônus < 1 que vale (Fase 4: "parem de brigar" deixa brigar menos atraente)
            goal["penalty"] = True
        self.goals.append(goal)

    def remove_goals(self, source: str) -> None:
        self.goals[:] = [g for g in self.goals if g["source"] != source]

    # -------------------------------------------------------------- traços
    def draw_new_trait(self, cid: str) -> str | None:
        """Traço novo sorteado (quem volta do Limbo volta estranho)."""
        current = set(self.traits_of(cid))
        blocked = set(current)
        for tid in current:
            if tid in self.data.traits:
                blocked |= set(self.data.traits[tid].opposites)
        options = sorted(t.id for t in self.data.traits.values()
                         if t.drawable and t.id not in blocked and not (set(t.opposites) & current))
        return self.rng.choice(options) if options else None

    def interrupt(self, cid: str) -> None:
        """Larga o que está fazendo agora (preso, fugindo, levando uma pegadinha...)."""
        st = self.states[cid]
        if st.activity is not None:
            self._finish_activity(st, interrupted=True)
        st.plan = None

    # ================================================================ Fase 3
    @property
    def weather_label(self) -> str:
        return self.weather.label

    def refresh_review_minutes(self, cid: str) -> None:
        if cid in self.data.characters:
            self._review_minutes[cid] = self._trigger_minutes(self.data.characters[cid])

    def refresh_blocked(self) -> None:
        """Lugares na névoa (telas desligadas): ninguém entra, quem está dentro fica."""
        self.blocked_places = self.screens.fogged_places(self)

    def blocked_for(self, cid: str) -> frozenset[str]:
        """A névoa não vale para quem é imune (o Mike)."""
        if "nevoa" in self.data.characters[cid].immunities:
            return frozenset()
        return self.blocked_places

    def trapped(self, cid: str) -> bool:
        return self.states[cid].place in self.blocked_for(cid)

    def send_to(self, cid: str, action_id: str, destination: str, target: str | None = None) -> None:
        self._send(cid, action_id, destination, target)

    def lifecycle_roll(self, when: str, cid: str, *, place: str | None = None, by_creature=None,
                       factor: float = 1.0, action: str | None = None, by: str | None = None) -> bool:
        detail = ""
        if by_creature is not None:
            cre = self.data.creatures.get(by_creature.kind)
            detail = cre.name if cre else by_creature.kind
        return lifecycle.roll(self, when, cid, action=action, place=place, by=by, factor=factor, detail=detail)

    def faction_leader_professions(self) -> dict[str, str]:
        """facção -> profissão do líder original (o Padre lidera a Igreja; quem virar padre, também)."""
        out = {}
        for fid, fac in self.data.world.factions.items():
            if fac.leader in self.data.characters:
                out[fid] = self.data.characters[fac.leader].profession
        return out

    def leader_of(self, fid: str) -> str | None:
        if fid in self.life.faction_leaders:
            return self.life.faction_leaders[fid]
        fac = self.data.world.factions.get(fid)
        return fac.leader if fac else None

    def _multipliers(self, cid: str) -> tuple[dict, dict]:
        """(taxas de necessidades, notas de ações) por clima, luto e consequências. Cache por tick."""
        cached = self._mult_cache.get(cid)
        if cached is not None:
            return cached
        rates, actions = lifecycle.multipliers(self, cid)
        for key in self.weather.effect_keys():
            eff = self.data.world.weather.effects.get(key)
            if eff is None:
                continue
            for n, m in eff.needs.items():
                rates[n] = rates.get(n, 1.0) * m
            for a, m in eff.actions.items():
                actions[a] = actions.get(a, 1.0) * m
        self._mult_cache[cid] = (rates, actions)
        return rates, actions

    def score_multiplier(self, cid: str, action: Action, place: str) -> list[tuple[str, float]]:
        """Fatores extras da nota (Fase 3): luto/consequências, clima, chuva em lugar externo."""
        out = []
        _rates, actions = self._multipliers(cid)
        m = actions.get(action.id)
        if m is not None and m != 1:
            out.append(("luto/clima", m))
        # Fase 4: decretos do Chefe (proibido/liberado) e gente no quarto (o olhar)
        m = commands_mod.decree_multiplier(self, cid, action.id)
        if m is not None and m != 1:
            out.append(("decreto", m))
        m = presence_mod.stare_multiplier(self, action.id)
        if m is not None and m != 1:
            out.append(("presença no quarto", m))
        if self.data.places[place].environment == "externo" and not action.sleeping:
            outdoor = 1.0
            for key in self.weather.effect_keys():
                eff = self.data.world.weather.effects.get(key)
                if eff is not None:
                    outdoor *= eff.outdoor
            if outdoor != 1:
                out.append((f"clima {self.weather.kind} lá fora", outdoor))
        return out

    def danger_at(self, place: str, is_night: bool) -> float:
        p = self.data.places[place]
        base = p.danger_night if (is_night and p.danger_night is not None) else p.danger
        return min(100.0, base + self.creatures.danger_at(self, place))

    # ===================================================================== tick
    def tick(self) -> None:
        dt = self.clock.step_minutes
        self._drain_commands()
        self.clock.advance(dt)
        self.ticks += 1
        period = self.clock.period()
        if period != self._period:
            self._period = period
            self.emit("period_changed", f"Começa a {self.clock.period_name(period).lower()}.",
                      tags=["sistema"], data={"period": period, "is_night": self.clock.is_night()})

        self._mult_cache = {}
        self.weather.update()
        night = self.clock.is_night()
        for st in self._living():
            self._update_needs(st, night, dt)
        for st in self._living():
            self._advance_activity(st, dt)
        for st in self._living():
            self._advance_movement(st, dt)
        law_mod.check_releases(self)
        social_mod.update(self)
        lifecycle.update(self)
        creatures_mod.update(self)
        commands_mod.update(self)
        if self._now_minutes() >= self._next_hourly:
            self._next_hourly += 60
            self._hourly()
        self.director.update(self)
        self._decide_all()

        if self._now_minutes() >= self._next_save:
            self.save()
            self._next_save = self._now_minutes() + self.data.world.storage.save_every_minutes
        elif self.storage is not None:
            self.storage.commit_if_dirty()
        self._update_snapshot()

    def _hourly(self) -> None:
        self.memories.decay(1.0)
        self.relations.drift(1.0)
        law_mod.daily_decay(self, 1.0)
        factions_mod.check_all(self)
        now = self._now_minutes()
        self.goals[:] = [g for g in self.goals if g["end"] > now]
        for place in list(self.visitors):
            self.visitors[place] = [v for v in self.visitors[place] if v[0] >= now - VISITORS_KEEP_MINUTES]
        social_mod.plan_hourly(self)
        lifecycle.hourly(self)
        creatures_mod.hourly(self)

    # ------------------------------------------------------------ necessidades
    def _update_needs(self, st: CharacterState, night: bool, dt: float) -> None:
        char = self.data.characters[st.id]
        action = self.data.actions.get(st.activity.action) if st.activity else None
        rates, _actions = self._multipliers(st.id)
        needs_mod.natural_change(self.data, char, st.needs, night, dt, sleeping=bool(action and action.sleeping),
                                 extra_traits=st.extra_traits, extra_mult=rates)
        # medo do clima (o Esquisito e a chuva): medos.gatilho igual ao tipo de clima (ou "chuva")
        wcfg = self.data.world.weather
        if wcfg.fear_per_hour and char.fears:
            triggers = {f.trigger for f in char.fears}
            if self.weather.kind in triggers or ("chuva" in triggers and self.weather.is_rain()):
                if self.data.places[st.place].environment == "externo" or self.weather.is_rain():
                    st.needs["medo"] = needs_mod.clamp(st.needs.get("medo", 0) + wcfg.fear_per_hour * dt / 60)
        if action is not None and st.activity.duration > 0:
            fraction = dt / st.activity.duration
            effects = action.failure.effects if (st.activity.failed and action.failure) else action.effects
            needs_mod.apply_effect(st.needs, effects.needs, fraction)
            if not st.activity.failed:
                for tid in self.traits_of(st.id):
                    if tid in action.effects.by_trait:
                        needs_mod.apply_effect(st.needs, action.effects.by_trait[tid], fraction)
                if action.repairs:
                    self._repair(st, action, fraction)

    def _repair(self, st: CharacterState, action: Action, fraction: float) -> None:
        here = [s for s in self.structures.at(st.activity.place) if s.hp < 100]
        if not here:
            return
        target = min(here, key=lambda s: (s.hp, s.id))
        before, after = self.structures.change(target.id, action.repairs * fraction)
        if target.hp >= 100:
            target.marks.clear()  # pintou por cima da pichação
        if before != after:
            # (F4) "destruído -> danificado" é só o começo da obra; "consertado" é quando fica inteiro
            situation = "estrutura_consertada" if after == "inteiro" else "estrutura_reerguida"
            self.say(st.id, situation, place=target.place, event_type="structure_changed",
                     tags=["trabalho"], importance=1, extra={"objeto": "{@" + target.id + "}"},
                     data={"structure": target.id, "from": before, "to": after, "hp": round(target.hp)},
                     fallback="{eu} termina o conserto de {objeto}.")

    def damage_structure(self, place: str, amount: float, by: str, cause: str) -> None:
        here = self.structures.at(place)
        if not here or amount <= 0:
            return
        target = self.rng.choice(sorted(here, key=lambda s: s.id))
        before, after = self.structures.change(target.id, -amount)
        if before != after:
            self.say(by, f"estrutura_{after}", place=place, event_type="structure_changed", tags=["briga"],
                     importance=2 if after == "destruido" else 1,
                     extra={"objeto": "{@" + target.id + "}"},
                     data={"structure": target.id, "from": before, "to": after, "hp": round(target.hp), "cause": cause},
                     fallback="{objeto} ficou " + STATE_NAMES[after] + ".")
        return target

    # ---------------------------------------------------- ações em andamento
    def _advance_activity(self, st: CharacterState, dt: float) -> None:
        if st.activity is None:
            return
        st.activity.elapsed += dt
        if st.activity.done:
            self._finish_activity(st, interrupted=False)

    def _finish_activity(self, st: CharacterState, interrupted: bool) -> None:
        act = st.activity
        st.activity = None
        if act is None or act.action == IDLE:
            return
        action = self.data.actions[act.action]
        fraction = min(1.0, act.elapsed / act.duration) if act.duration else 1.0
        # efeitos no alvo e afinidades: no fim, proporcionais ao que durou
        if act.target and act.target in self.states and not act.failed:
            target_st = self.states[act.target]
            if not act.target_applied:
                needs_mod.apply_effect(target_st.needs, action.effects.target_needs, fraction)
            self.change_affinity(st.id, act.target, action.effects.affinity * fraction)
            self.change_affinity(act.target, st.id, action.effects.target_affinity * fraction)
        if not act.failed:
            for other, delta in action.effects.affinity_with.items():
                if other != st.id:
                    self.change_affinity(st.id, other, delta * fraction)
        st.last_action = act.action
        if action.cooldown_minutes:
            st.cooldowns[act.action] = self._now_minutes() + action.cooldown_minutes
        text = ""
        if action.narration_end:
            text = speech.fill_narration(self.data, action.narration_end,
                                         self._speech_ctx(st.id, act.place, act.target), self.rng)
        self.emit("action_finished", text, actors=[st.id] + ([act.target] if act.target else []),
                  place=act.place, tags=action.tags, data={"action": act.action, "interrupted": interrupted,
                                                           "minutes": round(act.elapsed), "failed": act.failed})
        # consequências (Fase 2)
        damage = (action.failure.effects.structure_damage if (act.failed and action.failure)
                  else action.effects.structure_damage)
        if damage and not interrupted:
            self.damage_structure(act.place, damage, st.id, act.action)
        if act.failed or interrupted:
            return
        if action.special == "recrutar" and act.target:
            factions_mod.check(self, act.target)
        if action.special == "roubar":
            self._hide_loot(st, act.place)
        if action.special == "criatura":
            creatures_mod.fight(self, st.id, act.place)
        if action.event == "fight" and act.target in self.states:
            # briga de pastelão às vezes acaba mal de verdade (morte.causas com quando: briga)
            if not self.lifecycle_roll("briga", act.target, place=act.place, by=st.id, action=act.action):
                self.lifecycle_roll("briga", st.id, place=act.place, by=act.target, action=act.action, factor=0.5)
            if not st.alive:
                return
        if action.chase_chance and act.target and self.rng.random() < action.chase_chance:
            if self.states[act.target].alive:
                self._chase(st.id, act.target, act.place)

    def _start_activity(self, st: CharacterState, action_id: str, place: str, target: str | None,
                        duration: float, score: float) -> None:
        st.plan = None
        if action_id == IDLE:
            st.activity = Activity(action=action_id, place=place, duration=duration, target=target, score=score)
            return
        action = self.data.actions[action_id]
        # foi atrás de alguém e a pessoa já não está (ou dormiu)?
        if target and action.kind == "social" and not action.automatic:
            tst = self.states[target]
            if tst.place != place or tst.moving or tst.away or self.is_asleep(target):
                self.say(st.id, "nao_achou", target=target, place=place, event_type="missed",
                         data={"action": action_id}, fallback="{eu} procura {outro} e não acha.")
                st.last_action = action_id
                return
        failed = False
        if action.failure:
            chance = action.failure.chance
            for tid in self.traits_of(st.id):
                trait = self.data.traits.get(tid)
                if trait:
                    chance *= trait.effects.failure
            failed = self.rng.random() < min(0.95, chance)
        # comportamentos especiais que decidem o que vai ser dito (ou se nem acontece)
        extra, edata = {}, {}
        if action.special:
            ok = self._special_before(st, action, place, target, failed, extra, edata)
            if not ok:
                st.last_action = action_id
                return
        st.activity = Activity(action=action_id, place=place, duration=duration, target=target, score=score,
                               failed=failed)
        actors = [st.id] + ([target] if target else [])
        situation = action.speech
        if failed and action.failure and action.failure.speech:
            situation = action.failure.speech
        elif edata.get("situation"):
            situation = edata.pop("situation")
        elif target and situation == action.speech:
            # Fase 4: o assunto do momento (ressurreição, Aparição, ordem do Chefe)
            topic = commands_mod.topic_for(self, action_id, st.id, target)
            if topic is not None:
                situation, more = topic
                extra.update(more)
                edata["topic"] = situation
        spoken = None
        chance = 1.0 if (failed or action.special in ("fofoca", "confissao", "denuncia")) else action.speech_chance
        if situation and self.rng.random() < chance:
            spoken = speech.pick_line(self.data, situation, self._speech_ctx(st.id, place, target, extra),
                                      self.rng, st.recent_lines)
        template = action.narration or ("{eu} vai " + action.name[:1].lower() + action.name[1:] + " em {lugar}.")
        if failed and action.failure and action.failure.narration:
            template = action.failure.narration
        narration = speech.fill_narration(self.data, template, self._speech_ctx(st.id, place, target, extra), self.rng)
        kind = "slapstick" if failed else (action.event or "action_started")
        tags = list(action.tags)
        self.emit(kind, narration, actors=actors, place=place, tags=tags, importance=action.importance,
                  data={"action": action_id, "target": target, "minutes": round(duration),
                        "score": round(score, 3), "spoke": spoken is not None, "failed": failed, **edata})
        if spoken:
            self.emit("speech", spoken, actors=actors, place=place, tags=tags,
                      importance=action.importance, data={"situation": situation, "action": action_id})
        # o alvo responde (conversa de verdade tem duas pessoas)
        if target and not failed and action.target_speech and self.rng.random() < action.target_speech_chance:
            reply = speech.pick_line(self.data, action.target_speech, self._speech_ctx(target, place, st.id, extra),
                                     self.rng, self.states[target].recent_lines)
            if reply:
                self.emit("speech", reply, actors=[target, st.id], place=place, tags=tags,
                          data={"situation": action.target_speech, "action": action_id, "reply_to": st.id})
        self._consequences(st, action, place, target, failed, extra)
        if failed:  # pastelão que acaba mal de verdade (morte.causas com quando: falha)
            self.lifecycle_roll("falha", st.id, place=place, action=action_id)

    # ------------------------------------------------------- consequências
    def _consequences(self, st: CharacterState, action: Action, place: str, target: str | None, failed: bool,
                      extra: dict) -> None:
        """O que muda no mundo quando uma ação começa: memórias, lei, efeitos no alvo..."""
        self.visitors.setdefault(place, []).append([self._now_minutes(), st.id])
        if not failed:
            commands_mod.on_action_started(self, st.id, action, place)
        if failed:
            if action.failure and action.failure.memory:
                self.remember_scene(action.failure.memory, subject=st.id, object=None, place=place)
            if action.special == "prender" and target:
                self._flee(target, st.id, place)
            return
        if action.special:
            self._special_after(st, action, place, target, extra)
        if action.reconciles and target:
            self.memories.weaken_between(st.id, target, 0.3)
        if action.memory:
            self.remember_scene(action.memory, subject=st.id, object=target, place=place,
                                detail=extra.get("objeto", ""))
        if action.interrupts_target and target and target in self.states:
            self.interrupt(target)
            needs_mod.apply_effect(self.states[target].needs, action.effects.target_needs, 1.0)
            if st.activity is not None:
                st.activity.target_applied = True
            if action.target_reaction:
                react = self.data.actions[action.target_reaction]
                low, high = react.duration_minutes
                self._start_activity(self.states[target], react.id, place, None,
                                     float(self.rng.randint(low, high)), 0.0)
        if action.signs:
            here = self.structures.at(place)
            if here:
                spot = min(here, key=lambda s: s.id)
                spot.marks.append([st.id, action.infraction or ""])
        if action.observe:
            for other in self.present_at(place):
                ost = self.states[other]
                oact = self.data.actions.get(ost.activity.action) if ost.activity else None
                if other != st.id and oact and action.observe.tag in oact.tags:
                    self.remember(st.id, action.observe.memory, subject=other, place=place)
                    break
        # lei: infração em flagrante, ou o Fiscal chegando e vendo o que acontece
        # (Fase 4: um decreto do Chefe pode proibir ou liberar a ação)
        infraction = commands_mod.infraction_of(self, action)
        if infraction:
            for fiscal in law_mod.enforcers(self):
                if fiscal != st.id and law_mod.watching(self, fiscal, place):
                    if st.activity is not None:
                        st.activity.seen_by_law = True
                    law_mod.register(self, fiscal, st.id, infraction, place, "flagrante")
                    break
        if law_mod.is_enforcer(self, st.id):
            self._fiscal_looks(st.id, place)
        self._check_missing(st, action, place)
        self._check_lost_found(st, action, place)

    def _fiscal_looks(self, fiscal: str, place: str) -> None:
        caught = 0
        for other in self.present_at(place):
            ost = self.states[other]
            act = self.data.actions.get(ost.activity.action) if ost.activity else None
            infraction = commands_mod.infraction_of(self, act) if act else None
            if other == fiscal or not infraction or ost.activity.failed or ost.activity.seen_by_law:
                continue
            ost.activity.seen_by_law = True
            if law_mod.register(self, fiscal, other, infraction, place, "flagrante"):
                caught += 1
                if caught >= self.data.world.law.max_per_look:
                    break
        for s in self.structures.at(place):
            marks, s.marks = s.marks, []
            for who, infraction in marks:
                if who in self.states and infraction:
                    law_mod.register(self, fiscal, who, infraction, place, "assinatura")

    # ---------------------------------------------------- especiais (YAML: especial)
    def special_target_ok(self, action: Action, me: str, other: str) -> bool:
        sp = action.special
        if sp == "fofoca":
            return gossip_mod.best(self, me, other)[0] is not None
        if sp == "prender":
            return other in self.law.warrants and self.states[other].jailed_until is None
        if sp == "denuncia":
            return law_mod.is_enforcer(self, other) and law_mod.best_report(self, me)[0] is not None
        if sp == "confissao":
            return self._confession(me, other) is not None
        if sp == "recrutar":
            return self.states[other].faction != action.faction and other not in factions_mod.leaders(self)
        return True

    def special_place_ok(self, action: Action, me: str, place: str) -> bool:
        if action.repairs and self.structures.damage_at(place) <= 0:
            return False
        sp = action.special
        if sp == "roubar":
            return bool(self._loot_options(place))
        if sp == "ordem_reconstruir":
            return self.structures.worst()[1] > 0
        if sp == "funeral":
            return lifecycle.active_funeral_at(self, place) is not None
        if sp == "tumulo":
            return place == self.data.world.funeral.burial_place and self._grave_to_visit(me) is not None
        if sp == "criatura":
            return bool(self.creatures.at(place)) and "criaturas" not in self.data.characters[me].immunities
        if sp == "assembleia":
            return lifecycle.assembly_active(self, place)
        if sp == "anuncio_criador":
            return commands_mod.announce_ok(self, me)
        if sp == "reuniao_criador":
            return commands_mod.meeting_at(self, place) is not None
        return True

    def _grave_to_visit(self, cid: str) -> str | None:
        """O morto enterrado que `cid` mais sente falta (luto; senão, o de maior afinidade)."""
        buried = {g["cid"] for g in self.life.graves if not g.get("resurrected")
                  and not any(f["dead"] == g["cid"] and f["status"] != "terminado" for f in self.life.funerals)}
        if not buried:
            return None
        grieved = lifecycle.grieved_dead(self, cid)
        if grieved in buried:
            return grieved
        best = max(sorted(buried), key=lambda d: self.affinity(cid, d))
        return best if self.affinity(cid, best) >= 30 else None

    def _confession(self, me: str, priest: str) -> Memory | None:
        best = None
        for m in self.memories.of(me):
            if m.subject == me and m.sentiment < 0 and m.heard_from is None and not self.memories.knows(priest, m):
                if best is None or m.intensity > best.intensity:
                    best = m
        return best

    def _loot_options(self, place: str) -> list[str]:
        taken = {s["name"] for s in self.stolen if s["from_place"] == place and not s.get("returned")}
        return [o for o in self.data.places[place].objects if o not in taken]

    def _special_before(self, st: CharacterState, action: Action, place: str, target: str | None, failed: bool,
                        extra: dict, edata: dict) -> bool:
        """Prepara a ação especial. False = não tem como acontecer agora (não começa)."""
        sp = action.special
        if failed:
            return True
        if sp == "fofoca":
            res = gossip_mod.spread(self, st.id, target, place)
            if res is None:
                return False
            extra.update(res["vars"])
            edata.update(res["data"])
            if res["secret"] and "fofoca_confissao" in self.data.lines:
                edata["situation"] = "fofoca_confissao"
            return True
        if sp == "confissao":
            mem = self._confession(st.id, target)
            if mem is None:
                return False
            self.remember(target, mem.kind, subject=st.id, object=mem.object, place=mem.place, factor=0.9,
                          heard_from=st.id, detail=mem.detail, secret=True)
            extra["lembranca"] = self.memories.phrase(mem, "lembranca")
            edata.update({"memory_kind": mem.kind})
            return True
        if sp == "denuncia":
            mem, _v = law_mod.best_report(self, st.id)
            if mem is None:
                return False
            extra.update({"terceiro": mem.subject, "fato": self.memories.phrase(mem, "fato")})
            edata.update({"about": mem.subject, "memory_kind": mem.kind})
            return True
        if sp == "roubar":
            options = self._loot_options(place)
            if not options:
                return False
            extra["objeto"] = self.rng.choice(options)
            return True
        if sp == "recrutar":
            fac = self.data.world.factions.get(action.faction)
            extra["faccao"] = fac.name if fac else action.faction
            return True
        if sp == "ordem_reconstruir":
            where, damage = self.structures.worst()
            if where is None:
                return False
            extra["objeto"] = "{@" + where + "}"
            edata["where"] = where
            return True
        if sp == "prender":
            w = self.law.warrants.get(target)
            if not w:
                return False
            inf = self.data.world.law.infractions.get(w["infraction"])
            extra["infracao"] = inf.name if inf else w["infraction"]
            return True
        if sp == "funeral":
            fun = lifecycle.active_funeral_at(self, place)
            if fun is None:
                return False
            dead = fun["dead"]
            extra["morto"] = dead
            edata.update({"dead": dead, "funeral": fun["id"]})
            # cada um reage do seu jeito: primeiro as falas da personalidade (Fool, Florista,
            # Músico, Dama...); senão, pela afinidade com o morto
            aff = self.affinity(st.id, dead)
            ctx = self._speech_ctx(st.id, place, None, extra)
            own = [ln for ln in self.data.lines.get("funeral_personalidade", []) if speech.matches(ln, ctx, self.data)]
            if own and self.rng.random() < 0.7:
                edata["situation"] = "funeral_personalidade"
            elif aff >= 40:
                edata["situation"] = "funeral_amigo"
            elif aff <= -25:
                edata["situation"] = "funeral_inimigo"
            else:
                edata["situation"] = "funeral"
            return True
        if sp == "tumulo":
            dead = self._grave_to_visit(st.id)
            if dead is None:
                return False
            extra["morto"] = dead
            edata["dead"] = dead
            return True
        if sp == "anuncio_criador":
            return commands_mod.before_announce(self, st.id, place, extra, edata)
        if sp == "criatura":
            here = self.creatures.at(place)
            if not here:
                return False
            cre = self.data.creatures.get(here[0].kind)
            extra["objeto"] = here[0].service or (cre.name if cre else here[0].kind)
            edata["creature"] = here[0].kind
            return True
        return True

    def _special_after(self, st: CharacterState, action: Action, place: str, target: str | None,
                       extra: dict) -> None:
        sp = action.special
        if sp == "fofoca" and target and law_mod.is_enforcer(self, target):
            # contaram ao Fiscal uma infração (talvez com o culpado errado!)
            heard = [m for m in self.memories.of(target) if m.heard_from == st.id and not m.reported]
            for m in heard[-1:]:
                k = self.data.world.memory.kinds.get(m.kind)
                if k and k.infraction and m.subject:
                    m.reported = True
                    law_mod.register(self, target, m.subject, k.infraction, place, "denuncia", reporter=st.id)
        elif sp == "denuncia" and target:
            law_mod.report(self, st.id, target)
        elif sp == "prender" and target:
            law_mod.arrest(self, st.id, target)
        elif sp == "roubar":
            obj = extra.get("objeto", "")
            self.stolen.append({"name": obj, "from_place": place, "thief": st.id, "minute": self._now_minutes(),
                                "noticed": False, "lost": False, "hidden_place": None, "returned": False})
            self.remember(st.id, "roubo", subject=st.id, place=place, detail=obj)
            chance = self.data.world.theft.witness_notice_chance
            for other in self.present_at(place):
                if other != st.id and not self.is_asleep(other) and self.rng.random() < chance:
                    self.remember(other, "roubo", subject=st.id, place=place, detail=obj,
                                  factor=self.data.world.memory.witness_factor)
        elif sp == "funeral":
            fun = lifecycle.active_funeral_at(self, place)
            if fun is not None:
                lifecycle.joined(self, fun, st.id)
        elif sp == "assembleia":
            lifecycle.assembly_joined(self, st.id)
        elif sp == "anuncio_criador":
            commands_mod.after_announce(self, st.id, place)
        elif sp == "reuniao_criador":
            commands_mod.meeting_joined(self, st.id, place)
        elif sp == "ordem_reconstruir":
            where, _damage = self.structures.worst()
            repair = next((a for a in self.data.actions.values() if a.active and a.repairs), None)
            if where and repair:
                now = self._now_minutes()
                self.remove_goals(f"ordem:{st.id}")
                self.add_goal(who=None, action=repair.id, place=where, bonus=3.0, start=now, end=now + 8 * 60,
                              source=f"ordem:{st.id}")

    # ---------------------------------------------------- ganância e sumiços
    def _hide_loot(self, st: CharacterState, place: str) -> None:
        loot = next((s for s in reversed(self.stolen) if s["thief"] == st.id and not s["lost"]
                     and s["hidden_place"] is None), None)
        if loot is None:
            return
        spots = sorted(p for p, pl in self.data.places.items() if pl.access == "normal")
        loot["hidden_place"] = self.rng.choice(spots)
        if self.rng.random() < self.data.world.theft.forget_chance:
            loot["lost"] = True
            self.say(st.id, "esqueceu_esconderijo", place=st.place, event_type="action_started",
                     extra={"objeto": loot["name"]}, tags=["evento"], data={"action": "esconder", "lost": True},
                     fallback="{eu} esconde {objeto} em algum lugar... e já esqueceu onde.")

    def _check_missing(self, st: CharacterState, action: Action, place: str) -> None:
        """Quem começa a trabalhar no próprio local de trabalho percebe o que sumiu de lá."""
        if action.conditions.own_place != "trabalho" or utility.workplace_of(self.data, self.data.characters[st.id]) != place:
            return
        for loot in self.stolen:
            if loot["noticed"] or loot["from_place"] != place or loot["thief"] == st.id:
                continue
            loot["noticed"] = True
            since = loot["minute"] - 60
            seen = sorted({cid for minute, cid in self.visitors.get(place, []) if minute >= since
                           and cid != st.id and cid in self.states})
            suspect = None
            if seen:
                weights = [max(1.0, 40 - self.affinity(st.id, cid)) for cid in seen]
                suspect = rng_mod.weighted_choice(self.rng, seen, weights)
            st.needs["raiva"] = min(100.0, st.needs.get("raiva", 0) + self.data.world.theft.anger_on_notice)
            extra = {"objeto": loot["name"]}
            if suspect:
                extra["terceiro"] = suspect
                self.remember(st.id, "sumico", subject=suspect, place=place, detail=loot["name"])
            self.say(st.id, "sumico" if suspect else "sumico_sem_suspeito", place=place, event_type="suspicion",
                     extra=extra, tags=["evento"], importance=1,
                     data={"object": loot["name"], "suspect": suspect, "thief": loot["thief"],
                           "right": suspect == loot["thief"]},
                     fallback="{eu} percebe que sumiu {objeto}.")
            break

    def _check_lost_found(self, st: CharacterState, action: Action, place: str) -> None:
        if not action.wander:
            return
        cfg = self.data.world.theft
        for loot in self.stolen:
            if not loot["lost"] or loot.get("returned") or loot["hidden_place"] != place:
                continue
            if self.rng.random() >= cfg.find_chance:
                return
            loot["returned"] = True
            sacred = bool(set(cfg.sacred_traits) & set(self.traits_of(st.id)))
            kind = "achado_sagrado" if sacred else "achado"
            self.say(st.id, kind, place=place, event_type="found", extra={"objeto": loot["name"]},
                     tags=["misterio"], importance=1 if sacred else 0, data={"object": loot["name"], "sacred": sacred},
                     fallback="{eu} encontra {objeto} no meio de {lugar}, sem dono.")
            self.remember_scene(kind, subject=st.id, place=place, detail=loot["name"])
            return

    # ------------------------------------------------------ fugas e perseguições
    def _escape_route(self, place: str) -> str | None:
        options = sorted(e.to for e in self.data.graph.get(place, []) if passable(self.data, e.to, self.blocked_places)
                         and e.kind == "caminho")
        return self.rng.choice(options) if options else None

    def _send(self, cid: str, action_id: str, destination: str, target: str | None) -> None:
        st = self.states[cid]
        action = self.data.actions[action_id]
        low, high = action.duration_minutes
        _dist, came = shortest_paths(self.data, st.place, self.blocked_for(cid))
        edges = path_from(came, st.place, destination) or []
        st.plan = Plan(action=action_id, place=destination, target=target, duration=float(self.rng.randint(low, high)),
                       steps=[MoveStep(e.to, e.kind, e.minutes) for e in edges])
        if st.plan.steps:
            self._start_step(st)
        else:
            self._start_activity(st, action_id, destination, target, st.plan.duration, 0.0)

    def _chase(self, attacker: str, target: str, place: str) -> None:
        cfg = self.data.world.law
        dest = self._escape_route(place)
        if dest is None or self.states[target].place != place or self.states[target].away:
            return
        self.say(attacker, "perseguicao", target=target, place=place, event_type="chase", tags=["briga"],
                 importance=1, data={"to": dest}, fallback="{outro} sai correndo e {eu} vai atrás!")
        self.interrupt(target)
        self._send(target, cfg.flee_action, dest, None)
        self.interrupt(attacker)
        self._send(attacker, cfg.chase_action, dest, target)

    def _flee(self, offender: str, fiscal: str, place: str) -> None:
        """O infrator escapa do Fiscal (o mandado continua)."""
        cfg = self.data.world.law
        dest = self._escape_route(place)
        if dest is None:
            return
        self.interrupt(offender)
        self._send(offender, cfg.flee_action, dest, None)

    # ---------------------------------------------------------------- movimento
    def _start_step(self, st: CharacterState) -> None:
        step = st.plan.steps[0]
        if step.to in self.blocked_for(st.id) or st.place in self.blocked_for(st.id):
            # a névoa fechou o caminho (ou prendeu quem está aqui dentro): desiste
            self.say(st.id, "nevoa_barra", place=st.place, event_type="missed", tags=["misterio"],
                     data={"action": st.plan.action, "to": step.to},
                     fallback="{eu} dá de cara com a névoa e desiste do caminho.")
            st.plan = None
            st.last_action = None
            return
        st.plan.started_move = True
        origin = st.place
        data = {"from": origin, "to": step.to, "minutes": step.minutes, "destination": st.plan.place,
                "action": st.plan.action}
        if step.kind == "tunel":
            data.update(self._tunnel_info(origin, step.to))
            self.emit("teleport_started", f"{{@{st.id}}} entra no túnel de {{@{origin}}} para {{@{step.to}}}.",
                      actors=[st.id], place=origin, tags=["movimento"], importance=1, data=data)
        else:
            self.emit("move_started", f"{{@{st.id}}} sai de {{@{origin}}} rumo a {{@{step.to}}}.",
                      actors=[st.id], place=origin, tags=["movimento"], data=data)

    def _tunnel_info(self, a: str, b: str) -> dict:
        """Telas de origem/destino e a duração REAL da luz de LED (distância ÷ velocidade)."""
        cfg = self.data.world.tunnel
        sa, sb = self.data.screen_of(a), self.data.screen_of(b)
        screens = {s.id: s for s in self.data.world.screens}
        duration = cfg.min_duration_s
        if sa in screens and sb in screens:
            def center(s):
                return (s.position_cm.x + s.size_cm.width / 2, s.position_cm.y + s.size_cm.height / 2)
            (x1, y1), (x2, y2) = center(screens[sa]), center(screens[sb])
            duration = max(cfg.min_duration_s, math.hypot(x2 - x1, y2 - y1) / cfg.led_speed_cm_per_s)
        return {"from_place": a, "to_place": b, "from_screen": sa, "to_screen": sb,
                "duration_s": round(duration, 2)}

    def _advance_movement(self, st: CharacterState, dt: float) -> None:
        plan = st.plan
        if plan is None or st.activity is not None:
            return
        if not plan.steps:
            self._start_activity(st, plan.action, plan.place, plan.target, plan.duration, plan.score)
            return
        step = plan.steps[0]
        step.elapsed += dt
        if step.elapsed < step.minutes:
            return
        origin = st.place
        st.place = step.to
        st.prev_place = origin
        plan.steps.pop(0)
        final = not plan.steps
        data = {"from": origin, "to": step.to, "final": final, "destination": plan.place}
        if step.kind == "tunel":
            data.update(self._tunnel_info(origin, step.to))
            self.emit("teleport_finished", f"{{@{st.id}}} sai do túnel em {{@{step.to}}}.", actors=[st.id],
                      place=step.to, tags=["movimento"], importance=1, data=data)
        else:
            self.emit("move_arrived", f"{{@{st.id}}} chega em {{@{step.to}}}.", actors=[st.id],
                      place=step.to, tags=["movimento"], data=data)
        if final:
            self._start_activity(st, plan.action, plan.place, plan.target, plan.duration, plan.score)
        else:
            self._start_step(st)

    # ---------------------------------------------------------------- decisões
    def _decide_all(self) -> None:
        living = self._living()
        order = [st.id for st in living]
        self.rng.shuffle(order)
        ctx = self.decision_context()
        now = ctx.now_minutes
        review_every = self.data.world.decision.reevaluate_minutes
        for cid in order:
            st = self.states[cid]
            if st.away:
                continue  # foi para o Limbo no meio deste tick
            if ctx.minute_of_day in self._review_minutes.get(cid, ()):
                st.pending_review = True
            if any(g["who"] in (None, cid) and now <= g["start"] < now + 1 for g in self.goals):
                st.pending_review = True  # começou um objetivo (festa marcada, ordem do Chefe)
            if st.free:
                st.pending_review = False
                self._decide(st, ctx)
                ctx.present = self._present()
            elif st.activity is not None and (now >= st.next_review or st.pending_review):
                st.next_review = now + review_every
                st.pending_review = False
                if self._review(st, ctx):
                    ctx.present = self._present()

    def _decide(self, st: CharacterState, ctx: utility.DecisionContext,
                ranked: list[utility.Candidate] | None = None) -> None:
        char = self.data.characters[st.id]
        cfg = self.data.world.decision
        if ranked is None:
            ranked = utility.rank(utility.candidates(char, st, ctx), cfg.min_score)
        chosen = utility.choose(ranked, cfg.top_n, cfg.temperature, self.rng, cfg.relative_cutoff)
        if chosen is None:
            wander = next((a for a in self.data.actions.values() if a.wander and a.active and not a.automatic
                           and not a.conditions.professions), None)
            if wander is not None and st.jailed_until is None:
                chosen = utility.Candidate(wander.id, st.place, None, 0.0, 0.0, [utility.Factor("nada melhor", 0)])
            else:
                st.activity = Activity(action=IDLE, place=st.place, duration=IDLE_MINUTES)
                return
        explanation = utility.explain(chosen, ranked, cfg.top_n)
        st.last_explanation = explanation
        log.debug("[%s] %s %s", self.clock.hhmm(), st.id, explanation)
        self.emit("decision", f"{{@{st.id}}} {explanation}", actors=[st.id], place=st.place, tags=["sistema"],
                  data={"action": chosen.action, "place": chosen.place, "target": chosen.target,
                        "score": round(chosen.score, 3),
                        "top": [[c.label(), round(c.score, 3)] for c in ranked[:cfg.top_n]],
                        "factors": [[f.label, round(f.value, 3)] for f in chosen.factors]})
        self._make_plan(st, chosen, ctx)

    def _make_plan(self, st: CharacterState, chosen: utility.Candidate, ctx: utility.DecisionContext) -> None:
        action = self.data.actions[chosen.action]
        low, high = action.duration_minutes
        duration = float(self.rng.randint(low, high))
        destination = chosen.place
        if action.wander:
            destination = self._wander_destination(st, ctx)
        _dist, came = shortest_paths(self.data, st.place, self.blocked_for(st.id))
        edges = path_from(came, st.place, destination) or []
        plan = Plan(action=chosen.action, place=destination, target=chosen.target, score=chosen.score,
                    duration=duration, steps=[MoveStep(e.to, e.kind, e.minutes) for e in edges])
        st.plan = plan
        if not plan.steps:
            self._start_activity(st, plan.action, plan.place, plan.target, duration, chosen.score)
        else:
            self._start_step(st)

    def _wander_destination(self, st: CharacterState, ctx: utility.DecisionContext) -> str:
        """Perambular: um vizinho sorteado. Lugares perigosos têm menos chance,
        exceto para quem é imune a criaturas (o Mike vai a qualquer lugar)."""
        if st.jailed_until is not None:
            return st.place
        char = self.data.characters[st.id]
        fearless = "criaturas" in char.immunities
        options, weights = [], []
        blocked = self.blocked_for(st.id)
        if st.place in blocked:
            return st.place  # preso na névoa
        for edge in self.data.graph.get(st.place, []):
            if not passable(self.data, edge.to, blocked):
                continue
            danger = self.danger_at(edge.to, ctx.is_night)
            options.append(edge.to)
            weight = 1.0 if fearless else max(0.05, 1 - danger / 100) ** 2
            if edge.to == st.prev_place:
                weight *= 0.25  # quem perambula raramente volta direto por onde veio
            weights.append(weight)
        if not options:
            return st.place
        return rng_mod.weighted_choice(self.rng, options, weights)

    def _review(self, st: CharacterState, ctx: utility.DecisionContext) -> bool:
        """Quem está ocupado olha em volta: se algo vale MUITO mais que o que está
        fazendo, larga e vai (acordar para o trabalho, o sino do Padre...)."""
        if st.activity.action == IDLE:
            return False
        char = self.data.characters[st.id]
        cfg = self.data.world.decision
        action = self.data.actions.get(st.activity.action)
        if action is not None and action.automatic:
            return False  # fugindo / perseguindo: vai até o fim
        current = utility.current_score(char, st, ctx)
        act = st.activity
        if current < cfg.min_score:
            # o que está fazendo deixou de fazer sentido (ex.: dormir às 10h da manhã
            # sem sono, trabalhar depois do expediente): para e decide de novo
            self._finish_activity(st, interrupted=True)
            self._decide(st, ctx)
            return True
        ranked = utility.rank(utility.candidates(char, st, ctx), cfg.min_score)
        ranked = [c for c in ranked if not c.same_as(act.action, act.place, act.target)]
        if not ranked:
            return False
        best = ranked[0]
        minimum = cfg.wake_min_score if (action and action.sleeping) else cfg.interrupt_min_score
        if best.score < max(minimum, current * cfg.interrupt_factor):
            return False
        log.debug("[%s] %s interrompe %s (%.2f) por %s (%.2f)", self.clock.hhmm(), st.id, act.action,
                  current, best.label(), best.score)
        self._finish_activity(st, interrupted=True)
        self._decide(st, ctx, ranked)
        return True

    # ================================================================ comandos
    def submit(self, cmd: Command) -> None:
        """Thread-safe: qualquer thread pode mandar comandos (API, MQTT, CLI)."""
        self.commands.put(cmd)

    def submit_internal(self, name: str, payload: dict) -> None:
        """Comandos internos (resposta do LLM, ordem interpretada): também pela fila."""
        self.commands.put(Command(name, payload=payload))

    def _drain_commands(self) -> None:
        handled = False
        while True:
            try:
                cmd = self.commands.get_nowait()
            except queue.Empty:
                if handled:
                    self._update_snapshot()  # a API vê o efeito do comando mesmo com o mundo pausado
                return
            handled = True
            try:
                result = self.handle_command(cmd)
            except Exception as exc:  # um comando quebrado não pode parar o mundo
                log.exception("comando %s falhou", cmd.cmd)
                result = {"ok": False, "message": f"erro: {exc}"}
            if not cmd.cmd.startswith("_"):
                self._command_seq += 1
                entry = {"id": cmd.id or f"c{self._command_seq}", "cmd": cmd.cmd, "arg": cmd.arg,
                         "world_ts": self.clock.iso(), "result": result}
                self.command_log.append(entry)
            if cmd.reply is not None and not cmd.reply.done():
                cmd.reply.set_result(result)

    COMMANDS = ("pausar", "continuar", "velocidade", "nascer", "tela", "homelab", "clima") + tuple(
        sorted(commands_mod.CREATOR_COMMANDS))

    def handle_command(self, cmd: Command) -> dict:
        """Executa um comando (no thread da simulação). Devolve {"ok": bool, ...}."""
        if cmd.cmd == "pausar":
            self.paused = True
            self.emit("system", "O mundo foi pausado.", tags=["sistema"], data={"cmd": "pausar"})
            return {"ok": True, "paused": True}
        if cmd.cmd == "continuar":
            self.paused = False
            self.emit("system", "O mundo voltou a andar.", tags=["sistema"], data={"cmd": "continuar"})
            return {"ok": True, "paused": False}
        if cmd.cmd == "velocidade":
            try:
                value = float(cmd.arg)
                if value <= 0:
                    raise ValueError
            except ValueError:
                self.emit("system", f"velocidade inválida: {cmd.arg!r}", tags=["sistema"])
                return {"ok": False, "message": f"velocidade inválida: {cmd.arg!r}"}
            self.speed = value
            self.emit("system", f"Velocidade do mundo: {value:g}×.", tags=["sistema"], data={"speed": value})
            return {"ok": True, "speed": value}
        if cmd.cmd == "nascer":
            traits = [t.strip() for t in cmd.arg.replace(",", " ").split() if t.strip()]
            unknown = [t for t in traits if t not in self.data.traits]
            if unknown:
                self.emit("system", f"traço(s) desconhecido(s): {', '.join(unknown)}", tags=["sistema"])
            cid = lifecycle.birth(self, [t for t in traits if t in self.data.traits], reason="comando")
            return {"ok": cid is not None, "born": cid, "unknown_traits": unknown,
                    "message": None if cid else "não nasceu ninguém (população no máximo?)"}
        if cmd.cmd == "tela":  # "parede_centro offline" (telas/<id>/status no MQTT)
            parts = cmd.arg.split()
            if len(parts) == 2 and parts[1] in ("online", "offline"):
                changed = self.screens.set_status(self, parts[0], parts[1] == "online")
                return {"ok": True, "screen": parts[0], "status": parts[1], "changed": bool(changed)}
            self.emit("system", "uso: tela <id> online|offline", tags=["sistema"])
            return {"ok": False, "message": "uso: tela <id> online|offline"}
        if cmd.cmd == "homelab":  # "jellyfin down" (homelab/servicos/<nome> no MQTT)
            parts = cmd.arg.split()
            if len(parts) == 2:
                creatures_mod.homelab(self, parts[0], parts[1])
                return {"ok": True, "service": parts[0], "status": parts[1]}
            self.emit("system", "uso: homelab <serviço> down|up", tags=["sistema"])
            return {"ok": False, "message": "uso: homelab <serviço> down|up"}
        if cmd.cmd == "clima":  # "chuva 60": força um clima por N minutos (testes)
            parts = cmd.arg.split()
            if parts and parts[0] in self.data.world.weather.kinds:
                minutes = float(parts[1]) if len(parts) > 1 else 120
                self.weather.force(parts[0], minutes, "comando")
                return {"ok": True, "weather": parts[0], "minutes": minutes}
            self.emit("system", f"clima desconhecido: {cmd.arg!r}", tags=["sistema"])
            return {"ok": False, "message": f"clima desconhecido: {cmd.arg!r}"}
        if cmd.cmd in commands_mod.CREATOR_COMMANDS or cmd.cmd in commands_mod.INTERNAL_COMMANDS:
            return commands_mod.handle(self, cmd)
        self.emit("system", f"Comando '{cmd.cmd}' não existe.", tags=["sistema"], data={"cmd": cmd.cmd})
        return {"ok": False, "message": f"comando desconhecido: {cmd.cmd}. Comandos: {', '.join(self.COMMANDS)}"}

    # ------------------------------------------------------- ajudas da Fase 4
    def start_activity(self, cid: str, action_id: str, place: str, target: str | None, duration: float) -> None:
        self._start_activity(self.states[cid], action_id, place, target, duration, 0.0)

    def speech_context(self, cid: str, place: str, target: str | None = None) -> speech.SpeechContext:
        return self._speech_ctx(cid, place, target)

    def llm_usable(self) -> bool:
        """O LLM só entra com o mundo no relógio real (nunca em --fast nem nos testes)."""
        return (self.llm is not None and self.realtime and not self.paused and self.speed <= 10
                and self.llm.usable())

    def llm_line_ready(self, p: dict) -> dict:
        """Volta do LLM (comando interno): valida e publica; inválida ou vazia = o template."""
        text = (p.get("llm") or "").strip().strip('"').strip()
        used = False
        known = set(self.names())
        if text and len(text) <= self.data.world.ollama.max_chars and \
                not text_mod.check_template(text, known, variables={}):
            used = True
        line = text if used else p["line"]
        self.emit(p["event_type"], line, actors=p["actors"], place=p["place"], tags=p["tags"],
                  importance=p["importance"], data={**p["data"], "llm": used})
        return {"ok": True, "llm": used}

    # ============================================================ laço principal
    def run(self, until: datetime | None = None, fast: bool = False, max_ticks: int | None = None) -> None:
        """Roda até `until` (hora do mundo), `max_ticks`, ou `request_stop()`.

        fast=True: não espera nada, faz ticks o mais rápido possível.
        fast=False: segue o tempo real × `speed` (speed 600 = 10 minutos do mundo por
        segundo real: um dia inteiro em 2,4 minutos)."""
        step = timedelta(minutes=self.clock.step_minutes)
        done = 0
        self.realtime = not fast

        def finished() -> bool:
            return (self.stop_requested or (until is not None and self.clock.now + step > until)
                    or (max_ticks is not None and done >= max_ticks))

        real_anchor, world_anchor, anchor_speed = time.monotonic(), self.clock.now, self.speed
        while not finished():
            if fast:
                if self.paused:  # pausado: só escuta comandos (ex.: "continuar")
                    self._drain_commands()
                    time.sleep(0.05)
                else:
                    self.tick()
                    done += 1
                continue
            # comandos são atendidos na hora (não só no próximo tick: no tempo real,
            # um tick é um minuto inteiro; a API espera a resposta de `status`/`quem`)
            self._drain_commands()
            if self.paused or anchor_speed != self.speed:
                real_anchor, world_anchor, anchor_speed = time.monotonic(), self.clock.now, self.speed
                if self.paused:
                    time.sleep(0.1)
                    continue
            target = world_anchor + timedelta(seconds=(time.monotonic() - real_anchor) * self.speed)
            n = 0
            while self.clock.now + step <= target and n < MAX_CATCHUP_TICKS and not finished():
                self.tick()
                n += 1
                done += 1
                if self.paused or anchor_speed != self.speed:
                    break
            if n == 0:
                wait = (self.clock.now + step - target).total_seconds() / self.speed
                time.sleep(max(0.001, min(0.2, wait)))

    def request_stop(self) -> None:
        self.stop_requested = True

    def catch_up(self, real_now: datetime | None = None) -> None:
        """Religou com multiplicador 1 (tempo real): simula rápido o tempo perdido,
        no máximo `max_recuperacao_horas`; o resto é pulado com um aviso."""
        real_now = (real_now or datetime.now(self.clock.tz)).astimezone(self.clock.tz)
        lost = real_now - self.clock.now
        if lost <= timedelta(minutes=self.clock.step_minutes):
            return
        limit = timedelta(hours=self.data.world.clock.max_catchup_hours)
        if lost > limit:
            skipped = lost - limit
            self.clock.now = self.clock.now + skipped
            self._period = self.clock.period()
            self._next_hourly = self._now_minutes() + 60
            hours = skipped.total_seconds() / 3600
            self.emit("system", f"O mundo cochilou por {hours:.1f} horas.", tags=["sistema"], importance=1,
                      data={"skipped_hours": round(hours, 2)})
        self.run(until=real_now, fast=True)

    # ============================================================== persistência
    def save(self) -> None:
        if self.storage is None:
            return
        s = self.storage
        s.set_meta("world_time", self.clock.iso())
        s.set_meta("seed", self.seed)
        s.set_meta("rng_state", rng_mod.dump_state(self.rng))
        s.set_meta("speed", self.speed)
        s.set_meta("paused", "1" if self.paused else "0")
        s.set_meta("last_event_id", self._last_event_id)
        for st in self.states.values():
            s.save_character(st.id, alive=st.alive, place=st.place, needs=dict(st.needs),
                             current=st.current_json(), last_action=st.last_action,
                             flags={"cooldowns": st.cooldowns, "next_review": st.next_review,
                                    "pending_review": st.pending_review,
                                    "recent_lines": st.recent_lines, "faction": st.faction,
                                    "jailed_until": st.jailed_until, "limbo_until": st.limbo_until,
                                    "spouse": st.spouse, "prev_place": st.prev_place},
                             extra_traits=st.extra_traits)
        for a, b in sorted(self.relations.changed):
            s.save_relation(a, b, self.relations.values[(a, b)], self.clock.iso())
        self.relations.changed.clear()
        s.save_memories(self.memories.rows())
        s.set_meta("next_memory_id", self.memories.next_id)
        s.save_structures(self.structures.rows(), self.clock.iso())
        s.set_meta("society", json.dumps({
            "law": self.law.to_json(), "social": self.social.to_json(), "goals": self.goals,
            "stolen": self.stolen, "visitors": self.visitors, "relation_marks": self.relation_marks,
            "next_hourly": self._next_hourly,
            "life": self.life.to_json(), "weather": self.weather.to_json(), "screens": self.screens.to_json(),
            "creatures": self.creatures.to_json(), "director": self.director.to_json(),
            "creator": self.creator.to_json(),
        }, ensure_ascii=False))
        s.save_graves(self.life.graves)
        s.commit()

    def close(self) -> None:
        self.save()
        if self.storage is not None:
            self.storage.close()

    # ================================================================== leitura
    def _update_snapshot(self) -> None:
        snap = {
            "ts": self.clock.iso(), "period": self.clock.period(), "is_night": self.clock.is_night(),
            "speed": self.speed, "paused": self.paused,
            "weather": {"label": self.weather.label, "kind": self.weather.kind, "temp": self.weather.now.temp,
                        "forced": self.weather.now.forced},
            "tension": self.director.tension,
            "population": sum(1 for st in self.states.values() if st.alive and not st.frozen),
            "fog": sorted(self.blocked_places),
            "creatures": [{"uid": c.uid, "kind": c.kind, "place": c.place, "service": c.service}
                          for c in self.creatures.active],
            "characters": {
                cid: {"place": st.place, "action": st.activity.action if st.activity else None,
                      "moving": st.moving, "alive": st.alive, "needs": dict(st.needs),
                      "faction": st.faction, "jailed": st.jailed_until is not None, "away": st.away}
                for cid, st in self.states.items()
            },
            "structures": {sid: {"place": s.place, "hp": round(s.hp), "state": self.structures.state(sid)}
                           for sid, s in self.structures.items.items()},
            # Fase 4: nomes atuais (a API renderiza o histórico sem tocar no WorldData vivo)
            "names": self.names(),
            "seed": self.seed,
            "ticks": self.ticks,
        }
        with self._lock:
            self._snapshot = snap

    def snapshot(self) -> dict:
        """Cópia do estado para quem está FORA do thread da simulação (API, Fase 4)."""
        with self._lock:
            return dict(self._snapshot)
