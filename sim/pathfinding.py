"""Caminhos no grafo dos lugares (Dijkstra pelos minutos das conexões).

Lugares com acesso `especial` (Céu, Limbo) ou `nunca` (Mundo de Fora) não
entram no caminho, nem os que estão em `blocked` (névoa, Fase 3). O lugar de
partida sempre vale (quem já está lá dentro pode sair).
"""

from __future__ import annotations

import heapq

from sim.loader import Edge, WorldData


def passable(data: WorldData, place_id: str, blocked: frozenset[str] | set[str] = frozenset()) -> bool:
    place = data.places.get(place_id)
    return place is not None and place.access == "normal" and place_id not in blocked


def shortest_paths(
    data: WorldData, start: str, blocked: frozenset[str] | set[str] = frozenset()
) -> tuple[dict[str, float], dict[str, tuple[str, Edge]]]:
    """Distâncias (minutos) de `start` até todo lugar alcançável, e de onde se
    chega em cada um (para remontar o caminho)."""
    dist: dict[str, float] = {start: 0.0}
    came_from: dict[str, tuple[str, Edge]] = {}
    queue: list[tuple[float, str]] = [(0.0, start)]
    while queue:
        d, current = heapq.heappop(queue)
        if d > dist.get(current, float("inf")):
            continue
        for edge in data.graph.get(current, []):
            if not passable(data, edge.to, blocked):
                continue
            nd = d + edge.minutes
            if nd < dist.get(edge.to, float("inf")):
                dist[edge.to] = nd
                came_from[edge.to] = (current, edge)
                heapq.heappush(queue, (nd, edge.to))
    return dist, came_from


def path_from(came_from: dict[str, tuple[str, Edge]], start: str, goal: str) -> list[Edge] | None:
    """Lista de conexões de `start` até `goal` ([] se já está lá; None se não dá)."""
    if goal == start:
        return []
    if goal not in came_from:
        return None
    edges: list[Edge] = []
    current = goal
    while current != start:
        previous, edge = came_from[current]
        edges.append(edge)
        current = previous
    edges.reverse()
    return edges


def find_path(
    data: WorldData, start: str, goal: str, blocked: frozenset[str] | set[str] = frozenset()
) -> list[Edge] | None:
    _dist, came_from = shortest_paths(data, start, blocked)
    return path_from(came_from, start, goal)
