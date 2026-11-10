"""Simulação headless do Mundo Vivo (Divine Machinery).

Fase 0: esquemas de dados (`sim.schemas`), carregador/validador (`sim.loader`),
curvas de pontuação (`sim.curves`) e templates de texto (`sim.text`).
Fase 1: o núcleo — relógio (`clock`), sorteio (`rng`), estado (`state`),
necessidades (`needs`), caminhos (`pathfinding`), Utility AI (`utility`), falas
(`speech`), eventos (`events`), SQLite (`persistence`) e o mundo (`engine`).
O mapa dos módulos está em `docs/arquitetura.md`.
"""
