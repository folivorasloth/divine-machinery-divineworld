"""Utility AI (candidatos, nota, escolha com seed, explicação) e falas."""

from __future__ import annotations

import random
from datetime import datetime

import pytest

from sim import speech, utility
from sim.clock import WorldClock
from sim.engine import World
from sim.loader import load_data_or_raise
from sim.state import Activity
from tests.conftest import DATA


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


def world_at(data, hhmm: str, seed: int = 1) -> World:
    start = WorldClock.parse_start(data.world.clock, hhmm, real_now=datetime(2026, 11, 9, 12, 0))
    world = World(data, None, seed=seed, start=start)
    for st in world.states.values():  # ninguém começa dormindo nestes testes
        st.activity = None
    return world


def ranked_for(world: World, cid: str):
    ctx = world.decision_context()
    char = world.data.characters[cid]
    return utility.rank(utility.candidates(char, world.states[cid], ctx), world.data.world.decision.min_score)


def test_hungry_character_at_lunch_goes_to_eat(data):
    world = world_at(data, "12:10")
    st = world.states["chief"]
    st.place = "town_hall"
    st.needs.update(fome=85, sono=10, tedio=10, social=10, fe=0)
    best = ranked_for(world, "chief")[0]
    assert best.action == "comer"
    assert best.place == "community_kitchen"  # a rotina do Chefe aponta a cozinha
    assert any(f.label == "rotina" for f in best.factors)


def test_work_only_at_workplace_and_only_with_a_profession(data):
    world = world_at(data, "09:00")
    for cid in ("blacksmith", "mike"):
        world.states[cid].needs.update(fome=10, sono=10)
    work = [c for c in ranked_for(world, "blacksmith") if c.action == "trabalhar"]
    assert work and {c.place for c in work} == {"forge"}
    assert not [c for c in ranked_for(world, "mike") if c.action == "trabalhar"]  # Mike não tem profissão


def test_bell_only_inside_the_time_windows(data):
    for hhmm, expected in (("06:05", True), ("12:10", True), ("09:00", False), ("18:20", False)):
        world = world_at(data, hhmm)
        actions = {c.action for c in ranked_for(world, "priest")}
        assert ("tocar_sino" in actions) is expected, hhmm
    # só o Padre toca o sino
    world = world_at(data, "06:05")
    assert "tocar_sino" not in {c.action for c in ranked_for(world, "fool")}


def test_bell_wins_and_cooldown_prevents_repeating(data):
    world = world_at(data, "06:01")
    world.states["priest"].place = "cathedral"
    assert ranked_for(world, "priest")[0].action == "tocar_sino"
    world.states["priest"].cooldowns["tocar_sino"] = world._now_minutes() + 30
    assert "tocar_sino" not in {c.action for c in ranked_for(world, "priest")}


def test_conversation_needs_someone_awake_in_the_same_place(data):
    world = world_at(data, "15:00")
    for cid, st in world.states.items():
        st.place = "houses"
    world.states["fool"].place = "tavern"
    world.states["clown"].place = "tavern"
    targets = {c.target for c in ranked_for(world, "fool") if c.action == "conversar"}
    assert targets == {"clown"}
    world.states["clown"].activity = Activity(action="dormir", place="tavern", duration=60)
    assert not [c for c in ranked_for(world, "fool") if c.action == "conversar"]


def test_affinity_limits_who_you_talk_to(data):
    world = world_at(data, "15:00")
    for st in world.states.values():
        st.place = "houses"
    world.affinities[("priest", "medium")] = -90  # abaixo do afinidade_min -60
    targets = {c.target for c in ranked_for(world, "priest") if c.action == "conversar"}
    assert "medium" not in targets and "chief" in targets


def test_choice_is_reproducible_with_the_same_seed(data):
    world = world_at(data, "10:00")
    ranked = ranked_for(world, "teen")
    cfg = data.world.decision
    picks_a = [utility.choose(ranked, cfg.top_n, cfg.temperature, random.Random(5)).label() for _ in range(3)]
    picks_b = [utility.choose(ranked, cfg.top_n, cfg.temperature, random.Random(5)).label() for _ in range(3)]
    assert picks_a == picks_b
    # e a escolha é sempre uma das 3 melhores
    rng = random.Random(9)
    top = {c.label() for c in ranked[:3]}
    assert all(utility.choose(ranked, cfg.top_n, cfg.temperature, rng).label() in top for _ in range(50))


def test_relative_cutoff_drops_weak_options():
    a = utility.Candidate("a", "x", None, 0, 1.0)
    b = utility.Candidate("b", "x", None, 0, 0.1)
    rng = random.Random(1)
    assert {utility.choose([a, b], 3, 1.0, rng, relative_cutoff=0.5).action for _ in range(30)} == {"a"}


def test_explanation_has_top3_and_reasons(data):
    world = world_at(data, "12:10")
    world.states["chief"].needs.update(fome=85)
    ranked = ranked_for(world, "chief")
    text = utility.explain(ranked[0], ranked)
    assert text.startswith("escolheu comer@community_kitchen")
    assert "top3:" in text and text.count("@") >= 4
    assert "necessidade.fome=85→" in text and "rotina×" in text


def test_review_wakes_the_priest_for_the_bell(data):
    world = world_at(data, "06:00")
    st = world.states["priest"]
    st.place = "cathedral"
    st.needs.update(sono=10)
    st.activity = Activity(action="trabalhar", place="cathedral", duration=120)
    assert world._review(st, world.decision_context())
    assert st.activity.action == "tocar_sino"


# ------------------------------------------------------------------- falas


def ctx_for(world: World, cid: str, place: str, target=None) -> speech.SpeechContext:
    return world._speech_ctx(cid, place, target)


def test_lines_are_filtered_by_character_and_use_catchphrases(data):
    world = world_at(data, "07:00")
    rng = random.Random(3)
    lines = {speech.pick_line(data, "comer", ctx_for(world, "mike", "community_kitchen"), rng) for _ in range(40)}
    assert "{@mike} come. Só isso." in lines
    assert not any("concha" in line for line in lines)  # fala exclusiva da Cozinheira
    chef = {speech.pick_line(data, "comer", ctx_for(world, "chef_wife", "community_kitchen"), rng) for _ in range(40)}
    assert any("Come que esfria!" in line for line in chef)


def test_lines_needing_a_target_or_catchphrase_are_skipped(data):
    world = world_at(data, "07:00")
    rng = random.Random(3)
    # o Aprendiz não tem bordão: nenhuma fala com {bordao} pode sair para ele
    for _ in range(40):
        line = speech.pick_line(data, "resposta", ctx_for(world, "tech_apprentice", "houses", "fool"), rng)
        assert "{bordao}" not in line and '""' not in line


def test_anti_repetition_avoids_recent_lines(data):
    world = world_at(data, "07:00")
    rng = random.Random(4)
    recent: list[str] = []
    seen = [speech.pick_line(data, "dormir", ctx_for(world, "fool", "houses"), rng, recent) for _ in range(2)]
    assert seen[0] != seen[1]  # "dormir" tem 2 falas gerais para o Fool: não repete em seguida
    assert len(recent) == 2
