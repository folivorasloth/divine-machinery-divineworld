"""O Diretor (storyteller) — Fase 3.

Mede a TENSÃO do mundo e, quando ela foge muito do alvo do período, injeta um
evento de `data/events/*.yaml` para puxar o ritmo de volta. Ele nunca decide o
resultado de nada: só cria situações (muda necessidades de quem está num
lugar, cria um objetivo temporário, força um clima, faz aparecer uma
criatura). O que os NPCs fazem com isso sai da Utility AI de sempre.

Tensão (0..100), recalculada a cada `diretor.a_cada_minutos`:

    Σ pesos_eventos[tipo] × quantos eventos desse tipo nas últimas janela_horas
    + peso_medo_medio × medo médio dos vivos + peso_raiva_media × raiva média
    + peso_morte_recente × mortes nas últimas janela_morte_horas
    + peso_criatura × criaturas no mundo agora

Escolha: se a tensão está acima de `alvo[período] + margem`, o diretor procura
eventos com `tensao: acalma` (trégua, sopa quente...); abaixo de
`alvo − margem`, eventos `tensao: agita` (festa, maré estranha, boato...).
A chance de agir numa checagem cresce com a distância do alvo
(`chance_de_agir × distância/50`). Respeita `condicoes`, `cooldown_horas` e os
limites `max_eventos_diretor_por_hora/dia`.

Eventos `tipo: raro | lendario` (fantasma, ressurreição natural, o desenho do
Criador) não dependem da tensão: cada um é sorteado sozinho com a sua
`chance_por_dia` (fantasma e ressurreição usam os `limites` do world.yaml) e
um cooldown longo.

Toda escolha vai para o log (`director_event` no Chat, tabela `director_log`)
com o motivo: "tensão 12 < alvo 45: agita → noite_animada".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sim import creatures as creatures_mod
from sim import lifecycle
from sim import text as text_mod
from sim.needs import clamp
from sim.rng import weighted_choice
from sim.schemas import WorldEvent

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World

RARE_KINDS = ("raro", "lendario")
NIGHT_MINUTES = 690  # duração aproximada da noite (18:30–06:00), para a chance "por noite"


class Director:
    def __init__(self) -> None:
        self.tension = 50.0
        self.history: list[list] = []  # [minuto, tipo de evento] dentro da janela
        self.cooldowns: dict[str, float] = {}  # evento -> minuto em que pode repetir
        self.injected: list[float] = []  # minutos em que o diretor agiu (limites por hora/dia)
        self.next_check: float | None = None
        self.next_log: float | None = None
        self.log: list[dict] = []  # o que o diretor fez (também vai para a tabela director_log)
        self.watched: set[str] = set()

    def to_json(self) -> dict:
        return {"tension": self.tension, "history": self.history, "cooldowns": self.cooldowns,
                "injected": self.injected, "next_check": self.next_check, "next_log": self.next_log}

    def load(self, raw: dict) -> None:
        self.tension = float(raw.get("tension", 50.0))
        self.history = list(raw.get("history", []))
        self.cooldowns = dict(raw.get("cooldowns", {}))
        self.injected = list(raw.get("injected", []))
        self.next_check = raw.get("next_check")
        self.next_log = raw.get("next_log")

    # ---------------------------------------------------------- observação
    def observe(self, world: "World", ev) -> None:
        """Assinante do EventBus: guarda os eventos que contam para a tensão."""
        if ev.type in self.watched:
            self.history.append([world.now_minutes(), ev.type])

    # ---------------------------------------------------------------- tensão
    def measure(self, world: "World") -> float:
        cfg = world.data.world.director
        now = world.now_minutes()
        window = cfg.window_hours * 60
        self.history = [h for h in self.history if now - h[0] < window]
        value = 0.0
        for _m, kind in self.history:
            value += cfg.event_weights.get(kind, 0.0)
        alive = [st for st in world.states.values() if st.alive and not st.frozen and not st.away]
        if alive:
            value += cfg.fear_weight * sum(st.needs.get("medo", 0) for st in alive) / len(alive)
            value += cfg.anger_weight * sum(st.needs.get("raiva", 0) for st in alive) / len(alive)
        deaths = sum(1 for d in world.life.deaths if now - d["minute"] < cfg.death_window_hours * 60)
        value += cfg.death_weight * deaths
        value += cfg.creature_weight * len(world.creatures.active)
        return round(clamp(value), 1)

    def target(self, world: "World") -> float:
        return world.data.world.director.target.get(world.clock.period(), 40.0)

    # ------------------------------------------------------------- cada tick
    def update(self, world: "World") -> None:
        cfg = world.data.world.director
        now = world.now_minutes()
        if self.next_check is None:
            self.next_check = now + cfg.every_minutes
        if now < self.next_check:
            return
        self.next_check = now + cfg.every_minutes
        self.tension = self.measure(world)
        target = self.target(world)
        if self.next_log is None or now >= self.next_log:
            self.next_log = now + cfg.log_every_minutes
            world.emit("tension", f"Tensão do mundo: {self.tension:.0f} (alvo {target:.0f}).", tags=["sistema"],
                       data={"tension": self.tension, "target": target, "period": world.clock.period()})
        self.injected = [m for m in self.injected if now - m < 1440]
        self._rare(world, now)
        if not self._within_limits(world, now):
            return
        diff = self.tension - target
        if abs(diff) <= cfg.margin:
            return
        want = "acalma" if diff > 0 else "agita"
        if world.rng.random() >= min(1.0, abs(diff) / 50) * cfg.act_chance:
            return
        options = [e for e in sorted(world.data.events.values(), key=lambda e: e.id)
                   if e.active and e.kind not in RARE_KINDS and e.tension == want and self._ok(world, e, now)]
        if not options:
            return
        event = weighted_choice(world.rng, options, [e.weight for e in options])
        reason = (f"tensão {self.tension:.0f} {'>' if diff > 0 else '<'} alvo {target:.0f}: {want}")
        self.apply(world, event, reason)

    def _within_limits(self, world: "World", now: float) -> bool:
        lim = world.data.world.limits
        last_hour = sum(1 for m in self.injected if now - m < 60)
        return last_hour < lim.director_events_per_hour and len(self.injected) < lim.director_events_per_day

    def _ok(self, world: "World", event: WorldEvent, now: float) -> bool:
        if self.cooldowns.get(event.id, -1) > now:
            return False
        cond = event.conditions
        if cond.periods and world.clock.period() not in cond.periods:
            return False
        if cond.hours and not any(w.contains(world.clock.minute_of_day()) for w in cond.hours):
            return False
        if not cond.tension_min <= self.tension <= cond.tension_max:
            return False
        if cond.min_population and len(lifecycle.living(world)) < cond.min_population:
            return False
        if cond.weather and world.weather.kind not in cond.weather:
            return False
        return True

    def _rare(self, world: "World", now: float) -> None:
        lim = world.data.world.limits
        every = world.data.world.director.every_minutes
        for event in sorted(world.data.events.values(), key=lambda e: e.id):
            if not event.active or event.kind not in RARE_KINDS or not self._ok(world, event, now):
                continue
            special = event.effects.special
            if special == "fantasma":
                per_check = lim.ghost_chance_per_night * every / NIGHT_MINUTES if world.clock.is_night() else 0.0
            elif special == "ressurreicao":
                per_check = lim.natural_resurrection_chance_per_year / 365 * every / 1440
            else:
                per_check = (event.chance_per_day or 0.0) * every / 1440
            if per_check > 0 and world.rng.random() < per_check:
                self.apply(world, event, f"evento raro ({event.kind}), sorteado")

    # --------------------------------------------------------------- aplicar
    def apply(self, world: "World", event: WorldEvent, reason: str) -> bool:
        """Cria a situação do evento. True se aconteceu."""
        now = world.now_minutes()
        eff = event.effects
        place = world.rng.choice(sorted(event.places)) if event.places else None
        if eff.special == "fantasma":
            if not lifecycle.ghost(world):
                return False
        elif eff.special == "ressurreicao":
            dead = sorted(cid for cid, st in world.states.items() if not st.alive and not st.frozen)
            if not dead or not lifecycle.resurrect(world, world.rng.choice(dead), "natural"):
                return False
        if eff.creature:
            if creatures_mod.spawn(world, eff.creature, place, reason="diretor") is None:
                return False
        affected: list[str] = []
        if eff.needs:
            if eff.needs_for == "todos" or place is None:
                affected = lifecycle.living(world)
            else:
                affected = world.present_at(place)
            for cid in affected:
                st = world.states[cid]
                for n, v in eff.needs.items():
                    st.needs[n] = clamp(st.needs.get(n, 0) + v)
        if eff.goal:
            g = eff.goal
            gplace = g.place  # sem lugar no YAML = vale em qualquer lugar
            if g.who == "todos":
                world.add_goal(who=None, action=g.action, place=gplace, bonus=g.bonus, start=now,
                               end=now + g.hours * 60, source=f"diretor:{event.id}")
            else:
                for cid in world.present_at(place) if place else []:
                    world.add_goal(who=cid, action=g.action, place=gplace, bonus=g.bonus, start=now,
                                   end=now + g.hours * 60, source=f"diretor:{event.id}")
            for st in world.states.values():
                st.pending_review = True  # quem foi chamado pensa de novo agora
        if eff.weather:
            world.weather.force(eff.weather, eff.weather_minutes, "diretor")
        if eff.memory:
            for cid in affected or (world.present_at(place) if place else []):
                world.remember(cid, eff.memory, subject=None, place=place)
        self.cooldowns[event.id] = now + event.cooldown_hours * 60
        self.injected.append(now)
        if not eff.special:  # fantasma/ressurreição já contaram a história no Chat
            values = {"lugar": place or world.data.world.central_place, "clima": world.weather.label,
                      "hora": world.clock.hhmm()}
            txt = text_mod.fill(event.text, values)
            world.emit("director_event", txt, place=place, tags=list(event.tags) or ["evento"],
                       importance=event.importance,
                       data={"event": event.id, "kind": event.kind, "tension": self.tension, "reason": reason})
        entry = {"ts": world.clock.iso(), "tension": self.tension, "chosen": event.id, "reason": reason}
        self.log.append(entry)
        if world.storage is not None:
            world.storage.log_director(entry)
        return True
