"""Fase 3: morte, funeral, luto, herança, fantasmas, ressurreição, nascimentos,
sucessão, criaturas, clima, névoa e o diretor. Nada aqui usa a rede."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from sim import creatures, lifecycle, utility, weather
from sim.clock import WorldClock
from sim.engine import Command, World
from sim.loader import load_data, load_data_or_raise
from sim.persistence import Storage
from tests.conftest import DATA


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


def world_at(data, hhmm: str = "10:00", seed: int = 3, db=None, **kw) -> World:
    start = WorldClock.parse_start(data.world.clock, hhmm, real_now=datetime(2026, 11, 9, 12, 0))
    world = World(data, Storage(db) if db else None, seed=seed, start=start, **kw)
    for st in world.states.values():
        st.activity = None
        st.plan = None
    return world


def collect(world: World) -> list:
    events = []
    world.bus.subscribe(events.append)
    return events


def run_minutes(world: World, minutes: int) -> None:
    for _ in range(minutes):
        world.tick()


def types(events) -> list[str]:
    return [e.type for e in events]


# ------------------------------------------------------------------- morte
def test_kill_is_permanent_and_everyone_remembers(data):
    world = world_at(data)
    events = collect(world)
    lifecycle.kill(world, "clown", "acidente", place="market")
    st = world.states["clown"]
    assert not st.alive and st.place == data.world.death.body_place
    death = next(e for e in events if e.type == "death")
    assert death.importance == 3 and death.actors[0] == "clown" and "{" not in death.render(world.names())
    assert world.memories.strongest("fool", "morte", involving="clown").permanent
    assert "clown" not in world.present_at("market")
    # o Palhaço não decide mais nada, nem é alvo de conversa
    run_minutes(world, 30)
    assert world.states["clown"].activity is None and world.states["clown"].plan is None


def test_death_never_takes_the_city_below_min_population(data):
    world = world_at(data)
    lim = data.world.limits
    alive = lifecycle.living(world)
    for cid in alive[: len(alive) - lim.min_population]:
        lifecycle.kill(world, cid, "velhice")
    assert len(lifecycle.living(world)) == lim.min_population
    survivor = lifecycle.living(world)[0]
    # mesmo com chance 100%, o sorteio não mata mais ninguém
    world.data.world.death.causes["velhice"].chance = 1.0
    try:
        assert not lifecycle.roll(world, "diario", survivor)
    finally:
        world.data.world.death.causes["velhice"].chance = None
    assert world.states[survivor].alive


def test_grief_follows_affinity_and_relation_kind(data):
    world = world_at(data)
    lifecycle.kill(world, "teen", "acidente")
    mom = lifecycle.grief_level(world, "chef_wife")
    other = lifecycle.grief_level(world, "inspector")  # detesta o Adolescente
    assert mom > 0.8 and other == 0
    rates, actions = lifecycle.multipliers(world, "chef_wife")
    assert actions["festejar"] < 0.5 and rates["fe"] > 1
    # o luto entra na nota: festejar vale menos para a mãe
    assert ("luto/clima", actions["festejar"]) in world.score_multiplier(
        "chef_wife", data.actions["festejar"], "tavern")


def test_inheritance_goes_to_the_heir(data):
    world = world_at(data)
    events = collect(world)
    lifecycle.kill(world, "clown", "acidente")
    inh = next(e for e in events if e.type == "inheritance")
    assert inh.actors[0] == "fool" and world.life.objects["fool"] == ["nariz vermelho rachado"]


# ----------------------------------------------------------------- funeral
def test_funeral_rains_has_procession_reactions_and_a_grave(data):
    world = world_at(data, "08:00", seed=5)
    events = collect(world)
    lifecycle.kill(world, "florist", "velhice")
    fun = world.life.funerals[-1]
    assert fun["status"] == "planejado"
    minutes = int(fun["end"] - world.now_minutes()) + 5
    saw_rain_during = []
    for _ in range(minutes):
        world.tick()
        if fun["wake"] <= world.now_minutes() < fun["end"]:
            saw_rain_during.append(world.weather.kind)
    assert set(saw_rain_during) == {data.world.weather.funeral_kind}  # sempre chove no funeral
    ts = types(events)
    for t in ("funeral_planned", "funeral_started", "funeral_procession", "funeral_ended", "grave"):
        assert t in ts, t
    ended = next(e for e in events if e.type == "funeral_ended")
    assert len(ended.data["attendees"]) >= 6
    reactions = [e for e in events if e.type == "speech" and e.data.get("situation", "").startswith("funeral")]
    assert len(reactions) >= 5
    grave = next(e for e in events if e.type == "grave")
    txt = grave.render(world.names())
    assert "Florista" in txt and "Morte natural" in txt and "09/11/2026" in txt
    assert world.memories.strongest(ended.data["attendees"][0], "funeral") is not None


def test_funeral_reactions_follow_personality(data):
    """O Fool tem falas próprias no funeral (piada na hora errada)."""
    world = world_at(data, "08:00", seed=11)
    lifecycle.kill(world, "mike", "velhice")
    fun = world.life.funerals[-1]
    world.clock.now += timedelta(minutes=fun["start"] - world.now_minutes())
    world.states["fool"].place = data.world.funeral.burial_place
    extra, edata = {}, {}
    found = set()
    for _ in range(30):
        extra, edata = {}, {}
        assert world._special_before(world.states["fool"], data.actions["velar"], data.world.funeral.burial_place,
                                     None, False, extra, edata)
        found.add(edata["situation"])
    assert "funeral_personalidade" in found


# ------------------------------------------------------------- nascimento
def test_birth_writes_yaml_in_born_dir_and_joins_the_world(data, _isolated_life):
    world = world_at(data)
    events = collect(world)
    cid = lifecycle.birth(world, ["curioso"])
    born_dir = Path(os.environ["DW_BORN_DIR"])
    file = born_dir / f"{cid}.yaml"
    assert file.exists()
    raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    assert raw["id"] == cid and "curioso" in raw["tracos"] and raw["nome"].endswith("nº 1")
    assert cid in world.states and world.states[cid].alive
    assert any(e.type == "birth" and e.actors[0] == cid for e in events)
    # o repositório nunca recebe nascidos de teste
    assert not list((DATA / "characters" / "born").glob("born_*.yaml"))
    # o João pode renomear: o arquivo carrega e valida (lido via DW_BORN_DIR)
    loaded, report = load_data(DATA, environ={})
    assert report.ok and cid in loaded.characters
    # e o WorldData de quem chamou não foi alterado (o mundo usa uma cópia)
    assert cid not in data.characters


def test_birth_can_inherit_a_quirk_that_becomes_a_catchphrase(data):
    world = world_at(data, seed=2)
    lifecycle.kill(world, "fool", "velhice")
    world.data.traits_file.birth.inherit_chance = 1.0
    try:
        got = None
        for _ in range(12):
            cid = lifecycle.birth(world)
            herd = world.data.characters[cid].inherited
            assert herd is not None and herd.from_ == "fool"
            if herd.quirk:
                got = world.data.characters[cid]
                break
    finally:
        world.data.traits_file.birth.inherit_chance = 0.6
    assert got is not None and got.catchphrases == ["...hehe."]


def test_birth_chance_grows_with_vacancies_and_stops_at_max(data):
    world = world_at(data)
    base = lifecycle.birth_chance_per_day(world)
    lifecycle.kill(world, "mike", "velhice")
    assert lifecycle.birth_chance_per_day(world) > base
    world.data.world.limits.max_population, old = len(lifecycle.living(world)), world.data.world.limits.max_population
    try:
        assert lifecycle.birth_chance_per_day(world) == 0
    finally:
        world.data.world.limits.max_population = old


def test_birth_command(data):
    world = world_at(data)
    events = collect(world)
    world.submit(Command("nascer", "alegre curioso"))
    world.tick()
    birth = next(e for e in events if e.type == "birth")
    assert {"alegre", "curioso"} <= set(world.data.characters[birth.actors[0]].traits)


# --------------------------------------------------------------- sucessão
def test_priest_succession_by_vocation_takes_role_routine_and_church(data):
    world = world_at(data, seed=4)
    events = collect(world)
    lifecycle.kill(world, "priest", "velhice")
    vac = world.life.vacancies[-1]
    assert vac["profession"] == "padre" and vac["mode"] == "vocacao"
    world.clock.now += timedelta(minutes=vac["due"] - world.now_minutes() + 1)
    lifecycle._succession_hourly(world)
    succ = next(e for e in events if e.type == "succession")
    new = succ.actors[0]
    char = world.data.characters[new]
    assert char.profession == "padre" and char.workplace == "cathedral"
    assert any(b.action == "tocar_sino" for b in char.routine)
    assert world.leader_of("igreja") == new and world.states[new].faction == "igreja"
    # o papel volta depois de reiniciar (sobrevive ao banco)
    assert world.life.overrides[new]["profession"] == "padre"


def test_chief_succession_by_election(data):
    world = world_at(data, seed=6)
    events = collect(world)
    lifecycle.kill(world, "chief", "velhice")
    vac = world.life.vacancies[-1]
    assert vac["mode"] == "eleicao"
    world.clock.now += timedelta(minutes=vac["due"] - world.now_minutes() + 1)
    lifecycle._succession_hourly(world)  # convoca
    assert vac["assembly"] and any(e.type == "election" for e in events)
    run_minutes(world, int(vac["assembly"]["end"] - world.now_minutes()) + 2)
    lifecycle._succession_hourly(world)  # apura
    result = [e for e in events if e.type == "election" and e.data.get("phase") == "result"]
    assert result and sum(result[0].data["votes"].values()) >= 3
    winner = result[0].actors[0]
    assert world.data.characters[winner].profession == "lider"
    assert vac["status"] == "fechada"


# ------------------------------------------------------ fantasma e retorno
def test_ghost_appears_near_who_the_dead_loved_or_hated(data):
    world = world_at(data, "23:00")
    events = collect(world)
    lifecycle.kill(world, "clown", "acidente")
    world.clock.now += timedelta(hours=13)
    assert lifecycle.ghost(world)
    g = next(e for e in events if e.type == "ghost")
    target = g.data["target"]
    best = max(lifecycle.living(world), key=lambda o: abs(world.affinity("clown", o)))
    assert target == best
    assert world.memories.strongest(target, "fantasma") is not None


def test_natural_resurrection_comes_back_changed(data):
    world = world_at(data)
    events = collect(world)
    lifecycle.kill(world, "weirdo", "velhice")
    assert lifecycle.resurrect(world, "weirdo", "natural")
    st = world.states["weirdo"]
    assert st.alive and st.extra_traits and st.needs["medo"] > 80
    assert any(e.type == "resurrection" for e in events)
    assert world.memories.strongest("priest", "ressurreicao").permanent
    assert world.life.graves[-1]["resurrected"]


# --------------------------------------------------------------- criaturas
def test_night_creature_raises_danger_and_can_be_banished(data):
    world = world_at(data, "23:00")
    events = collect(world)
    before = world.danger_at("forest", True)
    ac = creatures.spawn(world, "olhos_no_escuro", "forest")
    assert world.danger_at("forest", True) > before
    assert any(e.type == "creature_spawned" and "{" not in e.render(world.names()) for e in events)
    world.states["blacksmith"].place = "forest"
    world.data.creatures["olhos_no_escuro"].win_chance = 1.0
    try:
        creatures.fight(world, "blacksmith", "forest")
    finally:
        world.data.creatures["olhos_no_escuro"].win_chance = 0.45
    assert ac not in world.creatures.active
    assert any(e.type == "creature_gone" and e.data["how"] == "vencida" for e in events)


def test_mike_is_immune_to_creatures(data):
    world = world_at(data, "23:00")
    world.states["mike"].place = "forest"
    world.states["mike"].needs["medo"] = 5
    creatures.spawn(world, "olhos_no_escuro", "forest")
    assert world.states["mike"].needs["medo"] == 5
    assert not world.special_place_ok(data.actions["enfrentar"], "mike", "forest")


def test_homelab_problem_becomes_a_creature_for_the_technicians(data):
    world = world_at(data, "14:00")
    events = collect(world)
    world.submit(Command("homelab", "jellyfin down"))
    world.tick()
    ac = next(a for a in world.creatures.active if a.service == "jellyfin")
    assert ac.place == "server_room" and ac.end is None
    goals = [g for g in world.goals if g["source"] == f"criatura#{ac.uid}"]
    assert {g["who"] for g in goals} == {"tech_old", "tech_apprentice"}
    spawned = next(e for e in events if e.type == "creature_spawned")
    assert "jellyfin" in spawned.render(world.names())
    # vencer o gremlin não resolve o problema real
    world.states["tech_old"].place = "server_room"
    creatures.fight(world, "tech_old", "server_room")
    assert ac in world.creatures.active
    world.submit(Command("homelab", "jellyfin up"))
    world.tick()
    assert ac not in world.creatures.active and not [g for g in world.goals if g["source"].startswith("criatura#")]


# ------------------------------------------------------------- clima/névoa
def test_weather_codes_map_to_kinds(data):
    assert weather.kind_for_code(data.world, 63) == "chuva"
    assert weather.kind_for_code(data.world, 0) == "limpo"
    assert weather.kind_for_code(data.world, 999) == data.world.weather.fallback


def test_weather_real_mode_uses_fetcher_then_cache_when_offline(data, tmp_path, monkeypatch):
    monkeypatch.setenv("DW_WEATHER_CACHE", str(tmp_path / "clima.json"))
    d = load_data_or_raise(DATA)
    calls = []

    def fake():
        calls.append(1)
        return {"code": 95, "temp": 22.0, "fetched_at": "x"}

    world = world_at(d, weather_fetcher=fake)
    assert world.weather.fetch_now() and world.weather.kind == "tempestade"
    assert (tmp_path / "clima.json").exists()

    def offline():
        raise OSError("sem internet")

    world2 = world_at(d, weather_fetcher=offline)
    assert not world2.weather.fetch_now()
    assert world2.weather.kind == "tempestade" and world2.weather.now.source == "cache"


def test_simulated_weather_changes_and_affects_outdoor_scores(data):
    world = world_at(data)
    kinds = set()
    for _ in range(3 * 1440 // 30):
        world.clock.advance(30)
        world.weather.update()
        kinds.add(world.weather.kind)
    assert len(kinds) >= 3
    world.weather.force("chuva", 60, "teste")
    world._mult_cache = {}
    labels = dict(world.score_multiplier("mike", data.actions["perambular"], "fields"))
    assert any("chuva" in k for k in labels) and min(labels.values()) < 1


def test_rain_scares_who_fears_rain(data):
    world = world_at(data)
    world.weather.force("chuva", 120, "teste")
    st = world.states["weirdo"]
    st.needs["medo"] = 5
    run_minutes(world, 60)
    assert st.needs["medo"] > 5 + 5  # medo de chuva (gatilho no YAML do Esquisito)


def test_offline_screen_fogs_places_traps_people_but_not_mike(data):
    world = world_at(data)
    events = collect(world)
    world.states["clown"].place = "forest"
    world.states["mike"].place = "forest"
    world.submit(Command("tela", "monitor_esquerda offline"))
    world.tick()
    assert {"forest", "mountain"} <= world.blocked_places
    assert sum(1 for e in events if e.type == "fog_on") == 2
    ctx = world.decision_context()
    clown = utility.candidates(data.characters["clown"], world.states["clown"], ctx)
    assert clown and {c.place for c in clown} == {"forest"}  # preso
    mike = utility.candidates(data.characters["mike"], world.states["mike"], ctx)
    assert {c.place for c in mike} - {"forest"}  # o Mike sai da névoa
    fiscal = utility.candidates(data.characters["inspector"], world.states["inspector"], ctx)
    assert "forest" not in {c.place for c in fiscal}  # ninguém entra
    world.submit(Command("tela", "monitor_esquerda online"))
    world.tick()
    assert not world.blocked_places and any(e.type == "fog_off" for e in events)


# ------------------------------------------------------------------ diretor
def test_director_agitates_a_calm_world_and_logs_the_reason(data, tmp_path):
    world = world_at(data, "20:00", db=tmp_path / "d.sqlite")
    events = collect(world)
    world.data.world.director.act_chance = 1.0
    try:
        for st in world.states.values():
            st.needs["medo"], st.needs["raiva"] = 0, 0
        world.director.history.clear()
        world.director.next_check = world.now_minutes()
        world.director.update(world)
    finally:
        world.data.world.director.act_chance = 0.25
    ev = next(e for e in events if e.type == "director_event")
    assert "agita" in ev.data["reason"] and data.events[ev.data["event"]].tension == "agita"
    world.save()
    row = world.storage.conn.execute("SELECT chosen, reason FROM director_log").fetchone()
    assert row["chosen"] == ev.data["event"]


def test_director_calms_a_chaotic_world_and_respects_limits(data):
    world = world_at(data, "14:00")
    events = collect(world)
    world.data.world.director.act_chance = 1.0
    try:
        for _ in range(6):
            world.director.history.append([world.now_minutes(), "fight"])
        for _ in range(12):
            world.director.next_check = world.now_minutes()
            world.director.update(world)
    finally:
        world.data.world.director.act_chance = 0.25
    chosen = [e for e in events if e.type == "director_event"]
    assert chosen and all(data.events[e.data["event"]].tension == "acalma" for e in chosen)
    assert len(chosen) <= data.world.limits.director_events_per_hour
    assert world.director.tension > 40


def test_tension_input_reaches_the_utility_ai(data):
    world = world_at(data)
    world.director.tension = 77
    assert world.decision_context().tension == 77


# -------------------------------------------------------------- persistência
def test_life_survives_restart(data, tmp_path):
    db = tmp_path / "w.sqlite"
    world = world_at(data, db=db)
    lifecycle.kill(world, "greedy", "briga", by="blacksmith")
    cid = lifecycle.birth(world)
    world.close()
    again = World(load_data_or_raise(DATA, environ={}), Storage(db))  # relê data/ (com o nascido)
    assert not again.states["greedy"].alive and again.states[cid].alive
    assert again.life.funerals and again.life.graves[-1]["cid"] == "greedy"
    row = again.storage.conn.execute("SELECT cause FROM graves WHERE char_id='greedy'").fetchone()
    assert row["cause"] == "briga"
    again.close()


def test_no_unfilled_variables_in_a_violent_week(data):
    """Uma semana com morte forçada logo no começo: funeral, luto, herança e sucessão
    sem nenhuma {variável} sobrando no Chat."""
    world = world_at(data, "06:00", seed=8)
    events = collect(world)
    lifecycle.kill(world, "blacksmith", "briga", by="clown")
    world.run(until=world.clock.now + timedelta(days=3), fast=True)
    names = world.names()
    bad = [e.render(names) for e in events if e.text and "{" in e.render(names)]
    assert not bad, bad[:5]
    assert "funeral_ended" in types(events) and "succession" in types(events)
