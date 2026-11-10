"""Carrega e valida tudo que está em `data/`.

Uso:
    from sim.loader import load_data
    data, report = load_data("data")
    if not report.ok:
        print(report.format())

O carregador nunca para no primeiro erro: junta todos os problemas num
`Report`, com mensagens em português que dizem o arquivo, o campo e o que
fazer. Erros impedem o mundo de rodar; avisos só chamam a atenção.

Regras de leitura:
- Arquivos que começam com `_` (ex.: `_MODELO.yaml`) são ignorados.
- `data/characters/` é lido com subpastas (os nascidos vão para `born/`).
- Fase 3: a pasta dos nascidos é `vida.pasta_nascidos` do world.yaml (relativa
  a `data/`), ou a variável de ambiente `DW_BORN_DIR` (lida SEMPRE do ambiente
  real, mesmo nos testes: é assim que testes e simulações de teste gravam os
  nascidos numa pasta temporária sem sujar o repositório). Se ela estiver fora
  de `data/characters/`, também é lida.
- No `world.yaml`, textos como `${MQTT_HOST:-mqtt.local}` são trocados pela
  variável de ambiente (ou pelo padrão depois de `:-`). Assim nenhum IP ou
  senha precisa ficar no repositório.
"""

from __future__ import annotations

import difflib
import os
import re
import typing
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from sim import curves, text
from sim.schemas import (
    LawConfig,
    Action,
    ActionsFile,
    Character,
    EventsFile,
    LinesFile,
    LineTemplate,
    Place,
    Profession,
    Trait,
    TraitsFile,
    Visual,
    WorldConfig,
    WorldEvent,
    SocialEventDef,
    CreatureDef,
    CreatorConfig,
)

# --------------------------------------------------------------------------
# Relatório de problemas
# --------------------------------------------------------------------------


@dataclass
class Issue:
    level: str  # "erro" | "aviso"
    file: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.file}: {self.message}"


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    def error(self, file: str, message: str) -> None:
        self.issues.append(Issue("erro", file, message))

    def warn(self, file: str, message: str) -> None:
        self.issues.append(Issue("aviso", file, message))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "erro"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "aviso"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def format(self) -> str:
        return "\n".join(str(i) for i in self.errors + self.warnings)


class DataError(Exception):
    """Lançada por `load_data_or_raise` quando há erros nos dados."""

    def __init__(self, report: Report):
        super().__init__("Erros nos dados do mundo:\n" + report.format())
        self.report = report


# --------------------------------------------------------------------------
# Dados carregados
# --------------------------------------------------------------------------


@dataclass
class Edge:
    to: str
    kind: str  # "caminho" | "tunel"
    minutes: float


@dataclass
class WorldData:
    root: Path
    world: WorldConfig
    places: dict[str, Place]
    characters: dict[str, Character]
    actions: dict[str, Action]
    traits: dict[str, Trait]
    professions: dict[str, Profession]
    traits_file: TraitsFile
    lines: dict[str, list[LineTemplate]]  # situação -> templates (todos os arquivos juntos)
    events: dict[str, WorldEvent]
    graph: dict[str, list[Edge]]  # grafo NÃO direcionado dos lugares
    source_files: dict[str, str] = field(default_factory=dict)  # id -> arquivo de origem
    social_events: dict[str, SocialEventDef] = field(default_factory=dict)  # Fase 2
    creatures: dict[str, CreatureDef] = field(default_factory=dict)  # Fase 3
    creator: CreatorConfig | None = None  # Fase 4 (data/events/criador.yaml)
    creator_file: str = ""
    # Fase 3: onde os nascidos são gravados (data/characters/born, ou DW_BORN_DIR)
    born_dir: Path | None = None

    def names(self) -> dict[str, str]:
        """id -> nome atual, para personagens, lugares e estruturas (usado por sim.text.render)."""
        result = {pid: p.name for pid, p in self.places.items()}
        for p in self.places.values():
            result.update({s.id: s.name for s in p.structures})
        result.update({cid: c.name for cid, c in self.characters.items()})
        return result

    def all_traits(self, char_id: str, extra: list[str] | tuple = ()) -> list[str]:
        """Traços do YAML + os ganhos em vida (Limbo, Fase 3: ressurreição)."""
        return list(self.characters[char_id].traits) + [t for t in extra if t not in self.characters[char_id].traits]

    def name_of(self, some_id: str) -> str:
        return self.names().get(some_id, some_id)

    def screen_of(self, place_id: str) -> str | None:
        for screen in self.world.screens:
            if place_id in screen.places:
                return screen.id
        return None

    def affinity(self, a: str, b: str) -> int:
        """Afinidade INICIAL de a com b (vinda do YAML). A afinidade viva fica no SQLite."""
        char = self.characters[a]
        for rel in char.relations:
            if rel.with_ == b:
                return rel.affinity
        return char.default_affinity


# --------------------------------------------------------------------------
# Leitura de YAML e variáveis de ambiente
# --------------------------------------------------------------------------

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand_env(value: Any, environ: dict[str, str] | None = None) -> Any:
    """Troca ${VAR} e ${VAR:-padrao} em todos os textos de uma estrutura."""
    env = os.environ if environ is None else environ
    if isinstance(value, str):
        return _ENV.sub(lambda m: env.get(m.group(1)) or (m.group(2) or ""), value)
    if isinstance(value, list):
        return [expand_env(v, env) for v in value]
    if isinstance(value, dict):
        return {k: expand_env(v, env) for k, v in value.items()}
    return value


def read_yaml(path: Path, report: Report, rel: str) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            content = yaml.safe_load(fh)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = f"linha {mark.line + 1}, coluna {mark.column + 1}" if mark else "posição desconhecida"
        report.error(
            rel,
            f"erro de sintaxe YAML na {where}: {exc.problem}. "
            "Confira a indentação (use espaços, não TAB) e se textos com ':' estão entre aspas.",
        )
        return None
    except yaml.YAMLError as exc:
        report.error(rel, f"erro ao ler YAML: {exc}")
        return None
    except UnicodeDecodeError:
        report.error(rel, "o arquivo não está em UTF-8. Salve de novo como UTF-8.")
        return None
    if content is None:
        report.error(rel, "arquivo vazio")
    return content


# --------------------------------------------------------------------------
# Tradução dos erros do pydantic
# --------------------------------------------------------------------------

_PATTERN_HINTS = {
    r"^[a-z][a-z0-9_]*$": "use só letras minúsculas sem acento, números e _ (ex.: chef_wife)",
    r"^#[0-9a-fA-F]{6}$": "cor no formato #RRGGBB (ex.: \"#ff8800\", com aspas)",
}


def _loc(loc: tuple) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + str(part)
    return out or "(raiz)"


def _allowed_keys(model: type[BaseModel], loc: tuple) -> list[str]:
    """Descobre as chaves válidas no ponto do erro, para sugerir correção."""
    current: Any = model
    for part in loc[:-1]:
        if isinstance(part, int) or current is None:
            continue
        found = None
        for name, info in current.model_fields.items():
            if part in (name, info.alias):
                found = info.annotation
                break
        current = _unwrap_model(found)
    if current is None:
        return []
    return [info.alias or name for name, info in current.model_fields.items()]


def _unwrap_model(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in getattr(annotation, "__args__", ()) or ():
        found = _unwrap_model(arg)
        if found:
            return found
    return None


def translate_error(err: dict, model: type[BaseModel]) -> str:
    where = _loc(err["loc"])
    kind = err["type"]
    ctx = err.get("ctx", {}) or {}
    if kind == "missing":
        return f"{where}: campo obrigatório faltando"
    if kind == "extra_forbidden":
        key = str(err["loc"][-1])
        allowed = _allowed_keys(model, err["loc"])
        close = difflib.get_close_matches(key, allowed, n=1)
        hint = f" Você quis dizer '{close[0]}'?" if close else ""
        if allowed:
            hint += f" Campos válidos aqui: {', '.join(sorted(allowed))}."
        return f"{where}: campo desconhecido '{key}'.{hint}"
    if kind == "string_pattern_mismatch":
        hint = _PATTERN_HINTS.get(ctx.get("pattern"), f"formato esperado: {ctx.get('pattern')}")
        if "das" in where or "ate" in where:
            hint = "horário no formato HH:MM, entre aspas (ex.: \"07:30\")"
        return f"{where}: valor {err.get('input')!r} inválido — {hint}"
    if kind in ("greater_than_equal", "greater_than"):
        sign = "≥" if kind == "greater_than_equal" else ">"
        bound = ctx.get("ge", ctx.get("gt"))
        return f"{where}: deve ser {sign} {bound} (veio {err.get('input')!r})"
    if kind in ("less_than_equal", "less_than"):
        sign = "≤" if kind == "less_than_equal" else "<"
        bound = ctx.get("le", ctx.get("lt"))
        return f"{where}: deve ser {sign} {bound} (veio {err.get('input')!r})"
    if kind in ("int_parsing", "int_type", "float_parsing", "float_type", "int_from_float"):
        return f"{where}: deve ser um número (veio {err.get('input')!r})"
    if kind in ("string_type",):
        return f"{where}: deve ser um texto (veio {err.get('input')!r}). Coloque entre aspas."
    if kind in ("bool_parsing", "bool_type"):
        return f"{where}: deve ser true ou false (veio {err.get('input')!r})"
    if kind in ("list_type", "tuple_type"):
        return f"{where}: deve ser uma lista (um item por linha começando com '- ', ou [a, b])"
    if kind in ("dict_type", "model_type", "model_attributes_type"):
        return f"{where}: deve ser um bloco de campos 'chave: valor'"
    if kind == "literal_error":
        return f"{where}: valor {err.get('input')!r} inválido. Opções: {ctx.get('expected')}"
    if kind == "too_short":
        return f"{where}: precisa ter pelo menos {ctx.get('min_length')} item(ns)"
    if kind == "string_too_short":
        return f"{where}: não pode ficar vazio"
    if kind == "value_error":
        msg = str(ctx.get("error", err.get("msg", "")))
        return f"{where}: {msg}" if where != "(raiz)" else msg
    return f"{where}: {err.get('msg')}"


def validate_model(model: type[BaseModel], raw: Any, report: Report, rel: str, prefix: str = ""):
    """Valida `raw` contra `model`. Em caso de erro, registra tudo e devolve None."""
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            report.error(rel, prefix + translate_error(err, model))
        return None


# --------------------------------------------------------------------------
# Carregamento
# --------------------------------------------------------------------------


def _yaml_files(folder: Path, recursive: bool = False) -> list[Path]:
    if not folder.is_dir():
        return []
    pattern = "**/*.yaml" if recursive else "*.yaml"
    files = [p for p in folder.glob(pattern) if not p.name.startswith("_")]
    files += [p for p in folder.glob(pattern.replace("yaml", "yml")) if not p.name.startswith("_")]
    return sorted(files)


def load_data(data_dir: str | Path = "data", environ: dict[str, str] | None = None):
    """Lê e valida `data/`. Devolve (WorldData ou None, Report)."""
    root = Path(data_dir)
    report = Report()

    def rel(path: Path) -> str:
        try:
            return str(path.relative_to(root.parent))
        except ValueError:
            return str(path)

    if not root.is_dir():
        report.error(str(root), "pasta de dados não encontrada")
        return None, report

    # world.yaml -------------------------------------------------------------
    world = None
    world_path = root / "world.yaml"
    if not world_path.exists():
        report.error(rel(world_path), "arquivo obrigatório não encontrado")
    else:
        raw = read_yaml(world_path, report, rel(world_path))
        if raw is not None:
            world = validate_model(WorldConfig, expand_env(raw, environ), report, rel(world_path))

    source: dict[str, str] = {}
    # ids de itens que existem mas têm erro: não repetimos "não existe" para eles
    broken: set[str] = set()

    def mark_broken(raw) -> None:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            broken.add(raw["id"])

    def register(kind: str, items: dict, obj, file: str) -> None:
        if obj.id in items:
            report.error(file, f"{kind} com id '{obj.id}' repetido (já existe em {source[kind + obj.id]})")
            return
        items[obj.id] = obj
        source[kind + obj.id] = file

    # places/ ------------------------------------------------------------------
    places: dict[str, Place] = {}
    for path in _yaml_files(root / "places"):
        raw = read_yaml(path, report, rel(path))
        if raw is None:
            continue
        place = validate_model(Place, raw, report, rel(path))
        if not place:
            mark_broken(raw)
        if place:
            register("lugar", places, place, rel(path))
            if place.id != path.stem:
                report.warn(rel(path), f"o id '{place.id}' é diferente do nome do arquivo ('{path.stem}')")

    # characters/ (com subpastas) -------------------------------------------
    characters: dict[str, Character] = {}
    born_dir = born_dir_for(root, world)
    char_files = _yaml_files(root / "characters", recursive=True)
    try:
        born_dir.resolve().relative_to((root / "characters").resolve())
    except ValueError:  # a pasta dos nascidos está fora de data/characters: lê também
        char_files += _yaml_files(born_dir)
    for path in char_files:
        raw = read_yaml(path, report, rel(path))
        if raw is None:
            continue
        char = validate_model(Character, raw, report, rel(path))
        if not char:
            mark_broken(raw)
        if char:
            register("personagem", characters, char, rel(path))
            if char.id != path.stem:
                report.warn(rel(path), f"o id '{char.id}' é diferente do nome do arquivo ('{path.stem}')")

    # actions/ -----------------------------------------------------------------
    actions: dict[str, Action] = {}
    for path in _yaml_files(root / "actions"):
        raw = read_yaml(path, report, rel(path))
        if raw is None:
            continue
        container = validate_model(ActionsFile, raw, report, rel(path))
        if not container:
            continue
        for index, item in enumerate(container.actions):
            label = f"ação '{item.get('id', index)}': " if isinstance(item, dict) else f"acoes[{index}]: "
            action = validate_model(Action, item, report, rel(path), prefix=label)
            if not action:
                mark_broken(item)
            if action:
                register("ação", actions, action, rel(path))

    # traits.yaml --------------------------------------------------------------
    traits: dict[str, Trait] = {}
    professions: dict[str, Profession] = {}
    traits_file = None
    traits_path = root / "traits.yaml"
    if not traits_path.exists():
        report.error(rel(traits_path), "arquivo obrigatório não encontrado")
    else:
        raw = read_yaml(traits_path, report, rel(traits_path))
        if raw is not None:
            traits_file = validate_model(TraitsFile, raw, report, rel(traits_path))
        if traits_file:
            for trait in traits_file.traits:
                register("traço", traits, trait, rel(traits_path))
            for prof in traits_file.professions:
                register("profissão", professions, prof, rel(traits_path))

    # lines/ -------------------------------------------------------------------
    lines: dict[str, list[LineTemplate]] = {}
    line_sources: list[tuple[str, str, LineTemplate]] = []  # (arquivo, situação, fala)
    for path in _yaml_files(root / "lines", recursive=True):
        raw = read_yaml(path, report, rel(path))
        if raw is None:
            continue
        lf = validate_model(LinesFile, raw, report, rel(path))
        if lf:
            for situation, templates in lf.situations.items():
                lines.setdefault(situation, []).extend(templates)
                line_sources += [(rel(path), situation, t) for t in templates]

    # events/ ------------------------------------------------------------------
    events: dict[str, WorldEvent] = {}
    social_events: dict[str, SocialEventDef] = {}
    creatures: dict[str, CreatureDef] = {}
    creator: CreatorConfig | None = None
    creator_file = ""
    for path in _yaml_files(root / "events"):
        raw = read_yaml(path, report, rel(path))
        if raw is None:
            continue
        container = validate_model(EventsFile, raw, report, rel(path))
        if not container:
            continue
        for index, item in enumerate(container.events):
            label = f"evento '{item.get('id', index)}': " if isinstance(item, dict) else f"eventos[{index}]: "
            event = validate_model(WorldEvent, item, report, rel(path), prefix=label)
            if not event:
                mark_broken(item)
            if event:
                register("evento", events, event, rel(path))
        for index, item in enumerate(container.social_events):
            label = f"evento social '{item.get('id', index)}': " if isinstance(item, dict) else f"eventos_sociais[{index}]: "
            sev = validate_model(SocialEventDef, item, report, rel(path), prefix=label)
            if not sev:
                mark_broken(item)
            if sev:
                register("evento social", social_events, sev, rel(path))
        for index, item in enumerate(container.creatures):
            label = f"criatura '{item.get('id', index)}': " if isinstance(item, dict) else f"criaturas[{index}]: "
            cre = validate_model(CreatureDef, item, report, rel(path), prefix=label)
            if not cre:
                mark_broken(item)
            if cre:
                register("criatura", creatures, cre, rel(path))
        if container.creator is not None:
            if creator is not None:
                report.error(rel(path), f"'criador' já foi definido em {creator_file}: só um arquivo pode ter")
            else:
                creator = validate_model(CreatorConfig, container.creator, report, rel(path), prefix="criador: ")
                creator_file = rel(path)

    if world is None or traits_file is None:
        return None, report

    data = WorldData(
        root=root,
        world=world,
        places=places,
        characters=characters,
        actions=actions,
        traits=traits,
        professions=professions,
        traits_file=traits_file,
        lines=lines,
        events=events,
        graph={},
        source_files={k: v for k, v in source.items()},
        social_events=social_events,
        creatures=creatures,
        born_dir=born_dir,
        creator=creator,
        creator_file=creator_file,
    )
    _cross_check(data, report, source, line_sources, rel(world_path), rel(traits_path), broken)
    return data, report


def born_dir_for(root: Path, world: WorldConfig | None) -> Path:
    """Pasta onde os nascidos são gravados: DW_BORN_DIR > vida.pasta_nascidos (relativa a data/)."""
    env = os.environ.get("DW_BORN_DIR", "").strip()
    if env:
        return Path(env)
    sub = world.life.born_dir if world is not None else "characters/born"
    path = Path(sub)
    return path if path.is_absolute() else root / path


def load_data_or_raise(data_dir: str | Path = "data", environ: dict[str, str] | None = None) -> WorldData:
    data, report = load_data(data_dir, environ)
    if data is None or not report.ok:
        raise DataError(report)
    return data


# --------------------------------------------------------------------------
# Checagens entre arquivos
# --------------------------------------------------------------------------


def _cross_check(
    data: WorldData,
    report: Report,
    source: dict[str, str],
    line_sources: list[tuple[str, str, LineTemplate]],
    world_file: str,
    traits_file: str,
    broken: set[str] = frozenset(),
) -> None:
    w = data.world
    needs = set(w.needs)
    periods = {p.id for p in w.clock.periods}
    names_to_ids = {c.name.lower(): cid for cid, c in data.characters.items()}
    names_to_ids.update({p.name.lower(): pid for pid, p in data.places.items()})

    def ref(file: str, where: str, kind: str, value: str | None, valid, allow_none=False) -> bool:
        """Confere se `value` é um id válido do tipo `kind`. Sugere correções."""
        if value is None:
            return allow_none
        if value in valid:
            return True
        if value in broken:
            return False  # o próprio arquivo dele já tem um erro reportado
        hint = ""
        if value.lower() in names_to_ids:
            hint = f" Isso parece um NOME; use o id '{names_to_ids[value.lower()]}'."
        else:
            close = difflib.get_close_matches(value, list(valid), n=1)
            if close:
                hint = f" Você quis dizer '{close[0]}'?"
        report.error(file, f"{where}: {kind} '{value}' não existe.{hint}")
        return False

    # ids únicos entre personagens e lugares (os tokens {@id} dependem disso)
    for cid in data.characters:
        if cid in data.places:
            report.error(source["personagem" + cid], f"o id '{cid}' é usado por um personagem E por um lugar")

    # world.yaml ---------------------------------------------------------------
    ref(world_file, "lugar_central", "lugar", w.central_place, data.places)
    starts = [p.start for p in w.clock.periods]
    if starts != sorted(starts) or starts[0] != "00:00":
        report.error(world_file, "relogio.periodos: devem começar em \"00:00\" e estar em ordem de horário")
    seen_places: dict[str, str] = {}
    screen_ids = set()
    for i, screen in enumerate(w.screens):
        if screen.id in screen_ids:
            report.error(world_file, f"telas[{i}]: id de tela '{screen.id}' repetido")
        screen_ids.add(screen.id)
        for pid in screen.places:
            if ref(world_file, f"telas[{i}] ('{screen.id}').lugares", "lugar", pid, data.places):
                if pid in seen_places:
                    report.error(
                        world_file,
                        f"telas: o lugar '{pid}' está em duas telas ('{seen_places[pid]}' e '{screen.id}'). "
                        "Cada lugar aparece em uma tela só.",
                    )
                seen_places[pid] = screen.id
                if data.places[pid].access == "nunca":
                    report.warn(world_file, f"telas: '{pid}' é um lugar que ninguém visita (acesso: nunca)")

    # traits.yaml --------------------------------------------------------------
    for trait in data.traits.values():
        where = f"traço '{trait.id}'"
        for need in trait.effects.needs:
            ref(traits_file, f"{where}.efeitos.necessidades", "necessidade", need, needs)
        for act in trait.effects.actions:
            ref(traits_file, f"{where}.efeitos.acoes", "ação", act, data.actions)
        for opp in trait.opposites:
            ref(traits_file, f"{where}.opostos", "traço", opp, data.traits)
    valid_bodies = set(typing.get_args(Visual.model_fields["body"].annotation))
    for body in data.traits_file.appearance.bodies:
        if body not in valid_bodies:
            report.error(traits_file, f"aparencias.corpos: '{body}' inválido. Opções: {', '.join(sorted(valid_bodies))}")
    for prof in data.professions.values():
        ref(traits_file, f"profissão '{prof.id}'.local_trabalho", "lugar", prof.workplace, data.places, True)

    # places/ ------------------------------------------------------------------
    graph: dict[str, list[Edge]] = {pid: [] for pid in data.places}
    declared: dict[tuple[str, str], tuple[str, float, str]] = {}
    for pid, place in data.places.items():
        file = source["lugar" + pid]
        ref(file, "regiao", "região (definida em world.yaml > regioes)", place.region, w.regions, True)
        for act in place.actions:
            ref(file, "acoes", "ação", act, data.actions)
        for i, conn in enumerate(place.connections):
            where = f"conexoes[{i}].para"
            if conn.to == pid:
                report.error(file, f"{where}: o lugar não pode se conectar com ele mesmo")
                continue
            if not ref(file, where, "lugar", conn.to, data.places):
                continue
            key = tuple(sorted((pid, conn.to)))
            if key in declared:
                kind, minutes, other_file = declared[key]
                if (kind, minutes) != (conn.kind, conn.minutes) and other_file != file:
                    report.error(
                        file,
                        f"conexão {key[0]} <-> {key[1]} declarada diferente em {other_file} "
                        f"({kind}, {minutes} min) e aqui ({conn.kind}, {conn.minutes} min). "
                        "Declare em um lado só, ou igual nos dois.",
                    )
                continue
            declared[key] = (conn.kind, conn.minutes, file)
            graph[pid].append(Edge(conn.to, conn.kind, conn.minutes))
            graph[conn.to].append(Edge(pid, conn.kind, conn.minutes))
    data.graph = graph

    for pid, place in data.places.items():
        file = source["lugar" + pid]
        if place.access == "normal" and not graph[pid]:
            report.error(file, "lugar sem conexão: ninguém consegue chegar aqui. Adicione 'conexoes'.")
        if place.access == "nunca" and graph[pid]:
            report.warn(file, "lugar com acesso 'nunca' tem conexões; elas serão ignoradas")
    # todo lugar 'normal' precisa ser alcançável a partir do lugar central
    if w.central_place in graph:
        reach = _reachable(graph, w.central_place, data.places)
        for pid, place in data.places.items():
            if place.access == "normal" and graph[pid] and pid not in reach:
                report.error(
                    source["lugar" + pid],
                    f"lugar isolado: não há caminho daqui até '{w.central_place}' (lugar_central)",
                )
    # túneis e telas: um túnel faz sentido entre telas diferentes
    for (a, b), (kind, _minutes, file) in declared.items():
        sa, sb = data.screen_of(a), data.screen_of(b)
        if kind == "tunel" and sa and sa == sb:
            report.warn(file, f"túnel {a} <-> {b} liga dois lugares da MESMA tela ('{sa}')")
        if kind == "caminho" and sa and sb and sa != sb:
            report.warn(
                file,
                f"caminho a pé {a} <-> {b} atravessa telas ('{sa}' -> '{sb}'). "
                "Entre telas o normal é 'tipo: tunel' (para os LEDs).",
            )

    # characters/ --------------------------------------------------------------
    for cid, char in data.characters.items():
        file = source["personagem" + cid]
        for t in char.traits:
            ref(file, "tracos", "traço (definido em traits.yaml)", t, data.traits)
        ref(file, "profissao", "profissão (definida em traits.yaml > profissoes)", char.profession, data.professions)
        ref(file, "local_trabalho", "lugar", char.workplace, data.places, True)
        ref(file, "casa", "lugar", char.home, data.places)
        ref(file, "grupo", "grupo (definido em world.yaml > grupos)", char.group, w.groups, True)
        for need in char.needs:
            ref(file, "necessidades", "necessidade (definida em world.yaml)", need, needs)
        for i, block in enumerate(char.routine):
            ref(file, f"rotina[{i}].acao", "ação", block.action, data.actions)
            ref(file, f"rotina[{i}].lugar", "lugar", block.place, data.places, True)
            if block.start == block.end:
                report.error(file, f"rotina[{i}]: 'das' e 'ate' iguais ({block.start})")
        seen = set()
        for i, rel in enumerate(char.relations):
            where = f"relacoes[{i}].com"
            if rel.with_ == cid:
                report.error(file, f"{where}: um personagem não pode ter relação consigo mesmo")
            elif ref(file, where, "personagem", rel.with_, data.characters):
                if rel.with_ in seen:
                    report.error(file, f"{where}: relação com '{rel.with_}' repetida")
                seen.add(rel.with_)
        for i, heir in enumerate(char.inheritance.heirs):
            ref(file, f"heranca.herdeiros[{i}]", "personagem", heir, data.characters)

    # Fase 2: sociedade ---------------------------------------------------------
    memory_kinds = set(w.memory.kinds)
    factions = set(w.factions)
    infractions = set(w.law.infractions)
    known_ids_all = set(data.characters) | set(data.places)
    for kid, kind in w.memory.kinds.items():
        ref(world_file, f"memoria.tipos.{kid}.infracao", "infração (leis.infracoes)", kind.infraction, infractions, True)
        for key, template in (("fato", kind.fact), ("lembranca", kind.recollection)):
            for problem in text.check_template(template, known_ids_all, text.MEMORY_VARS):
                report.error(world_file, f"memoria.tipos.{kid}.{key}: {problem}")
    for fid, fac in w.factions.items():
        ref(world_file, f"faccoes.{fid}.lider", "personagem", fac.leader, data.characters)
    ref(world_file, "leis.profissao_fiscal", "profissão", w.law.enforcer_profession, data.professions)
    for key in ("prison", "limbo", "limbo_return"):
        ref(world_file, f"leis.{LawConfig.model_fields[key].alias}", "lugar", getattr(w.law, key), data.places)
    for i, aid in enumerate(w.law.prison_actions):
        ref(world_file, f"leis.acoes_na_prisao[{i}]", "ação", aid, data.actions)
    for key in ("flee_action", "chase_action"):
        ref(world_file, f"leis.{LawConfig.model_fields[key].alias}", "ação", getattr(w.law, key), data.actions)
    structure_ids: dict[str, str] = {}
    for pid, place in data.places.items():
        for st in place.structures:
            if st.id in data.characters or st.id in data.places or st.id in structure_ids:
                report.error(source["lugar" + pid], f"estruturas: id '{st.id}' repetido (já é personagem, lugar ou outra estrutura)")
            structure_ids[st.id] = pid
    for cid, char in data.characters.items():
        ref(source["personagem" + cid], "faccao", "facção (world.yaml > faccoes)", char.faction, factions, True)
    for sid, sev in data.social_events.items():
        file = source["evento social" + sid]
        where = f"evento social '{sid}'"
        ref(file, f"{where}.acao", "ação", sev.action, data.actions)
        ref(file, f"{where}.lugar", "lugar", sev.place, data.places, True)
        for c in sev.organizers.characters:
            ref(file, f"{where}.organizadores.personagens", "personagem", c, data.characters)
        for t in sev.organizers.traits:
            ref(file, f"{where}.organizadores.tracos", "traço", t, data.traits)
        for p in sev.organizers.professions:
            ref(file, f"{where}.organizadores.profissoes", "profissão", p, data.professions)
        for g in sev.organizers.groups:
            ref(file, f"{where}.organizadores.grupos", "grupo", g, w.groups)
        for f in sev.organizers.factions:
            ref(file, f"{where}.organizadores.faccoes", "facção", f, factions)
        for n in sev.desire:
            ref(file, f"{where}.vontade", "necessidade", n, needs)
        for c in sev.excluded:
            ref(file, f"{where}.excluidos", "personagem", c, data.characters)
        for key in ("memory", "failure_memory"):
            ref(file, f"{where}.{SocialEventDef.model_fields[key].alias}", "tipo de memória (world.yaml > memoria.tipos)",
                getattr(sev, key), memory_kinds, True)
        for key, templates in sev.texts.model_dump().items():
            for template in templates:
                for problem in text.check_template(template, known_ids_all):
                    report.error(file, f"{where}.textos: {problem}")
        if sev.place and sev.action in data.actions:
            act = data.actions[sev.action]
            if not act.anywhere and sev.action not in data.places[sev.place].actions:
                report.warn(file, f"{where}: o lugar '{sev.place}' não oferece a ação '{sev.action}'")

    input_ids = {
        "necessidade": needs, "personagem": set(data.characters), "facção": factions,
        "tipo de memória": memory_kinds,
    }

    # actions/ -----------------------------------------------------------------
    offered = {a for p in data.places.values() for a in p.actions}
    for aid, action in data.actions.items():
        file = source["ação" + aid]
        where = f"ação '{aid}'"
        cond = action.conditions
        for p in cond.periods:
            ref(file, f"{where}.condicoes.periodos", "período", p, periods)
        for p in cond.professions:
            ref(file, f"{where}.condicoes.profissoes", "profissão", p, data.professions)
        for t in cond.traits:
            ref(file, f"{where}.condicoes.tracos", "traço", t, data.traits)
        for c in cond.characters:
            ref(file, f"{where}.condicoes.personagens", "personagem", c, data.characters)
        for n in cond.min_needs:
            ref(file, f"{where}.condicoes.necessidades_min", "necessidade", n, needs)
        for n in list(action.effects.needs) + list(action.effects.target_needs):
            ref(file, f"{where}.efeitos", "necessidade", n, needs)
        for i, cons in enumerate(action.considerations):
            problem = _check_input(cons.input, input_ids, has_target=cond.target is not None)
            if problem:
                report.error(file, f"{where}.consideracoes[{i}].entrada: {problem}")
        if action.speech and action.speech not in data.lines:
            report.warn(file, f"{where}.fala: não há falas para a situação '{action.speech}' em data/lines/")
        if action.target_speech and action.target_speech not in data.lines:
            report.warn(file, f"{where}.fala_alvo: não há falas para a situação '{action.target_speech}' em data/lines/")
        if action.target_speech and action.kind != "social":
            report.error(file, f"{where}.fala_alvo: só faz sentido em ações 'social' (com alvo)")
        for key, template in (("narracao", action.narration), ("narracao_fim", action.narration_end)):
            if template:
                for problem in text.check_template(template, set(data.characters) | set(data.places)):
                    report.error(file, f"{where}.{key}: {problem}")
                _warn_literal_names(report, file, f"{where}.{key}", template, {c.name: cid for cid, c in data.characters.items()})
        if action.failure and action.failure.speech and action.failure.speech not in data.lines:
            report.warn(file, f"{where}.falha.fala: não há falas para a situação '{action.failure.speech}'")
        if action.failure:
            ref(file, f"{where}.falha.memoria", "tipo de memória", action.failure.memory, memory_kinds, True)
        ref(file, f"{where}.memoria", "tipo de memória (world.yaml > memoria.tipos)", action.memory, memory_kinds, True)
        ref(file, f"{where}.infracao", "infração (world.yaml > leis.infracoes)", action.infraction, infractions, True)
        ref(file, f"{where}.faccao", "facção", action.faction, factions, True)
        if action.special == "recrutar" and not action.faction:
            report.error(file, f"{where}: especial 'recrutar' precisa de 'faccao'")
        if action.observe:
            ref(file, f"{where}.observa.memoria", "tipo de memória", action.observe.memory, memory_kinds)
        for f in cond.factions:
            ref(file, f"{where}.condicoes.faccoes", "facção", f, factions)
        if cond.target:
            for c in cond.target.characters:
                ref(file, f"{where}.condicoes.alvo.personagens", "personagem", c, data.characters)
            for p in cond.target.professions:
                ref(file, f"{where}.condicoes.alvo.profissoes", "profissão", p, data.professions)
        for c in action.effects.affinity_with:
            ref(file, f"{where}.efeitos.afinidade_com", "personagem", c, data.characters)
        for t, effects in action.effects.by_trait.items():
            ref(file, f"{where}.efeitos.por_traco", "traço", t, data.traits)
            for n in effects:
                ref(file, f"{where}.efeitos.por_traco.{t}", "necessidade", n, needs)
        if action.target_reaction and ref(file, f"{where}.reacao_alvo", "ação", action.target_reaction, data.actions):
            if not data.actions[action.target_reaction].automatic:
                report.error(file, f"{where}.reacao_alvo: a ação '{action.target_reaction}' precisa ser 'automatica: true'")
        if action.seek_target and action.kind != "social":
            report.error(file, f"{where}.ir_atras: só faz sentido em ações 'social'")
        if (
            action.active
            and action.kind != "movimento"
            and not action.anywhere
            and not action.wander
            and not cond.own_place
            and aid not in offered
        ):
            report.warn(file, f"{where}: nenhum lugar oferece esta ação (adicione em 'acoes' de algum lugar)")

    # lines/ -------------------------------------------------------------------
    known_ids = set(data.characters) | set(data.places)
    char_names = {c.name: cid for cid, c in data.characters.items()}
    for file, situation, line in line_sources:
        where = f"situação '{situation}', fala \"{_short(line.text)}\""
        for problem in text.check_template(line.text, known_ids):
            report.error(file, f"{where}: {problem}")
        for c in line.characters:
            ref(file, f"{where}: personagens", "personagem", c, data.characters)
        for t in line.traits:
            ref(file, f"{where}: tracos", "traço", t, data.traits)
        for p in line.places:
            ref(file, f"{where}: lugares", "lugar", p, data.places)
        for p in line.periods:
            ref(file, f"{where}: periodos", "período", p, periods)
        for n in line.min_needs:
            ref(file, f"{where}: necessidades_min", "necessidade", n, needs)
        for m in line.memory:
            ref(file, f"{where}: memoria", "tipo de memória (world.yaml > memoria.tipos)", m, memory_kinds)
        _warn_literal_names(report, file, where, line.text, char_names)
    for cid, char in data.characters.items():
        for phrase in char.catchphrases:
            _warn_literal_names(report, source["personagem" + cid], "bordoes", phrase, char_names, skip=cid)

    # events/ ------------------------------------------------------------------
    for eid, event in data.events.items():
        file = source["evento" + eid]
        where = f"evento '{eid}'"
        for p in event.places:
            ref(file, f"{where}.lugares", "lugar", p, data.places)
        for p in event.conditions.periods:
            ref(file, f"{where}.condicoes.periodos", "período", p, periods)
        for n in event.effects.needs:
            ref(file, f"{where}.efeitos.necessidades", "necessidade", n, needs)
        if event.effects.goal:
            ref(file, f"{where}.efeitos.objetivo.acao", "ação", event.effects.goal.action, data.actions)
            ref(file, f"{where}.efeitos.objetivo.lugar", "lugar", event.effects.goal.place, data.places, True)
        for problem in text.check_template(event.text, known_ids):
            report.error(file, f"{where}.texto: {problem}")
        _warn_literal_names(report, file, f"{where}.texto", event.text, char_names)

    # Fase 3: vida, morte, clima, criaturas, diretor -------------------------
    _check_phase3(data, report, source, line_sources, world_file, traits_file, ref, needs, periods, memory_kinds,
                  known_ids)

    # Fase 4: o Criador ---------------------------------------------------------
    _check_creator(data, report, ref, memory_kinds)

    # tags usadas em ações e eventos devem ser categorias do chat conhecidas
    categories = set(w.chat_categories)
    for sid, sev in data.social_events.items():
        for tag in sev.tags:
            if tag not in categories:
                report.warn(source["evento social" + sid], f"evento social '{sid}'.tags: '{tag}' não está em world.yaml > categorias_chat")
    for aid, action in data.actions.items():
        for tag in action.tags:
            if tag not in categories:
                report.warn(source["ação" + aid], f"ação '{aid}'.tags: '{tag}' não está em world.yaml > categorias_chat")
    for eid, event in data.events.items():
        for tag in event.tags:
            if tag not in categories:
                report.warn(source["evento" + eid], f"evento '{eid}'.tags: '{tag}' não está em world.yaml > categorias_chat")


def _check_phase3(data, report, source, line_sources, world_file, traits_file, ref, needs, periods,
                  memory_kinds, known_ids) -> None:
    w = data.world
    wk = w.weather.kinds
    if wk:
        ref(world_file, "clima.clima_padrao", "tipo de clima (clima.tipos)", w.weather.fallback, wk)
        ref(world_file, "clima.clima_do_funeral", "tipo de clima (clima.tipos)", w.weather.funeral_kind, wk)
        for k in w.weather.simulated.weights:
            ref(world_file, "clima.simulado.pesos", "tipo de clima (clima.tipos)", k, wk)
    for k, eff in w.weather.effects.items():
        ref(world_file, "clima.efeitos", "tipo de clima (clima.tipos, frio ou calor)", k, set(wk) | {"frio", "calor"})
        for n in eff.needs:
            ref(world_file, f"clima.efeitos.{k}.necessidades", "necessidade", n, needs)
        for a in eff.actions:
            ref(world_file, f"clima.efeitos.{k}.acoes", "ação", a, data.actions)
    for cid_, cause in w.death.causes.items():
        where = f"morte.causas.{cid_}"
        for a in cause.actions:
            ref(world_file, f"{where}.acoes", "ação", a, data.actions)
        for p in cause.places:
            ref(world_file, f"{where}.lugares", "lugar", p, data.places)
        for t in cause.by_trait:
            ref(world_file, f"{where}.por_traco", "traço", t, data.traits)
        situation = cause.situation or f"morte_{cid_}"
        if situation not in data.lines:
            report.warn(world_file, f"{where}: não há falas para a situação '{situation}' em data/lines/")
    for key, value in (("morte.memoria", w.death.memory), ("vida.memoria_fantasma", w.life.ghost_memory),
                       ("vida.memoria_ressurreicao", w.life.resurrection_memory),
                       ("criaturas.memoria", w.creatures.memory), ("criaturas.memoria_vitoria", w.creatures.win_memory),
                       ("funeral.memoria", w.funeral.memory)):
        ref(world_file, key, "tipo de memória (memoria.tipos)", value, memory_kinds, True)
    for key, value in (("morte.lugar_do_corpo", w.death.body_place), ("funeral.local_velorio", w.funeral.wake_place),
                       ("funeral.local_enterro", w.funeral.burial_place)):
        ref(world_file, key, "lugar", value, data.places)
    for key, value in (("funeral.acao", w.funeral.action), ("sucessao.acao_assembleia", w.succession.assembly_action),
                       ("criaturas.acao_enfrentar", w.creatures.fight_action)):
        ref(world_file, key, "ação", value, data.actions)
    for p in w.funeral.leaders:
        ref(world_file, "funeral.quem_conduz", "profissão", p, data.professions)
    for n in list(w.grief.shock) + list(w.grief.rates):
        ref(world_file, "luto", "necessidade", n, needs)
    for a in w.grief.actions:
        ref(world_file, "luto.acoes", "ação", a, data.actions)
    for cid, cons in w.consequences.items():
        where = f"se_morrer.{cid}"
        ref(world_file, where, "personagem", cid, data.characters)
        for a in cons.actions:
            ref(world_file, f"{where}.acoes", "ação", a, data.actions)
        for c in list(cons.who) + list(cons.grief_factor):
            ref(world_file, f"{where}", "personagem", c, data.characters)
        if cons.goal:
            ref(world_file, f"{where}.objetivo.acao", "ação", cons.goal.action, data.actions)
            ref(world_file, f"{where}.objetivo.lugar", "lugar", cons.goal.place, data.places, True)
        if cons.text:
            for problem in text.check_template(cons.text, known_ids):
                report.error(world_file, f"{where}.texto: {problem}")
    for prof, role in w.succession.roles.items():
        where = f"sucessao.papeis.{prof}"
        ref(world_file, where, "profissão", prof, data.professions)
        for t in role.traits:
            ref(world_file, f"{where}.tracos", "traço", t, data.traits)
        ref(world_file, f"{where}.lugar", "lugar", role.place, data.places, True)
        if role.mode == "eleicao" and not role.place:
            report.error(world_file, f"{where}: modo eleicao precisa de 'lugar'")
    for p in w.director.target:
        ref(world_file, "diretor.alvo", "período", p, periods)
    birth = data.traits_file.birth
    for key, value in (("nascimento.casa", birth.home), ("nascimento.aparece_em", birth.appears_at)):
        ref(traits_file, key, "lugar", value, data.places)
    for i, block in enumerate(birth.routine):
        ref(traits_file, f"nascimento.rotina[{i}].acao", "ação", block.action, data.actions)
        ref(traits_file, f"nascimento.rotina[{i}].lugar", "lugar", block.place, data.places, True)
    for cid, char in data.characters.items():
        if char.inherited:
            ref(source["personagem" + cid], "herdou.de", "personagem", char.inherited.from_, data.characters)
    for crid, cre in data.creatures.items():
        file = source["criatura" + crid]
        where = f"criatura '{crid}'"
        for p in cre.places:
            ref(file, f"{where}.lugares", "lugar", p, data.places)
        for p in cre.periods:
            ref(file, f"{where}.periodos", "período", p, periods)
        for p in list(cre.experts) + list(cre.goal_professions):
            ref(file, f"{where}", "profissão", p, data.professions)
        for key, templates in cre.texts.model_dump().items():
            for template in templates:
                for problem in text.check_template(template, known_ids):
                    report.error(file, f"{where}.textos: {problem}")
    for eid, event in data.events.items():
        file = source["evento" + eid]
        where = f"evento '{eid}'"
        if event.effects.weather and wk:
            ref(file, f"{where}.efeitos.clima", "tipo de clima (world.yaml > clima.tipos)", event.effects.weather, wk)
        ref(file, f"{where}.efeitos.criatura", "criatura (data/events/creatures.yaml)", event.effects.creature,
            data.creatures, True)
        ref(file, f"{where}.efeitos.memoria", "tipo de memória", event.effects.memory, memory_kinds, True)
        if event.kind in ("raro", "lendario") and event.chance_per_day is None and not event.effects.special:
            report.error(file, f"{where}: evento raro/lendário precisa de 'chance_por_dia'")
    for file, situation, line in line_sources:
        for c in line.dead:
            ref(file, f"situação '{situation}': mortos", "personagem", c, data.characters)
        for p in line.professions:
            ref(file, f"situação '{situation}': profissoes", "profissão", p, data.professions)


def _check_creator(data, report, ref, memory_kinds) -> None:
    c = data.creator
    if c is None:
        return
    file = data.creator_file
    w = data.world

    def goals(where, items):
        for i, g in enumerate(items):
            ref(file, f"{where}.objetivos[{i}].acao", "ação", g.action, data.actions)
            ref(file, f"{where}.objetivos[{i}].lugar", "lugar", g.place, data.places, True)

    def situation(where, sit):
        if sit and sit not in data.lines:
            report.warn(file, f"{where}: não há falas para a situação '{sit}' em data/lines/")

    for key, ann in (("chefe", c.chief), ("medium", c.medium)):
        ref(file, f"criador.{key}.profissao", "profissão", ann.profession, data.professions)
        ref(file, f"criador.{key}.acao", "ação", ann.action, data.actions)
        situation(f"criador.{key}.fala_recebe", ann.speech_received)
        situation(f"criador.{key}.fala_confusa", ann.speech_confused)
        for t in ann.resistance.traits:
            ref(file, f"criador.{key}.resistencia.tracos", "traço", t, data.traits)
        for oid, order in ann.orders.items():
            where = f"criador.{key}.interpretacoes.{oid}"
            goals(where + ".efeitos", order.effects.goals)
            for n in order.effects.needs:
                ref(file, f"{where}.efeitos.necessidades", "necessidade", n, w.needs)
            ref(file, f"{where}.efeitos.evento_social", "evento social", order.effects.social_event,
                data.social_events, True)
            ref(file, f"{where}.efeitos.memoria", "tipo de memória", order.effects.memory, memory_kinds, True)
            ref(file, f"{where}.efeitos.assunto", "assunto (criador.assuntos)", order.effects.topic, c.topics, True)
            situation(where + ".fala", order.speech)
            if not order.words and order.confused_weight == 0:
                report.warn(file, f"{where}: sem 'palavras' e com peso_sem_entender 0: nunca acontece")
    rule = c.chief.rule
    ref(file, "criador.chefe.regra.infracao", "infração (world.yaml > leis.infracoes)", rule.infraction,
        w.law.infractions)
    for a in list(rule.aliases) + list(rule.suggestions):
        ref(file, "criador.chefe.regra", "ação", a, data.actions)
    for t in rule.obey_traits:
        ref(file, "criador.chefe.regra.obediencia_tracos", "traço", t, data.traits)
    ref(file, "criador.chefe.reuniao.acao", "ação", c.chief.meeting.action, data.actions)
    ref(file, "criador.chefe.reuniao.lugar", "lugar", c.chief.meeting.place, data.places)
    ref(file, "criador.chefe.reuniao.memoria", "tipo de memória", c.chief.meeting.memory, memory_kinds, True)
    for key in ("done_speech", "expired_speech", "resist_speech"):
        situation(f"criador.chefe.{key}", getattr(c.chief, key))
    ref(file, "criador.reviver.assunto", "assunto (criador.assuntos)", c.revive.topic, c.topics, True)
    for tid, topic in c.topics.items():
        for a in topic.actions:
            ref(file, f"criador.assuntos.{tid}.acoes", "ação", a, data.actions)
        situation(f"criador.assuntos.{tid}", topic.situation or f"assunto_{tid}")
    pr = c.presence
    ref(file, "criador.presenca.acao_olhar", "ação", pr.stare_action, data.actions)
    ref(file, "criador.presenca.memoria_aparicao", "tipo de memória", pr.apparition_memory, memory_kinds, True)
    ref(file, "criador.presenca.assunto_aparicao", "assunto", pr.apparition_topic, c.topics, True)
    ref(file, "criador.presenca.faccao_que_enlouquece", "facção", pr.faction_crazy, w.factions)
    goals("criador.presenca", pr.goals)


def _check_input(entry: str, valid: dict[str, set[str]], has_target: bool) -> str | None:
    """`valid` diz os ids válidos depois do ponto, por tipo ('necessidade' -> {fome, ...})."""
    kind = curves.input_kind(entry)
    if kind not in curves.INPUT_RANGES:
        return f"entrada '{entry}' desconhecida. Opções: {', '.join(sorted(curves.INPUT_RANGES))}"
    if kind in curves.DOTTED_INPUTS:
        what = curves.DOTTED_INPUTS[kind]
        if "." not in entry:
            return f"use '{kind}.<{what}>' (ex.: {kind}.{sorted(valid[what])[0] if valid[what] else 'x'})"
        item = entry.split(".", 1)[1]
        if item not in valid[what]:
            return f"{what} '{item}' não existe"
    elif "." in entry:
        return f"a entrada '{kind}' não leva '.<algo>'"
    if kind in curves.TARGET_INPUTS and not has_target:
        return f"a entrada '{kind}' só funciona em ações com 'condicoes.alvo'"
    return None


def _reachable(graph: dict[str, list[Edge]], start: str, places: dict[str, Place]) -> set[str]:
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for edge in graph[current]:
            if edge.to not in seen and places[edge.to].access != "nunca":
                seen.add(edge.to)
                queue.append(edge.to)
    return seen


def _warn_literal_names(report: Report, file: str, where: str, phrase: str, names: dict[str, str], skip=None):
    """Um nome escrito por extenso numa fala não acompanha uma renomeação.
    O certo é usar {@id}. Isso é só aviso: nada quebra, mas o texto fica velho."""
    for name, cid in names.items():
        if cid == skip or len(name) < 3:
            continue
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", phrase):
            report.warn(file, f"{where}: o nome '{name}' está escrito por extenso. Use {{@{cid}}} para "
                              "o texto acompanhar se o nome mudar.")


def _short(value: str, size: int = 40) -> str:
    return value if len(value) <= size else value[: size - 1] + "…"
