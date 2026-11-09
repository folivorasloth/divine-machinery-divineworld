"""Os dados reais de data/ (convertidos da bible) carregam sem erro e fazem sentido."""

from __future__ import annotations

import yaml

from sim.loader import load_data, validate_model, Report
from sim.schemas import Character
from tests.conftest import DATA, messages

EXPECTED_CHARACTERS = {
    "clown", "fool", "musician", "priest", "chef_wife", "chef_husband", "teen",
    "cowboy_fat", "cowboy_thin", "cowboy_old", "medium", "weirdo", "mike", "lady",
    "inspector", "blacksmith", "florist", "greedy", "tech_old", "tech_apprentice", "chief",
}

# todos os lugares da tabela da bible (+ sub-lugares da Cidade e o Campo)
EXPECTED_PLACES = {
    "town_square", "town_hall", "community_kitchen", "tavern", "forge", "market", "houses",
    "fields", "cathedral", "prison", "cemetery", "forest", "sea", "desert", "mountain",
    "underground", "sky", "server_room", "limbo", "outside_world",
}


def load_real():
    data, report = load_data(DATA, environ={})
    assert data is not None, messages(report)
    return data, report


def test_real_data_has_no_errors():
    data, report = load_real()
    assert report.ok, messages(report)


def test_real_data_has_no_warnings():
    _, report = load_real()
    assert not report.warnings, messages(report)


def test_all_bible_characters_exist():
    data, _ = load_real()
    assert set(data.characters) == EXPECTED_CHARACTERS


def test_provisional_names_follow_role_except_mike():
    data, _ = load_real()
    assert data.characters["mike"].name == "Mike"
    for cid, char in data.characters.items():
        if cid != "mike":
            assert char.name.startswith(("O ", "A ")), f"{cid}: {char.name}"


def test_all_bible_places_exist():
    data, _ = load_real()
    assert set(data.places) == EXPECTED_PLACES


def test_tunnels_exist_and_graph_is_symmetric():
    data, _ = load_real()
    tunnels = [(a, e.to) for a, edges in data.graph.items() for e in edges if e.kind == "tunel"]
    assert tunnels, "deveria haver conexões do tipo tunel"
    for a, edges in data.graph.items():
        for edge in edges:
            back = [e for e in data.graph[edge.to] if e.to == a]
            assert back and back[0].kind == edge.kind and back[0].minutes == edge.minutes


def test_groups_and_couple_are_individuals_with_relations():
    data, _ = load_real()
    for cowboy in ("cowboy_fat", "cowboy_thin", "cowboy_old"):
        assert data.characters[cowboy].group == "cowboys"
    assert data.affinity("chef_wife", "chef_husband") > 50
    assert data.affinity("chef_husband", "chef_wife") > 50
    assert data.affinity("clown", "fool") > 50
    assert data.affinity("priest", "medium") < 0
    assert data.affinity("blacksmith", "clown") < 0
    # sem relação explícita, vale a afinidade_padrao
    assert data.affinity("florist", "mike") == data.characters["florist"].default_affinity


def test_screens_example_has_four_screens():
    data, _ = load_real()
    assert len(data.world.screens) == 4
    assert data.screen_of("server_room") == "tela_homelab"


def test_env_defaults_are_placeholders_not_ips():
    data, _ = load_real()
    assert data.world.mqtt.host == "mqtt.local"
    assert data.world.mqtt.port == 1883
    assert data.world.seed is None


def test_model_template_is_a_valid_character():
    raw = yaml.safe_load((DATA / "characters" / "_MODELO.yaml").read_text(encoding="utf-8"))
    report = Report()
    char = validate_model(Character, raw, report, "_MODELO.yaml")
    assert char is not None, messages(report)


def test_model_template_is_ignored_by_loader():
    data, _ = load_real()
    assert "modelo_exemplo" not in data.characters


def test_every_routine_action_is_scorable():
    data, _ = load_real()
    for cid, char in data.characters.items():
        for block in char.routine:
            assert data.actions[block.action].kind != "movimento", (cid, block.action)
