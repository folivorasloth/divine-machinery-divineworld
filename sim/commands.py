"""Os comandos do Criador (Fase 4) — seção 13.1 de docs/arquitetura.md.

Chegam todos pela mesma fila (`World.submit`): CLI, API HTTP e MQTT
`world/commands`. O que cada um faz, em regras pequenas (os números e as
palavras ficam em `data/events/criador.yaml`):

- `chefe "<ordem>"`: a ordem é entendida por palavras-chave (ou pelo LLM, ou
  "como dá"). O Chefe sente uma INTUIÇÃO e ganha um objetivo: ir até a Praça
  anunciar (ação `anunciar_ordem`). Quando ele anuncia, a ordem vira objetivos
  para a cidade, e cada morador reage pela personalidade (aceita, atrasa ou
  resiste). Ninguém conserta nada por mágica: "reconstruam a ferraria" só fica
  pronta quando os NPCs escolherem `construir` lá (a Utility AI de sempre) e o
  conserto aos poucos (`conserta`) deixar as estruturas inteiras.
- `medium "<mensagem>"`: a Médium ouve uma VOZ. Com `chance_erro` entende
  errado (de preferência do jeito mais desastroso) e, quando revelar a visão
  (`revelar_visao`), a seita ganha os objetivos da interpretação.
- `reviver <id>`: `lifecycle.resurrect(..., "criador")`, mais o assunto do
  momento (a cidade comenta por dias nas conversas).
- `status`, `quem <id>`: leitura (respondem com um dicionário; não mudam nada).
- `presenca <n>` (MQTT sala/camera/pessoas) e `aparicao` estão em `sim.presence`.

Estado (salvo em meta.society.creator): ordens, decretos, reuniões, assuntos
do momento e a presença no quarto.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sim import lifecycle
from sim import presence as presence_mod
from sim import social_events as social_mod
from sim.needs import clamp, mood
from sim.rng import weighted_choice

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import Command, World
    from sim.schemas import AnnouncerConfig, CreatorEffects, OrderKind

CREATOR_COMMANDS = {"chefe", "medium", "reviver", "status", "quem", "presenca", "aparicao", "raio"}
INTERNAL_COMMANDS = {"_ordem_interpretada", "_llm_fala"}
def needs_rebuild(world: "World", place: str | None) -> bool:
    """O lugar tem alguma estrutura que não está "inteira" (estruturas.danificado_abaixo)?
    "Reconstruir" termina quando tudo volta a ficar inteiro; o resto do capricho
    (de 70 a 100) a cidade faz quando quiser, como sempre."""
    if place is None:
        return False
    return any(world.structures.state(s.id) != "inteiro" for s in world.structures.at(place))


@dataclass
class CreatorState:
    orders: list[dict] = field(default_factory=list)   # ordens do Chefe e vozes da Médium
    decrees: list[dict] = field(default_factory=list)  # regras do Chefe: {action, mode, until, order}
    meetings: list[dict] = field(default_factory=list)
    topics: list[dict] = field(default_factory=list)   # assuntos do momento: {kind, subject, start, until}
    presence: dict = field(default_factory=dict)       # sim.presence
    next_id: int = 1

    def to_json(self) -> dict:
        keep = [o for o in self.orders if o["status"] in ("recebida", "interpretando", "esperando", "em_andamento")]
        keep += [o for o in self.orders if o not in keep][-10:]  # as últimas resolvidas (para o status)
        return {"orders": keep, "decrees": self.decrees, "meetings": self.meetings, "topics": self.topics,
                "presence": self.presence, "next_id": self.next_id}

    @classmethod
    def from_json(cls, raw: dict | None) -> "CreatorState":
        st = cls()
        for key, value in (raw or {}).items():
            if hasattr(st, key):
                setattr(st, key, value)
        return st


# ===================================================================== texto
def norm(text: str) -> str:
    """minúsculo, sem acento, sem pontuação (para comparar palavras-chave)."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", text).strip() + " "


def _hits(words: list[str], text: str) -> int:
    """Quantos pedaços de palavra aparecem no texto (cada pedaço conta no começo de uma palavra)."""
    return sum(1 for w in words if w and (" " + norm(w).strip()) in text)


def match_kind(orders: dict, text: str) -> tuple[str | None, int]:
    t = norm(text)
    best, best_hits = None, 0
    for oid, order in orders.items():
        n = _hits(order.words, t)
        if n > best_hits:
            best, best_hits = oid, n
    return best, best_hits


ARTICLES = ("o ", "a ", "os ", "as ")


def _strip_article(name: str) -> str:
    n = norm(name).strip()
    for art in ARTICLES:
        if n.startswith(art):
            return n[len(art):]
    return n


def find_place(world: "World", text: str) -> str | None:
    """O lugar citado na mensagem ("a ferraria", "forge", "a bigorna"). O nome mais longo ganha."""
    t = norm(text)
    options: list[tuple[int, str]] = []
    for pid, place in world.data.places.items():
        keys = {_strip_article(place.name), pid.replace("_", " ")}
        for s in place.structures:
            keys.add(_strip_article(s.name))
        for key in keys:
            if key and f" {key} " in t:
                options.append((len(key), pid))
    if not options:
        return None
    return max(options)[1]


def find_action(world: "World", text: str, aliases: dict[str, list[str]]) -> str | None:
    t = norm(text)
    options: list[tuple[int, str]] = []
    for aid, action in world.data.actions.items():
        keys = [aid.replace("_", " "), _strip_article(action.name)] + list(aliases.get(aid, []))
        for key in keys:
            k = norm(key).strip()
            if k and (" " + k) in t:
                options.append((len(k), aid))
    if not options:
        return None
    return max(options)[1]


def name_token(world: "World", some_id: str | None) -> str:
    """{@id} para lugares/estruturas/personagens; o nome da ação em minúsculo para ações."""
    if not some_id:
        return ""
    if some_id in world.data.actions:
        name = world.data.actions[some_id].name
        return name[:1].lower() + name[1:]
    return "{@" + some_id + "}"


# ===================================================================== ajuda
def creator_cfg(world: "World"):
    return world.data.creator


def _living(world: "World") -> list[str]:
    return [c for c in lifecycle.living(world) if not world.states[c].away]


def _receiver(world: "World", profession: str) -> str | None:
    """Quem tem a profissão (o Chefe atual, a Médium atual), vivo e no mundo."""
    people = [c for c in _living(world) if world.data.characters[c].profession == profession]
    return people[0] if people else None


def faction_members(world: "World", fid: str) -> list[str]:
    return [c for c in _living(world) if world.states[c].faction == fid]


def resistance_factor(world: "World", ann: "AnnouncerConfig", cid: str, boss: str | None) -> float:
    """Quanto `cid` topa a ordem de `boss`: Π traços × (1 + afinidade/100 × peso)."""
    res = ann.resistance
    f = 1.0
    for tid in world.traits_of(cid):
        f *= res.traits.get(tid, 1.0)
    if boss and boss != cid:
        f *= max(0.0, 1 + world.affinity(cid, boss) / 100 * res.affinity_weight)
    return f


def _who(world: "World", who: str, receiver: str | None) -> list[str]:
    if who == "quem_recebe":
        return [receiver] if receiver else []
    if who in ("seita", "igreja"):
        return faction_members(world, who)
    return _living(world)


def _pending_for(world: "World", cid: str) -> dict | None:
    for o in world.creator.orders:
        if o["status"] == "recebida" and o.get("receiver") == cid:
            return o
    return None


def _ann(world: "World", order: dict):
    c = creator_cfg(world)
    return c.chief if order["channel"] == "chefe" else c.medium


def _kind_def(world: "World", order: dict) -> "OrderKind | None":
    return _ann(world, order).orders.get(order.get("kind"))


# ================================================================= comandos
def handle(world: "World", cmd: "Command") -> dict:
    c = creator_cfg(world)
    name = cmd.cmd
    if c is None and name in ("chefe", "medium"):
        return _fail(world, "data/events/criador.yaml não existe: sem ordens do Criador.")
    if name == "chefe":
        return receive(world, "chefe", cmd.arg.strip().strip('"'), cmd.id)
    if name == "medium":
        return receive(world, "medium", cmd.arg.strip().strip('"'), cmd.id)
    if name == "reviver":
        return revive(world, cmd.arg.strip())
    if name == "status":
        return {"ok": True, "status": status(world)}
    if name == "quem":
        cid = cmd.arg.strip()
        if cid not in world.states:
            return {"ok": False, "message": f"personagem '{cid}' não existe"}
        return {"ok": True, "sheet": character_sheet(world, cid)}
    if name == "raio":
        return lightning(world, cmd.arg.strip())
    if name == "presenca":
        return presence_mod.set_presence(world, cmd.arg)
    if name == "aparicao":
        return presence_mod.apparition(world, forced=True)
    if name == "_ordem_interpretada":
        return _interpreted(world, cmd.payload or {})
    if name == "_llm_fala":
        return world.llm_line_ready(cmd.payload or {})
    return {"ok": False, "message": f"comando desconhecido: {name}"}


def _fail(world: "World", message: str) -> dict:
    world.emit("system", message, tags=["sistema"], data={"error": True})
    return {"ok": False, "message": message}


def _announce_command(world: "World", channel: str, text: str) -> None:
    world.emit("creator_command", f"O Criador fala com {'o Chefe' if channel == 'chefe' else 'a Médium'}: \"{text}\"",
               tags=["criador"], importance=1, data={"cmd": channel, "arg": text})


# ------------------------------------------------------------- receber
def receive(world: "World", channel: str, text: str, cmd_id: str = "") -> dict:
    if not text:
        return _fail(world, f"uso: {channel} \"<mensagem>\"")
    ann = creator_cfg(world).chief if channel == "chefe" else creator_cfg(world).medium
    st = world.creator
    kind, hits = match_kind(ann.orders, text)
    order = {"id": st.next_id, "channel": channel, "text": text, "kind": kind, "how": "palavras" if kind else None,
             "place": find_place(world, text), "status": "recebida", "received": world.clock.iso(),
             "created": world.now_minutes(), "cmd": cmd_id, "receiver": None, "responses": {}, "builders": []}
    st.next_id += 1
    st.orders.append(order)
    _announce_command(world, channel, text)
    if kind is None:
        cfg = world.data.world.ollama
        if world.llm_usable() and cfg.interpret_orders:
            order["status"] = "interpretando"
            options = sorted(ann.orders)
            if world.llm.interpret(text, options, lambda k, oid=order["id"]: world.submit_internal(
                    "_ordem_interpretada", {"order": oid, "kind": k})):
                return {"ok": True, "order": order["id"], "message": "o LLM está interpretando a ordem"}
            order["status"] = "recebida"
        _confused_kind(world, ann, order)
    if channel == "medium":
        _medium_twist(world, ann, order)
    _deliver(world, order)
    return {"ok": True, "order": order["id"], "kind": order["kind"], "how": order["how"],
            "place": order["place"], "receiver": order["receiver"], "status": order["status"]}


def _confused_kind(world: "World", ann, order: dict) -> None:
    options = sorted(k for k, o in ann.orders.items() if o.confused_weight > 0)
    if not options:
        options = sorted(ann.orders)
    order["kind"] = weighted_choice(world.rng, options, [max(0.01, ann.orders[k].confused_weight) for k in options])
    order["how"] = "como_da"
    order["confused"] = True


def _interpreted(world: "World", payload: dict) -> dict:
    order = next((o for o in world.creator.orders if o["id"] == payload.get("order")), None)
    if order is None or order["status"] != "interpretando":
        return {"ok": False, "message": "ordem não está esperando interpretação"}
    ann = _ann(world, order)
    order["status"] = "recebida"
    kind = payload.get("kind")
    if kind in ann.orders:
        order["kind"], order["how"] = kind, "llm"
    else:
        _confused_kind(world, ann, order)
    if order["channel"] == "medium":
        _medium_twist(world, ann, order)
    _deliver(world, order)
    return {"ok": True, "order": order["id"], "kind": order["kind"], "how": order["how"]}


def _medium_twist(world: "World", ann, order: dict) -> None:
    """A Médium às vezes entende errado de propósito (chance_erro), de preferência
    do jeito mais desastroso; e a mensagem que ela repete sai torta."""
    order["heard"] = order["text"]
    if world.rng.random() >= ann.error_chance:
        return
    pool = [d for d in ann.disasters if d in ann.orders and d != order["kind"]]
    if not pool:
        pool = sorted(k for k in ann.orders if k != order["kind"])
    if not pool:
        return
    order["meant"] = order["kind"]
    order["kind"] = weighted_choice(world.rng, pool, [max(0.05, ann.orders[k].confused_weight) for k in pool])
    order["wrong"] = True
    words = [w for w in order["text"].split() if len(w.strip(".,!?;:\"'")) >= 4]
    if words and ann.swap_words:
        victim = world.rng.choice(words)
        order["heard"] = order["text"].replace(victim, world.rng.choice(ann.swap_words), 1)


def _deliver(world: "World", order: dict) -> None:
    """A intuição chega ao Chefe (a voz chega à Médium). Sem ninguém no papel, espera."""
    ann = _ann(world, order)
    receiver = _receiver(world, ann.profession)
    if receiver is None:
        if order["status"] != "esperando":
            order["status"] = "esperando"
            prof = world.data.professions[ann.profession].name
            world.emit("creator_order", f"A mensagem do Criador fica no ar: não há {prof} para ouvir.",
                       tags=["criador"], importance=1, data={"order": order["id"], "phase": "waiting"})
        return
    now = world.now_minutes()
    order["receiver"] = receiver
    order["status"] = "recebida"
    order["expires"] = now + ann.hours * 60
    kd = _kind_def(world, order)
    kind_name = kd.name if kd else order["kind"]
    heard = order.get("heard", order["text"])
    world.say(receiver, ann.speech_received, event_type="creator_order" if order["channel"] == "chefe" else "creator_voice",
              extra={"fato": heard, "evento": kind_name}, tags=["criador"], importance=2,
              data={"order": order["id"], "phase": "received", "kind": order["kind"], "how": order["how"],
                    "wrong": order.get("wrong", False)},
              fallback="{eu} sente uma coisa estranha: \"{fato}\".")
    if order.get("confused") and ann.speech_confused:
        world.say(receiver, ann.speech_confused, event_type="speech", extra={"fato": heard, "evento": kind_name},
                  tags=["criador"], importance=1, data={"order": order["id"]})
    world.add_goal(who=receiver, action=ann.action, place=None, bonus=ann.bonus, start=now, end=order["expires"],
                   source=f"criador#{order['id']}")
    world.states[receiver].pending_review = True


# ----------------------------------------------------------- o anúncio
def announce_ok(world: "World", cid: str) -> bool:
    return world.creator is not None and _pending_for(world, cid) is not None


def before_announce(world: "World", cid: str, place: str, extra: dict, edata: dict) -> bool:
    """`_special_before` da ação de anunciar: prepara as variáveis da fala."""
    order = _pending_for(world, cid)
    if order is None:
        return False
    kd = _kind_def(world, order)
    extra["fato"] = order.get("heard", order["text"])
    extra["evento"] = kd.name if kd else str(order["kind"])
    target = None
    if kd and kd.special == "reconstruir":
        target = _rebuild_target(world, order)
    elif kd and kd.special == "regra":
        rule = creator_cfg(world).chief.rule
        mode, action, invented = _rule_of(world, order["text"], rule)
        order.update({"rule_action": action, "rule_mode": mode, "rule_invented": invented})
        target = action
        edata["situation"] = "regra_proibida" if mode == "proibido" else "regra_liberada"
    elif kd and kd.special == "reuniao":
        target = creator_cfg(world).chief.meeting.place
    else:
        target = order.get("place")
    extra["objeto"] = name_token(world, target) or "agora"
    if kd and kd.speech and "situation" not in edata:
        edata["situation"] = kd.speech
    edata.update({"order": order["id"], "kind": order["kind"], "phase": "announced"})
    return True


def after_announce(world: "World", cid: str, place: str) -> None:
    order = _pending_for(world, cid)
    if order is None:
        return
    ann = _ann(world, order)
    kd = _kind_def(world, order)
    now = world.now_minutes()
    order["status"] = "em_andamento"
    order["announced"] = world.clock.iso()
    order["announced_at"] = place
    world.remove_goals(f"criador#{order['id']}")
    if kd is None:
        order["status"] = "cumprida"
        return
    eff = kd.effects
    if eff.memory:
        world.remember_scene(eff.memory, subject=cid, place=place)
    order["until"] = now + kd.hours * 60
    special = kd.special
    if special == "reconstruir":
        _start_rebuild(world, order, ann, kd, cid, place)
    elif special == "festa":
        sid = eff.social_event
        inst = social_mod.plan_now(world, sid, cid, now + 60) if sid else None
        if inst is None:
            world.say(cid, "ordem_festa_marcada", place=place, tags=["criador"], importance=1,
                      data={"order": order["id"]})
        else:
            order["social"] = inst.id
        order["status"] = "cumprida"
    elif special == "regra":
        _start_decree(world, order, kd)
    elif special == "reuniao":
        _start_meeting(world, order, ann, cid)
    else:
        if eff.social_event:
            inst = social_mod.plan_now(world, eff.social_event, cid, now + 60)
            if inst is not None:
                order["social"] = inst.id
        order["status"] = "cumprida" if not eff.goals else "em_andamento"
    _apply_effects(world, order, ann, eff, cid, place)
    if order["channel"] == "chefe":
        add_topic(world, "ordem", cid)
    counts = {k: sum(1 for r in order["responses"].values() if r["kind"] == k) for k in ("aceita", "atrasa", "resiste")}
    if order["responses"]:
        summary = (f"Reação à {'ordem' if order['channel'] == 'chefe' else 'visão'} ({kd.name}): "
                   f"{counts['aceita']} aceitam, {counts['atrasa']} vão atrasar, {counts['resiste']} resistem.")
    else:
        summary = f"A {'ordem' if order['channel'] == 'chefe' else 'visão'} ({kd.name}) foi anunciada."
    world.emit("creator_order" if order["channel"] == "chefe" else "creator_voice", summary,
               actors=[cid], place=place, tags=["criador"],
               data={"order": order["id"], "phase": "applied", "kind": order["kind"],
                     "responses": order["responses"], "counts": counts, "target_place": order.get("target_place"),
                     "rule": [order.get("rule_mode"), order.get("rule_action")] if special == "regra" else None})


def _apply_effects(world: "World", order: dict, ann, eff: "CreatorEffects", boss: str, place: str) -> None:
    """Necessidades, objetivos (com a reação de cada um) e o assunto do momento."""
    now = world.now_minutes()
    if eff.needs:
        for cid in _who(world, eff.needs_for, boss):
            st = world.states[cid]
            for n, v in eff.needs.items():
                st.needs[n] = clamp(st.needs.get(n, 0) + v)
    for g in eff.goals:
        gplace = g.place
        if g.order_place:
            gplace = order.get("place") or order.get("target_place") or gplace
        for cid in _who(world, g.who, boss):
            if g.bonus < 1:  # "menos vontade": vale para todos, sem resistência
                world.add_goal(who=cid, action=g.action, place=gplace, bonus=g.bonus, start=now,
                               end=now + g.hours * 60, source=f"criador#{order['id']}", penalty=True)
                continue
            start, bonus = _respond(world, order, ann, cid, boss, g.bonus, place)
            if start is None:
                continue
            world.add_goal(who=cid, action=g.action, place=gplace, bonus=bonus, start=start,
                           end=now + g.hours * 60, source=f"criador#{order['id']}")
            world.states[cid].pending_review = True
    if eff.topic:
        add_topic(world, eff.topic, boss)


def _respond(world: "World", order: dict, ann, cid: str, boss: str, bonus: float, place: str
             ) -> tuple[float | None, float]:
    """Como `cid` recebe a ordem (uma vez por ordem): aceita, atrasa ou resiste.
    Devolve (minuto em que começa a valer | None se resiste, bônus pessoal)."""
    res = ann.resistance
    now = world.now_minutes()
    resp = order["responses"].get(cid)
    if resp is None:
        if cid == boss:
            factor = 1.5
        else:
            factor = resistance_factor(world, ann, cid, boss)
        if factor < res.resist_below:
            kind, delay = "resiste", 0.0
        elif factor < res.delay_below:
            kind, delay = "atrasa", world.rng.uniform(*res.delay_hours) * 60
        else:
            kind, delay = "aceita", 0.0
        resp = {"kind": kind, "factor": round(factor, 2), "start": now + delay}
        order["responses"][cid] = resp
        _maybe_say_response(world, order, ann, cid, kind, place)
    if resp["kind"] == "resiste":
        return None, 1.0
    personal = 1 + (bonus - 1) * min(2.0, resp["factor"])
    return max(now, resp["start"]), personal


def _maybe_say_response(world: "World", order: dict, ann, cid: str, kind: str, place: str) -> None:
    """Só quem está por perto (no lugar do anúncio) reage em voz alta, no máximo max_falas."""
    if cid == order.get("receiver") or world.states[cid].place != place or world.is_asleep(cid):
        return
    said = order.setdefault("said", 0)
    if said >= ann.resistance.max_lines:
        return
    situation = {"resiste": "ordem_resiste" if order["channel"] == "chefe" else "visao_resiste",
                 "atrasa": "ordem_atrasa",
                 "aceita": "ordem_aceita" if order["channel"] == "chefe" else "visao_aceita"}[kind]
    if order["channel"] == "chefe" and kind == "resiste":
        situation = creator_cfg(world).chief.resist_speech
    if kind == "aceita" and world.rng.random() < 0.5:
        return
    kd = _kind_def(world, order)
    ev = world.say(cid, situation, place=place, tags=["criador"], importance=1,
                   extra={"evento": kd.name if kd else "", "fato": order["text"]},
                   data={"order": order["id"], "response": kind})
    if ev is not None:
        order["said"] = said + 1


# ------------------------------------------------------- reconstruir
def _rebuild_target(world: "World", order: dict) -> str | None:
    place = order.get("place")
    if place and world.structures.at(place):
        return place
    worst, damage = world.structures.worst()
    return worst if needs_rebuild(world, worst) else place


def _start_rebuild(world: "World", order: dict, ann, kd, boss: str, place: str) -> None:
    target = _rebuild_target(world, order)
    order["target_place"] = target
    if not needs_rebuild(world, target):
        world.say(boss, "ordem_sem_estrago", place=place, tags=["criador"], importance=1,
                  extra={"objeto": name_token(world, target) or "a cidade"}, data={"order": order["id"]})
        order["status"] = "sem_estrago"
        return
    repair = next((a for a in sorted(world.data.actions.values(), key=lambda a: a.id) if a.active and a.repairs), None)
    if repair is None:
        order["status"] = "cumprida"
        return
    order["repair_action"] = repair.id
    now = world.now_minutes()
    for cid in _living(world):
        start, bonus = _respond(world, order, ann, cid, boss, kd.bonus, place)
        if start is None:
            continue
        world.add_goal(who=cid, action=repair.id, place=target, bonus=bonus, start=start, end=order["until"],
                       source=f"criador#{order['id']}")
        world.states[cid].pending_review = True
    order["damage_at_start"] = round(world.structures.damage_at(target))
    order["started"] = now


def on_action_started(world: "World", cid: str, action, place: str) -> None:
    """Gancho do engine: quem começa a consertar o lugar de uma ordem entra na lista da obra."""
    if world.creator is None or not action.repairs:
        return
    for order in world.creator.orders:
        if order["status"] == "em_andamento" and order.get("target_place") == place \
                and order.get("repair_action") == action.id:
            if cid not in order["builders"]:
                order["builders"].append(cid)


def _check_rebuild(world: "World", order: dict) -> None:
    target = order.get("target_place")
    # pronto = tudo inteiro de novo (o conserto é aos poucos; o capricho final fica para depois)
    if target is None or needs_rebuild(world, target):
        return
    order["status"] = "cumprida"
    order["done"] = world.clock.iso()
    world.remove_goals(f"criador#{order['id']}")
    builders = [b for b in order["builders"] if b in world.states and world.states[b].alive]
    boss = order.get("receiver")
    speaker = boss if boss in world.states and world.states[boss].alive else (builders[0] if builders else None)
    if speaker:
        world.say(speaker, creator_cfg(world).chief.done_speech, place=world.states[speaker].place,
                  event_type="creator_order", tags=["criador", "trabalho"], importance=2,
                  extra={"objeto": name_token(world, target),
                         **({"convidados": world.list_names(builders)} if builders else {})},
                  data={"order": order["id"], "phase": "done", "place": target, "builders": builders},
                  fallback="{objeto} está de pé de novo. A cidade fez.")
    for b in builders:
        world.remember(b, "mutirao", subject=boss or b, place=target)
        if boss and b != boss:
            world.change_affinity(b, boss, 2)


# ------------------------------------------------------------- regra
def _rule_of(world: "World", text: str, rule) -> tuple[str, str, bool]:
    t = norm(text)
    allow = _hits(rule.allow_words, t)
    prohibit = _hits(rule.prohibit_words, t)
    mode = "liberado" if allow and not prohibit else "proibido"
    action = find_action(world, text, rule.aliases)
    invented = False
    if action is None:
        options = [a for a in rule.suggestions if a in world.data.actions]
        action = world.rng.choice(options) if options else "cochilar"
        invented = True
    return mode, action, invented


def _start_decree(world: "World", order: dict, kd) -> None:
    now = world.now_minutes()
    # quem ouviu o anúncio reage (o Adolescente já sai de skate; o Fiscal aplaude)
    boss = order.get("receiver")
    place = order.get("announced_at")
    ann = creator_cfg(world).chief
    for cid in world.present_at(place) if place else []:
        _respond(world, order, ann, cid, boss, 2.0, place)
    action = order["rule_action"]
    world.creator.decrees = [d for d in world.creator.decrees if d["action"] != action]
    world.creator.decrees.append({"action": action, "mode": order["rule_mode"], "until": now + kd.hours * 60,
                                  "order": order["id"], "boss": order.get("receiver")})
    for st in world.states.values():
        st.pending_review = True


def decree_for(world: "World", action_id: str) -> dict | None:
    if world.creator is None:
        return None
    now = world.now_minutes()
    for d in world.creator.decrees:
        if d["action"] == action_id and d["until"] > now:
            return d
    return None


def infraction_of(world: "World", action) -> str | None:
    """A infração de uma ação AGORA: a do YAML, a do decreto (proibido) ou nenhuma (liberado)."""
    d = decree_for(world, action.id)
    if d is None or creator_cfg(world) is None:
        return action.infraction
    if d["mode"] == "liberado":
        return None
    return action.infraction or creator_cfg(world).chief.rule.infraction


def decree_multiplier(world: "World", cid: str, action_id: str) -> float | None:
    d = decree_for(world, action_id)
    if d is None:
        return None
    rule = creator_cfg(world).chief.rule
    if d["mode"] == "liberado":
        return rule.allowed_bonus
    mults = [rule.obey_traits[t] for t in world.traits_of(cid) if t in rule.obey_traits]
    return max(mults) if mults else rule.obey


# ----------------------------------------------------------- reunião
def _start_meeting(world: "World", order: dict, ann, boss: str) -> None:
    m = creator_cfg(world).chief.meeting
    now = world.now_minutes()
    start = now + m.starts_in_minutes
    meeting = {"order": order["id"], "place": m.place, "start": start, "end": start + m.minutes,
               "attendees": [], "boss": boss, "status": "marcada"}
    world.creator.meetings.append(meeting)
    world.say(boss, "reuniao_convocada", place=world.states[boss].place, tags=["criador", "evento"], importance=1,
              extra={"hora": world.hhmm_of(start)}, data={"order": order["id"], "start": world.iso_of(start)})
    for cid in _living(world):
        s, bonus = _respond(world, order, ann, cid, boss, m.bonus, m.place)
        if s is None or s > start:
            continue  # quem resiste ou atrasa demais não vai
        world.add_goal(who=cid, action=m.action, place=m.place, bonus=bonus, start=start - 20, end=start + m.minutes,
                       source=f"criador#{order['id']}")


def meeting_at(world: "World", place: str) -> dict | None:
    if world.creator is None:
        return None
    now = world.now_minutes()
    for m in world.creator.meetings:
        if m["status"] != "terminada" and m["place"] == place and m["start"] - 20 <= now < m["end"]:
            return m
    return None


def meeting_joined(world: "World", cid: str, place: str) -> None:
    m = meeting_at(world, place)
    if m is not None and cid not in m["attendees"]:
        m["attendees"].append(cid)


def _finish_meeting(world: "World", m: dict) -> None:
    m["status"] = "terminada"
    order = next((o for o in world.creator.orders if o["id"] == m["order"]), None)
    if order:
        order["status"] = "cumprida"
        world.remove_goals(f"criador#{order['id']}")
    people = [p for p in m["attendees"] if world.states[p].alive]
    boss = m["boss"] if world.states.get(m["boss"]) and world.states[m["boss"]].alive else (people[0] if people else None)
    if boss is None:
        return
    situation = "reuniao_fim" if len(people) >= 2 else "reuniao_vazia"
    world.say(boss, situation, place=m["place"], event_type="creator_order", tags=["criador", "evento"], importance=1,
              extra={"convidados": world.list_names([p for p in people if p != boss])},
              data={"order": m["order"], "phase": "done", "attendees": people})
    mem = creator_cfg(world).chief.meeting.memory
    if mem:
        for p in people:
            world.remember(p, mem, subject=boss, place=m["place"])


# ----------------------------------------------------------- assuntos
def add_topic(world: "World", kind: str, subject: str | None, place: str | None = None) -> None:
    cfg = creator_cfg(world)
    if cfg is None or kind not in cfg.topics:
        return
    now = world.now_minutes()
    world.creator.topics = [t for t in world.creator.topics if not (t["kind"] == kind and t["subject"] == subject)]
    world.creator.topics.append({"kind": kind, "subject": subject, "place": place, "start": now,
                                 "until": now + cfg.topics[kind].days * 1440})


def topic_for(world: "World", action_id: str, speaker: str, target: str | None) -> tuple[str, dict] | None:
    """Assunto do momento numa conversa: (situação, variáveis) ou None."""
    cfg = creator_cfg(world)
    if cfg is None or not world.creator.topics:
        return None
    now = world.now_minutes()
    for t in sorted(world.creator.topics, key=lambda t: -t["start"]):
        tdef = cfg.topics.get(t["kind"])
        if tdef is None or action_id not in tdef.actions or now >= t["until"]:
            continue
        if t["subject"] in (speaker, target):
            continue
        fading = 1 - (now - t["start"]) / max(1.0, t["until"] - t["start"])
        if world.rng.random() >= tdef.chance * fading:
            continue
        situation = tdef.situation or f"assunto_{t['kind']}"
        if situation not in world.data.lines:
            continue
        extra = {"terceiro": t["subject"]} if t["subject"] else {}
        return situation, extra
    return None


# ------------------------------------------------------------- raio
def lightning(world: "World", place: str) -> dict:
    """`raio <lugar>`: um raio cai e destrói as estruturas do lugar (para testar as
    reconstruções: depois, `chefe "reconstruam ..."`). Quem estiver lá leva um susto."""
    if place not in world.data.places:
        return _fail(world, f"raio: lugar '{place}' não existe")
    hit = world.structures.at(place)
    if not hit:
        return {"ok": False, "message": f"{world.data.name_of(place)} não tem nada para quebrar"}
    for s in hit:
        world.structures.change(s.id, -100)
    world.emit("structure_changed", f"Um raio cai do nada em {{@{place}}}. Destruído: "
               f"{world.list_names([s.id for s in hit])}.", place=place, tags=["criador", "misterio"], importance=2,
               data={"cause": "raio", "structures": [s.id for s in hit], "to": "destruido"})
    for cid in world.present_at(place):
        world.states[cid].needs["medo"] = clamp(world.states[cid].needs.get("medo", 0) + 30)
    return {"ok": True, "place": place, "destroyed": [s.id for s in hit]}


# ------------------------------------------------------------- reviver
def revive(world: "World", cid: str) -> dict:
    if cid not in world.states:
        return _fail(world, f"reviver: personagem '{cid}' não existe")
    st = world.states[cid]
    if st.alive:
        return {"ok": False, "message": f"{world.data.name_of(cid)} está viv{'a' if world.data.characters[cid].pronoun == 'ela' else 'o'}."}
    world.emit("creator_command", f"O Criador estende a mão sobre o Cemitério: reviver {{@{cid}}}.",
               actors=[cid], tags=["criador"], importance=1, data={"cmd": "reviver", "arg": cid})
    cfg = creator_cfg(world)
    fear = cfg.revive.fear if cfg else 85.0
    forget = cfg.revive.forget_chance if cfg else 0.5
    if not lifecycle.resurrect(world, cid, "criador", fear=fear, forget_chance=forget):
        return _fail(world, f"não deu para reviver '{cid}'")
    if cfg and cfg.revive.topic:
        add_topic(world, cfg.revive.topic, cid, world.data.world.death.body_place)
    for other in world.states.values():
        other.pending_review = True
    return {"ok": True, "revived": cid, "traits": world.traits_of(cid), "fear": st.needs.get("medo")}


# ===================================================================== a cada tick
def update(world: "World") -> None:
    if world.creator is None or creator_cfg(world) is None:
        return
    now = world.now_minutes()
    for order in world.creator.orders:
        status = order["status"]
        if status == "esperando":
            if world.ticks % 60 == 0:
                _deliver(world, order)
        elif status == "recebida" and now >= order.get("expires", now + 1):
            order["status"] = "perdida"
            world.remove_goals(f"criador#{order['id']}")
            who = order.get("receiver")
            if who and world.states[who].alive:
                world.emit("creator_order", f"{{@{who}}} deixa a intuição para depois... e esquece.",
                           actors=[who], place=world.states[who].place, tags=["criador"], importance=1,
                           data={"order": order["id"], "phase": "lost"})
        elif status == "em_andamento":
            if order.get("target_place"):
                _check_rebuild(world, order)
            if order["status"] == "em_andamento" and now >= order.get("until", now + 1):
                order["status"] = "abandonada"
                world.remove_goals(f"criador#{order['id']}")
                if order.get("target_place"):
                    who = order.get("receiver")
                    if who and world.states[who].alive:
                        kd = _kind_def(world, order)
                        world.say(who, creator_cfg(world).chief.expired_speech, place=world.states[who].place,
                                  event_type="creator_order", tags=["criador"], importance=1,
                                  extra={"evento": kd.name if kd else ""},
                                  data={"order": order["id"], "phase": "expired"})
                else:
                    order["status"] = "cumprida"
    for m in world.creator.meetings:
        if m["status"] != "terminada" and now >= m["end"]:
            _finish_meeting(world, m)
    world.creator.meetings = [m for m in world.creator.meetings if m["status"] != "terminada" or now - m["end"] < 60]
    for d in list(world.creator.decrees):
        if d["until"] <= now:
            world.creator.decrees.remove(d)
            boss = d.get("boss")
            if boss and boss in world.states and world.states[boss].alive:
                world.say(boss, "regra_fim", place=world.states[boss].place, event_type="creator_order",
                          tags=["criador"], importance=1, extra={"objeto": name_token(world, d["action"])},
                          data={"phase": "decree_end", "action": d["action"]})
    world.creator.topics = [t for t in world.creator.topics if t["until"] > now]
    presence_mod.update(world)


# ===================================================================== leitura
def status(world: "World") -> dict:
    snap = world.snapshot() or {}
    names = world.names()
    orders = [{"id": o["id"], "canal": o["channel"], "texto": o["text"], "entendeu": o["kind"], "como": o["how"],
               "estado": o["status"], "quem_recebeu": names.get(o.get("receiver"), o.get("receiver")),
               "lugar": names.get(o.get("target_place") or o.get("place"), o.get("target_place") or o.get("place")),
               "errou": o.get("wrong", False),
               "respostas": {k: sum(1 for r in o["responses"].values() if r["kind"] == k)
                             for k in ("aceita", "atrasa", "resiste")},
               "construiram": [names.get(b, b) for b in o.get("builders", [])]}
              for o in world.creator.orders[-10:]] if world.creator else []
    return {
        "hora": world.clock.iso(), "periodo": world.clock.period_name(), "noite": world.clock.is_night(),
        "clima": world.weather.label, "tensao": world.director.tension, "velocidade": world.speed,
        "pausado": world.paused, "populacao": len(lifecycle.living(world)),
        "mortos": sorted(names.get(c, c) for c, st in world.states.items() if not st.alive),
        "nevoa": sorted(names.get(p, p) for p in world.blocked_places),
        "criaturas": [c.get("kind") for c in snap.get("creatures", [])],
        "ordens": orders,
        "decretos": [{"acao": d["action"], "modo": d["mode"], "ate": world.iso_of(d["until"])}
                     for d in (world.creator.decrees if world.creator else [])],
        "assuntos": [{"assunto": t["kind"], "sobre": names.get(t["subject"], t["subject"]),
                      "ate": world.iso_of(t["until"])} for t in (world.creator.topics if world.creator else [])],
        "presenca": presence_mod.summary(world),
        "llm": world.llm.summary() if world.llm is not None else {"ativo": False},
        "ticks": world.ticks,
    }


def character_sheet(world: "World", cid: str) -> dict:
    """A ficha viva (`quem <id>`): necessidades, humor, ação, plano, memórias, relações, última decisão."""
    names = world.names()
    char = world.data.characters[cid]
    st = world.states[cid]
    mems = sorted(world.memories.of(cid), key=lambda m: -m.intensity)[:12]
    memories = []
    for m in mems:
        phrase = world.memories.phrase(m, "lembranca") or m.kind
        memories.append({"tipo": m.kind, "frase": world_render(world, phrase), "intensidade": round(m.intensity),
                         "sentimento": m.sentiment, "permanente": m.permanent, "quando": m.ts,
                         "ouviu_de": names.get(m.heard_from, m.heard_from) if m.heard_from else None})
    rels = []
    for other in world.states:
        if other == cid:
            continue
        aff = world.affinity(cid, other)
        rels.append((aff, other))
    rels.sort()

    def rel(aff, other):
        return {"id": other, "nome": names.get(other, other), "afinidade": round(aff, 1),
                "inicial": world.relations.initial(cid, other)}
    act = st.activity
    plan = st.plan
    goals = [g for g in world.goals if g["who"] in (None, cid) and g["start"] <= world.now_minutes() < g["end"]]
    return {
        "id": cid, "nome": char.name, "vivo": st.alive, "pronome": char.pronoun,
        "profissao": char.profession, "tracos": world.traits_of(cid), "tracos_ganhos": list(st.extra_traits),
        "faccao": st.faction, "lugar": st.place, "lugar_nome": names.get(st.place, st.place),
        "acao": act.action if act else None, "acao_desde_min": round(act.elapsed) if act else None,
        "alvo": act.target if act else None,
        "plano": {"acao": plan.action, "destino": plan.place, "passos": len(plan.steps)} if plan else None,
        "necessidades": {k: round(v, 1) for k, v in st.needs.items()},
        "humor": mood(world.data, st.needs),
        "preso": st.jailed_until is not None, "no_limbo": st.away, "conjuge": st.spouse,
        "luto": round(lifecycle.grief_level(world, cid), 2),
        "memorias": memories,
        "gosta_mais": [rel(a, o) for a, o in reversed(rels[-5:])],
        "gosta_menos": [rel(a, o) for a, o in rels[:5]],
        "objetivos": [{"acao": g["action"], "lugar": g["place"], "bonus": round(g["bonus"], 2), "fonte": g["source"]}
                      for g in goals[:10]],
        "ultima_decisao": st.last_explanation,
    }


def world_render(world: "World", text: str) -> str:
    from sim.text import render

    return render(text, world.names())
