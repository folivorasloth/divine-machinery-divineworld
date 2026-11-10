"""Valida todos os arquivos de `data/`.

    python -m tools.validate            # valida ./data
    python -m tools.validate --dados outra/pasta
    python -m tools.validate --estrito  # avisos também contam como erro

Sai com código 0 se não houver erros, 1 se houver.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.markup import escape

from sim.loader import load_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida os YAML do Mundo Vivo.")
    parser.add_argument("--dados", default="data", help="pasta de dados (padrão: data)")
    parser.add_argument("--estrito", action="store_true", help="falha também com avisos")
    args = parser.parse_args(argv)

    data, report = load_data(args.dados)

    say = Console(highlight=False).print

    for issue in report.errors:
        say(f"[bold red]ERRO[/]  {escape(issue.file)}: {escape(issue.message)}")
    for issue in report.warnings:
        say(f"[yellow]AVISO[/] {escape(issue.file)}: {escape(issue.message)}")

    if data is not None:
        say(
            f"\n[bold]{data.world.name}[/]: {len(data.characters)} personagens, "
            f"{len(data.places)} lugares, {len(data.actions)} ações, {len(data.traits)} traços, "
            f"{len(data.professions)} profissões, {sum(len(v) for v in data.lines.values())} falas "
            f"em {len(data.lines)} situações, {len(data.events)} eventos, {len(data.social_events)} eventos sociais, "
            f"{len(data.world.memory.kinds)} tipos de memória, {len(data.world.screens)} telas."
        )

    failed = not report.ok or (args.estrito and report.warnings)
    if failed:
        say(f"\n[bold red]{len(report.errors)} erro(s)[/], {len(report.warnings)} aviso(s).")
        return 1
    say(f"\n[bold green]Tudo certo![/] 0 erros, {len(report.warnings)} aviso(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
