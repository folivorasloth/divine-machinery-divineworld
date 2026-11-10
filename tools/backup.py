"""Backup do mundo (o SQLite) — seguro com o servidor rodando (Fase 6).

    python -m tools.backup                         # var/world.sqlite -> var/backups/world-AAAA-MM-DD_HHMM.sqlite
    python -m tools.backup --banco var/world.sqlite --destino /mnt/nas/dw --manter 14
    docker compose exec world python -m tools.backup     # no Docker (var/ é um volume)

Usa a API de backup do próprio SQLite (copia uma foto consistente mesmo com o
mundo escrevendo; não precisa parar nada) e apaga os backups mais antigos,
mantendo os `--manter` mais novos. Para restaurar: pare o servidor, copie o
arquivo de backup por cima de var/world.sqlite (apague world.sqlite-wal e
-shm se existirem) e ligue de novo.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def backup(db: Path, dest_dir: Path, keep: int) -> Path:
    if not db.exists():
        raise FileNotFoundError(f"banco não encontrado: {db}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y-%m-%d_%H%M%S}"
    target = dest_dir / f"{db.stem}-{stamp}.sqlite"
    n = 1
    while target.exists():  # dois backups no mesmo segundo
        target = dest_dir / f"{db.stem}-{stamp}-{n}.sqlite"
        n += 1
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    old = sorted(dest_dir.glob(f"{db.stem}-*.sqlite"), key=lambda f: (f.stat().st_mtime_ns, f.name))
    for f in old[:-keep] if keep > 0 else []:
        f.unlink()
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backup do SQLite do mundo (seguro com o servidor rodando).")
    p.add_argument("--banco", default=os.environ.get("DW_DB_PATH", "var/world.sqlite"), help="arquivo do mundo")
    p.add_argument("--destino", default=None, help="pasta dos backups (padrão: <pasta do banco>/backups)")
    p.add_argument("--manter", type=int, default=10, help="quantos backups manter (padrão 10; 0 = todos)")
    args = p.parse_args(argv)
    db = Path(args.banco)
    dest = Path(args.destino) if args.destino else db.parent / "backups"
    try:
        target = backup(db, dest, args.manter)
    except (OSError, sqlite3.Error) as exc:
        print(f"Backup falhou: {exc}", file=sys.stderr)
        return 1
    print(f"Backup salvo em {target} ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
