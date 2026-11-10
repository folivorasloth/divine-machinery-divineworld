"""Utility AI: candidatos, nota, escolha ponderada e explicação.

Fórmula (seção 6 de docs/arquitetura.md):

    nota = peso
         × Π curva_i(entrada_i)          # considerações do YAML (0..1 cada)
         × Π traço.efeitos.acoes[ação]   # traços do personagem
         × rotina                        # bloco de rotina ativo com essa ação (e lugar)
         × viagem                        # 0.5 ^ (minutos_de_viagem / meia_vida)
         × repetição                     # se foi a última ação

Cada fator vira um `Factor` para o log explicar a decisão ("escolheu comer
porque fome=72→0.78, rotina×2...").
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from sim import curves
from sim.loader import WorldData
from sim.pathfinding import shortest_paths
from sim.rng import weighted_choice
from sim.schemas import Action, Character
from sim.state import CharacterState

DEFAULT_TENSION = 50.0  # o diretor (Fase 3) mede a tensão de verdade


@dataclass
class Factor:
    label: str  # ex.: "necessidade.fome=72→0.78", "traço preguicoso", "rotina"
    value: float

    def __str__(self) -> str:
        return f"{self.label}×{self.value:.2f}" if "→" not in self.label else self.label


@dataclass
class Candidate:
    action: str
    place: str
    target: str | None
    travel_minutes: float
    score: float
    factors: list[Factor] = field(default_factory=list)

    def label(self) -> str:
        who = f"({self.target})" if self.target else ""
        return f"{self.action}{who}@{self.place}"

    def same_as(self, action: str, place: str, target: str | None) -> bool:
        return (self.action, self.place, self.target) == (action, place, target)


@dataclass
class DecisionContext:
    """O que a Utility AI precisa saber do mundo neste instante."""

    data: WorldData
    minute_of_day: int
    hour: float
    period: str
    is_night: bool
    now_minutes: float  # relógio em minutos absolutos (para cooldowns)
    states: dict[str, CharacterState]
    present: dict[str, list[str]]  # lugar -> ids parados ali (vivos, sem estar andando)
    affinity: Callable[[str, str], float]
    blocked: frozenset[str] = frozenset()
    tension: float = DEFAULT_TENSION


# --------------------------------------------------------------------------
# Entradas e condições
# --------------------------------------------------------------------------


def read_input(entry: str, ctx: DecisionContext, me: CharacterState, place: str, target: str | None) -> float:
    kind = curves.input_kind(entry)
    if kind == "necessidade":
        return me.needs.get(entry.split(".", 1)[1], 0.0)
    if kind == "alvo_necessidade":
        if not target:
            return 0.0
        return ctx.states[target].needs.get(entry.split(".", 1)[1], 0.0)
    if kind == "afinidade":
        return ctx.affinity(me.id, target) if target else 0.0
    if kind == "hora":
        return ctx.hour
    if kind == "presentes":
        return float(len([c for c in ctx.present.get(place, []) if c != me.id]))
    if kind == "perigo":
        p = ctx.data.places[place]
        return p.danger_night if (ctx.is_night and p.danger_night is not None) else p.danger
    if kind == "tensao":
        return ctx.tension
    return 0.0  # pragma: no cover - o validador impede entradas desconhecidas


def conditions_ok(action: Action, char: Character, me: CharacterState, ctx: DecisionContext,
                  check_cooldown: bool = True) -> bool:
    cond = action.conditions
    if cond.periods and ctx.period not in cond.periods:
        return False
    if cond.hours and not any(w.contains(ctx.minute_of_day) for w in cond.hours):
        return False
    if cond.professions and char.profession not in cond.professions:
        return False
    if cond.traits and not set(cond.traits) & set(char.traits):
        return False
    if cond.characters and char.id not in cond.characters:
        return False
    for nid, minimum in cond.min_needs.items():
        if me.needs.get(nid, 0) < minimum:
            return False
    if check_cooldown and me.cooldowns.get(action.id, -1) > ctx.now_minutes:
        return False
    return True


def workplace_of(data: WorldData, char: Character) -> str | None:
    if char.workplace:
        return char.workplace
    prof = data.professions.get(char.profession)
    return prof.workplace if prof else None


def active_routine(char: Character, minute_of_day: int):
    return [b for b in char.routine if b.window().contains(minute_of_day)]


def candidate_places(action: Action, char: Character, me: CharacterState, ctx: DecisionContext) -> list[str]:
    data = ctx.data
    own = action.conditions.own_place
    if own == "trabalho":
        wp = workplace_of(data, char)
        return [wp] if wp else []
    if own == "casa":
        return [char.home]
    if action.anywhere or action.wander:
        places = [me.place]
        # se a rotina manda fazer esta ação num lugar específico, ele também vale
        for block in active_routine(char, ctx.minute_of_day):
            if block.action == action.id and block.place and block.place not in places:
                places.append(block.place)
        return places
    return [pid for pid, p in data.places.items() if action.id in p.actions]


def social_targets(action: Action, me: CharacterState, ctx: DecisionContext) -> list[str]:
    rule = action.conditions.target
    out = []
    for other in ctx.present.get(me.place, []):
        if other == me.id:
            continue
        st = ctx.states[other]
        if st.activity is not None:
            act = ctx.data.actions.get(st.activity.action)
            if act is not None and act.sleeping:
                continue  # ninguém conversa com quem está dormindo
        aff = ctx.affinity(me.id, other)
        if rule.affinity_min is not None and aff < rule.affinity_min:
            continue
        if rule.affinity_max is not None and aff > rule.affinity_max:
            continue
        out.append(other)
    return out


# --------------------------------------------------------------------------
# Nota
# --------------------------------------------------------------------------


def score(
    action: Action,
    char: Character,
    me: CharacterState,
    place: str,
    target: str | None,
    travel_minutes: float,
    ctx: DecisionContext,
    repeat: bool = True,
) -> tuple[float, list[Factor]]:
    data = ctx.data
    factors = [Factor("peso", action.base_weight)]
    value = action.base_weight
    for cons in action.considerations:
        raw = read_input(cons.input, ctx, me, place, target)
        f = curves.evaluate(cons.curve, raw, curves.input_range(cons.input))
        factors.append(Factor(f"{cons.input}={raw:.0f}→{f:.2f}", f))
        value *= f
    for tid in char.traits:
        trait = data.traits.get(tid)
        mult = trait.effects.actions.get(action.id) if trait else None
        if mult is not None and mult != 1:
            factors.append(Factor(f"traço {tid}", mult))
            value *= mult
    routine = 1.0
    for block in active_routine(char, ctx.minute_of_day):
        if block.action == action.id and (block.place is None or block.place == place):
            routine = max(routine, block.weight)
    if routine != 1.0:
        factors.append(Factor("rotina", routine))
        value *= routine
    if travel_minutes > 0:
        travel = 0.5 ** (travel_minutes / data.world.decision.travel_half_life_minutes)
        factors.append(Factor(f"viagem {travel_minutes:.0f}min", travel))
        value *= travel
    if repeat and me.last_action == action.id:
        pen = data.world.decision.repeat_penalty
        factors.append(Factor("repetição", pen))
        value *= pen
    return value, factors


def candidates(char: Character, me: CharacterState, ctx: DecisionContext) -> list[Candidate]:
    data = ctx.data
    dist, _came = shortest_paths(data, me.place, ctx.blocked)
    out: list[Candidate] = []
    for action in data.actions.values():
        if not action.active or action.kind == "movimento":
            continue
        if not conditions_ok(action, char, me, ctx):
            continue
        for place in candidate_places(action, char, me, ctx):
            if place not in dist:
                continue  # inalcançável (especial, névoa, sem caminho)
            if action.kind == "social":
                if place != me.place:
                    continue  # ir atrás de alguém em outro lugar é da Fase 2
                for target in social_targets(action, me, ctx):
                    s, f = score(action, char, me, place, target, 0.0, ctx)
                    out.append(Candidate(action.id, place, target, 0.0, s, f))
            else:
                s, f = score(action, char, me, place, None, dist[place], ctx)
                out.append(Candidate(action.id, place, None, dist[place], s, f))
    return out


def current_score(char: Character, me: CharacterState, ctx: DecisionContext) -> float:
    """Nota da ação em andamento AGORA (sem viagem, sem repetição, sem cooldown).
    Se as condições dela deixaram de valer (ex.: acabou o horário), vale 0."""
    act = me.activity
    action = ctx.data.actions.get(act.action) if act else None
    if action is None:
        return 0.0
    if not conditions_ok(action, char, me, ctx, check_cooldown=False):
        return 0.0
    value, _f = score(action, char, me, act.place, act.target, 0.0, ctx, repeat=False)
    return value


# --------------------------------------------------------------------------
# Escolha e explicação
# --------------------------------------------------------------------------


def rank(cands: list[Candidate], min_score: float) -> list[Candidate]:
    good = [c for c in cands if c.score >= min_score]
    # ordem estável: nota, depois rótulo (para a mesma seed dar o mesmo resultado)
    good.sort(key=lambda c: (-c.score, c.label()))
    return good


def choose(ranked: list[Candidate], top_n: int, temperature: float, rng: random.Random,
           relative_cutoff: float = 0.0) -> Candidate | None:
    top = ranked[:top_n]
    if not top:
        return None
    top = [c for c in top if c.score >= top[0].score * relative_cutoff]
    weights = [c.score ** (1.0 / temperature) for c in top]
    return weighted_choice(rng, top, weights)


def explain(chosen: Candidate, ranked: list[Candidate], top_n: int = 3) -> str:
    """Duas linhas: escolha + top3, e os fatores da escolhida."""
    top = ", ".join(f"{c.label()} {c.score:.2f}" for c in ranked[:top_n])
    factors = " × ".join(str(f) for f in chosen.factors)
    return f"escolheu {chosen.label()} ({chosen.score:.2f}) | top{top_n}: {top}\n    {chosen.action}: {factors}"
