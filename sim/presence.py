"""O olhar e a Aparição (Fase 4) — MQTT `sala/camera/pessoas`.

- **Presença**: o comando `presenca <n>` (vem do tópico; `n` = pessoas no
  quarto) liga a "sensação" por `presenca_expira_minutos`. Com presença, a nota
  de `encarar_tela` é multiplicada (`multiplicador_olhar`) e o olhar coletivo
  fica mais provável.
- **Olhar coletivo** (de hora em hora, `limites.chance_olhar_por_hora`): num
  lugar que aparece numa tela, quem está acordado e parado para tudo e encara
  a tela por um ou dois minutos. Depois volta ao normal (a Utility AI decide).
- **Aparição** (lendária): cada vez que alguém ENTRA no quarto (0 → 1+
  pessoas), com `chance_aparicao` e cooldown de `limites.cooldown_aparicao_dias`,
  a cidade vê uma silhueta borrada do lado de fora da tela. A seita enlouquece,
  o Padre fala em milagre, o Esquisito anota tudo; vira memória permanente e
  assunto por dias. O comando `aparicao` força uma (para testar).

Os números ficam em `data/events/criador.yaml > criador.presenca`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sim import lifecycle
from sim import speech
from sim.needs import clamp
from sim.state import Activity

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World

DAY = 1440


def _cfg(world: "World"):
    return world.data.creator.presence if world.data.creator else None


def _state(world: "World") -> dict:
    return world.creator.presence


def active(world: "World") -> bool:
    """Tem gente no quarto agora (a última mensagem com pessoas ainda vale)?"""
    cfg = _cfg(world)
    st = _state(world)
    if cfg is None or not st.get("count"):
        return False
    return world.now_minutes() - st.get("seen", -1e9) < cfg.presence_timeout_minutes


def summary(world: "World") -> dict:
    st = _state(world)
    last = st.get("last_apparition")
    return {"pessoas": st.get("count", 0), "ativa": active(world),
            "ultima_aparicao": world.iso_of(last) if last else None}


def set_presence(world: "World", arg) -> dict:
    """`presenca 2` / `presenca 0` (ou um JSON do tópico já convertido em número)."""
    try:
        count = int(float(str(arg).strip() or 0))
    except ValueError:
        return {"ok": False, "message": f"presenca: número inválido {arg!r}"}
    cfg = _cfg(world)
    if cfg is None:
        return {"ok": False, "message": "sem criador.presenca"}
    st = _state(world)
    was = active(world)
    st["count"] = max(0, count)
    if count > 0:
        st["seen"] = world.now_minutes()
    result = {"ok": True, "pessoas": st["count"], "apparition": False}
    if count > 0 and not was:  # alguém ENTROU no quarto
        last = st.get("last_apparition")
        cooldown = world.data.world.limits.apparition_cooldown_days * DAY
        if (last is None or world.now_minutes() - last >= cooldown) and world.rng.random() < cfg.apparition_chance:
            result["apparition"] = apparition(world)["ok"]
    return result


def stare_multiplier(world: "World", action_id: str) -> float | None:
    cfg = _cfg(world)
    if cfg is None or action_id != cfg.stare_action or not active(world):
        return None
    return cfg.stare_multiplier


def _screen_places(world: "World") -> dict[str, list[str]]:
    return {s.id: list(s.places) for s in world.data.world.screens}


def _awake_still(world: "World", place: str) -> list[str]:
    out = []
    for cid in world.present_at(place):
        st = world.states[cid]
        act = world.data.actions.get(st.activity.action) if st.activity else None
        if world.is_asleep(cid) or (act is not None and act.automatic) or st.jailed_until is not None:
            continue
        out.append(cid)
    return out


def group_stare(world: "World", place: str | None = None) -> bool:
    """Um ou vários NPCs param e encaram a tela ao mesmo tempo."""
    cfg = _cfg(world)
    action = world.data.actions.get(cfg.stare_action) if cfg else None
    if action is None:
        return False
    if place is None:
        visible = {p for places in _screen_places(world).values() for p in places}
        options = sorted(p for p in visible if _awake_still(world, p))
        if not options:
            return False
        place = world.rng.choice(options)
    people = _awake_still(world, place)
    world.rng.shuffle(people)
    people = sorted(people[: cfg.group_stare_max])
    if not people:
        return False
    low, high = action.duration_minutes
    for cid in people:
        # todos param e encaram em silêncio (uma linha só no Chat, a do olhar coletivo)
        world.interrupt(cid)
        world.states[cid].activity = Activity(action=action.id, place=place,
                                              duration=float(world.rng.randint(low, high)))
    ctx = world.speech_context(people[0], place)
    ctx.extra["convidados"] = world.list_names(people)
    line = speech.pick_line(world.data, "olhar_coletivo", ctx, world.rng, world.states[people[0]].recent_lines)
    if line is None:
        line = speech.fill_narration(world.data, "{convidados} param e encaram a tela.", ctx, world.rng)
    world.emit("stare", line, actors=people, place=place, tags=["misterio"], importance=1,
               data={"people": people, "presence": active(world), "action": action.id})
    return True


def hourly(world: "World") -> None:
    cfg = _cfg(world)
    if cfg is None:
        return
    chance = world.data.world.limits.stare_chance_per_hour
    if active(world):
        chance *= cfg.group_stare_multiplier
    if chance > 0 and world.rng.random() < chance:
        group_stare(world)


def update(world: "World") -> None:
    if world.ticks % 60 == 0:
        hourly(world)


def _speaker_line(world: "World", cid: str, situation: str) -> bool:
    """A fala desta situação existe para este personagem (filtros personagens/profissões)?"""
    ctx = world.speech_context(cid, world.states[cid].place)
    return any(speech.matches(ln, ctx, world.data) for ln in world.data.lines.get(situation, []))


def apparition(world: "World", forced: bool = False) -> dict:
    """A Aparição: a silhueta borrada do Criador do outro lado da tela."""
    cfg = _cfg(world)
    if cfg is None:
        return {"ok": False, "message": "sem criador.presenca"}
    living = [c for c in lifecycle.living(world) if not world.states[c].away]
    if not living:
        return {"ok": False, "message": "ninguém para ver"}
    screens = _screen_places(world)
    # a tela com mais gente acordada
    best, best_n = None, -1
    for sid in sorted(screens):
        n = sum(len(_awake_still(world, p)) for p in screens[sid])
        if n > best_n:
            best, best_n = sid, n
    places = screens.get(best, [world.data.world.central_place])
    crowd = [(len(_awake_still(world, p)), p) for p in places]
    place = max(crowd)[1] if crowd else world.data.world.central_place
    witnesses = sorted(c for c in living if not world.is_asleep(c))
    now = world.now_minutes()
    _state(world)["last_apparition"] = now
    narrator = (witnesses or living)[0]
    world.say(narrator, "aparicao", place=place, event_type="apparition", tags=["misterio", "criador"], importance=3,
              data={"screen": best, "places": places, "duration_s": cfg.apparition_seconds,
                    "witnesses": witnesses, "forced": forced},
              fallback="Uma silhueta borrada aparece do outro lado da tela e some.")
    # reações: cada um do seu jeito (Padre, Médium, Esquisito, a seita, alguns outros)
    crazy = cfg.faction_crazy
    others = 0
    seita = 0
    # o Padre e a Médium reagem mesmo que estivessem dormindo (acordam com a gritaria)
    leaders = [c for c in living if world.data.characters[c].profession in ("padre", "medium") and c not in witnesses]
    for cid in leaders + witnesses:
        prof = world.data.characters[cid].profession
        if prof == "padre":
            situation = "aparicao_padre"
        elif prof == "medium":
            situation = "aparicao_medium"
        elif _speaker_line(world, cid, "aparicao_esquisito"):
            situation = "aparicao_esquisito"
        elif world.states[cid].faction == crazy and seita < 3:
            situation, seita = "aparicao_seita", seita + 1
        elif others < 2 and world.rng.random() < 0.3:
            situation, others = "aparicao_outros", others + 1
        else:
            continue
        world.say(cid, situation, place=world.states[cid].place, tags=["misterio", "criador"], importance=2,
                  data={"apparition": True})
    for cid in living:
        st = world.states[cid]
        st.needs["medo"] = clamp(st.needs.get("medo", 0) + 20)
        if st.faction == crazy:
            st.needs["fe"] = clamp(st.needs.get("fe", 0) - 30)
            st.needs["medo"] = clamp(st.needs.get("medo", 0) - 10)  # a seita não tem medo: tem êxtase
        if cfg.apparition_memory:
            world.remember(cid, cfg.apparition_memory, subject=None, place=place,
                           factor=1.0 if cid in witnesses else world.data.world.memory.gossip_factor)
    medium = next((c for c in living if world.data.characters[c].profession == "medium"), None)
    for g in cfg.goals:
        if g.who == "quem_recebe":
            who = [medium] if medium else []
        elif g.who in ("seita", "igreja"):
            who = [c for c in living if world.states[c].faction == g.who]
        else:
            who = living
        for cid in who:
            world.add_goal(who=cid, action=g.action, place=g.place, bonus=g.bonus, start=now, end=now + g.hours * 60,
                           source="aparicao")
            world.states[cid].pending_review = True
    if cfg.apparition_topic:
        from sim.commands import add_topic

        add_topic(world, cfg.apparition_topic, None, place)
    return {"ok": True, "screen": best, "place": place, "witnesses": len(witnesses)}
