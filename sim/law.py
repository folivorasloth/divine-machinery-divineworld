"""Leis e punição (seção 11 de docs/arquitetura.md).

Infrações (`world.yaml > leis.infracoes`: pichar, roubar, barulho, brigar,
quebrar, baderna...) chegam ao Fiscal de três jeitos:

- **flagrante**: ele está acordado no lugar quando a ação começa (ou chega e
  ela ainda está acontecendo);
- **assinatura**: a pichação fica assinada na estrutura; quando o Fiscal passa
  pelo lugar, descobre quem foi;
- **denúncia**: alguém conta para ele (ação `denunciar`) ou ele ouve numa
  fofoca — que pode ter chegado torta, e aí cai na pessoa errada.

Cada infração soma `gravidade` em pontos para o infrator (que somem devagar:
`pontos_somem_por_dia`). Pontos abaixo de `pontos_para_prisao`: advertência.
A partir disso: prisão por `limites.horas_de_prisao`. A partir de
`pontos_para_limbo`: o Limbo por `limites.dias_no_limbo` (some das telas e
volta "estranho", com um traço novo sorteado de `traits.yaml`).

Se o infrator não está ali, o Fiscal ganha um mandado e vai atrás dele (ação
`prender`, com `ir_atras`). O infrator pode fugir (falha da ação) e começa uma
perseguição.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World

HOW_SITUATION = {"flagrante": "infracao_flagrante", "assinatura": "infracao_assinatura",
                 "denuncia": "infracao_denuncia"}


class Law:
    def __init__(self) -> None:
        self.points: dict[str, float] = {}
        # infrator -> {"infraction", "until" (minuto), "how", "by"}
        self.warrants: dict[str, dict] = {}
        # "infrator:infração" -> minuto do último registro (reincidência)
        self.last: dict[str, float] = {}

    def to_json(self) -> dict:
        return {"points": self.points, "warrants": self.warrants, "last": self.last}

    def load(self, raw: dict) -> None:
        self.points = dict(raw.get("points", {}))
        self.warrants = dict(raw.get("warrants", {}))
        self.last = dict(raw.get("last", {}))


def enforcers(world: "World") -> list[str]:
    prof = world.data.world.law.enforcer_profession
    return [cid for cid, st in world.states.items()
            if st.alive and not st.frozen and not st.away and st.jailed_until is None
            and world.data.characters[cid].profession == prof]


def is_enforcer(world: "World", cid: str) -> bool:
    return world.data.characters[cid].profession == world.data.world.law.enforcer_profession


def watching(world: "World", fiscal: str, place: str) -> bool:
    """O Fiscal está acordado, parado, neste lugar?"""
    st = world.states[fiscal]
    return st.place == place and not st.moving and not world.is_asleep(fiscal) and not st.away


def register(world: "World", fiscal: str, offender: str, infraction: str, place: str, how: str,
             reporter: str | None = None) -> str | None:
    """Registra a infração. Devolve o veredito: advertencia | prisao | limbo (ou None)."""
    cfg = world.data.world.law
    inf = cfg.infractions.get(infraction)
    off = world.states.get(offender)
    if inf is None or off is None or offender == fiscal or not off.alive or off.away or off.jailed_until is not None:
        return None
    if inf.hours and not any(w.contains(world.clock.minute_of_day()) for w in inf.hours):
        return None
    law = world.law
    key = f"{offender}:{infraction}"
    now = world.now_minutes()
    if now - law.last.get(key, -1e12) < cfg.repeat_hours * 60:
        return None
    law.last[key] = now
    law.points[offender] = law.points.get(offender, 0.0) + inf.severity
    points = law.points[offender]
    verdict = "limbo" if points >= cfg.limbo_points else "prisao" if points >= cfg.prison_points else "advertencia"
    extra = {"infracao": inf.name}
    if reporter:
        extra["terceiro"] = reporter
    world.say(fiscal, HOW_SITUATION[how], target=offender, place=world.states[fiscal].place, event_type="infraction",
              extra=extra, tags=["briga"], importance=1,
              data={"infraction": infraction, "offender": offender, "how": how, "reporter": reporter,
                    "points": round(points, 1), "verdict": verdict},
              fallback="{eu} anota {infracao} de {outro} no bloquinho.")
    world.change_affinity(offender, fiscal, -5)
    off.needs["raiva"] = min(100.0, off.needs.get("raiva", 0) + 10)
    if verdict == "advertencia":
        if watching(world, fiscal, off.place):
            world.say(fiscal, "advertencia", target=offender, place=off.place, event_type="infraction",
                      extra=extra, tags=["briga"], data={"infraction": infraction, "offender": offender,
                                                          "warning": True},
                      fallback="{eu} dá uma advertência para {outro}.")
        return verdict
    if watching(world, fiscal, off.place) and not off.moving:
        arrest(world, fiscal, offender, infraction)
    else:
        law.warrants[offender] = {"infraction": infraction, "until": world.now_minutes() + cfg.warrant_hours * 60,
                                  "how": how, "by": fiscal}
    return verdict


def arrest(world: "World", fiscal: str, offender: str, infraction: str | None = None) -> None:
    cfg = world.data.world
    law = world.law
    warrant = law.warrants.pop(offender, None)
    infraction = infraction or (warrant or {}).get("infraction")
    st = world.states[offender]
    world.interrupt(offender)
    points = law.points.get(offender, 0.0)
    inf = cfg.law.infractions.get(infraction) if infraction else None
    extra = {"infracao": inf.name if inf else "infração"}
    if points >= cfg.law.limbo_points:
        law.points[offender] = 0.0
        st.limbo_until = world.now_minutes() + cfg.limits.limbo_days * 1440
        origin = st.place
        world.say(fiscal, "limbo", target=offender, place=origin, event_type="limbo_in", extra=extra,
                  tags=["briga", "misterio"], importance=2,
                  data={"offender": offender, "infraction": infraction, "until_days": cfg.limits.limbo_days},
                  fallback="{eu} pede o Limbo para {outro}. {outro} some num clarão branco.")
        st.place = cfg.law.limbo
        st.plan, st.activity = None, None
        world.remember_scene("limbo", subject=fiscal, object=offender, place=origin)
        return
    st.jailed_until = world.now_minutes() + cfg.limits.prison_hours * 60
    world.say(fiscal, "prisao", target=offender, place=st.place, event_type="arrest", extra=extra,
              tags=["briga"], importance=2,
              data={"offender": offender, "infraction": infraction, "hours": cfg.limits.prison_hours},
              fallback="{eu} apita e leva {outro} para {@prison}.")
    world.remember_scene("prisao", subject=fiscal, object=offender, place=st.place)


def daily_decay(world: "World", hours: float) -> None:
    rate = world.data.world.law.points_decay_per_day * hours / 24
    for cid in list(world.law.points):
        world.law.points[cid] = max(0.0, world.law.points[cid] - rate)
        if world.law.points[cid] == 0:
            del world.law.points[cid]
    now = world.now_minutes()
    for cid in [c for c, w in world.law.warrants.items() if w["until"] <= now]:
        del world.law.warrants[cid]
    keep = world.data.world.law.repeat_hours * 60
    world.law.last = {k: v for k, v in world.law.last.items() if now - v < keep}


def best_report(world: "World", cid: str) -> tuple[object | None, float]:
    """A memória de infração (de outra pessoa) mais forte que `cid` ainda não contou ao Fiscal."""
    kinds = world.data.world.memory.kinds
    best, value = None, 0.0
    for m in world.memories.of(cid):
        k = kinds.get(m.kind)
        if not k or not k.infraction or m.reported or not m.subject or m.subject == cid:
            continue
        sub = world.states.get(m.subject)
        if sub is None or sub.jailed_until is not None or sub.away or is_enforcer(world, m.subject):
            continue
        if m.intensity > value:
            best, value = m, m.intensity
    return best, value


def report(world: "World", reporter: str, fiscal: str) -> bool:
    """`reporter` conta ao Fiscal a infração mais forte que lembra."""
    mem, _v = best_report(world, reporter)
    if mem is None:
        return False
    mem.reported = True
    kind = world.data.world.memory.kinds[mem.kind]
    world.remember(fiscal, mem.kind, subject=mem.subject, object=mem.object, place=mem.place,
                   factor=0.8, heard_from=reporter, distorted=mem.distorted, detail=mem.detail)
    register(world, fiscal, mem.subject, kind.infraction, world.states[fiscal].place, "denuncia", reporter=reporter)
    return True


def check_releases(world: "World") -> None:
    now = world.now_minutes()
    cfg = world.data.world
    for cid in sorted(world.states):
        st = world.states[cid]
        if st.jailed_until is not None and now >= st.jailed_until:
            st.jailed_until = None
            world.narrate(cid, "solto", place=st.place, event_type="released", tags=["briga"], importance=1,
                          fallback="{eu} sai da prisão, de cabeça baixa.")
        if st.limbo_until is not None and now >= st.limbo_until:
            st.limbo_until = None
            st.place = cfg.law.limbo_return
            trait = world.draw_new_trait(cid)
            extra = {}
            if trait:
                st.extra_traits.append(trait)
                extra["traco"] = world.data.traits[trait].name.lower()
            world.narrate(cid, "volta_do_limbo", place=st.place, event_type="limbo_out", tags=["misterio"],
                          importance=2, extra=extra, data={"new_trait": trait},
                          fallback="{eu} volta do Limbo. Está diferente.")
