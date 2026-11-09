"""Fixtures compartilhadas: uma cópia de data/ que cada teste pode estragar à vontade."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    """Cópia completa de data/ num diretório temporário."""
    target = tmp_path / "data"
    shutil.copytree(DATA, target)
    return target


def edit_yaml(path: Path, change) -> None:
    """Abre um YAML, aplica `change(conteudo)` e salva de volta."""
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(content)
    path.write_text(yaml.safe_dump(content, allow_unicode=True, sort_keys=False), encoding="utf-8")


def messages(report) -> str:
    return "\n".join(str(i) for i in report.issues)
