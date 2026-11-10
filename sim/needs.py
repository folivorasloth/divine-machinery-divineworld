"""Variação das necessidades a cada tick (seção 5 de docs/arquitetura.md).

    taxa_base = taxa_noite se é noite, senão taxa_dia
    mult      = personagem.necessidades[n].taxa (padrão 1) × Π traço.efeitos.necessidades[n]
    acumula:  valor += taxa_base × mult × dt_horas
    retorna:  valor se aproxima da base em taxa_base × mult × dt_horas (sem passar)
    + efeito da ação em andamento: efeito_total × (dt / duração)
    tudo limitado a 0..100

Quem está numa ação com `dormindo: true` não ganha sono sozinho.
"""

from __future__ import annotations

from sim.loader import WorldData
from sim.schemas import Character


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def initial_needs(data: WorldData, char: Character) -> dict[str, float]:
    result = {}
    for nid, need in data.world.needs.items():
        override = char.needs.get(nid)
        value = override.initial if override and override.initial is not None else need.initial
        result[nid] = float(value)
    return result


def rate_multiplier(data: WorldData, char: Character, need_id: str, extra_traits: list[str] = ()) -> float:
    mult = 1.0
    override = char.needs.get(need_id)
    if override and override.rate is not None:
        mult *= override.rate
    for tid in list(char.traits) + list(extra_traits):
        trait = data.traits.get(tid)
        if trait:
            mult *= trait.effects.needs.get(need_id, 1.0)
    return mult


def natural_change(
    data: WorldData,
    char: Character,
    needs: dict[str, float],
    is_night: bool,
    dt_minutes: float,
    sleeping: bool = False,
) -> None:
    """Aplica a variação natural (taxas) em `needs`, no lugar."""
    dt_hours = dt_minutes / 60.0
    for nid, need in data.world.needs.items():
        if sleeping and nid == "sono":
            continue
        rate = (need.rate_night if is_night else need.rate_day) * rate_multiplier(data, char, nid)
        value = needs.get(nid, need.initial)
        if need.mode == "acumula":
            value += rate * dt_hours
        else:  # retorna: anda em direção à base sem passar dela
            step = rate * dt_hours
            if value > need.base:
                value = max(need.base, value - step)
            elif value < need.base:
                value = min(need.base, value + step)
        needs[nid] = clamp(value)


def apply_effect(needs: dict[str, float], effects: dict[str, float], fraction: float) -> None:
    """Soma `efeito_total × fração` (fração = dt/duração da ação)."""
    for nid, total in effects.items():
        if nid in needs:
            needs[nid] = clamp(needs[nid] + total * fraction)


def mood(data: WorldData, needs: dict[str, float], threshold: float = 60.0) -> str:
    """Palavra de humor para a variável {humor}: a necessidade mais alta acima
    do limite que tenha `humor` no world.yaml; senão, `humor_neutro`."""
    best, best_value = None, threshold
    for nid, need in data.world.needs.items():
        if need.mood and needs.get(nid, 0) >= best_value:
            best, best_value = need.mood, needs[nid]
    return best or data.world.neutral_mood
