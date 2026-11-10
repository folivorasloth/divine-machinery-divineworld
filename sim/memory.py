"""Memória por NPC (seção 11 de docs/arquitetura.md).

Cada personagem guarda acontecimentos marcantes: quem fez (`subject`), com quem
(`object`), onde, quando, com que intensidade (0..100) e sentimento (-1..1).

- Os tipos (briga, roubo, festa...) e quanto cada um decai por dia ficam em
  `world.yaml > memoria.tipos`. Memórias pequenas decaem e somem abaixo de
  `esquecer_abaixo`; as `permanente` (casamento, Limbo, morte) ficam.
- Quem só viu (testemunha) ou só ouviu (fofoca) lembra mais fraco.
- A mesma coisa de novo (mesmo tipo, mesmas pessoas, no mesmo dia) reforça a
  memória em vez de criar outra.
- As frases (`fato`, `lembranca`) viram as variáveis {fato} e {lembranca} das
  falas: "desde aquela briga na Cozinha Comunitária...".

Tudo por id: renomear alguém não quebra memória nenhuma.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sim import text
from sim.schemas import MemoryConfig

DAY_MINUTES = 1440.0


@dataclass
class Memory:
    id: int
    owner: str
    kind: str
    subject: str | None  # quem fez
    object: str | None  # com quem / em quem
    place: str | None
    intensity: float
    sentiment: float
    permanent: bool
    ts: str  # hora do mundo (ISO)
    minute: float  # minuto absoluto do mundo (para "no mesmo dia")
    heard_from: str | None = None  # fofoca: quem contou
    distorted: bool = False  # a fofoca chegou torta (trocou quem fez)
    detail: str = ""  # objeto roubado, nome da facção...
    reported: bool = False  # já foi contada ao Fiscal
    secret: bool = False  # contada em confissão (só o Padre sabe... até ele contar)

    def involves(self, cid: str) -> bool:
        return cid in (self.subject, self.object)


class Memories:
    def __init__(self, cfg: MemoryConfig):
        self.cfg = cfg
        self.by_owner: dict[str, list[Memory]] = {}
        self.next_id = 1

    # -------------------------------------------------------------- formar
    def form(self, owner: str, kind: str, *, subject: str | None, object: str | None = None,
             place: str | None = None, ts: str, minute: float, factor: float = 1.0,
             heard_from: str | None = None, distorted: bool = False, detail: str = "",
             secret: bool = False) -> tuple[Memory | None, bool]:
        """Cria (ou reforça) uma memória. Devolve (memória, nova?)."""
        k = self.cfg.kinds.get(kind)
        if k is None:
            return None, False
        intensity = k.intensity * factor
        mine = self.by_owner.setdefault(owner, [])
        for m in mine:
            if (m.kind, m.subject, m.object) == (kind, subject, object) and minute - m.minute < DAY_MINUTES:
                m.intensity = min(100.0, max(m.intensity, intensity) + intensity * 0.3)
                m.minute, m.ts = minute, ts
                if heard_from is None:  # viu com os próprios olhos: deixa de ser "ouvi dizer"
                    m.heard_from, m.distorted = None, False
                return m, False
        mem = Memory(id=self.next_id, owner=owner, kind=kind, subject=subject, object=object, place=place,
                     intensity=min(100.0, intensity), sentiment=k.sentiment, permanent=k.permanent, ts=ts,
                     minute=minute, heard_from=heard_from, distorted=distorted, detail=detail, secret=secret)
        self.next_id += 1
        mine.append(mem)
        if len(mine) > self.cfg.max_per_npc:
            # esquece a mais fraca que não é permanente
            weakest = min((m for m in mine if not m.permanent), key=lambda m: m.intensity, default=None)
            if weakest is not None:
                mine.remove(weakest)
        return mem, True

    # ------------------------------------------------------------- decair
    def decay(self, hours: float) -> None:
        for owner, mine in self.by_owner.items():
            keep = []
            for m in mine:
                if not m.permanent:
                    k = self.cfg.kinds.get(m.kind)
                    m.intensity -= (k.decay_per_day if k else 10) * hours / 24
                if m.permanent or m.intensity >= self.cfg.forget_below:
                    keep.append(m)
            mine[:] = keep

    # ------------------------------------------------------------ consultar
    def of(self, owner: str) -> list[Memory]:
        return self.by_owner.get(owner, [])

    def strongest(self, owner: str, kind: str | None = None, involving: str | None = None,
                  kinds: list[str] | None = None) -> Memory | None:
        best = None
        for m in self.of(owner):
            if kind is not None and m.kind != kind:
                continue
            if kinds and m.kind not in kinds:
                continue
            if involving is not None and not m.involves(involving):
                continue
            if best is None or m.intensity > best.intensity:
                best = m
        return best

    def intensity(self, owner: str, kind: str, involving: str | None = None) -> float:
        m = self.strongest(owner, kind, involving)
        return m.intensity if m else 0.0

    def conflict_with(self, owner: str, other: str) -> float:
        """Minha memória RUIM mais forte de algo entre mim e `other` (0 se nenhuma)."""
        return max((m.intensity for m in self.of(owner) if m.sentiment < 0 and m.involves(other)
                    and m.involves(owner) and m.heard_from is None), default=0.0)

    def knows(self, owner: str, mem: Memory) -> bool:
        """`owner` já sabe disso (mesmo tipo e mesmas pessoas)?"""
        return any((m.kind, m.subject, m.object) == (mem.kind, mem.subject, mem.object) for m in self.of(owner))

    def weaken_between(self, a: str, b: str, factor: float) -> None:
        """Fazer as pazes: as memórias ruins entre os dois perdem força."""
        for owner, other in ((a, b), (b, a)):
            for m in self.of(owner):
                if m.sentiment < 0 and m.involves(other) and m.involves(owner) and not m.permanent:
                    m.intensity *= factor

    # --------------------------------------------------------------- frases
    def phrase(self, mem: Memory, which: str = "fato") -> str:
        """'fato' (fofoca, 3ª pessoa) ou 'lembranca' (quem viveu), com tokens {@id}."""
        k = self.cfg.kinds[mem.kind]
        template = k.fact if which == "fato" else k.recollection
        ctx = {"quem": mem.subject or "", "alvo": mem.object or "", "lugar": mem.place or "", "objeto": mem.detail}
        return text.fill(template, {key: v for key, v in ctx.items() if v})

    # ---------------------------------------------------------- persistência
    def rows(self) -> list[dict]:
        return [asdict(m) for mine in self.by_owner.values() for m in mine]

    def load(self, rows: list[dict], next_id: int) -> None:
        self.by_owner = {}
        for row in rows:
            m = Memory(**row)
            self.by_owner.setdefault(m.owner, []).append(m)
        self.next_id = max([next_id] + [m.id + 1 for mine in self.by_owner.values() for m in mine])
