"""Afinidade viva entre pares (seção 11 de docs/arquitetura.md).

- Começa pelo YAML (`relacoes` de cada personagem, ou `afinidade_padrao`).
- Muda com as ações (conversar +1, brigar -10...), com as memórias que se
  formam (cada tipo de memória tem `afinidade`) e com as fofocas.
- Volta devagar para o valor inicial (`relacoes.retorno_por_hora`): rancor
  dura dias, mas passa — a não ser que algo novo aconteça.
- Só os pares que mudaram ficam guardados (tabela `relations` do SQLite).
"""

from __future__ import annotations

from sim.loader import WorldData


class Relations:
    def __init__(self, data: WorldData):
        self.data = data
        self.values: dict[tuple[str, str], float] = {}  # só os pares que mudaram desde o YAML
        self.changed: set[tuple[str, str]] = set()

    def initial(self, a: str, b: str) -> float:
        if a not in self.data.characters:
            return 0.0
        return float(self.data.affinity(a, b))

    def get(self, a: str, b: str) -> float:
        if (a, b) in self.values:
            return self.values[(a, b)]
        if a not in self.data.characters or b not in self.data.characters:
            return 0.0
        return float(self.data.affinity(a, b))

    def change(self, a: str, b: str, delta: float) -> tuple[float, float]:
        """Soma `delta`; devolve (antes, depois)."""
        before = self.get(a, b)
        if not delta or a == b or a not in self.data.characters or b not in self.data.characters:
            return before, before
        after = max(-100.0, min(100.0, before + delta))
        self.values[(a, b)] = after
        self.changed.add((a, b))
        return before, after

    def drift(self, hours: float) -> None:
        """Volta devagar para a afinidade inicial."""
        rate = self.data.world.relations.return_per_hour * hours
        if rate <= 0:
            return
        for (a, b), value in self.values.items():
            base = self.initial(a, b)
            if value > base:
                new = max(base, value - rate)
            elif value < base:
                new = min(base, value + rate)
            else:
                continue
            if new != value:
                self.values[(a, b)] = new
                self.changed.add((a, b))
