"""Falas: escolhe um template de `data/lines/` e preenche as variáveis.

`pick_line(...)`:
1. junta as falas da situação; filtra por `personagens`, `tracos`,
   `lugares`, `periodos`, `climas` e `necessidades_min` (filtro vazio = vale
   para todos);
2. descarta falas que precisam de algo que não existe agora ({outro} sem
   alvo, {bordao} de quem não tem bordão, {morto}/{objeto} antes das fases 2-3);
3. evita as falas usadas recentemente pelo mesmo personagem (anti-repetição);
4. sorteia pelo `peso` e preenche com `sim.text.fill` (ids viram `{@id}`).
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from sim import text
from sim.loader import WorldData
from sim.rng import weighted_choice
from sim.schemas import LineTemplate

RECENT_LIMIT = 8  # quantas falas recentes de cada personagem são evitadas


@dataclass
class SpeechContext:
    speaker: str
    place: str
    period: str
    hour: str
    period_name: str
    weather: str
    mood: str
    needs: dict[str, float]
    target: str | None = None
    # Fase 2: variáveis extras da situação ({terceiro}, {fato}, {objeto}, {evento}...)
    extra: dict[str, str] = field(default_factory=dict)
    # pronome ("ele"/"ela") de eu/outro/terceiro, para a concordância {o|a}
    genders: dict[str, str] = field(default_factory=dict)
    # recall(tipos) -> frase {lembranca} da memória mais forte desses tipos
    # envolvendo o alvo (ou qualquer um, sem alvo); None se não lembra
    recall: Callable[[list[str]], str | None] | None = None
    # Fase 3: tipo do clima (id de clima.tipos: chuva, limpo...) e o morto da situação
    weather_kind: str = ""
    dead: str | None = None
    profession: str | None = None  # profissão ATUAL de quem fala (sucessão)


# variáveis que só existem em algumas situações: fala que usa e não tem é pulada
_SITUATIONAL = {"terceiro", "fato", "objeto", "evento", "infracao", "faccao", "traco", "morto", "convidados"}


def _needs_vars(line: str, ctx: SpeechContext, data: WorldData) -> bool:
    used = set(text.fields(line))
    speaker = data.characters[ctx.speaker]
    if ("outro" in used or "bordao_outro" in used) and not ctx.target:
        return False
    if "bordao" in used and not speaker.catchphrases:
        return False
    if "bordao_outro" in used and ctx.target and not data.characters[ctx.target].catchphrases:
        return False
    for var in used & _SITUATIONAL:
        if not ctx.extra.get(var):
            return False
    if "lembranca" in used and "lembranca" not in ctx.extra:
        return False  # {lembranca} só em falas com filtro `memoria` (ou quando vem pronta)
    return True


def matches(line: LineTemplate, ctx: SpeechContext, data: WorldData) -> bool:
    speaker = data.characters[ctx.speaker]
    if line.characters and ctx.speaker not in line.characters:
        return False
    if line.traits and not set(line.traits) & set(speaker.traits):
        return False
    if line.places and ctx.place not in line.places:
        return False
    if line.periods and ctx.period not in line.periods:
        return False
    if line.weather and ctx.weather not in line.weather and ctx.weather_kind not in line.weather:
        return False
    if line.dead and ctx.dead not in line.dead:
        return False
    if line.professions and (ctx.profession or speaker.profession) not in line.professions:
        return False
    for nid, minimum in line.min_needs.items():
        if ctx.needs.get(nid, 0) < minimum:
            return False
    if line.memory:
        if ctx.recall is None or ctx.recall(line.memory) is None:
            return False
        if "lembranca" in set(text.fields(line.text)):
            return _needs_vars(line.text.replace("{lembranca}", ""), ctx, data)
    return _needs_vars(line.text, ctx, data)


def fill_context(ctx: SpeechContext, data: WorldData, rng: random.Random) -> dict[str, str]:
    speaker = data.characters[ctx.speaker]
    profession = data.professions.get(speaker.profession)
    values = {
        "eu": ctx.speaker,
        "lugar": ctx.place,
        "hora": ctx.hour,
        "periodo": ctx.period_name,
        "clima": ctx.weather,
        "humor": ctx.mood,
        "trabalho": profession.activity if profession and profession.activity else "trabalha",
    }
    if speaker.catchphrases:
        values["bordao"] = rng.choice(speaker.catchphrases)
    if ctx.target:
        values["outro"] = ctx.target
        other = data.characters.get(ctx.target)
        if other and other.catchphrases:
            values["bordao_outro"] = rng.choice(other.catchphrases)
    values.update({k: v for k, v in ctx.extra.items() if v})
    return values


def pick_line(
    data: WorldData,
    situation: str,
    ctx: SpeechContext,
    rng: random.Random,
    recent: list[str] | None = None,
) -> str | None:
    """Devolve o texto preenchido (com tokens {@id}) ou None se não houver fala."""
    options = [line for line in data.lines.get(situation, []) if matches(line, ctx, data)]
    if not options:
        return None
    if recent:
        fresh = [line for line in options if line.text not in recent]
        options = fresh or options  # se todas foram usadas, aceita repetir
    line = weighted_choice(rng, options, [line.weight for line in options])
    if recent is not None:
        recent.append(line.text)
        del recent[:-RECENT_LIMIT]
    values = fill_context(ctx, data, rng)
    if line.memory and ctx.recall is not None:
        values["lembranca"] = ctx.recall(line.memory) or ""
    # duas passadas: {lembranca}/{fato} trazem {@id} dentro, e o resto é preenchido
    return text.fill(line.text, values, ctx.genders)


def fill_narration(data: WorldData, template: str, ctx: SpeechContext, rng: random.Random) -> str:
    return text.fill(template, fill_context(ctx, data, rng), ctx.genders)
