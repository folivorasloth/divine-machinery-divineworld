"""Fixtures compartilhadas: uma cópia de data/ que cada teste pode estragar à vontade."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"

# Fase 3: antes de qualquer fixture carregar data/, os nascidos dos testes já vão
# para uma pasta temporária (nunca para data/characters/born do repositório)
os.environ["DW_BORN_DIR"] = tempfile.mkdtemp(prefix="dw_test_born_")


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


@pytest.fixture(autouse=True)
def _isolated_life(tmp_path_factory, monkeypatch):
    """Fase 3: nascimentos nunca gravam em data/characters/born durante os testes
    (DW_BORN_DIR aponta para uma pasta temporária) e o clima nunca vai à internet."""
    born = tmp_path_factory.mktemp("nascidos")
    monkeypatch.setenv("DW_BORN_DIR", str(born))

    def no_network(*_a, **_k):
        raise OSError("sem rede nos testes")

    monkeypatch.setattr("sim.weather.fetch_open_meteo", no_network)
    yield born
