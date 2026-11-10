"""Estado VIVO do mundo (o que muda a cada tick).

Os dados do YAML (`sim.loader.WorldData`) são só leitura; aqui fica o que a
simulação altera e o que vai para o SQLite. Tudo referenciado por id.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Activity:
    """Uma ação em andamento (ex.: comer na cozinha por 30 minutos)."""

    action: str
    place: str
    duration: float  # minutos do mundo
    elapsed: float = 0.0
    target: str | None = None
    score: float = 0.0  # nota na hora da decisão (para o log)
    failed: bool = False  # Fase 2: deu errado (pastelão): vale `falha.efeitos`
    target_applied: bool = False  # efeitos no alvo já aplicados no começo (interrompe_alvo)
    seen_by_law: bool = False  # o Fiscal já registrou esta infração

    @property
    def done(self) -> bool:
        return self.elapsed >= self.duration


@dataclass
class MoveStep:
    """Um passo de movimento: atravessar UMA conexão do grafo."""

    to: str
    kind: str  # caminho | tunel
    minutes: float
    elapsed: float = 0.0


@dataclass
class Plan:
    """O que um NPC decidiu: andar até `place` e então fazer `action`."""

    action: str
    place: str
    target: str | None = None
    score: float = 0.0
    steps: list[MoveStep] = field(default_factory=list)
    duration: float = 0.0  # duração sorteada da ação (minutos)
    started_move: bool = False


@dataclass
class CharacterState:
    id: str
    place: str
    needs: dict[str, float]
    alive: bool = True
    activity: Activity | None = None
    plan: Plan | None = None
    last_action: str | None = None
    # ação -> minuto do mundo (timestamp em minutos) até quando não pode repetir
    cooldowns: dict[str, float] = field(default_factory=dict)
    # minuto do mundo da próxima reavaliação de quem está ocupado
    next_review: float = 0.0
    # passou um minuto-gatilho (começo de bloco de rotina, janela do sino) enquanto
    # andava: reavalia assim que chegar
    pending_review: bool = False
    # textos de fala usados recentemente (anti-repetição; não é salvo)
    recent_lines: list[str] = field(default_factory=list)
    # última explicação de decisão (para o `quem <id>` da Fase 4)
    last_explanation: str = ""
    frozen: bool = False  # está no banco mas sumiu do YAML
    # Fase 2 ------------------------------------------------------------------
    extra_traits: list[str] = field(default_factory=list)  # ganhos em vida (Limbo)
    faction: str | None = None  # igreja, seita... (começa pelo YAML)
    jailed_until: float | None = None  # minuto do mundo em que sai da prisão
    limbo_until: float | None = None  # minuto do mundo em que volta do Limbo
    spouse: str | None = None  # casou numa festa de casamento
    prev_place: str | None = None  # de onde veio (perambular evita voltar direto)

    @property
    def away(self) -> bool:
        """No Limbo: some das telas, não decide, necessidades congeladas."""
        return self.limbo_until is not None

    @property
    def moving(self) -> bool:
        return self.plan is not None and bool(self.plan.steps) and self.plan.started_move

    @property
    def free(self) -> bool:
        return self.activity is None and self.plan is None

    def current_json(self) -> dict | None:
        if self.activity is None and self.plan is None:
            return None
        return {
            "activity": asdict(self.activity) if self.activity else None,
            "plan": asdict(self.plan) if self.plan else None,
        }

    def restore_current(self, raw: dict | None) -> None:
        self.activity = None
        self.plan = None
        if not raw:
            return
        if raw.get("activity"):
            self.activity = Activity(**raw["activity"])
        if raw.get("plan"):
            plan = dict(raw["plan"])
            plan["steps"] = [MoveStep(**s) for s in plan.get("steps", [])]
            self.plan = Plan(**plan)
