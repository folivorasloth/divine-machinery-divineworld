"""O mundo rodando de verdade: um dia inteiro, determinismo, persistência,
comandos e a linha de comando `tools.run`."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import pytest

from sim.clock import WorldClock
from sim.engine import Command, World
from sim.loader import load_data_or_raise
from sim.persistence import Storage
from tests.conftest import DATA

START = "2026-11-09T00:00"


def new_world(data, db=None, seed=42, start=START, speed=None) -> World:
    storage = Storage(db) if db else None
    return World(data, storage, seed=seed, start=WorldClock.parse_start(data.world.clock, start), speed=speed)


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


@pytest.fixture(scope="module")
def one_day(data, tmp_path_factory):
    """Um dia inteiro (00:00 -> 24:00) em modo rápido, com banco, seed 42."""
    db = tmp_path_factory.mktemp("dia") / "world.sqlite"
    world = new_world(data, db)
    events = []
    world.bus.subscribe(events.append)
    world.run(until=world.clock.now + timedelta(days=1), fast=True)
    world.close()
    return events, db


def started(events):
    """personagem -> Counter de ações iniciadas."""
    out = defaultdict(Counter)
    for ev in events:
        if ev.type in ("action_started", "bell"):
            out[ev.actors[0]][ev.data["action"]] += 1
    return out


def test_every_npc_has_a_plausible_day(data, one_day):
    events, _db = one_day
    acts = started(events)
    talked = Counter()
    for ev in events:
        if ev.type == "action_started" and ev.data["action"] == "conversar":
            talked.update(ev.actors)
    for cid, char in data.characters.items():
        a = acts[cid]
        assert a["dormir"] >= 1, f"{cid} não dormiu: {a}"
        assert a["comer"] >= 2, f"{cid} comeu pouco: {a}"
        if char.workplace and cid != "mike":
            assert a["trabalhar"] >= 1, f"{cid} não trabalhou: {a}"
    # socializar: quase todo mundo conversa pelo menos uma vez (Mike é Mike)
    lonely = [cid for cid in data.characters if talked[cid] == 0 and cid != "mike"]
    assert len(lonely) <= 2, lonely
    # ninguém fica parado o dia todo no mesmo lugar
    places = defaultdict(set)
    for ev in events:
        if ev.type == "action_started":
            places[ev.actors[0]].add(ev.place)
    assert all(len(places[cid]) >= 3 for cid in data.characters), {c: len(p) for c, p in places.items()}


def test_sleep_happens_at_night(one_day):
    events, _db = one_day
    for ev in events:
        if ev.type == "action_started" and ev.data["action"] == "dormir":
            hour = int(ev.ts[11:13])
            assert hour >= 19 or hour < 9, f"dormiu às {ev.ts} ({ev.actors[0]})"


def test_mike_wanders_without_purpose(one_day):
    events, _db = one_day
    a = started(events)["mike"]
    assert a["perambular"] >= 10
    assert a["perambular"] > sum(n for act, n in a.items() if act not in ("perambular",))
    assert a["trabalhar"] == 0
    wander_places = {ev.place for ev in events if ev.type == "action_started" and ev.actors[0] == "mike"
                     and ev.data["action"] == "perambular"}
    assert len(wander_places) >= 5


def test_priest_rings_the_bell_on_time(one_day):
    events, _db = one_day
    bells = [ev for ev in events if ev.type == "bell"]
    assert [ev.ts[11:13] for ev in bells] == ["06", "12", "18"]
    assert all(int(ev.ts[14:16]) <= 15 for ev in bells)  # dentro da janela de 15 min
    assert all(ev.actors == ["priest"] and ev.place == "cathedral" for ev in bells)


def test_tunnel_events_have_what_the_leds_need(one_day):
    events, _db = one_day
    tunnels = [ev for ev in events if ev.type == "teleport_started"]
    assert tunnels, "ninguém usou um túnel num dia inteiro"
    for ev in tunnels:
        for key in ("from_place", "to_place", "from_screen", "to_screen", "duration_s"):
            assert key in ev.data
        assert ev.data["duration_s"] >= 2
    finished = [ev for ev in events if ev.type == "teleport_finished"]
    assert len(finished) >= len(tunnels) - 21  # alguém pode estar no meio do túnel no fim do dia


def test_conversations_produce_speech_with_tokens(data, one_day):
    events, _db = one_day
    speeches = [ev for ev in events if ev.type == "speech"]
    assert len(speeches) > 50
    assert any(ev.data.get("reply_to") for ev in speeches)  # alguém respondeu
    names = data.names()
    for ev in speeches:
        assert "{eu}" not in ev.text and "{outro}" not in ev.text
        assert "{@" not in ev.render(names)
        for token in re.findall(r"\{@([a-z_]+)\}", ev.text):
            assert token in names


def test_events_are_persisted_and_queryable(one_day):
    events, db = one_day
    storage = Storage(db)
    persisted = [ev for ev in events if ev.type != "decision"]
    assert storage.count_events() == len(persisted) + 1  # + "O mundo começa" (antes de assinarmos)
    mike = storage.query_events(character="mike", limit=5)
    assert len(mike) == 5 and all("mike" in ev.actors for ev in mike)
    bells = storage.query_events(type="bell")
    assert len(bells) == 3
    assert storage.query_events(tag="igreja", limit=1)
    storage.close()


def test_same_seed_same_story(data):
    def run(seed):
        world = new_world(data, seed=seed)
        out = []
        world.bus.subscribe(lambda ev: out.append((ev.type, ev.ts, ev.text, tuple(ev.actors), ev.place)))
        world.run(until=world.clock.now + timedelta(hours=8), fast=True)
        return out

    first, second = run(7), run(7)
    assert first == second
    assert run(8) != first


def test_world_continues_where_it_stopped(data, tmp_path):
    db = tmp_path / "world.sqlite"
    world = new_world(data, db, seed=3)
    world.run(until=world.clock.now + timedelta(hours=9, minutes=17), fast=True)
    saved_time = world.clock.iso()
    saved_needs = {cid: dict(st.needs) for cid, st in world.states.items()}
    saved_activity = {cid: (st.activity.action if st.activity else None) for cid, st in world.states.items()}
    last_id = world._last_event_id
    world.close()

    again = World(data, Storage(db), speed=1)
    assert again.resumed
    assert again.clock.iso() == saved_time
    assert again.seed == 3
    for cid, st in again.states.items():
        assert st.needs == pytest.approx(saved_needs[cid], abs=0.01)
        assert (st.activity.action if st.activity else None) == saved_activity[cid]
    assert again._last_event_id == last_id + 1  # só o evento "o mundo acorda"
    again.run(until=again.clock.now + timedelta(hours=1), fast=True)
    assert again.clock.iso() > saved_time
    again.close()


def test_resumed_world_is_still_deterministic(data, tmp_path):
    """Parar no meio e continuar dá a mesma história que rodar direto (o RNG é salvo)."""
    def collect(world, out):
        world.bus.subscribe(lambda ev: out.append((ev.type, ev.ts, ev.text)) if ev.type != "system" else None)

    straight = []
    w = new_world(data, tmp_path / "a.sqlite", seed=11)
    collect(w, straight)
    w.run(until=w.clock.now + timedelta(hours=4), fast=True)
    w.close()

    split = []
    w = new_world(data, tmp_path / "b.sqlite", seed=11)
    collect(w, split)
    w.run(until=w.clock.now + timedelta(hours=2), fast=True)
    w.close()
    w = World(data, Storage(tmp_path / "b.sqlite"))
    collect(w, split)
    w.run(until=w.clock.now + timedelta(hours=2), fast=True)
    w.close()
    assert split == straight


def test_renaming_after_saving_changes_even_the_history(data_copy, tmp_path):
    db = tmp_path / "world.sqlite"
    d1 = load_data_or_raise(data_copy, environ={})
    w = new_world(d1, db)
    w.run(until=w.clock.now + timedelta(hours=12), fast=True)
    w.close()
    path = data_copy / "characters" / "mike.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("nome: Mike", "nome: Miguelito"), encoding="utf-8")
    d2 = load_data_or_raise(data_copy, environ={})
    storage = Storage(db)
    old = storage.query_events(character="mike", limit=3)
    assert old and all("Miguelito" in ev.render(d2.names()) for ev in old if "{@mike}" in ev.text)
    w = World(d2, storage)  # o estado salvo (por id) continua valendo
    assert w.states["mike"].needs
    w.close()


def test_character_missing_from_yaml_is_frozen_not_deleted(data, tmp_path):
    db = tmp_path / "world.sqlite"
    w = new_world(data, db)
    # um personagem que existia no banco mas cujo YAML o João apagou
    w.storage.save_character("old_friend", alive=True, place="tavern", needs={"fome": 1}, current=None,
                             last_action=None, flags={})
    w.close()
    w = World(data, Storage(db))
    assert "old_friend" in w.frozen_rows and "old_friend" not in w.states
    w.close()
    assert "old_friend" in Storage(db).load_characters()  # nada foi apagado


def test_commands_pause_and_speed(data):
    world = new_world(data)
    world.submit(Command("velocidade", "120"))
    world.submit(Command("pausar"))
    world.tick()
    assert world.speed == 120 and world.paused
    world.handle_command(Command("continuar"))
    assert not world.paused


def test_catch_up_skips_long_downtime(data, tmp_path):
    db = tmp_path / "world.sqlite"
    w = new_world(data, db, start="2026-11-09T08:00")
    w.close()
    events = []
    w = World(data, Storage(db), speed=1)
    w.bus.subscribe(events.append)
    real_now = datetime.fromisoformat("2026-11-09T20:00:00-03:00")
    w.catch_up(real_now)
    assert w.clock.now == real_now
    skipped = [ev for ev in events if ev.type == "system" and "cochilou" in ev.text]
    assert skipped and skipped[0].data["skipped_hours"] == pytest.approx(12 - data.world.clock.max_catchup_hours)
    w.close()


def test_new_world_at_night_starts_asleep(data):
    world = new_world(data, start="2026-11-09T03:00")
    asleep = [cid for cid, st in world.states.items() if st.activity and st.activity.action == "dormir"]
    assert len(asleep) >= 15
    assert world.states["priest"].place == "cathedral"  # o Padre mora na Catedral


def test_cli_runs_non_interactively(tmp_path, capsys):
    from tools import run

    out = tmp_path / "chat.txt"
    code = run.main(["--fast", "--horas", "3", "--novo", "--inicio", "05:00", "--seed", "1",
                     "--banco", str(tmp_path / "w.sqlite"), "--saida", str(out), "--resumo"])
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "SINO" in text and "Começa a manhã." in text and "Resumo por personagem" in text
    # filtro por personagem
    code = run.main(["--fast", "--horas", "8", "--banco", str(tmp_path / "w.sqlite"), "--personagem", "mike",
                     "--saida", str(out)])
    assert code == 0
    lines = [line for line in out.read_text(encoding="utf-8").splitlines() if line.startswith("[")]
    # (uma fala de quem conversa COM o Mike pode não citar o nome dele: "{eu}: \"{bordao}\"")
    assert lines and sum("Mike" in line for line in lines) >= 0.8 * len(lines)
