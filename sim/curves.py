"""Curvas de resposta da Utility AI.

Uma "consideração" de uma ação pega uma entrada (ex.: `necessidade.fome` = 72)
e passa por uma curva que devolve um fator entre 0 e 1. A nota da ação é o
produto dos fatores (ver docs/arquitetura.md). Exemplo de YAML:

    consideracoes:
      - entrada: necessidade.fome
        curva: {tipo: pontos, pontos: [[0, 0], [40, 0.2], [80, 1]]}

Para `linear`, `potencia`, `logistica` e `degrau`, a entrada é normalizada para
0..1 usando a faixa da entrada (INPUT_RANGES). `pontos` e `degrau`/`logistica`
usam o valor CRU (ex.: fome 0..100, hora 0..24), que é mais fácil de pensar.
"""

from __future__ import annotations

import math

from sim.schemas import Curve

# Faixa de cada tipo de entrada. "necessidade.<id>" e "alvo_necessidade.<id>"
# valem para qualquer necessidade definida no world.yaml.
INPUT_RANGES: dict[str, tuple[float, float]] = {
    "necessidade": (0, 100),  # minha necessidade (necessidade.fome)
    "alvo_necessidade": (0, 100),  # necessidade do alvo (alvo_necessidade.tedio)
    "afinidade": (-100, 100),  # minha afinidade com o alvo
    "hora": (0, 24),  # hora do mundo com fração (15.5 = 15:30)
    "presentes": (0, 20),  # outros personagens no mesmo lugar
    "perigo": (0, 100),  # perigo do lugar (perigo_noite à noite)
    "tensao": (0, 100),  # tensão do mundo medida pelo diretor (Fase 3; 50 antes)
    # Fase 2 (sociedade) ---------------------------------------------------
    "afinidade_inicial": (-100, 100),  # afinidade do YAML com o alvo (o "amor de fundo")
    "afinidade_com": (-100, 100),  # minha afinidade com alguém: afinidade_com.medium
    "presenca": (0, 1),  # 1 se alguém está no lugar candidato: presenca.priest
    "faccao": (0, 1),  # 1 se sou da facção: faccao.seita
    "conflito_alvo": (0, 100),  # minha memória ruim mais forte envolvendo o alvo
    "memoria": (0, 100),  # minha memória mais forte deste tipo: memoria.briga
    "memoria_alvo": (0, 100),  # idem, envolvendo o alvo: memoria_alvo.briga
    "fofoca": (0, 100),  # quão suculenta é a melhor fofoca que tenho para contar ao alvo
    "denuncia": (0, 100),  # minha memória mais forte de uma infração de outro (ainda não denunciada)
    "dano": (0, 100),  # quanto o lugar candidato está estragado (100 - menor resistência)
    "dano_cidade": (0, 100),  # o pior estrago do mundo inteiro
    "mandado": (0, 1),  # 1 se o alvo tem mandado de prisão (para o Fiscal)
}

# entradas que precisam de ".<algo>" e o que é o algo
DOTTED_INPUTS = {
    "necessidade": "necessidade", "alvo_necessidade": "necessidade", "afinidade_com": "personagem",
    "presenca": "personagem", "faccao": "facção", "memoria": "tipo de memória", "memoria_alvo": "tipo de memória",
}
# entradas que só funcionam em ações com alvo (condicoes.alvo)
TARGET_INPUTS = {"afinidade", "alvo_necessidade", "afinidade_inicial", "conflito_alvo", "memoria_alvo",
                 "fofoca", "mandado"}


def input_kind(entry: str) -> str:
    """'necessidade.fome' -> 'necessidade'; 'hora' -> 'hora'."""
    return entry.split(".", 1)[0]


def input_range(entry: str) -> tuple[float, float]:
    return INPUT_RANGES[input_kind(entry)]


def evaluate(curve: Curve, raw: float, value_range: tuple[float, float] = (0, 100)) -> float:
    """Aplica a curva a um valor cru e devolve um fator em [minimo, 1]."""
    low, high = value_range
    norm = (raw - low) / (high - low) if high > low else 0.0
    norm = min(1.0, max(0.0, norm))

    if curve.kind == "linear":
        y = norm
    elif curve.kind == "potencia":
        y = norm ** curve.exponent
    elif curve.kind == "logistica":
        # meio e inclinação na escala crua (ex.: meio 70 de fome)
        steep = curve.steepness or 0.15
        y = 1.0 / (1.0 + math.exp(-steep * (raw - curve.midpoint)))
    elif curve.kind == "degrau":
        y = 1.0 if raw >= curve.threshold else 0.0
    elif curve.kind == "pontos":
        y = _piecewise(curve.points, raw)
    else:  # pragma: no cover - o esquema já impede
        raise ValueError(f"tipo de curva desconhecido: {curve.kind}")

    if curve.invert:
        y = 1.0 - y
    return max(curve.floor, min(1.0, max(0.0, y)))


def _piecewise(points: list[tuple[float, float]], x: float) -> float:
    """Interpolação linear entre pontos [x, y]; fora da faixa, repete a ponta."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]
