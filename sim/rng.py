"""O sorteio do mundo: um único `random.Random` por mundo.

Nenhum módulo usa o `random` global. Com a mesma seed, os mesmos dados e o
modo rápido, a sequência de eventos é idêntica (ver tests/test_engine.py).
O estado do RNG é salvo no SQLite para o mundo continuar igual ao religar.
"""

from __future__ import annotations

import json
import random


def make_rng(seed: int | None) -> tuple[random.Random, int]:
    """Cria o RNG. Sem seed, sorteia uma (e devolve, para ficar registrada)."""
    if seed is None:
        seed = random.SystemRandom().randrange(1, 2**31)
    return random.Random(seed), seed


def dump_state(rng: random.Random) -> str:
    version, internal, gauss = rng.getstate()
    return json.dumps([version, list(internal), gauss])


def load_state(rng: random.Random, raw: str) -> None:
    version, internal, gauss = json.loads(raw)
    rng.setstate((version, tuple(internal), gauss))


def weighted_choice(rng: random.Random, items: list, weights: list[float]):
    """Sorteio proporcional ao peso (pesos <= 0 nunca saem)."""
    total = sum(w for w in weights if w > 0)
    if total <= 0:
        return items[0]
    pick = rng.random() * total
    for item, weight in zip(items, weights):
        if weight <= 0:
            continue
        pick -= weight
        if pick <= 0:
            return item
    return items[-1]
