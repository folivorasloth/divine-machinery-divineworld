"""Relatório de VARIEDADE do mundo (Fase 3).

    python -m tools.report --days 7                 # 7 dias acelerados, seed aleatória
    python -m tools.report --days 30 --seed 7 --saida var/variedade.md
    python -m tools.report --days 7 --estrito       # sai com código 1 se houver alerta

Simula N dias no modo mais rápido possível, num banco e numa pasta de
nascidos TEMPORÁRIOS (nada fica em var/ nem em data/), e mostra:

- ações mais e menos usadas (e as que nunca aconteceram);
- falas repetidas: o texto EXATO que apareceu no Chat (com os nomes já
  preenchidos), quantas vezes, de que situação — e ALERTA para as que passam
  do limite de repetição;
- eventos por tipo; mortes, nascimentos e população;
- personagens "parados" (fazem pouca coisa diferente).

Limite de repetição (padrão): uma fala exata pode aparecer no máximo
`max(3, dias × 0,5)` vezes — 3 numa semana, 15 num mês. Por quê: o Chat do
Mundo mostra ~400 linhas por dia e o João olha a parede algumas vezes por
dia; a mesma frase, com as mesmas pessoas, mais de uma vez a cada dois dias
já começa a ser notada (o pilar da bible é "a cada olhada, algo diferente").
Frases com variáveis (nomes, lugares) contam separado quando o texto final
muda — é o que o João vê. Mude com `--limite-por-dia` e `--limite-minimo`.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from rich.console import Console
from rich.table import Table

NOT_ACTION_TYPES = {"action_finished", "speech", "move_started", "move_arrived", "teleport_started",
                    "teleport_finished", "decision", "missed", "tension"}


class Collector:
    def __init__(self, world) -> None:
        self.world = world
        self.types: Counter = Counter()
        self.actions: Counter = Counter()
        self.actions_by_char: dict[str, Counter] = defaultdict(Counter)
        self.lines: Counter = Counter()  # texto final -> vezes
        self.line_situation: dict[str, str] = {}
        self.situations: Counter = Counter()
        self.narrations: Counter = Counter()
        self.deaths: list[tuple[str, str, str]] = []
        self.births: list[tuple[str, str]] = []
        self.population: list[int] = []

    def __call__(self, ev) -> None:
        self.types[ev.type] += 1
        if ev.type == "decision":
            return
        action = ev.data.get("action")
        if action and ev.type not in NOT_ACTION_TYPES and ev.actors and not ev.data.get("reply_to"):
            self.actions[action] += 1
            self.actions_by_char[ev.actors[0]][action] += 1
        names = self.world.names()
        if ev.data.get("situation") and ev.text:
            txt = ev.render(names)
            self.lines[txt] += 1
            self.line_situation.setdefault(txt, ev.data["situation"])
            self.situations[ev.data["situation"]] += 1
        elif ev.text and action and ev.type not in ("action_finished",) and not ev.data.get("spoke"):
            self.narrations[ev.render(names)] += 1
        if ev.type == "death":
            self.deaths.append((ev.ts[:16], ev.actors[0], ev.data.get("cause_name", "")))
        if ev.type == "birth":
            self.births.append((ev.ts[:16], ev.actors[0]))
        if ev.type == "period_changed":
            self.population.append(sum(1 for st in self.world.states.values() if st.alive and not st.frozen))


def run(days: float, seed: int | None, start: str | None, data_dir: str):
    """Simula num diretório temporário. Devolve (world, collector, segundos)."""
    tmp = tempfile.TemporaryDirectory(prefix="dw_report_")
    os.environ["DW_BORN_DIR"] = str(Path(tmp.name) / "nascidos")
    from sim.clock import WorldClock
    from sim.engine import World
    from sim.loader import load_data_or_raise
    from sim.persistence import Storage

    data = load_data_or_raise(data_dir)
    begin = WorldClock.parse_start(data.world.clock, start) if start else None
    world = World(data, Storage(Path(tmp.name) / "mundo.sqlite"), seed=seed, start=begin)
    col = Collector(world)
    world.bus.subscribe(col)
    t0 = time.monotonic()
    world.run(until=world.clock.now + timedelta(days=days), fast=True)
    elapsed = time.monotonic() - t0
    world.close()
    world._tmp = tmp  # mantém a pasta viva até o fim do relatório
    return world, col, elapsed


def build_report(world, col: Collector, days: float, per_day: float, minimum: int, elapsed: float):
    """Monta as tabelas (rich) e a lista de alertas."""
    names = world.names()
    limit = max(minimum, math.ceil(days * per_day))
    tables = []
    alerts: list[str] = []

    t = Table(title=f"Resumo — {days:g} dias, seed {world.seed}, {elapsed:.0f} s reais")
    t.add_column("item")
    t.add_column("valor")
    alive = sum(1 for st in world.states.values() if st.alive and not st.frozen)
    pop = col.population or [alive]
    t.add_row("eventos no Chat", str(sum(n for k, n in col.types.items() if k != "decision")))
    t.add_row("falas (de data/lines)", f"{sum(col.lines.values())} ({len(col.lines)} textos diferentes)")
    t.add_row("população", f"começou {pop[0]}, terminou {alive}, mínimo {min(pop)}, máximo {max(pop)}")
    t.add_row("mortes", str(len(col.deaths)))
    t.add_row("nascimentos", str(len(col.births)))
    t.add_row("limite de repetição", f"{limit} vezes por fala exata (max({minimum}, {days:g} × {per_day:g}))")
    tables.append(t)

    t = Table(title="Mortes e nascimentos")
    t.add_column("quando")
    t.add_column("o quê")
    for ts, who, cause in col.deaths:
        t.add_row(ts.replace("T", " "), f"morreu {names.get(who, who)} ({cause})")
    for ts, who in col.births:
        t.add_row(ts.replace("T", " "), f"nasceu {names.get(who, who)}")
    tables.append(t)

    active = sorted(a.id for a in world.data.actions.values()
                    if a.active and not a.automatic and a.kind != "movimento")
    used = col.actions
    t = Table(title="Ações mais usadas (começos)")
    t.add_column("ação")
    t.add_column("vezes", justify="right")
    for a, n in used.most_common(12):
        t.add_row(a, str(n))
    tables.append(t)
    t = Table(title="Ações menos usadas")
    t.add_column("ação")
    t.add_column("vezes", justify="right")
    for a in sorted(active, key=lambda a: (used[a], a))[:12]:
        t.add_row(a, str(used[a]))
    tables.append(t)
    never = [a for a in active if used[a] == 0]
    if never:  # só informação: algumas dependem de algo raro (eleição só se o Chefe morrer)
        t.caption = f"Nunca aconteceram: {', '.join(never)}"

    t = Table(title=f"Falas mais repetidas (alerta acima de {limit})")
    t.add_column("vezes", justify="right")
    t.add_column("situação")
    t.add_column("fala")
    for txt, n in col.lines.most_common(15):
        flag = " ⚠" if n > limit else ""
        t.add_row(f"{n}{flag}", col.line_situation[txt], txt[:110])
    tables.append(t)
    over = [(txt, n) for txt, n in col.lines.items() if n > limit]
    for txt, n in sorted(over, key=lambda x: -x[1]):
        alerts.append(f"fala repetida {n}× (limite {limit}) [{col.line_situation[txt]}]: {txt[:100]}")

    t = Table(title="Narrações mais repetidas (só informação: cada ação tem uma narração-padrão)")
    t.add_column("vezes", justify="right")
    t.add_column("narração")
    for txt, n in col.narrations.most_common(8):
        t.add_row(str(n), txt[:120])
    tables.append(t)

    t = Table(title="Eventos por tipo")
    t.add_column("tipo")
    t.add_column("quantos", justify="right")
    for k, n in col.types.most_common():
        if k != "decision":
            t.add_row(k, str(n))
    tables.append(t)

    t = Table(title="Personagens: variedade do que fizeram")
    t.add_column("personagem")
    t.add_column("ações", justify="right")
    t.add_column("diferentes", justify="right")
    t.add_column("mais comum")
    for cid in sorted(world.states, key=lambda c: names.get(c, c)):
        acts = col.actions_by_char.get(cid, Counter())
        total = sum(acts.values())
        top = ", ".join(f"{a} {n}" for a, n in acts.most_common(3))
        alive_txt = "" if world.states[cid].alive else " (†)"
        t.add_row(names.get(cid, cid) + alive_txt, str(total), str(len(acts)), top)
        if world.states[cid].alive and total and len(acts) < 5:
            alerts.append(f"{names.get(cid, cid)} fez só {len(acts)} ações diferentes")
    tables.append(t)
    return tables, alerts, limit


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Simula N dias e mostra um relatório de variedade.")
    p.add_argument("--days", "--dias", type=float, default=7, help="dias simulados (padrão 7)")
    p.add_argument("--seed", type=int, default=None, help="semente (padrão: aleatória, mostrada no relatório)")
    p.add_argument("--inicio", default="00:00", help='hora do mundo no começo (padrão "00:00")')
    p.add_argument("--dados", default="data", help="pasta de dados (padrão: data)")
    p.add_argument("--limite-por-dia", type=float, default=0.5,
                   help="vezes por dia simulado que uma mesma fala pode aparecer (padrão 0.5)")
    p.add_argument("--limite-minimo", type=int, default=3, help="limite mínimo de repetição (padrão 3)")
    p.add_argument("--saida", default=None, help="também grava o relatório neste arquivo (texto)")
    p.add_argument("--estrito", action="store_true", help="sai com código 1 se houver algum alerta")
    args = p.parse_args(argv)

    console = Console(highlight=False)
    console.print(f"Simulando {args.days:g} dias (pasta temporária, nada é gravado em data/ ou var/)...")
    world, col, elapsed = run(args.days, args.seed, args.inicio, args.dados)
    tables, alerts, _limit = build_report(world, col, args.days, args.limite_por_dia, args.limite_minimo, elapsed)
    out = open(args.saida, "w", encoding="utf-8") if args.saida else None
    consoles = [console] + ([Console(file=out, no_color=True, highlight=False, width=180)] if out else [])
    for c in consoles:
        for t in tables:
            c.print(t)
        if alerts:
            c.print("[bold red]ALERTAS[/]")
            for a in alerts:
                c.print(f"  - {a}")
        else:
            c.print("[bold green]Nenhum alerta de repetição.[/]")
    if out:
        out.close()
    return 1 if (alerts and args.estrito) else 0


if __name__ == "__main__":
    sys.exit(main())
