"""Fofoca: repassar memórias para terceiros, com chance de distorção.

Quem fofoca escolhe, entre as suas memórias, a mais "suculenta" sobre um
TERCEIRO (nem quem fala, nem quem ouve), que quem ouve ainda não sabe:

    suculência = intensidade × (0.3 + 1.2 × lado ruim + 0.3 × lado bom) × (1.3 se é infração)

(notícia ruim corre mais que notícia boa)

Quem ouve ganha uma cópia mais fraca (`memoria.fator_fofoca`), marcada com
`heard_from`. Com `fofoca.chance_distorcao` (o dobro para quem tem o traço
`fofoca.traco_fofoqueiro`), a fofoca chega torta: quem fez vira OUTRA pessoa.
É assim que acusações caem na pessoa errada.

Segredos de confissão (`secret`) só saem da boca de quem tem o traço
fofoqueiro (o Padre conta sem perceber).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sim.memory import Memory

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World


def is_gossiper(world: "World", cid: str) -> bool:
    trait = world.data.world.gossip.gossiper_trait
    return bool(trait) and trait in world.traits_of(cid)


def juiciness(world: "World", mem: Memory) -> float:
    kind = world.data.world.memory.kinds.get(mem.kind)
    bonus = 1.3 if kind and kind.infraction else 1.0
    bad, good = max(0.0, -mem.sentiment), max(0.0, mem.sentiment)
    return mem.intensity * (0.3 + 1.2 * bad + 0.3 * good) * bonus


def best(world: "World", speaker: str, listener: str) -> tuple[Memory | None, float]:
    """A melhor fofoca que `speaker` tem para contar a `listener` (e a nota 0..100)."""
    gossiper = is_gossiper(world, speaker)
    chosen, value = None, 0.0
    for m in world.memories.of(speaker):
        if not m.subject or m.subject in (speaker, listener) or m.object in (speaker, listener):
            continue
        if m.secret and not gossiper:
            continue
        if m.subject not in world.states:
            continue
        if world.memories.knows(listener, m):
            continue
        v = juiciness(world, m)
        if v > value or (v == value and chosen is not None and m.id < chosen.id):
            chosen, value = m, v
    return chosen, min(100.0, value)


def spread(world: "World", speaker: str, listener: str, place: str) -> dict | None:
    """Conta a fofoca. Devolve as variáveis da fala e os dados do evento (ou None)."""
    mem, _value = best(world, speaker, listener)
    if mem is None:
        return None
    cfg = world.data.world
    subject, distorted = mem.subject, False
    chance = cfg.gossip.distortion_chance * (2 if is_gossiper(world, speaker) else 1)
    if world.rng.random() < min(1.0, chance):
        options = sorted(c for c, st in world.states.items()
                         if st.alive and not st.frozen and c not in (speaker, listener, mem.subject, mem.object))
        if options:
            subject, distorted = world.rng.choice(options), True
    copy, _new = world.remember(listener, mem.kind, subject=subject, object=mem.object, place=mem.place,
                                factor=cfg.memory.gossip_factor * (mem.intensity / 100 + 0.3),
                                heard_from=speaker, distorted=distorted or mem.distorted, detail=mem.detail)
    if copy is None:
        return None
    fact = world.memories.phrase(copy, "fato")
    return {
        "vars": {"terceiro": subject, "fato": fact, "objeto": mem.detail} if mem.detail
        else {"terceiro": subject, "fato": fact},
        "data": {"memory_kind": mem.kind, "about": subject, "true_subject": mem.subject,
                 "distorted": distorted, "secret": mem.secret, "memory_id": copy.id},
        "memory": copy,
        "secret": mem.secret,
    }
