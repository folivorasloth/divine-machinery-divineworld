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
- personagens "parados" (fazem pouca coisa diferente);
- Fase 6, **balanceamento** (`build_balance`): prisões por semana, eventos sociais
  (planejados × sucesso × fracasso), eventos do diretor (o mais repetido e os que
  nunca saíram), criaturas, mortes por causa e rajadas de morte, necessidades que
  "explodem" (ficam ≥ 95) e ocupação dos lugares (vazios e lotados). Os limites dos
  alertas estão em BALANCE_LIMITS, logo abaixo, explicados um por um.

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


# Limites dos alertas de BALANCEAMENTO (Fase 6). Por quê de cada um:
BALANCE_LIMITS = {
    # 21 moradores: mais de ~1 prisão por dia vira rotina e a Prisão vira o assunto da cidade
    "prisoes_por_semana": 8,
    # um evento social que fracassa em mais de 3 de cada 4 tentativas parece bug, não emergência
    "sucesso_minimo_evento_social": 0.25,
    # nenhum evento do diretor deve ser mais de 30% de tudo que ele injeta (repetição)
    "fatia_maxima_evento_diretor": 0.30,
    # 3 mortes em 7 dias numa cidade de ~20 é uma praga (o luto de uma ainda nem acabou)
    "mortes_em_7_dias": 3,
    # uma necessidade ≥ 95 em mais de 15% das amostras (de toda a cidade) está "explodindo"
    "fatia_maxima_necessidade_95": 0.15,
    # um personagem com a mesma necessidade ≥ 95 em mais de 40% das amostras está travado nela
    "fatia_maxima_necessidade_95_por_personagem": 0.40,
}


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
        # Fase 6: balanceamento
        self.arrests: list[str] = []
        self.social: dict[str, Counter] = defaultdict(Counter)  # evento -> planned/sucesso/fracasso
        self.director: Counter = Counter()
        self.creatures: Counter = Counter()
        self.death_minutes: list[float] = []
        self.death_causes: Counter = Counter()
        self.need_samples = 0
        self.need_high: Counter = Counter()  # necessidade -> amostras >= 95
        self.char_samples: Counter = Counter()
        self.char_need_high: Counter = Counter()  # (personagem, necessidade) -> amostras >= 95
        self.place_samples = 0
        self.place_total: Counter = Counter()
        self.place_max: Counter = Counter()

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
            self._sample()
        if ev.type == "arrest":
            self.arrests.append(ev.ts)
        elif ev.type == "social_event_planned":
            self.social[ev.data.get("social_event", "?")]["planejado"] += 1
        elif ev.type == "social_event_ended":
            self.social[ev.data.get("social_event", "?")][ev.data.get("result", "?")] += 1
        elif ev.type == "director_event":
            self.director[ev.data.get("event", "?")] += 1
        elif ev.type == "creature_spawned":
            self.creatures[ev.data.get("creature", "?")] += 1
        elif ev.type == "death":
            self.death_minutes.append(self.world.now_minutes())
            self.death_causes[ev.data.get("cause_name") or ev.data.get("cause", "?")] += 1

    def _sample(self) -> None:
        """4 vezes por dia (troca de período): necessidades e onde cada um está."""
        living = [st for st in self.world.states.values() if st.alive and not st.frozen]
        self.place_samples += 1
        here: Counter = Counter(st.place for st in living)
        for pid in self.world.data.places:
            self.place_total[pid] += here[pid]
            self.place_max[pid] = max(self.place_max[pid], here[pid])
        for st in living:
            self.char_samples[st.id] += 1
            self.need_samples += 1  # uma amostra por pessoa (a fatia é de cada necessidade)
            for nid, v in st.needs.items():
                if v >= 95:
                    self.need_high[nid] += 1
                    self.char_need_high[(st.id, nid)] += 1


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


def build_balance(world, col: Collector, days: float):
    """Fase 6: tabelas e alertas de BALANCEAMENTO (limites em BALANCE_LIMITS)."""
    names = world.names()
    L = BALANCE_LIMITS
    tables, alerts = [], []
    weeks = max(days / 7, 1e-9)

    t = Table(title="Balanceamento — saúde do mundo")
    t.add_column("item")
    t.add_column("valor")
    t.add_column("limite")
    per_week = len(col.arrests) / weeks
    t.add_row("prisões por semana", f"{per_week:.1f} ({len(col.arrests)} no total)", f"≤ {L['prisoes_por_semana']}")
    if days >= 7 and per_week > L["prisoes_por_semana"]:
        alerts.append(f"prisões demais: {per_week:.1f} por semana (limite {L['prisoes_por_semana']})")
    worst7 = 0
    mins = sorted(col.death_minutes)
    for i, m in enumerate(mins):
        worst7 = max(worst7, sum(1 for x in mins[i:] if x - m < 7 * 1440))
    t.add_row("mortes", f"{len(mins)} ({', '.join(f'{k} {n}' for k, n in col.death_causes.most_common())})", "")
    t.add_row("pior janela de 7 dias", f"{worst7} morte(s)", f"< {L['mortes_em_7_dias']}")
    if worst7 >= L["mortes_em_7_dias"]:
        alerts.append(f"rajada de mortes: {worst7} em 7 dias (limite {L['mortes_em_7_dias'] - 1})")
    pop = col.population or [0]
    lim = world.data.world.limits
    t.add_row("população (mín–máx)", f"{min(pop)}–{max(pop)}", f"{lim.min_population}–{lim.max_population}")
    if min(pop) < lim.min_population or max(pop) > lim.max_population:
        alerts.append(f"população saiu dos limites: {min(pop)}–{max(pop)}")
    t.add_row("criaturas", ", ".join(f"{k} {n}" for k, n in col.creatures.most_common()) or "nenhuma", "")
    tables.append(t)

    t = Table(title="Eventos sociais (organizados pelos NPCs)")
    for c in ("evento", "planejados", "sucesso", "fracasso", "taxa de sucesso"):
        t.add_column(c)
    for sid in sorted(set(world.data.social_events) | set(col.social)):
        c = col.social.get(sid, Counter())
        done = c["sucesso"] + c["fracasso"]
        rate = c["sucesso"] / done if done else None
        t.add_row(sid, str(c["planejado"]), str(c["sucesso"]), str(c["fracasso"]),
                  f"{rate:.0%}" if rate is not None else "—")
        if done >= 3 and rate < L["sucesso_minimo_evento_social"]:
            alerts.append(f"evento social '{sid}' fracassa demais: {c['sucesso']}/{done} com sucesso")
        if days >= 30 and c["planejado"] == 0:
            alerts.append(f"evento social '{sid}' nunca foi organizado em {days:g} dias")
    tables.append(t)

    t = Table(title="Diretor: eventos injetados")
    t.add_column("evento")
    t.add_column("vezes", justify="right")
    t.add_column("fatia", justify="right")
    total = sum(col.director.values())
    for eid, n in col.director.most_common():
        t.add_row(eid, str(n), f"{n / total:.0%}")
        if total >= 10 and n / total > L["fatia_maxima_evento_diretor"]:
            alerts.append(f"diretor repete '{eid}': {n} de {total} ({n / total:.0%})")
    never = sorted(e for e in world.data.events if e not in col.director)
    if never:
        t.caption = f"Nunca saíram: {', '.join(never)} (raros/lendários podem não sair num mês)"
    tables.append(t)

    t = Table(title="Necessidades ≥ 95 (explodindo)")
    t.add_column("necessidade")
    t.add_column("amostras ≥ 95", justify="right")
    t.add_column("fatia", justify="right")
    n_samples = max(1, col.need_samples)
    for nid, n in col.need_high.most_common():
        t.add_row(nid, str(n), f"{n / n_samples:.1%}")
        if n / n_samples > L["fatia_maxima_necessidade_95"]:
            alerts.append(f"necessidade '{nid}' explodindo: ≥ 95 em {n / n_samples:.0%} das amostras")
    stuck = []
    for (cid, nid), n in col.char_need_high.most_common():
        frac = n / max(1, col.char_samples[cid])
        if frac > L["fatia_maxima_necessidade_95_por_personagem"] and col.char_samples[cid] >= 8:
            stuck.append(f"{names.get(cid, cid)}: {nid} {frac:.0%}")
            alerts.append(f"{names.get(cid, cid)} vive com {nid} ≥ 95 ({frac:.0%} das amostras)")
    if stuck:
        t.caption = "Travados: " + "; ".join(stuck)
    tables.append(t)

    t = Table(title="Ocupação dos lugares (amostras 4× por dia)")
    t.add_column("lugar")
    t.add_column("média", justify="right")
    t.add_column("máximo", justify="right")
    samples = max(1, col.place_samples)
    for pid in sorted(world.data.places, key=lambda p: -col.place_total[p]):
        t.add_row(names.get(pid, pid), f"{col.place_total[pid] / samples:.1f}", str(col.place_max[pid]))
    empty = [names.get(p, p) for p, pl in world.data.places.items()
             if col.place_max[p] == 0 and pl.access == "normal"]
    if empty:
        t.caption = "Ninguém foi visto (nas amostras): " + ", ".join(empty)
    tables.append(t)
    return tables, alerts


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
    p.add_argument("--sem-balanceamento", action="store_true",
                   help="só o relatório de variedade (sem prisões, eventos, mortes, necessidades, lugares)")
    args = p.parse_args(argv)

    console = Console(highlight=False)
    console.print(f"Simulando {args.days:g} dias (pasta temporária, nada é gravado em data/ ou var/)...")
    world, col, elapsed = run(args.days, args.seed, args.inicio, args.dados)
    tables, alerts, _limit = build_report(world, col, args.days, args.limite_por_dia, args.limite_minimo, elapsed)
    if not args.sem_balanceamento:
        btables, balerts = build_balance(world, col, args.days)
        tables += btables
        alerts += balerts
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
            c.print("[bold green]Nenhum alerta (repetição" + ("" if args.sem_balanceamento else " e balanceamento")
                    + ").[/]")
    if out:
        out.close()
    return 1 if (alerts and args.estrito) else 0


if __name__ == "__main__":
    sys.exit(main())
