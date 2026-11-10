"""Roda o Mundo Vivo no terminal, com o Chat do Mundo colorido.

    python -m tools.run                       # tempo real (multiplicador do world.yaml)
    python -m tools.run --speed 60            # 1 hora do mundo por minuto real
    python -m tools.run --speed 600 --dias 1  # um dia em ~2,4 minutos e sai
    python -m tools.run --fast --dias 1 --novo --inicio 05:00 --seed 42 --resumo
                                              # um dia inteiro em segundos, do zero, e um resumo no fim
    python -m tools.run --personagem mike --lugar tavern   # filtros (podem repetir)

O estado fica no SQLite (`persistencia.banco` do world.yaml, ou --banco). Ao
religar, o mundo continua de onde parou. Ctrl+C salva e sai.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from sim.clock import WorldClock
from sim.engine import World
from sim.events import Event
from sim.loader import DataError, load_data_or_raise
from sim.persistence import Storage

# estilo de cada tipo de evento no terminal
STYLES = {
    "system": "bold red",
    "period_changed": "bold blue",
    "bell": "bold yellow",
    "speech": "white",
    "action_started": "cyan",
    "action_finished": "dim cyan",
    "teleport_started": "magenta",
    "teleport_finished": "magenta",
    "move_started": "dim green",
    "move_arrived": "dim green",
    "decision": "dim",
}

LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "aviso": logging.WARNING, "erro": logging.ERROR}

# o que aparece por padrão (o resto com --movimento / --debug)
MOVE_TYPES = {"move_started", "move_arrived"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Roda o Mundo Vivo com o Chat do Mundo no terminal.")
    p.add_argument("--speed", type=float, default=None,
                   help="multiplicador do tempo (60 = 1 hora do mundo por minuto real). Padrão: world.yaml")
    p.add_argument("--fast", action="store_true", help="não espera o tempo real: simula o mais rápido possível")
    p.add_argument("--horas", type=float, default=None, help="roda N horas do mundo e sai")
    p.add_argument("--dias", type=float, default=None, help="roda N dias do mundo e sai")
    p.add_argument("--personagem", action="append", default=[], help="só eventos deste personagem (id; pode repetir)")
    p.add_argument("--lugar", action="append", default=[], help="só eventos deste lugar (id; pode repetir)")
    p.add_argument("--movimento", action="store_true", help="mostra também cada passo de caminhada")
    p.add_argument("--debug", action="store_true", help="mostra no chat cada decisão (top 3 e os motivos de cada nota)")
    p.add_argument("--banco", default=None, help="arquivo SQLite (padrão: persistencia.banco do world.yaml)")
    p.add_argument("--novo", action="store_true", help="apaga o banco e começa um mundo novo")
    p.add_argument("--seed", type=int, default=None, help="semente do sorteio (só para mundo novo)")
    p.add_argument("--inicio", default=None,
                   help='hora do mundo ao criar um mundo novo: "05:30" (hoje) ou "2026-11-09T05:30"')
    p.add_argument("--resumo", action="store_true", help="no fim, mostra um resumo do dia de cada personagem")
    p.add_argument("--saida", default=None, help="também grava o Chat do Mundo (sem cores) neste arquivo")
    p.add_argument("--dados", default="data", help="pasta de dados (padrão: data)")
    return p


class ChatPrinter:
    """Assinante do EventBus que imprime o Chat do Mundo."""

    def __init__(self, world: World, consoles: list[Console], characters: list[str], places: list[str],
                 show_moves: bool, debug: bool):
        self.world = world
        self.consoles = consoles
        self.characters = set(characters)
        self.places = set(places)
        self.show_moves = show_moves
        self.debug = debug

    def wanted(self, ev: Event) -> bool:
        if ev.type == "decision" and not self.debug:
            return False
        if ev.type in MOVE_TYPES and not self.show_moves:
            return False
        if ev.type == "action_started" and ev.data.get("spoke"):
            return False  # a fala (speech) já conta o que está acontecendo
        if ev.type == "action_finished" and not ev.text:
            return False
        if ev.type in ("system", "period_changed"):
            return True
        if self.characters and not self.characters & set(ev.actors):
            return False
        if self.places:
            where = {ev.place, ev.data.get("from"), ev.data.get("to")}
            if not self.places & where:
                return False
        return True

    def __call__(self, ev: Event) -> None:
        if not self.wanted(ev):
            return
        names = self.world.names()
        when = f"{ev.ts[8:10]}/{ev.ts[5:7]} {ev.ts[11:16]}"  # "2026-11-09T06:00..." -> "09/11 06:00"
        where = names.get(ev.place, ev.place) if ev.place else ""
        prefix = "SINO " if ev.type == "bell" else ""
        line = f"[{when}] " + (f"({where}) " if where else "") + prefix + ev.render(names)
        style = STYLES.get(ev.type, "white")
        for console in self.consoles:
            console.print(f"[{style}]{escape(line)}[/]")


class DayStats:
    """Conta o que cada personagem fez (para o --resumo)."""

    def __init__(self) -> None:
        self.actions: dict[str, Counter] = defaultdict(Counter)
        self.minutes: dict[str, Counter] = defaultdict(Counter)
        self.places: dict[str, set] = defaultdict(set)
        self.talked: Counter = Counter()
        self.bells: list[str] = []
        self.teleports = 0

    def __call__(self, ev: Event) -> None:
        if not ev.actors:
            return
        who = ev.actors[0]
        if ev.type in ("action_started", "bell"):
            self.actions[who][ev.data["action"]] += 1
            if ev.place:
                self.places[who].add(ev.place)
            if ev.data.get("target"):
                self.talked[ev.data["target"]] += 1
        if ev.type == "action_finished":
            self.minutes[who][ev.data["action"]] += ev.data.get("minutes", 0)
        if ev.type == "bell":
            self.bells.append(ev.ts[11:16])
        if ev.type == "teleport_started":
            self.teleports += 1

    def table(self, world: World) -> Table:
        names = world.names()
        # quem ainda está no meio de uma ação (ex.: dormindo) conta o que já fez
        for cid, st in world.states.items():
            if st.activity is not None:
                self.minutes[cid][st.activity.action] += st.activity.elapsed
        t = Table(title="Resumo por personagem (contagem de ações iniciadas; horas de sono)")
        for col in ("personagem", "dormir (h)", "comer", "trabalhar", "conversar*", "festejar", "perambular",
                    "outros", "lugares"):
            t.add_column(col)
        main = {"dormir", "comer", "trabalhar", "conversar", "festejar", "perambular"}
        for cid in world.data.characters:
            acts = self.actions[cid]
            others = ", ".join(f"{a} {n}" for a, n in sorted(acts.items()) if a not in main)
            sleep_h = self.minutes[cid]["dormir"] / 60
            t.add_row(names[cid], f"{acts['dormir']} ({sleep_h:.1f})", str(acts["comer"]), str(acts["trabalhar"]),
                      f"{acts['conversar']}+{self.talked[cid]}", str(acts["festejar"]), str(acts["perambular"]),
                      others, str(len(self.places[cid])))
        t.caption = (f"* conversar: puxou papo + foi chamado. Sino tocado às: {', '.join(self.bells) or '—'}. "
                     f"Viagens por túnel: {self.teleports}.")
        return t


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console(highlight=False)
    try:
        data = load_data_or_raise(args.dados)
    except DataError as exc:
        console.print(f"[bold red]{escape(str(exc))}[/]\nRode: python -m tools.validate")
        return 1
    # o log técnico (stderr) segue o nivel_log do world.yaml; as decisões aparecem
    # no próprio Chat do Mundo com --debug (sem duplicar no log)
    logging.basicConfig(level=LOG_LEVELS[data.world.log_level], format="%(levelname)s %(name)s: %(message)s")
    for cid in args.personagem:
        if cid not in data.characters:
            console.print(f"[red]personagem '{escape(cid)}' não existe[/]")
            return 1
    for pid in args.lugar:
        if pid not in data.places:
            console.print(f"[red]lugar '{escape(pid)}' não existe[/]")
            return 1

    db_path = Path(args.banco or data.world.storage.database)
    if args.novo:
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
    storage = Storage(db_path)
    start = WorldClock.parse_start(data.world.clock, args.inicio) if args.inicio else None
    if storage.has_world() and (args.inicio or args.seed is not None):
        console.print("[yellow]--inicio e --seed só valem para mundo novo (use --novo); continuando o mundo salvo.[/]")

    out_file = open(args.saida, "w", encoding="utf-8") if args.saida else None
    consoles = [console] + ([Console(file=out_file, no_color=True, highlight=False, width=200)] if out_file else [])

    world = World(data, storage, seed=args.seed, speed=args.speed, start=start)
    printer = ChatPrinter(world, consoles, args.personagem, args.lugar, args.movimento, args.debug)
    stats = DayStats()
    world.bus.subscribe(printer)
    world.bus.subscribe(stats)

    def on_sigterm(_signum, _frame):
        world.request_stop()

    signal.signal(signal.SIGTERM, on_sigterm)

    console.print(f"[bold]{escape(data.world.name)}[/] — hora do mundo {world.clock.iso()}, seed {world.seed}, "
                  f"velocidade {'máxima (--fast)' if args.fast else f'{world.speed:g}×'}, banco {db_path}"
                  + (" (continuando)" if world.resumed else " (mundo novo)"))

    until = None
    total_hours = (args.horas or 0) + (args.dias or 0) * 24
    if total_hours > 0:
        until = world.clock.now + timedelta(hours=total_hours)
    try:
        if world.resumed and world.speed == 1 and not args.fast:
            world.catch_up()
        world.run(until=until, fast=args.fast)
    except KeyboardInterrupt:
        console.print("\n[bold]Ctrl+C: salvando o mundo...[/]")
    finally:
        world.close()
        if args.resumo:
            for c in consoles:
                c.print(stats.table(world))
        console.print(f"Mundo salvo em {db_path} — hora do mundo {world.clock.iso()}, {world.ticks} ticks.")
        if out_file:
            out_file.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
