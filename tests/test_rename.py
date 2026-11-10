"""Critério de aceite da Fase 0: mudar o `nome` de um personagem (ou lugar)
no YAML não exige mudar nenhum outro arquivo."""

from __future__ import annotations

import re

from sim import text
from sim.loader import load_data
from tests.conftest import messages


def _rename(path, new_name):
    # edita só a linha `nome:` (como o João faria no editor), preservando comentários
    content = path.read_text(encoding="utf-8")
    content, count = re.subn(r"^nome: .*$", f"nome: {new_name}", content, count=1, flags=re.M)
    assert count == 1
    path.write_text(content, encoding="utf-8")


def test_renaming_a_character_touches_only_its_file(data_copy):
    _rename(data_copy / "characters" / "clown.yaml", "Bozó das Couves")
    data, report = load_data(data_copy, environ={})
    assert report.ok and not report.warnings, messages(report)
    assert data.characters["clown"].name == "Bozó das Couves"
    # relações apontando para o palhaço continuam valendo (são por id)
    assert data.affinity("fool", "clown") > 50
    assert data.affinity("blacksmith", "clown") < 0
    # textos guardados com tokens de id passam a mostrar o nome novo
    stored = text.fill("{eu} buzina pra {outro}.", {"eu": "clown", "outro": "fool"})
    assert stored == "{@clown} buzina pra {@fool}."
    assert text.render(stored, data.names()) == "Bozó das Couves buzina pro Fool."


def test_renaming_every_character_and_place_still_validates(data_copy):
    for path in list((data_copy / "characters").glob("*.yaml")) + list((data_copy / "places").glob("*.yaml")):
        if not path.name.startswith("_"):
            _rename(path, f"Nome Novo {path.stem}")
    data, report = load_data(data_copy, environ={})
    assert report.ok, messages(report)
    assert data.name_of("tavern") == "Nome Novo tavern"
