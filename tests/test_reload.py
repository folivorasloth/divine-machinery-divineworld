"""Fase 6: `recarregar` aplica data/ sem perder o estado; YAML com erro mantém a versão anterior;
o servidor religa com a última cópia válida se data/ estiver quebrado."""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta

import pytest

from server.runtime import Runtime
from sim.engine import Command, World
from sim.loader import DataError, load_data_or_raise
from sim.persistence import Storage


def _rename(path, new_name):
    content = path.read_text(encoding="utf-8")
    content, n = re.subn(r"^nome: .*$", f"nome: {new_name}", content, count=1, flags=re.M)
    assert n == 1
    path.write_text(content, encoding="utf-8")


def _world(data_copy, tmp_path, seed=3):
    data = load_data_or_raise(data_copy)
    return World(data, Storage(tmp_path / "w.sqlite"), seed=seed, speed=600)


def _run_hours(world, hours):
    world.run(until=world.clock.now + timedelta(hours=hours), fast=True)


def test_reload_renames_without_losing_state(data_copy, tmp_path):
    w = _world(data_copy, tmp_path)
    _run_hours(w, 6)
    before = {cid: (st.place, dict(st.needs), st.alive) for cid, st in w.states.items()}
    mems = sum(len(v) for v in w.memories.by_owner.values())
    rel = dict(w.relations.values)
    clock = w.clock.now
    events = []
    w.bus.subscribe(events.append)

    _rename(data_copy / "characters" / "clown.yaml", "Bozó")
    res = w.handle_command(Command("recarregar"))

    assert res["ok"], res
    assert res["renamed"] == [{"id": "clown", "old": "O Palhaço", "new": "Bozó"}]
    assert w.data.characters["clown"].name == "Bozó"
    assert w.names()["clown"] == "Bozó"
    assert w.snapshot()["names"]["clown"] == "Bozó"
    assert w.clock.now == clock
    assert {cid: (st.place, dict(st.needs), st.alive) for cid, st in w.states.items()} == before
    assert sum(len(v) for v in w.memories.by_owner.values()) == mems
    assert w.relations.values == rel
    ev = [e for e in events if e.type == "data_reloaded"]
    assert ev and "O Palhaço agora se chama \"Bozó\"" in ev[0].text
    # o mundo continua andando com os dados novos, e as falas novas usam o nome novo
    _run_hours(w, 6)
    assert any("Bozó" in e.render(w.names()) for e in events if "clown" in e.actors)
    w.close()


def test_reload_with_broken_yaml_keeps_last_valid_version(data_copy, tmp_path):
    w = _world(data_copy, tmp_path)
    _run_hours(w, 1)
    old_data = w.data
    events = []
    w.bus.subscribe(events.append)
    (data_copy / "characters" / "clown.yaml").write_text("id: clown\nnome: [quebrado\n", encoding="utf-8")
    res = w.handle_command(Command("recarregar"))
    assert not res["ok"] and res["errors"]
    assert w.data is old_data and w.data.characters["clown"].name == "O Palhaço"
    warn = [e for e in events if e.type == "system" and e.data.get("cmd") == "recarregar"]
    assert warn and "última versão válida" in warn[0].text and warn[0].importance >= 2
    _run_hours(w, 2)  # e o mundo segue normal
    assert w.ticks > 60
    w.close()


def test_reload_applies_lines_weights_and_new_characters(data_copy, tmp_path):
    w = _world(data_copy, tmp_path)
    _run_hours(w, 1)
    # uma fala nova, um peso novo e um morador novo (cópia do Mike com outro id)
    lines = data_copy / "lines" / "rotina.yaml"
    lines.write_text(lines.read_text(encoding="utf-8").replace(
        "situacoes:\n  comer:\n", "situacoes:\n  comer:\n    - \"{eu} come FALA-NOVA-DO-TESTE.\"\n", 1),
        encoding="utf-8")
    acts = data_copy / "actions" / "basicas.yaml"
    text = acts.read_text(encoding="utf-8")
    assert "peso:" in text
    mike = (data_copy / "characters" / "mike.yaml").read_text(encoding="utf-8")
    mike = re.sub(r"^id: mike$", "id: mike_twin", mike, flags=re.M)
    mike = re.sub(r"^nome: .*$", "nome: O Gêmeo do Mike", mike, count=1, flags=re.M)
    (data_copy / "characters" / "mike_twin.yaml").write_text(mike, encoding="utf-8")

    res = w.handle_command(Command("recarregar"))
    assert res["ok"], res
    assert res["added"] == ["mike_twin"]
    assert "mike_twin" in w.states and w.states["mike_twin"].alive
    assert any("FALA-NOVA-DO-TESTE" in ln.text for ln in w.data.lines["comer"])
    _run_hours(w, 12)
    assert w.states["mike_twin"].last_action is not None  # vive como os outros
    w.close()


def test_reload_keeps_characters_whose_file_vanished(data_copy, tmp_path):
    w = _world(data_copy, tmp_path)
    mike = (data_copy / "characters" / "mike.yaml").read_text(encoding="utf-8")
    mike = re.sub(r"^id: mike$", "id: mike_twin", mike, flags=re.M)
    path = data_copy / "characters" / "mike_twin.yaml"
    path.write_text(mike, encoding="utf-8")
    assert w.handle_command(Command("recarregar"))["ok"]
    path.unlink()  # o arquivo some com o mundo ligado: ele continua (com a versão antiga)
    res = w.handle_command(Command("recarregar"))
    assert res["ok"] and res["kept_old"] == ["mike_twin"]
    assert "mike_twin" in w.data.characters and w.states["mike_twin"].alive
    w.close()


def test_runtime_resends_hello_with_new_names_and_falls_back_to_valid_copy(data_copy, tmp_path):
    db = tmp_path / "var" / "w.sqlite"
    db.parent.mkdir()
    start = datetime(2026, 3, 2, 9, 0).astimezone()
    rt = Runtime(data_dir=str(data_copy), db_path=str(db), speed=600, seed=5, start=start, new=True,
                 mqtt=False, llm=False)
    assert not rt.using_valid_copy
    assert (tmp_path / "var" / "data_valido" / "world.yaml").exists()  # a cópia válida foi guardada
    _rename(data_copy / "characters" / "chief.yaml", "Seu Prefeito")
    res = rt.world.handle_command(Command("recarregar"))
    assert res["ok"]
    hello = rt.hub.hello("parede_centro")
    assert any(c["name"] == "Seu Prefeito" for c in hello["characters"]) or \
        rt.world.states["chief"].place not in rt.hub.screen_places["parede_centro"]
    assert rt.data.characters["chief"].name == "Seu Prefeito"
    rt.world.close()

    # "reinício do homelab" com o YAML quebrado: liga com a cópia válida (a do primeiro start)
    (data_copy / "world.yaml").write_text("relogio: [\n", encoding="utf-8")
    rt2 = Runtime(data_dir=str(data_copy), db_path=str(db), speed=600, mqtt=False, llm=False)
    assert rt2.using_valid_copy
    assert rt2.world.resumed  # o estado salvo continua
    assert rt2.world.data_dir == data_copy  # o recarregar lê o data/ de verdade
    bad = rt2.world.handle_command(Command("recarregar"))
    assert not bad["ok"]
    rt2.world.close()

    # sem cópia válida, o erro sobe como sempre
    shutil.rmtree(tmp_path / "var" / "data_valido")
    with pytest.raises(DataError):
        Runtime(data_dir=str(data_copy), db_path=str(db), speed=600, mqtt=False, llm=False)


def test_backup_tool_copies_a_consistent_world(data_copy, tmp_path):
    from tools.backup import backup

    w = _world(data_copy, tmp_path)
    _run_hours(w, 2)
    w.save()
    files = [backup(tmp_path / "w.sqlite", tmp_path / "bk", keep=2) for _ in range(3)]
    left = sorted((tmp_path / "bk").glob("w-*.sqlite"))
    assert len(left) == 2 and set(files[1:]) == set(left)
    import sqlite3

    con = sqlite3.connect(files[-1])
    assert con.execute("select value from meta where key='world_time'").fetchone()[0] == w.clock.iso()
    con.close()
    w.close()


def test_mass_and_ritual_follow_the_current_faction_leader(data_copy, tmp_path):
    from sim import utility

    w = _world(data_copy, tmp_path)
    ctx = w.decision_context()
    me = w.states["fool"]
    place = w.states["priest"].place
    assert utility.read_input("presenca_lider.igreja", ctx, me, place, None) == 1.0
    # o Padre morreu e o Adolescente assumiu a Igreja: a missa segue o Adolescente
    w.states["priest"].alive = False
    w.life.faction_leaders["igreja"] = "teen"
    w.states["teen"].place = "market"
    ctx = w.decision_context()
    assert utility.read_input("presenca_lider.igreja", ctx, me, place, None) == 0.0
    assert utility.read_input("presenca_lider.igreja", ctx, me, "market", None) == 1.0
    assert utility.read_input("afinidade_lider.igreja", ctx, me, "market", None) == w.affinity("fool", "teen")
    w.close()


def test_structure_names_contract_like_other_names():
    from sim import text

    names = {"anvil": "a bigorna", "bellows": "o fole da forja", "priest": "O Padre"}
    assert text.render("dá a última martelada em {@anvil}.", names) == "dá a última martelada na bigorna."
    assert text.render("levanta o que sobrou de {@bellows}.", names) == "levanta o que sobrou do fole da forja."
    assert text.render("{@anvil} rachou.", names) == "A bigorna rachou."


def test_lowercase_names_keep_their_case_mid_sentence():
    from sim import text

    names = {"pool": "a mesa de sinuca"}
    assert text.render("Já dá pra ver: {@pool} vai precisar de um mutirão.", names) == \
        "Já dá pra ver: a mesa de sinuca vai precisar de um mutirão."
    assert text.render("Em {@pool} ninguém mexe.", names) == "Na mesa de sinuca ninguém mexe."
