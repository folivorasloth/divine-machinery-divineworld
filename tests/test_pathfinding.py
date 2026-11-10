"""Caminhos no grafo dos lugares."""

from __future__ import annotations

import pytest

from sim.loader import load_data_or_raise
from sim.pathfinding import find_path, shortest_paths
from tests.conftest import DATA


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


def test_same_place_is_empty_path(data):
    assert find_path(data, "tavern", "tavern") == []


def test_shortest_path_uses_minutes(data):
    # Casas -> Taverna: casas->praça (4) + praça->taverna (3) = 7 min
    path = find_path(data, "houses", "tavern")
    assert [e.to for e in path] == ["town_square", "tavern"]
    dist, _ = shortest_paths(data, "houses")
    assert dist["tavern"] == 7


def test_path_through_tunnels(data):
    # Praça -> Floresta é túnel; Floresta -> Montanha é caminho
    path = find_path(data, "town_square", "mountain")
    assert [(e.to, e.kind) for e in path] == [("forest", "tunel"), ("mountain", "caminho")]


def test_special_and_never_places_are_unreachable(data):
    dist, _ = shortest_paths(data, "town_square")
    assert "sky" not in dist  # acesso especial
    assert "limbo" not in dist
    assert "outside_world" not in dist  # acesso nunca
    assert "desert" in dist


def test_blocked_places_are_avoided(data):
    # com o Mercado bloqueado (névoa, Fase 3), não dá para chegar ao Mar
    assert find_path(data, "town_square", "sea", blocked={"market"}) is None
    # e a Taverna continua alcançável pela praça
    assert [e.to for e in find_path(data, "market", "tavern", blocked={"town_square"})] == ["tavern"]
