"""Recarregar `data/` sem reiniciar o mundo (Fase 6) e a cópia da última versão válida.

    python -m tools.cli recarregar        (ou POST /api/commands {"cmd": "recarregar"},
                                           ou "recarregar" no tópico MQTT world/commands)

Como funciona (`reload_world`), sempre no thread da simulação:

1. Lê e valida `data/` de novo (o mesmo `load_data` do `tools.validate`).
2. **Com erro:** nada muda. O mundo continua com a versão que já estava na
   memória e publica um aviso `system` no Chat do Mundo com os primeiros erros
   (o comando responde `ok: false` com a lista).
3. **Sem erro:** troca o `WorldData` do mundo pelo novo e acerta o estado vivo:
   - quem já existia continua onde está, com necessidades, memórias,
     relações (afinidade viva), ação em andamento, prisão, luto...;
   - nome, aparência, traços, rotina, falas, pesos de ações, eventos e quase
     todo o `world.yaml` passam a valer no próximo tick;
   - personagem com arquivo novo entra em casa (como um morador novo);
   - personagem cujo arquivo SUMIU continua com a versão antiga (aviso): para
     tirar alguém do mundo, pare o servidor (aí ele fica "congelado" no banco);
   - ações/eventos/criaturas que deixaram de existir: quem estava fazendo
     para, objetivos e criaturas daquele tipo somem;
   - sucessões (o Adolescente que virou Médium) são reaplicadas por cima.
4. Publica `data_reloaded` (o servidor manda um `hello` novo para cada tela:
   o 3D redesenha com os nomes e as cores novas) e salva.

O que NÃO recarrega (precisa reiniciar): `mqtt`, `servidor`, `persistencia`,
`ollama` (endereço/modelo) e o `relogio` (fuso e passo). O comando avisa.

Última versão válida (`save_valid_copy`/`valid_copy_dir`): toda vez que os dados
carregam sem erro no servidor, uma cópia de `data/` (sem os nascidos) vai para
`var/data_valido/`. Se o servidor religar (reinício do homelab) e o YAML estiver
com erro, ele sobe com essa cópia e avisa — e o `recarregar` volta a ler o
`data/` de verdade assim que o João corrigir.
"""

from __future__ import annotations

import dataclasses
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from sim import lifecycle
from sim.loader import WorldData, load_data
from sim.structures import Structure

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World

log = logging.getLogger("sim.reload")

# seções do world.yaml lidas só ao ligar (mudar exige reiniciar o servidor)
RESTART_SECTIONS = {"mqtt": "mqtt", "server": "servidor", "storage": "persistencia", "ollama": "ollama"}
MAX_ERRORS_SHOWN = 8


def reload_world(world: "World", data_dir: str | Path | None = None) -> dict:
    root = Path(data_dir or world.data_dir)
    new, report = load_data(root)
    if new is None or not report.ok:
        errors = [str(i) for i in report.errors][:MAX_ERRORS_SHOWN]
        more = len(report.errors) - len(errors)
        text = (f"recarregar: {len(report.errors)} erro(s) nos arquivos de data/. Nada mudou: o mundo "
                f"continua com a última versão válida. Corrija e rode recarregar de novo "
                f"(python -m tools.validate mostra tudo). Primeiro erro: {errors[0] if errors else '?'}")
        world.emit("system", text, tags=["sistema"], importance=2,
                   data={"cmd": "recarregar", "ok": False, "errors": errors})
        log.warning("recarregar falhou (%d erros); mantida a versão anterior", len(report.errors))
        return {"ok": False, "message": "erros nos YAML; mantida a versão anterior",
                "errors": errors, "more_errors": max(0, more)}
    summary = apply_data(world, new)
    summary["warnings"] = [str(i) for i in report.warnings][:MAX_ERRORS_SHOWN]
    return {"ok": True, **summary}


def apply_data(world: "World", new: WorldData) -> dict:
    """Troca os dados do mundo por `new` (já validado) sem perder o estado vivo."""
    old = world.data
    new = dataclasses.replace(new, characters=dict(new.characters))
    old_names = {cid: c.name for cid, c in old.characters.items()}
    old_place_names = {pid: p.name for pid, p in old.places.items()}

    # quem sumiu do YAML continua com a definição antiga (nunca apagar alguém vivo por engano)
    kept_old = []
    for cid, char in old.characters.items():
        if cid not in new.characters and cid in world.states:
            new.characters[cid] = char
            kept_old.append(cid)
    # quem está "congelado" no banco (sumiu do YAML antes de ligar) e ganhou o arquivo de volta só
    # volta ao reiniciar: o estado dele está nas linhas congeladas, não na memória
    frozen_back = sorted(cid for cid in new.characters if cid not in world.states and cid in world.frozen_rows)
    for cid in frozen_back:
        del new.characters[cid]
    added = sorted(cid for cid in new.characters if cid not in world.states)

    world.data = new
    world.relations.data = new
    world.structures.data = new
    world.memories.cfg = new.world.memory
    world.weather.cfg = new.world.weather
    world.director.watched = set(new.world.director.event_weights)
    # estruturas novas nos lugares (as que sumiram ficam no banco, sem efeito)
    for pid, place in new.places.items():
        for sdef in place.structures:
            if sdef.id not in world.structures.items:
                world.structures.items[sdef.id] = Structure(id=sdef.id, place=pid)

    # sucessões em cima da ficha nova (profissão, local de trabalho, rotina do papel)
    lifecycle.apply_all_overrides(world)

    stopped = []
    for cid, st in world.states.items():
        char = new.characters[cid]
        st.extra_traits = [t for t in st.extra_traits if t in new.traits]
        if st.place not in new.places:
            st.place, st.plan, st.activity = char.home, None, None
        if st.activity and st.activity.action not in new.actions and st.activity.action != "_parado":
            st.activity = None
            stopped.append(cid)
        if st.plan and (st.plan.action not in new.actions or st.plan.place not in new.places
                        or any(step.to not in new.places for step in st.plan.steps)):
            st.plan = None
        for nid, value in _initial_needs(world, char).items():
            st.needs.setdefault(nid, value)
        if st.alive and not st.activity and not st.plan:
            st.pending_review = True
    for cid in added:
        st = world.new_state(cid)
        world.states[cid] = st
    world.goals = [g for g in world.goals if g.get("action") in new.actions]
    world.creatures.active = [c for c in world.creatures.active if c.kind in new.creatures]
    world.social.instances = [i for i in world.social.instances if i.kind in new.social_events]

    world._mult_cache = {}
    for cid, char in new.characters.items():
        world.refresh_review_minutes(cid)
    world.refresh_blocked()
    from sim import factions as factions_mod

    factions_mod.init_membership(world)

    renamed = [{"id": cid, "old": old_names[cid], "new": c.name}
               for cid, c in new.characters.items() if cid in old_names and old_names[cid] != c.name]
    renamed += [{"id": pid, "old": old_place_names[pid], "new": p.name}
                for pid, p in new.places.items() if pid in old_place_names and old_place_names[pid] != p.name]
    restart = [yaml_key for attr, yaml_key in RESTART_SECTIONS.items()
               if getattr(old.world, attr) != getattr(new.world, attr)]
    if old.world.clock.timezone != new.world.clock.timezone or old.world.clock.step_minutes != new.world.clock.step_minutes:
        restart.append("relogio (fuso/passo)")

    parts = []
    if renamed:
        parts.append("; ".join(f'{r["old"]} agora se chama "{r["new"]}"' for r in renamed[:6])
                     + (f" (e mais {len(renamed) - 6})" if len(renamed) > 6 else ""))
    if added:
        parts.append("chegou: " + ", ".join(f"{{@{cid}}}" for cid in added))
    if kept_old:
        parts.append("sem arquivo (continuam com a versão antiga): " + ", ".join(kept_old))
    if frozen_back:
        restart.append("volta de " + ", ".join(frozen_back))
    if restart:
        parts.append("só vale depois de reiniciar: " + ", ".join(restart))
    text = "Os dados do mundo foram recarregados." + (" " + ". ".join(parts) + "." if parts else "")
    summary = {"renamed": renamed, "added": added, "kept_old": kept_old, "stopped": stopped,
               "restart_needed": restart, "characters": len(new.characters), "places": len(new.places),
               "actions": len(new.actions), "lines": sum(len(v) for v in new.lines.values())}
    world.save()
    world._update_snapshot()  # os nomes novos já valem para a API e para o hello das telas
    world.emit("data_reloaded", text, actors=added, tags=["sistema"], importance=1, data=summary)
    log.info("dados recarregados: %s", text)
    return summary


def _initial_needs(world: "World", char) -> dict:
    from sim import needs as needs_mod

    return needs_mod.initial_needs(world.data, char)


# ------------------------------------------------------- última versão válida
def valid_copy_dir(var_dir: str | Path) -> Path:
    return Path(var_dir) / "data_valido"


def save_valid_copy(data: WorldData, var_dir: str | Path) -> Path | None:
    """Copia `data/` (que acabou de carregar sem erro) para `var/data_valido/`.
    Os nascidos ficam de fora (a pasta deles é sempre a de verdade)."""
    dest = valid_copy_dir(var_dir)
    src = Path(data.root).resolve()
    born = Path(data.born_dir).resolve() if data.born_dir else None
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        shutil.rmtree(tmp, ignore_errors=True)

        def ignore(folder, names):
            return [n for n in names if born is not None and (Path(folder) / n).resolve() == born]

        shutil.copytree(src, tmp, ignore=ignore)
        shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)
        return dest
    except OSError as exc:  # disco cheio, sem permissão: não impede o mundo de rodar
        log.warning("não consegui guardar a cópia válida de data/ em %s: %s", dest, exc)
        shutil.rmtree(tmp, ignore_errors=True)
        return None
