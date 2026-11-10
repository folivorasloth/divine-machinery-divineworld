"""Fase 2: relações, memória, fofoca, conflito, pastelão, estruturas, leis,
facções, ganância e eventos sociais organizados pelos NPCs."""

from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, timedelta

import pytest

from sim import factions, gossip, law, social_events, speech, text, utility
from sim.clock import WorldClock
from sim.engine import World
from sim.loader import load_data_or_raise
from sim.persistence import Storage
from sim.state import Activity
from tests.conftest import DATA


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


def world_at(data, hhmm: str = "10:00", seed: int = 1, db=None) -> World:
    start = WorldClock.parse_start(data.world.clock, hhmm, real_now=datetime(2026, 11, 9, 12, 0))
    world = World(data, Storage(db) if db else None, seed=seed, start=start)
    for st in world.states.values():  # todo mundo acordado e livre
        st.activity = None
        st.plan = None
    return world


def put(world: World, place: str, *cids: str) -> None:
    for cid in cids:
        world.states[cid].place = place


def collect(world: World) -> list:
    events = []
    world.bus.subscribe(events.append)
    return events


def ranked_for(world: World, cid: str):
    ctx = world.decision_context()
    char = world.data.characters[cid]
    return utility.rank(utility.candidates(char, world.states[cid], ctx), world.data.world.decision.min_score)


# ------------------------------------------------------------------ memória
def test_memories_form_reinforce_decay_and_permanent_ones_stay(data):
    world = world_at(data)
    mem, new = world.remember("fool", "briga", subject="clown", object="fool", place="market")
    assert new and mem.intensity == data.world.memory.kinds["briga"].intensity
    again, new2 = world.remember("fool", "briga", subject="clown", object="fool", place="market")
    assert not new2 and again is mem and mem.intensity > 60  # reforçou, não duplicou
    world.remember("fool", "limbo", subject="inspector", object="fool", place="town_square")
    world.memories.decay(24 * 30)  # um mês
    kinds = {m.kind for m in world.memories.of("fool")}
    assert "briga" not in kinds  # memória pequena some
    assert "limbo" in kinds  # memória grande fica


def test_memory_changes_affinity_and_feeds_lines(data):
    world = world_at(data)
    before = world.affinity("florist", "greedy")
    world.remember("florist", "roubo", subject="greedy", place="market", detail="uma melancia")
    assert world.affinity("florist", "greedy") < before
    mem = world.memories.strongest("florist", "roubo")
    assert world.memories.phrase(mem, "fato") == "{@greedy} roubou uma melancia em {@market}"
    assert text.render(world.memories.phrase(mem, "fato"), data.names()) == "O Ganancioso roubou uma melancia na Feira"
    # fala com filtro `memoria` só sai para quem lembra, e preenche {lembranca}
    world.remember("chef_wife", "briga", subject="chef_husband", object="chef_wife", place="community_kitchen")
    rng = random.Random(2)
    lines = {speech.pick_line(data, "conversa", world._speech_ctx("chef_wife", "community_kitchen", "chef_husband"), rng)
             for _ in range(300)}
    rendered = [text.render(line, data.names()) for line in lines]
    assert any("aquela briga na Cozinha Comunitária" in line for line in rendered)
    assert not any("{lembranca}" in line for line in lines)


def test_conflict_only_counts_what_happened_between_the_two(data):
    world = world_at(data)
    world.remember("fool", "briga", subject="clown", object="blacksmith", place="forge", factor=0.6)  # só viu
    assert world.memories.conflict_with("fool", "clown") == 0
    world.remember("fool", "discussao", subject="clown", object="fool", place="forge")
    assert world.memories.conflict_with("fool", "clown") > 0


# ------------------------------------------------------------------ relações
def test_affinity_slowly_returns_to_the_initial_value(data):
    world = world_at(data)
    initial = world.affinity("chef_wife", "chef_husband")
    world.change_affinity("chef_wife", "chef_husband", -50)
    world.relations.drift(10)
    value = world.affinity("chef_wife", "chef_husband")
    assert initial - 50 < value < initial
    world.relations.drift(10_000)
    assert world.affinity("chef_wife", "chef_husband") == pytest.approx(initial)


# --------------------------------------------------------------------- fofoca
def test_gossip_passes_a_weaker_copy_and_can_be_distorted(data, monkeypatch):
    world = world_at(data)
    world.remember("lady", "roubo", subject="greedy", place="market", detail="um rádio de pilha")
    mem, value = gossip.best(world, "lady", "chief")
    assert mem is not None and value > 0
    assert gossip.best(world, "lady", "greedy")[0] is None  # não se fofoca do próprio ouvinte
    res = gossip.spread(world, "lady", "chief", "town_square")
    copy = res["memory"]
    assert copy.owner == "chief" and copy.heard_from == "lady" and copy.intensity < mem.intensity
    assert gossip.best(world, "lady", "chief")[0] is None  # o Chefe já sabe
    # com distorção certa, o culpado muda
    monkeypatch.setattr(data.world.gossip, "distortion_chance", 1.0)
    res = gossip.spread(world, "lady", "fool", "town_square")
    assert res["data"]["distorted"] and res["data"]["about"] != "greedy"


def test_confession_secrets_only_leak_from_the_gossiper(data):
    world = world_at(data)
    world.remember("greedy", "roubo", subject="greedy", place="community_kitchen", detail="um queijo curado")
    assert world.special_target_ok(data.actions["confessar"], "greedy", "priest")
    put(world, "cathedral", "greedy", "priest")
    events = collect(world)
    world._start_activity(world.states["greedy"], "confessar", "cathedral", "priest", 10, 1.0)
    secret = world.memories.strongest("priest", "roubo")
    assert secret.secret and secret.heard_from == "greedy"
    assert any(ev.type == "speech" and "queijo" in ev.text for ev in events)
    # o Padre (fofoqueiro) conta; outra pessoa com a mesma memória secreta, não
    assert gossip.best(world, "priest", "chief")[0] is secret
    world.remember("florist", "roubo", subject="greedy", place="community_kitchen", secret=True)
    assert gossip.best(world, "florist", "chief")[0] is None


# ---------------------------------------------------- conflito e reconciliação
def test_fight_interrupts_the_target_and_everyone_remembers(data, monkeypatch):
    monkeypatch.setattr(data.actions["brigar"].failure, "chance", 0.0)  # sem pastelão neste teste
    world = world_at(data, "15:00")
    put(world, "forge", "blacksmith", "clown", "mike")
    world.states["clown"].activity = Activity(action="trabalhar", place="forge", duration=60)
    events = collect(world)
    world._start_activity(world.states["blacksmith"], "brigar", "forge", "clown", 5, 1.0)
    assert any(ev.type == "fight" for ev in events)
    assert world.states["clown"].activity is None  # largou o trabalho
    assert world.states["clown"].needs["medo"] > 20  # e sentiu na hora
    assert world.memories.strongest("clown", "briga").subject == "blacksmith"
    witness = world.memories.strongest("mike", "briga")
    assert witness is not None and witness.intensity < world.memories.strongest("clown", "briga").intensity


def test_apology_needs_a_conflict_and_some_love(data):
    world = world_at(data, "16:00")
    put(world, "community_kitchen", "chef_wife", "chef_husband", "greedy")
    def apologies(cid):
        return [c for c in ranked_for(world, cid) if c.action in ("pedir_desculpas", "abracar")]
    assert not apologies("chef_husband")  # sem briga, nada a desculpar
    world.remember_scene("discussao", subject="chef_wife", object="chef_husband", place="community_kitchen")
    assert {c.target for c in apologies("chef_husband")} == {"chef_wife"}
    # o Ganancioso nunca gostou dos Cozinheiros: não faz as pazes depois de brigar
    world.remember_scene("discussao", subject="greedy", object="chef_wife", place="community_kitchen")
    assert not [c for c in apologies("greedy") if c.target == "chef_wife"]


def test_reconcile_weakens_bad_memories_between_the_two(data):
    world = world_at(data, "16:00")
    put(world, "tavern", "cowboy_fat", "cowboy_thin")
    world.remember_scene("briga", subject="cowboy_fat", object="cowboy_thin", place="tavern")
    before = world.memories.conflict_with("cowboy_thin", "cowboy_fat")
    events = collect(world)
    world._start_activity(world.states["cowboy_fat"], "abracar", "tavern", "cowboy_thin", 3, 1.0)
    assert any(ev.type == "reconcile" for ev in events)
    assert world.memories.conflict_with("cowboy_thin", "cowboy_fat") < before * 0.5
    assert world.memories.strongest("cowboy_thin", "pazes") is not None


def test_slapstick_failure_uses_the_failure_line_and_traits_raise_the_chance(data):
    world = world_at(data, "15:00")
    put(world, "server_room", "tech_apprentice", "tech_old")
    events = collect(world)
    for seed in range(200):
        world.rng.seed(seed)
        world.states["tech_apprentice"].cooldowns.clear()
        world._start_activity(world.states["tech_apprentice"], "fucar", "server_room", None, 5, 1.0)
        if any(ev.type == "slapstick" for ev in events):
            break
        world.states["tech_apprentice"].activity = None
    slap = [ev for ev in events if ev.type == "slapstick"]
    assert slap and world.states["tech_apprentice"].activity.failed
    assert world.memories.strongest("tech_old", "choque") is not None  # o Técnico viu o choque
    # desastrado (Aprendiz) falha mais que o normal
    assert data.traits["desastrado"].effects.failure > 1


# ----------------------------------------------------------------- estruturas
def test_structures_get_damaged_and_repaired(data):
    world = world_at(data, "10:00")
    events = collect(world)
    assert world.structures.damage_at("forge") == 0
    assert not [c for c in ranked_for(world, "blacksmith") if c.action == "construir"]  # nada para consertar
    for _ in range(4):
        world.damage_structure("forge", 30, "clown", "quebrar")
    changes = [ev for ev in events if ev.type == "structure_changed"]
    assert changes and changes[-1].data["to"] in ("danificado", "destruido")
    assert [c for c in ranked_for(world, "blacksmith") if c.action == "construir" and c.place == "forge"]
    st = world.states["blacksmith"]
    put(world, "forge", "blacksmith")
    st.activity = Activity(action="construir", place="forge", duration=60)
    worst = world.structures.damage_at("forge")
    for _ in range(60):
        world._update_needs(st, False, 1)
    assert world.structures.damage_at("forge") < worst


def test_chief_orders_repairs_as_a_goal_for_everyone(data):
    world = world_at(data, "10:00")
    world.damage_structure("tavern", 60, "clown", "quebrar")
    world.damage_structure("tavern", 60, "clown", "quebrar")
    put(world, "town_hall", "chief")
    world._start_activity(world.states["chief"], "mandar_reconstruir", "town_hall", None, 10, 1.0)
    assert any(g["action"] == "construir" and g["place"] == "tavern" and g["who"] is None for g in world.goals)
    cands = [c for c in ranked_for(world, "florist") if c.action == "construir" and c.place == "tavern"]
    assert cands and any(f.label.startswith("objetivo") for f in cands[0].factors)


# ---------------------------------------------------------------------- leis
def test_fiscal_warns_then_arrests_then_limbo(data):
    world = world_at(data, "10:00")
    put(world, "market", "inspector", "teen")
    world.states["inspector"].activity = Activity(action="patrulhar", place="market", duration=30)
    events = collect(world)
    assert law.register(world, "inspector", "teen", "pichar", "market", "flagrante") == "advertencia"
    assert law.register(world, "inspector", "teen", "pichar", "market", "flagrante") is None  # reincidência: já anotado
    world.law.last.clear()
    assert law.register(world, "inspector", "teen", "pichar", "market", "flagrante") == "prisao"
    assert world.states["teen"].jailed_until is not None and any(ev.type == "arrest" for ev in events)
    # preso só faz coisas na Prisão
    places = {c.place for c in ranked_for(world, "teen")}
    assert places <= {data.world.law.prison}
    # solto depois do tempo
    world.states["teen"].jailed_until = world.now_minutes() - 1
    law.check_releases(world)
    assert world.states["teen"].jailed_until is None and any(ev.type == "released" for ev in events)
    # caso grave: Limbo, some das telas e volta estranho
    world.law.points["teen"] = data.world.law.limbo_points
    world.law.last.clear()
    put(world, "market", "teen")
    law.register(world, "inspector", "teen", "roubar", "market", "flagrante")
    teen = world.states["teen"]
    assert teen.away and teen.place == "limbo" and any(ev.type == "limbo_in" for ev in events)
    assert "teen" not in world.present_at("limbo")
    teen.limbo_until = world.now_minutes() - 1
    law.check_releases(world)
    assert not teen.away and teen.place == data.world.law.limbo_return
    assert teen.extra_traits and teen.extra_traits[0] in data.traits
    assert world.memories.strongest("teen", "limbo").permanent


def test_absent_offender_gets_a_warrant_and_the_fiscal_goes_after_him(data):
    world = world_at(data, "10:00")
    put(world, "town_hall", "inspector")
    put(world, "market", "greedy")
    world.remember("chef_wife", "sumico", subject="greedy", place="community_kitchen", detail="um pão inteiro")
    put(world, "town_hall", "chef_wife")
    events = collect(world)
    world._start_activity(world.states["chef_wife"], "denunciar", "town_hall", "inspector", 5, 1.0)
    assert "greedy" in world.law.warrants
    assert any(ev.type == "infraction" and ev.data["how"] == "denuncia" for ev in events)
    prender = [c for c in ranked_for(world, "inspector") if c.action == "prender"]
    assert prender and prender[0].target == "greedy" and prender[0].place == "market"


def test_noise_only_counts_at_night(data):
    world = world_at(data, "20:00")
    put(world, "tavern", "inspector", "cowboy_fat")
    assert law.register(world, "inspector", "cowboy_fat", "barulho", "tavern", "flagrante") is None
    world = world_at(data, "23:00")
    put(world, "tavern", "inspector", "cowboy_fat")
    assert law.register(world, "inspector", "cowboy_fat", "barulho", "tavern", "flagrante") == "advertencia"


def test_graffiti_is_signed_and_found_later(data):
    world = world_at(data, "10:00")
    for st in world.states.values():
        st.place = "town_square"  # ninguém em casa
    put(world, "houses", "teen")
    world._start_activity(world.states["teen"], "pichar", "houses", None, 5, 1.0)
    assert any(s.marks for s in world.structures.at("houses"))
    world.states["teen"].activity = None  # picha e vai embora
    put(world, "town_square", "teen")
    events = collect(world)
    put(world, "houses", "inspector")
    world._start_activity(world.states["inspector"], "patrulhar", "houses", None, 20, 1.0)
    assert any(ev.type == "infraction" and ev.data["how"] == "assinatura" and ev.data["offender"] == "teen"
               for ev in events)


# ---------------------------------------------------------- ganância e sumiço
def test_theft_then_the_cook_notices_and_suspects_someone(data):
    world = world_at(data, "09:00")
    put(world, "community_kitchen", "greedy")
    world._start_activity(world.states["greedy"], "roubar", "community_kitchen", None, 5, 1.0)
    assert world.stolen and world.stolen[0]["thief"] == "greedy"
    events = collect(world)
    put(world, "community_kitchen", "chef_wife")
    world._start_activity(world.states["chef_wife"], "trabalhar", "community_kitchen", None, 60, 1.0)
    sus = [ev for ev in events if ev.type == "suspicion"]
    assert sus and sus[0].data["suspect"] == "greedy"  # só ele passou por lá
    assert world.memories.strongest("chef_wife", "sumico").subject == "greedy"


# ------------------------------------------------------------------- facções
def test_factions_start_from_yaml_and_change_by_affinity(data):
    world = world_at(data)
    assert world.states["priest"].faction == "igreja" and world.states["medium"].faction == "seita"
    assert world.states["weirdo"].faction == "seita" and world.states["teen"].faction is None
    events = collect(world)
    world.change_affinity("teen", "medium", 30)  # depois de muitos rituais
    factions.check(world, "teen")
    assert world.states["teen"].faction == "seita"
    assert any(ev.type == "faction" and ev.data["change"] == "join" for ev in events)
    # ritual da seita só onde a Médium está
    world2 = world_at(data, "22:00")
    put(world2, "forest", "medium")
    put(world2, "town_square", "teen")
    world2.states["medium"].activity = Activity(action="ritual", place="forest", duration=60)
    places = {c.place for c in ranked_for(world2, "teen") if c.action == "participar_ritual"}
    assert places == {"forest"}


# ------------------------------------------------------------ eventos sociais
def test_npcs_organize_a_party_that_can_happen_or_fail(data, monkeypatch):
    world = world_at(data, "16:00")
    sev = data.social_events["festa_taverna"]
    monkeypatch.setattr(sev, "chance_per_hour", 1.0)
    world.states["florist"].needs["tedio"] = 90
    events = collect(world)
    social_events.plan_hourly(world)
    planned = [ev for ev in events if ev.type == "social_event_planned" and ev.data["social_event"] == "festa_taverna"]
    assert planned
    inst = world.social.active()[0]
    assert inst.guests and any(g["source"].startswith("festa_taverna") for g in world.goals)
    assert sev.start_window.contains(int(WorldClock.parse_start(data.world.clock, planned[0].data["start"]).hour * 60
                                         + WorldClock.parse_start(data.world.clock, planned[0].data["start"]).minute))
    # na hora, com gente no lugar: acontece; no fim: memória boa para quem foi
    world.clock.now = WorldClock.parse_start(data.world.clock, planned[0].data["start"])
    put(world, "tavern", inst.organizer, *inst.guests[:4])
    social_events.update(world)
    assert inst.status == "acontecendo"
    world.clock.now = world.clock.now + timedelta(minutes=inst.end - inst.start + 1)
    social_events.update(world)
    assert inst.status == "terminado"
    assert world.memories.strongest(inst.guests[0], "festa") is not None
    # outra festa, mas ninguém aparece: fracassa
    world.social.cooldown_until.clear()
    for st in world.states.values():
        st.place = "houses"
    social_events.plan_hourly(world)
    inst2 = world.social.active()[0]
    world.clock.now = datetime.fromisoformat(world.iso_of(inst2.start + 60))
    social_events.update(world)
    assert inst2.status == "fracassado"
    assert world.memories.strongest(inst2.organizer, "festa_fracassada") is not None


def test_wedding_needs_love_and_never_between_relatives(data, monkeypatch):
    world = world_at(data, "08:00")
    sev = data.social_events["casamento"]
    monkeypatch.setattr(sev, "chance_per_hour", 1.0)
    for a, b in (("clown", "fool"), ("fool", "clown")):  # irmãos
        world.change_affinity(a, b, 100)
    assert social_events._partner(world, sev, "fool") is None
    for a, b in (("fool", "florist"), ("florist", "fool")):
        world.change_affinity(a, b, 100)
    assert social_events._partner(world, sev, "fool") == "florist"
    assert world.states["chef_wife"].spouse == "chef_husband"  # o casal do YAML já é casado


# ------------------------------------------------------------- gênero nas falas
def test_gender_agreement_in_templates(data):
    assert text.fill("{eu} acorda meio perdid{o|a}.", {"eu": "lady"}, {"eu": "ela"}) == "{@lady} acorda meio perdida."
    assert text.fill("{eu} acorda meio perdid{o|a}.", {"eu": "chief"}, {"eu": "ele"}) == "{@chief} acorda meio perdido."
    assert text.fill("viu {outro:o|a}", {}, {"outro": "ela"}) == "viu a"
    assert not text.check_template("{eu} cansad{o|a} e {outro:ele|ela}", {"x"})
    world = world_at(data, "12:00")
    ctx = world._speech_ctx("lady", "town_square")
    assert speech.fill_narration(data, data.actions["cochilar"].narration_end, ctx, random.Random(1)).endswith("perdida.")


# ------------------------------------------------------------- persistência
def test_society_survives_a_restart(data, tmp_path):
    db = tmp_path / "w.sqlite"
    world = world_at(data, "10:00", db=db)
    world.remember("fool", "festa", subject="clown", object="fool", place="tavern")
    world.damage_structure("forge", 40, "clown", "quebrar")
    world.law.points["teen"] = 1.5
    world.states["teen"].jailed_until = world.now_minutes() + 100
    world.states["teen"].extra_traits = ["curioso"]
    world.add_goal(who=None, action="construir", place="forge", bonus=3, start=0, end=world.now_minutes() + 500,
                   source="teste")
    world.close()
    again = World(data, Storage(db))
    assert again.memories.strongest("fool", "festa").subject == "clown"
    assert again.structures.damage_at("forge") == pytest.approx(40)
    assert again.law.points["teen"] == 1.5 and again.states["teen"].jailed_until is not None
    assert again.states["teen"].extra_traits == ["curioso"] and "curioso" in again.traits_of("teen")
    assert any(g["source"] == "teste" for g in again.goals)
    again.close()


def test_long_split_run_is_still_deterministic(data, tmp_path):
    """Com a sociedade toda (memórias, leis, eventos...), parar e continuar dá a mesma história."""
    def run(world, out, hours):
        world.bus.subscribe(lambda ev: out.append((ev.type, ev.ts, ev.text)) if ev.type != "system" else None)
        world.run(until=world.clock.now + timedelta(hours=hours), fast=True)
        world.close()

    start = WorldClock.parse_start(data.world.clock, "2026-11-09T12:00")
    straight, split = [], []
    run(World(data, Storage(tmp_path / "a.sqlite"), seed=21, start=start), straight, 20)
    run(World(data, Storage(tmp_path / "b.sqlite"), seed=21, start=start), split, 10)
    run(World(data, Storage(tmp_path / "b.sqlite")), split, 10)
    assert split == straight


# ----------------------------------------------------- critério de aceite (semana)
@pytest.fixture(scope="module")
def week(data):
    start = WorldClock.parse_start(data.world.clock, "2026-11-09T00:00")
    world = World(data, None, seed=42, start=start)
    events = []
    world.bus.subscribe(lambda ev: events.append(ev) if ev.type != "decision" else None)
    world.run(until=world.clock.now + timedelta(days=7), fast=True)
    return events


def test_a_week_has_fights_peace_gossip_parties_arrests_and_rituals(week):
    count = Counter(ev.type for ev in week)
    assert count["fight"] >= 2 and count["argument"] >= 10
    assert count["reconcile"] >= 5
    assert count["gossip"] >= 20
    parties = [ev for ev in week if ev.type == "social_event_ended" and ev.data["result"] == "sucesso"]
    assert parties, "nenhum evento organizado por NPCs deu certo"
    assert count["arrest"] >= 1
    assert count["ritual"] >= 5
    # nada disso vem de roteiro: cada festa teve um organizador diferente ou em dia diferente
    assert len({(ev.actors[0], ev.ts[:10]) for ev in parties}) == len(parties)


def test_week_texts_have_no_leftover_variables(data, week):
    names = data.names()
    for ev in week:
        rendered = ev.render(names)
        assert "{" not in rendered, rendered
