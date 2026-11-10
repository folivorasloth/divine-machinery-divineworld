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
  6. decisões dos livres + reavaliação de quem está ocupado (interrupção)
  7. salvar no SQLite a cada `salvar_a_cada_minutos`
Só o thread da simulação mexe no estado. API/CLI/MQTT só põem comandos na fila.
"""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sim import needs as needs_mod
from sim import rng as rng_mod
from sim import speech, utility
from sim.clock import WorldClock
from sim.events import Event, EventBus
from sim.loader import WorldData
from sim.pathfinding import passable, path_from, shortest_paths
from sim.persistence import Storage
from sim.schemas import time_to_minutes
from sim.state import Activity, CharacterState, MoveStep, Plan

log = logging.getLogger("sim.engine")

IDLE = "_parado"  # "ação" interna: ficar parado quando nada vale a pena
IDLE_MINUTES = 10
MAX_CATCHUP_TICKS = 600  # no tempo real, no máximo isso de ticks atrasados por rodada


@dataclass
class Command:
    cmd: str
    arg: str = ""
    id: str = ""


class World:
    def __init__(
        self,
        data: WorldData,
        storage: Storage | None = None,
        *,
        seed: int | None = None,
        speed: float | None = None,
        start: datetime | None = None,
    ):
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
        self.affinities: dict[tuple[str, str], float] = {}  # só os pares que mudaram
        self._changed_relations: set[tuple[str, str]] = set()
        self.weather_label = data.world.weather.fallback  # clima real chega na Fase 3
        self.frozen_rows: dict[str, dict] = {}

        if storage is not None:
            self.bus.subscribe(storage.insert_event)

        resumed = storage is not None and storage.has_world()
        self.resumed = resumed
        if resumed:
            saved_seed = int(storage.get_meta("seed"))
            self.rng, self.seed = rng_mod.make_rng(saved_seed)
            rng_mod.load_state(self.rng, storage.get_meta("rng_state"))
            self.clock = WorldClock(data.world.clock, datetime.fromisoformat(storage.get_meta("world_time")))
            self.speed = speed if speed is not None else float(storage.get_meta("speed", data.world.clock.multiplier))
            self.paused = storage.get_meta("paused", "0") == "1"
            self._last_event_id = int(storage.get_meta("last_event_id", "0"))
            self.affinities = storage.load_relations()
        else:
            self.rng, self.seed = rng_mod.make_rng(seed if seed is not None else data.world.seed)
            self.clock = WorldClock(data.world.clock, start or WorldClock.parse_start(data.world.clock, None))
            self.speed = speed if speed is not None else data.world.clock.multiplier

        self.states: dict[str, CharacterState] = {}
        self._review_minutes: dict[str, set[int]] = {}
        self._load_characters()
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

    # ===================================================================== setup
    def _load_characters(self) -> None:
        rows = self.storage.load_characters() if self.storage else {}
        for cid, char in self.data.characters.items():
            row = rows.pop(cid, None)
            if row is None:  # personagem novo: entra em casa, com as necessidades iniciais
                st = CharacterState(id=cid, place=char.home, needs=needs_mod.initial_needs(self.data, char))
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

    def names(self) -> dict[str, str]:
        return self.data.names()

    def affinity(self, a: str, b: str) -> float:
        if (a, b) in self.affinities:
            return self.affinities[(a, b)]
        return float(self.data.affinity(a, b))

    def change_affinity(self, a: str, b: str, delta: float) -> None:
        if not delta or a == b or a not in self.data.characters:
            return
        self.affinities[(a, b)] = max(-100.0, min(100.0, self.affinity(a, b) + delta))
        self._changed_relations.add((a, b))

    def emit(self, type: str, text: str = "", *, actors=(), place=None, tags=(), importance=0, data=None) -> Event:
        self._last_event_id += 1
        ev = Event(type=type, ts=self.clock.iso(), text=text, actors=list(actors), place=place,
                   tags=list(tags), importance=importance, data=dict(data or {}), id=self._last_event_id)
        self.bus.publish(ev)
        return ev

    def _speech_ctx(self, cid: str, place: str, target: str | None = None) -> speech.SpeechContext:
        st = self.states[cid]
        return speech.SpeechContext(
            speaker=cid, place=place, period=self.clock.period(), hour=self.clock.hhmm(),
            period_name=self.clock.period_name(), weather=self.weather_label,
            mood=needs_mod.mood(self.data, st.needs), needs=st.needs, target=target,
        )

    def _present(self) -> dict[str, list[str]]:
        present: dict[str, list[str]] = {}
        for cid, st in self.states.items():
            if st.alive and not st.frozen and not st.moving:
                present.setdefault(st.place, []).append(cid)
        return present

    def decision_context(self) -> utility.DecisionContext:
        return utility.DecisionContext(
            data=self.data, minute_of_day=self.clock.minute_of_day(), hour=self.clock.hour_float(),
            period=self.clock.period(), is_night=self.clock.is_night(), now_minutes=self._now_minutes(),
            states=self.states, present=self._present(), affinity=self.affinity,
        )

    def _living(self) -> list[CharacterState]:
        return [st for st in self.states.values() if st.alive and not st.frozen]

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

        night = self.clock.is_night()
        for st in self._living():
            self._update_needs(st, night, dt)
        for st in self._living():
            self._advance_activity(st, dt)
        for st in self._living():
            self._advance_movement(st, dt)
        self._decide_all()

        if self._now_minutes() >= self._next_save:
            self.save()
            self._next_save = self._now_minutes() + self.data.world.storage.save_every_minutes
        elif self.storage is not None:
            self.storage.commit_if_dirty()
        self._update_snapshot()

    # ------------------------------------------------------------ necessidades
    def _update_needs(self, st: CharacterState, night: bool, dt: float) -> None:
        char = self.data.characters[st.id]
        action = self.data.actions.get(st.activity.action) if st.activity else None
        needs_mod.natural_change(self.data, char, st.needs, night, dt, sleeping=bool(action and action.sleeping))
        if action is not None and st.activity.duration > 0:
            needs_mod.apply_effect(st.needs, action.effects.needs, dt / st.activity.duration)

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
        if act.target and act.target in self.states:
            target_st = self.states[act.target]
            needs_mod.apply_effect(target_st.needs, action.effects.target_needs, fraction)
            self.change_affinity(st.id, act.target, action.effects.affinity * fraction)
            self.change_affinity(act.target, st.id, action.effects.target_affinity * fraction)
        st.last_action = act.action
        if action.cooldown_minutes:
            st.cooldowns[act.action] = self._now_minutes() + action.cooldown_minutes
        text = ""
        if action.narration_end:
            text = speech.fill_narration(self.data, action.narration_end,
                                         self._speech_ctx(st.id, act.place, act.target), self.rng)
        self.emit("action_finished", text, actors=[st.id] + ([act.target] if act.target else []),
                  place=act.place, tags=action.tags, data={"action": act.action, "interrupted": interrupted,
                                                           "minutes": round(act.elapsed)})

    def _start_activity(self, st: CharacterState, action_id: str, place: str, target: str | None,
                        duration: float, score: float) -> None:
        st.plan = None
        st.activity = Activity(action=action_id, place=place, duration=duration, target=target, score=score)
        if action_id == IDLE:
            return
        action = self.data.actions[action_id]
        actors = [st.id] + ([target] if target else [])
        spoken = None
        if action.speech and self.rng.random() < action.speech_chance:
            spoken = speech.pick_line(self.data, action.speech, self._speech_ctx(st.id, place, target),
                                      self.rng, st.recent_lines)
        template = action.narration or ("{eu} vai " + action.name[:1].lower() + action.name[1:] + " em {lugar}.")
        narration = speech.fill_narration(self.data, template, self._speech_ctx(st.id, place, target), self.rng)
        kind = action.event or "action_started"
        self.emit(kind, narration, actors=actors, place=place, tags=action.tags, importance=action.importance,
                  data={"action": action_id, "target": target, "minutes": round(duration),
                        "score": round(score, 3), "spoke": spoken is not None})
        if spoken:
            self.emit("speech", spoken, actors=actors, place=place, tags=action.tags,
                      importance=action.importance, data={"situation": action.speech, "action": action_id})
        # o alvo responde (conversa de verdade tem duas pessoas)
        if target and action.target_speech and self.rng.random() < action.target_speech_chance:
            reply = speech.pick_line(self.data, action.target_speech, self._speech_ctx(target, place, st.id),
                                     self.rng, self.states[target].recent_lines)
            if reply:
                self.emit("speech", reply, actors=[target, st.id], place=place, tags=action.tags,
                          data={"situation": action.target_speech, "action": action_id, "reply_to": st.id})

    # ---------------------------------------------------------------- movimento
    def _start_step(self, st: CharacterState) -> None:
        step = st.plan.steps[0]
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
            if ctx.minute_of_day in self._review_minutes.get(cid, ()):
                st.pending_review = True
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
            wander = next((a for a in self.data.actions.values() if a.wander and a.active), None)
            if wander is not None:
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
        _dist, came = shortest_paths(self.data, st.place, ctx.blocked)
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
        char = self.data.characters[st.id]
        fearless = "criaturas" in char.immunities
        options, weights = [], []
        for edge in self.data.graph.get(st.place, []):
            if not passable(self.data, edge.to, ctx.blocked):
                continue
            place = self.data.places[edge.to]
            danger = place.danger_night if (ctx.is_night and place.danger_night is not None) else place.danger
            options.append(edge.to)
            weights.append(1.0 if fearless else max(0.05, 1 - danger / 100) ** 2)
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
        action = self.data.actions.get(act.action)
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

    def _drain_commands(self) -> None:
        while True:
            try:
                cmd = self.commands.get_nowait()
            except queue.Empty:
                return
            self.handle_command(cmd)

    def handle_command(self, cmd: Command) -> None:
        if cmd.cmd == "pausar":
            self.paused = True
            self.emit("system", "O mundo foi pausado.", tags=["sistema"], data={"cmd": "pausar"})
        elif cmd.cmd == "continuar":
            self.paused = False
            self.emit("system", "O mundo voltou a andar.", tags=["sistema"], data={"cmd": "continuar"})
        elif cmd.cmd == "velocidade":
            try:
                value = float(cmd.arg)
                if value <= 0:
                    raise ValueError
            except ValueError:
                self.emit("system", f"velocidade inválida: {cmd.arg!r}", tags=["sistema"])
                return
            self.speed = value
            self.emit("system", f"Velocidade do mundo: {value:g}×.", tags=["sistema"], data={"speed": value})
        else:
            self.emit("system", f"Comando '{cmd.cmd}' ainda não existe (Fase 4).", tags=["sistema"],
                      data={"cmd": cmd.cmd})

    # ============================================================ laço principal
    def run(self, until: datetime | None = None, fast: bool = False, max_ticks: int | None = None) -> None:
        """Roda até `until` (hora do mundo), `max_ticks`, ou `request_stop()`.

        fast=True: não espera nada, faz ticks o mais rápido possível.
        fast=False: segue o tempo real × `speed` (speed 600 = 10 minutos do mundo por
        segundo real: um dia inteiro em 2,4 minutos)."""
        step = timedelta(minutes=self.clock.step_minutes)
        done = 0

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
            if self.paused or anchor_speed != self.speed:
                self._drain_commands()
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
                                    "recent_lines": st.recent_lines})
        for a, b in sorted(self._changed_relations):
            s.save_relation(a, b, self.affinities[(a, b)], self.clock.iso())
        self._changed_relations.clear()
        s.commit()

    def close(self) -> None:
        self.save()
        if self.storage is not None:
            self.storage.close()

    # ================================================================== leitura
    def _update_snapshot(self) -> None:
        snap = {
            "ts": self.clock.iso(), "period": self.clock.period(), "is_night": self.clock.is_night(),
            "speed": self.speed, "paused": self.paused, "weather": {"label": self.weather_label},
            "characters": {
                cid: {"place": st.place, "action": st.activity.action if st.activity else None,
                      "moving": st.moving, "alive": st.alive, "needs": dict(st.needs)}
                for cid, st in self.states.items()
            },
        }
        with self._lock:
            self._snapshot = snap

    def snapshot(self) -> dict:
        """Cópia do estado para quem está FORA do thread da simulação (API, Fase 4)."""
        with self._lock:
            return dict(self._snapshot)
