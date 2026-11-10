"""Facções: a Igreja (Padre) e a Seita (Médium) disputam fiéis.

Quem é de qual facção fica em `CharacterState.faction` (começa pelo campo
`faccao` do YAML; os líderes de `world.yaml > faccoes` sempre são da sua).
A disputa é pela afinidade com os líderes:

- ir à missa / ao ritual (`efeitos.afinidade_com`) e ser recrutado (ação com
  `especial: recrutar`) sobem a afinidade com o líder;
- de hora em hora (e depois de cada recrutamento) o mundo confere: quem passou
  de `afinidade_para_entrar` com um líder, e gosta mais dele do que dos líderes
  rivais, entra (ou troca de lado); quem caiu abaixo de `afinidade_para_sair`
  com o próprio líder, sai.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World


def init_membership(world: "World") -> None:
    for fid, fac in world.data.world.factions.items():
        if fac.leader in world.states:
            world.states[fac.leader].faction = fid


def leaders(world: "World") -> set[str]:
    return {f.leader for f in world.data.world.factions.values()}


def check(world: "World", cid: str) -> None:
    factions = world.data.world.factions
    st = world.states[cid]
    if not factions or cid in leaders(world) or not st.alive or st.frozen or st.away:
        return
    aff = {fid: world.affinity(cid, f.leader) for fid, f in factions.items() if f.leader in world.states
           and world.states[f.leader].alive}
    current = st.faction
    if current and current in aff and aff[current] < factions[current].leave_affinity:
        st.faction = None
        world.narrate(cid, "sai_da_faccao", place=st.place, event_type="faction", tags=["seita", "igreja"],
                      importance=1, extra={"faccao": factions[current].name},
                      data={"faction": current, "change": "leave"}, fallback="{eu} larga {faccao}.")
        current = None
    best = None
    for fid in sorted(aff):
        if fid == current:
            continue
        others = [v for f, v in aff.items() if f != fid]
        if aff[fid] >= factions[fid].join_affinity and all(aff[fid] > v for v in others):
            if best is None or aff[fid] > aff[best]:
                best = fid
    if best and (current is None or aff[best] > aff[current]):
        old = current
        st.faction = best
        leader = factions[best].leader
        world.narrate(cid, "entra_na_faccao", place=st.place, event_type="faction", tags=["seita", "igreja"],
                      importance=2, extra={"faccao": factions[best].name}, target=leader,
                      data={"faction": best, "change": "join", "from": old},
                      fallback="{eu} agora é de {faccao}.")
        world.remember_scene("conversao", subject=cid, object=leader, place=st.place,
                             detail=factions[best].name)


def check_all(world: "World") -> None:
    for cid in sorted(world.states):
        check(world, cid)
