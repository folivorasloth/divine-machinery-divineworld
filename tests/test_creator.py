"""Fase 4: os comandos do Criador (chefe, medium, reviver, status, quem), o olhar
e a Aparição. Nada aqui usa rede (sem MQTT, sem Ollama)."""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from sim import commands, lifecycle, presence
from sim.clock import WorldClock
from sim.engine import Command, World
from sim.loader import load_data_or_raise
from sim.persistence import Storage
from tests.conftest import DATA


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


def world_at(data, hhmm: str = "07:00", seed: int = 3, db=None) -> World:
    start = WorldClock.parse_start(data.world.clock, hhmm, real_now=datetime(2026, 11, 10, 12, 0))
    return World(data, Storage(db) if db else None, seed=seed, start=start)


def collect(world: World) -> list:
    events = []
    world.bus.subscribe(events.append)
    return events


def run_until(world: World, cond, max_ticks: int) -> bool:
    for _ in range(max_ticks):
        world.tick()
        if cond():
            return True
    return False


def with_creator(data, **changes):
    """Cópia dos dados com partes do criador.yaml trocadas (ex.: chance de erro da Médium)."""
    creator = data.creator
    medium = creator.medium.model_copy(update=changes)
    return dataclasses.replace(data, creator=creator.model_copy(update={"medium": medium}))


# ------------------------------------------------------------ entender ordens
def test_keywords_place_and_action(data):
    w = world_at(data)
    chief = data.creator.chief
    assert commands.match_kind(chief.orders, "reconstruam a ferraria")[0] == "reconstruir"
    assert commands.match_kind(chief.orders, "Façam uma FESTA hoje!")[0] == "festa"
    assert commands.match_kind(chief.orders, "proibido brigar na praça")[0] == "regra"
    assert commands.match_kind(chief.orders, "convoquem uma reunião")[0] == "reuniao"
    assert commands.match_kind(chief.orders, "xablau quântico")[0] is None
    assert commands.find_place(w, "reconstruam a ferraria") == "forge"
    assert commands.find_place(w, "consertem a bigorna, por favor") == "forge"
    assert commands.find_place(w, "festa na Taverna") == "tavern"
    assert commands._rule_of(w, "proibido andar de skate", chief.rule)[:2] == ("proibido", "andar_de_skate")
    assert commands._rule_of(w, "liberem o skate", chief.rule)[:2] == ("liberado", "andar_de_skate")
    mode, action, invented = commands._rule_of(w, "regra nova: sei lá", chief.rule)
    assert invented and action in chief.rule.suggestions


def test_unknown_order_is_interpreted_somehow(data):
    w = world_at(data)
    res = w.handle_command(Command("chefe", "xablau quântico"))
    assert res["ok"] and res["how"] == "como_da" and res["kind"] in data.creator.chief.orders


# ------------------------------------------------- o critério de aceite
def test_chief_order_rebuilds_forge_through_npc_behavior(data):
    """`chefe "reconstruam a ferraria"`: ninguém conserta por mágica. A ordem vira
    objetivos; os NPCs escolhem `construir` na Ferraria e o conserto é aos poucos."""
    w = world_at(data, "07:00", seed=3)
    for s in w.structures.at("forge"):
        w.structures.change(s.id, -100)
    events = collect(w)
    res = w.handle_command(Command("chefe", "reconstruam a ferraria"))
    assert res["ok"] and res["kind"] == "reconstruir" and res["place"] == "forge" and res["receiver"] == "chief"
    # a intuição não conserta nada: só um objetivo para o Chefe ir anunciar
    assert all(s.hp == 0 for s in w.structures.at("forge"))
    assert any(g["who"] == "chief" and g["action"] == "anunciar_ordem" for g in w.goals)
    order = w.creator.orders[-1]
    assert run_until(w, lambda: order["status"] == "cumprida", 60 * 24 * 2)
    announced = [e for e in events if e.type == "action_started" and e.data.get("action") == "anunciar_ordem"]
    assert announced and announced[0].actors == ["chief"] and announced[0].place == "town_square"
    builds = [e for e in events if e.type == "action_started" and e.data.get("action") == "construir"
              and e.place == "forge" and e.id > announced[0].id]
    assert len(builds) >= 2
    assert set(order["builders"]) <= {e.actors[0] for e in builds}
    repaired = [e for e in events if e.type == "structure_changed" and e.place == "forge"]
    assert repaired and all(e.actors[0] in order["builders"] or e.data.get("cause") for e in repaired)
    assert all(w.structures.state(s.id) == "inteiro" for s in w.structures.at("forge"))
    done = [e for e in events if e.type == "creator_order" and e.data.get("phase") == "done"]
    assert done and done[0].data["builders"] == order["builders"]
    # personalidade: quem é rebelde ou vazio não obedece
    assert order["responses"]["teen"]["kind"] == "resiste"
    assert order["responses"]["mike"]["kind"] == "resiste"
    assert order["responses"]["blacksmith"]["kind"] == "aceita"
    assert any(r["kind"] == "atrasa" for r in order["responses"].values())


def test_no_chief_alive_order_waits_for_successor(data):
    w = world_at(data)
    lifecycle.kill(w, "chief", "velhice")
    res = w.handle_command(Command("chefe", "façam uma festa"))
    assert res["status"] == "esperando"
    assert w.creator.orders[-1]["status"] == "esperando"


def test_party_order_plans_a_social_event_by_the_chief(data):
    w = world_at(data, "10:00", seed=4)
    w.handle_command(Command("chefe", "façam uma festa na taverna"))
    order = w.creator.orders[-1]
    assert run_until(w, lambda: order["status"] != "recebida", 60 * 6)
    inst = [i for i in w.social.instances if i.kind == "festa_taverna"]
    assert inst and inst[-1].organizer == "chief" and inst[-1].guests


def test_decree_prohibits_and_the_rebel_disobeys(data):
    w = world_at(data, "10:00", seed=5)
    events = collect(w)
    w.handle_command(Command("chefe", "proibido andar de skate"))
    order = w.creator.orders[-1]
    assert run_until(w, lambda: order["status"] != "recebida", 60 * 6)
    skate = data.actions["andar_de_skate"]
    assert commands.infraction_of(w, skate) == "decreto"
    assert commands.decree_multiplier(w, "teen", "andar_de_skate") > 1  # rebelde: faz MAIS
    assert commands.decree_multiplier(w, "inspector", "andar_de_skate") < 0.1
    assert any(e.data.get("situation") == "regra_proibida" for e in events)
    # liberar uma ação que é infração: a lei deixa de ver
    w.creator.decrees.append({"action": "pichar", "mode": "liberado", "until": w.now_minutes() + 60, "order": 0})
    assert commands.infraction_of(w, data.actions["pichar"]) is None


def test_meeting_brings_people_to_the_square(data):
    w = world_at(data, "09:00", seed=6)
    events = collect(w)
    w.handle_command(Command("chefe", "convoquem uma reunião na praça"))
    order = w.creator.orders[-1]
    assert run_until(w, lambda: order["status"] == "cumprida", 60 * 10)
    end = [e for e in events if e.type == "creator_order" and e.data.get("phase") == "done"]
    assert end and len(end[-1].data["attendees"]) >= 3


def test_penalty_goal_makes_an_action_less_attractive(data):
    w = world_at(data)
    now = w.now_minutes()
    w.add_goal(who=None, action="brigar", place=None, bonus=0.3, start=now - 1, end=now + 60, source="t", penalty=True)
    ctx = w.decision_context()
    from sim.utility import goal_bonus

    assert goal_bonus(ctx, "clown", "brigar", "market")[0] == pytest.approx(0.3)
    w.add_goal(who=None, action="festejar", place=None, bonus=0.5, start=now - 1, end=now + 60, source="t")
    assert goal_bonus(ctx, "clown", "festejar", "market")[0] == 1.0  # sem penalty, bônus < 1 não vale (F2)


# ------------------------------------------------------------- a Médium
def test_medium_hears_and_reveals_with_cult_goals(data):
    d = with_creator(data, error_chance=0.0)
    w = world_at(d, "20:00", seed=7)
    events = collect(w)
    res = w.handle_command(Command("medium", "chamem os anjos com velas"))
    assert res["kind"] == "ritual" and res["receiver"] == "medium"
    assert any(e.type == "creator_voice" and e.data.get("phase") == "received" for e in events)
    order = w.creator.orders[-1]
    assert run_until(w, lambda: order["status"] != "recebida", 60 * 8)
    assert any(g["who"] == "medium" and g["action"] == "ritual" for g in w.goals)
    cult = commands.faction_members(w, "seita")
    assert any(g["who"] in cult and g["action"] == "participar_ritual" for g in w.goals if g["who"] != "medium")
    assert any(e.data.get("situation") == "visao_anuncio" for e in events)


def test_medium_sometimes_gets_it_wrong_on_purpose(data):
    d = with_creator(data, error_chance=1.0)
    w = world_at(d, "20:00", seed=8)
    res = w.handle_command(Command("medium", "façam as pazes, parem de brigar"))
    order = w.creator.orders[-1]
    assert order["wrong"] and order["meant"] == "paz"
    assert order["kind"] in d.creator.medium.disasters
    assert order["heard"] != order["text"]  # repete a mensagem torta
    assert res["kind"] == order["kind"]


# ------------------------------------------------------------- reviver
def test_revive_is_legendary_and_the_city_talks(data):
    w = world_at(data, "10:00", seed=9)
    lifecycle.kill(w, "blacksmith", "acidente")
    assert any(f["dead"] == "blacksmith" and f["status"] != "terminado" for f in w.life.funerals)
    events = collect(w)
    res = w.handle_command(Command("reviver", "blacksmith"))
    assert res["ok"] and w.states["blacksmith"].alive
    st = w.states["blacksmith"]
    assert st.needs["medo"] >= 80 and st.extra_traits  # volta mudado
    res_ev = [e for e in events if e.type == "resurrection"]
    assert res_ev and res_ev[0].data["how"] == "criador" and res_ev[0].importance == 3
    sits = {e.data.get("situation") for e in events}
    assert {"ressurreicao_padre", "ressurreicao_medium"} <= sits
    # o funeral marcado foi cancelado (ninguém vela um vivo)
    assert all(f["status"] == "terminado" for f in w.life.funerals if f["dead"] == "blacksmith")
    assert not [g for g in w.goals if g["source"].startswith("funeral#")]
    # memória permanente e assunto do momento: a cidade comenta por dias
    assert w.memories.strongest("priest", kinds=["ressurreicao"]) is not None
    assert any(t["kind"] == "ressurreicao" and t["subject"] == "blacksmith" for t in w.creator.topics)
    run_until(w, lambda: False, 60 * 14)
    talk = [e for e in events if e.data.get("situation") == "assunto_ressurreicao"]
    assert talk, "ninguém comentou a ressurreição nas conversas"
    assert all("blacksmith" not in e.actors for e in talk)  # comentam SOBRE ele, não com ele
    # reviver um vivo não faz nada
    assert not w.handle_command(Command("reviver", "blacksmith"))["ok"]
    assert not w.handle_command(Command("reviver", "ninguem"))["ok"]


# --------------------------------------------------------- status e quem
def test_status_and_quem(data):
    w = world_at(data)
    w.tick()
    s = w.handle_command(Command("status"))["status"]
    assert s["populacao"] == len(lifecycle.living(w)) and "presenca" in s and "ordens" in s
    sheet = w.handle_command(Command("quem", "clown"))["sheet"]
    for key in ("necessidades", "humor", "memorias", "gosta_mais", "gosta_menos", "ultima_decisao", "lugar"):
        assert key in sheet
    assert sheet["nome"] == data.characters["clown"].name
    assert not w.handle_command(Command("quem", "ninguem"))["ok"]


def test_unknown_command_answers_with_the_list(data):
    w = world_at(data)
    res = w.handle_command(Command("voar"))
    assert not res["ok"] and "chefe" in res["message"]


def test_command_reply_future_and_log(data):
    import concurrent.futures

    w = world_at(data)
    fut = concurrent.futures.Future()
    w.submit(Command("nascer", "alegre", id="abc", reply=fut))
    w.tick()
    assert fut.result(timeout=1)["ok"]
    assert w.command_log[-1]["id"] == "abc"


# ------------------------------------------------- o olhar e a Aparição
def test_presence_makes_staring_likelier(data):
    w = world_at(data, "10:00")
    stare = data.actions["encarar_tela"]
    assert presence.stare_multiplier(w, "encarar_tela") is None
    w.handle_command(Command("presenca", "1"))
    assert presence.active(w)
    assert presence.stare_multiplier(w, "encarar_tela") == data.creator.presence.stare_multiplier
    assert ("presença no quarto", 3) in w.score_multiplier("clown", stare, "market")
    w.handle_command(Command("presenca", "0"))
    assert not presence.active(w)


def test_group_stare(data):
    w = world_at(data, "10:00", seed=2)
    for _ in range(30):
        w.tick()
    events = collect(w)
    place = max(data.places, key=lambda p: len(presence._awake_still(w, p)) if data.screen_of(p) else -1)
    assert presence.group_stare(w, place)
    ev = [e for e in events if e.type == "stare"]
    assert ev and len(ev[0].data["people"]) >= 1
    assert all(w.states[c].activity.action == "encarar_tela" for c in ev[0].data["people"])


def test_apparition_is_legendary(data):
    w = world_at(data, "11:00", seed=4)
    for _ in range(20):
        w.tick()
    events = collect(w)
    res = w.handle_command(Command("aparicao"))
    assert res["ok"]
    ap = [e for e in events if e.type == "apparition"]
    assert ap and ap[0].importance == 3 and ap[0].data["places"]
    sits = [e.data.get("situation") for e in events]
    assert "aparicao_padre" in sits and "aparicao_medium" in sits and "aparicao_esquisito" in sits
    assert all(w.memories.strongest(c, kinds=["aparicao"]) for c in lifecycle.living(w))
    assert any(g["source"] == "aparicao" and g["action"] == "participar_ritual" for g in w.goals)
    assert any(t["kind"] == "aparicao" for t in w.creator.topics)


def test_apparition_chance_on_entering_the_room(data):
    d = dataclasses.replace(data, creator=data.creator.model_copy(
        update={"presence": data.creator.presence.model_copy(update={"apparition_chance": 1.0})}))
    w = world_at(d, "11:00", seed=4)
    events = collect(w)
    assert w.handle_command(Command("presenca", "2"))["apparition"]
    assert [e for e in events if e.type == "apparition"]
    # cooldown: sair e entrar de novo não traz outra
    w.handle_command(Command("presenca", "0"))
    w.creator.presence["seen"] = -1e9
    assert not w.handle_command(Command("presenca", "1"))["apparition"]


# ---------------------------------------------------------- persistência
def test_creator_state_survives_restart(data, tmp_path):
    db = tmp_path / "w.sqlite"
    w = world_at(data, "09:00", db=db)
    w.handle_command(Command("chefe", "reconstruam a ferraria"))
    w.handle_command(Command("presenca", "1"))
    w.close()
    w2 = World(data, Storage(db))
    assert w2.creator.orders and w2.creator.orders[-1]["text"] == "reconstruam a ferraria"
    assert w2.creator.presence["count"] == 1
    w2.close()


def test_creator_yaml_is_validated(data_copy):
    from sim.loader import load_data
    from tests.conftest import edit_yaml, messages

    path = data_copy / "events" / "criador.yaml"
    edit_yaml(path, lambda c: c["criador"]["chefe"].__setitem__("acao", "anunciar_ordm"))
    _d, report = load_data(data_copy, environ={})
    assert not report.ok and "anunciar_ordem" in messages(report)
