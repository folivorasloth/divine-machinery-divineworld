"""Esquemas (pydantic) de tudo que mora em `data/`.

Convenção: os atributos em Python são em inglês; as chaves nos YAML são em
português, sem acento (via `alias`). Ex.: `Character.name` <- `nome:` no YAML.
Os erros de validação usam sempre a chave do YAML, porque é ela que o João vê.

Este módulo só descreve a FORMA dos dados. As checagens que cruzam arquivos
(ex.: "essa relação aponta para um id que existe?") ficam em `sim.loader`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --------------------------------------------------------------------------
# Tipos básicos
# --------------------------------------------------------------------------

ID_PATTERN = r"^[a-z][a-z0-9_]*$"
HEX_PATTERN = r"^#[0-9a-fA-F]{6}$"
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$"

Id = Annotated[str, Field(pattern=ID_PATTERN)]
HexColor = Annotated[str, Field(pattern=HEX_PATTERN)]
ClockTime = Annotated[str, Field(pattern=TIME_PATTERN)]
Percent = Annotated[float, Field(ge=0, le=100)]
Affinity = Annotated[int, Field(ge=-100, le=100)]
Multiplier = Annotated[float, Field(ge=0)]


def time_to_minutes(value: str) -> int:
    """'07:30' -> 450. '24:00' -> 1440."""
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


class DataModel(BaseModel):
    """Base de todos os esquemas: campo desconhecido é erro (pega erro de digitação)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TimeWindow(DataModel):
    """Janela de horário. Pode atravessar a meia-noite (das 22:00 até 06:00)."""

    start: ClockTime = Field(alias="das")
    end: ClockTime = Field(alias="ate")

    def contains(self, minute_of_day: int) -> bool:
        start, end = time_to_minutes(self.start), time_to_minutes(self.end)
        if start <= end:
            return start <= minute_of_day < end
        return minute_of_day >= start or minute_of_day < end


# --------------------------------------------------------------------------
# world.yaml
# --------------------------------------------------------------------------


class NeedDef(DataModel):
    """Uma necessidade/humor (0 a 100; quanto maior, mais urgente)."""

    name: str = Field(alias="nome", min_length=1)
    description: str = Field("", alias="descricao")
    # acumula: sobe sozinha com o tempo (fome, sono...).
    # retorna: volta devagar para a `base` (raiva, medo...).
    mode: Literal["acumula", "retorna"] = Field(alias="modo")
    base: Percent = 0
    initial: Percent = Field(alias="inicial")
    # pontos por hora do mundo; no modo "retorna" é a velocidade de volta à base
    rate_day: float = Field(alias="taxa_dia")
    rate_night: float = Field(alias="taxa_noite")
    # palavra de humor usada na variável {humor} das falas quando esta
    # necessidade é a mais alta (ex.: fome -> "faminto")
    mood: str = Field("", alias="humor")


class Period(DataModel):
    id: Id
    name: str = Field(alias="nome")
    start: ClockTime = Field(alias="das")


class ClockConfig(DataModel):
    multiplier: float = Field(1.0, alias="multiplicador", gt=0)
    timezone: str = Field("America/Sao_Paulo", alias="fuso")
    step_minutes: float = Field(1.0, alias="passo_minutos", gt=0, le=60)
    day_start: ClockTime = Field("06:00", alias="dia_comeca")
    night_start: ClockTime = Field("18:30", alias="noite_comeca")
    max_catchup_hours: float = Field(2.0, alias="max_recuperacao_horas", ge=0)
    periods: list[Period] = Field(alias="periodos", min_length=1)


class WeatherConfig(DataModel):
    city: str = Field(alias="cidade")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    refresh_minutes: int = Field(30, alias="atualizar_minutos", ge=5)
    cache_file: str = Field(alias="cache_arquivo")
    timeout_seconds: float = Field(5, alias="timeout_segundos", gt=0)
    fallback: str = Field("nublado", alias="clima_padrao")


class MqttTopics(DataModel):
    events: str = Field(alias="eventos")
    state: str = Field(alias="estado")
    chat: str = Field(alias="chat")
    tunnel_leds: str = Field(alias="tunel_leds")
    status: str = Field(alias="status")
    commands: str = Field(alias="comandos")
    presence: str = Field(alias="presenca")
    homelab: str = Field(alias="homelab")
    screen_status: str = Field(alias="status_telas")


class MqttConfig(DataModel):
    enabled: bool = Field(True, alias="ativo")
    host: str
    port: int = Field(alias="porta", ge=1, le=65535)
    username: str = Field("", alias="usuario")
    password: str = Field("", alias="senha")
    client_id: str = Field("divine-world", alias="client_id")
    state_every_minutes: float = Field(1.0, alias="estado_a_cada_minutos", gt=0)
    reconnect_seconds: float = Field(30, alias="reconectar_segundos", gt=0)
    topics: MqttTopics = Field(alias="topicos")


class OllamaConfig(DataModel):
    enabled: bool = Field(False, alias="ativo")
    url: str
    model: str = Field(alias="modelo")
    timeout_seconds: float = Field(4, alias="timeout_segundos", gt=0)
    max_per_hour: int = Field(30, alias="max_por_hora", ge=0)


class ServerConfig(DataModel):
    host: str
    port: int = Field(alias="porta", ge=1, le=65535)


class StorageConfig(DataModel):
    database: str = Field(alias="banco")
    save_every_minutes: float = Field(5, alias="salvar_a_cada_minutos", gt=0)


class LimitsConfig(DataModel):
    """Limites e chances do mundo. As fases 2-3 usam estes números; todos editáveis."""

    max_population: int = Field(alias="max_populacao", ge=1)
    min_population: int = Field(alias="min_populacao", ge=0)
    max_extras: int = Field(alias="max_figurantes", ge=0)
    director_events_per_hour: int = Field(alias="max_eventos_diretor_por_hora", ge=0)
    director_events_per_day: int = Field(alias="max_eventos_diretor_por_dia", ge=0)
    death_chance_per_day: float = Field(alias="chance_morte_por_dia", ge=0, le=1)
    ghost_chance_per_night: float = Field(alias="chance_fantasma_por_noite", ge=0, le=1)
    natural_resurrection_chance_per_year: float = Field(
        alias="chance_ressurreicao_natural_por_ano", ge=0, le=1
    )
    birth_interval_days: float = Field(alias="intervalo_nascimento_dias", gt=0)
    stare_chance_per_hour: float = Field(alias="chance_olhar_por_hora", ge=0, le=1)
    apparition_cooldown_days: float = Field(alias="cooldown_aparicao_dias", ge=0)
    prison_hours: float = Field(alias="horas_de_prisao", ge=0)
    limbo_days: float = Field(alias="dias_no_limbo", ge=0)
    funeral_rain_minutes: int = Field(alias="minutos_de_chuva_no_funeral", ge=0)

    @model_validator(mode="after")
    def _population(self) -> "LimitsConfig":
        if self.min_population > self.max_population:
            raise ValueError("min_populacao não pode ser maior que max_populacao")
        return self


class DecisionConfig(DataModel):
    """Parâmetros da Utility AI (ver docs/arquitetura.md, seção 'Utility AI')."""

    top_n: int = Field(3, alias="top_n", ge=1)
    temperature: float = Field(1.0, alias="temperatura", gt=0)
    travel_half_life_minutes: float = Field(alias="meia_vida_viagem_minutos", gt=0)
    repeat_penalty: float = Field(alias="penalidade_repeticao", ge=0, le=1)
    min_score: float = Field(0.01, alias="nota_minima", ge=0)
    # só entram no sorteio as opções com nota >= melhor × fracao_da_melhor
    # (0 = desliga; 0.5 = só o que vale pelo menos metade da melhor)
    relative_cutoff: float = Field(0.0, alias="fracao_da_melhor", ge=0, le=1)
    # Fase 1: quem está ocupado reavalia a cada N minutos do mundo e troca de
    # ação (interrompe) se a melhor opção valer `fator_interrupcao` vezes a
    # nota atual E pelo menos `nota_para_interromper`. É assim que alguém acorda
    # para o trabalho, ou o Padre larga tudo para tocar o sino.
    reevaluate_minutes: float = Field(10, alias="reavaliar_a_cada_minutos", gt=0)
    interrupt_factor: float = Field(3.0, alias="fator_interrupcao", ge=1)
    interrupt_min_score: float = Field(0.5, alias="nota_para_interromper", ge=0)
    # acordar alguém (ação com `dormindo: true`) exige um motivo mais forte
    wake_min_score: float = Field(2.0, alias="nota_para_acordar", ge=0)


class NamedThing(DataModel):
    name: str = Field(alias="nome", min_length=1)


class Position(DataModel):
    x: float
    y: float


class Size(DataModel):
    width: float = Field(alias="largura", gt=0)
    height: float = Field(alias="altura", gt=0)


class Screen(DataModel):
    id: Id
    name: str = Field(alias="nome")
    places: list[Id] = Field(alias="lugares", min_length=1)
    position_cm: Position = Field(alias="posicao_cm")
    size_cm: Size = Field(alias="tamanho_cm")
    max_fps: int = Field(30, alias="fps_max", ge=1, le=144)
    quality: Literal["baixa", "media", "alta"] = Field("media", alias="qualidade")


class TunnelConfig(DataModel):
    led_speed_cm_per_s: float = Field(alias="velocidade_led_cm_por_s", gt=0)
    min_duration_s: float = Field(alias="duracao_minima_s", ge=0)


class WorldConfig(DataModel):
    name: str = Field(alias="nome")
    seed: int | None = None
    central_place: Id = Field(alias="lugar_central")
    clock: ClockConfig = Field(alias="relogio")
    needs: dict[Id, NeedDef] = Field(alias="necessidades", min_length=1)
    decision: DecisionConfig = Field(alias="decisao")
    limits: LimitsConfig = Field(alias="limites")
    regions: dict[Id, NamedThing] = Field(default_factory=dict, alias="regioes")
    groups: dict[Id, NamedThing] = Field(default_factory=dict, alias="grupos")
    chat_categories: dict[Id, NamedThing] = Field(alias="categorias_chat")
    weather: WeatherConfig = Field(alias="clima")
    mqtt: MqttConfig
    ollama: OllamaConfig
    server: ServerConfig = Field(alias="servidor")
    storage: StorageConfig = Field(alias="persistencia")
    tunnel: TunnelConfig = Field(alias="tunel")
    screens: list[Screen] = Field(default_factory=list, alias="telas")
    log_level: Literal["debug", "info", "aviso", "erro"] = Field("info", alias="nivel_log")
    # {humor} das falas quando nenhuma necessidade está alta
    neutral_mood: str = Field("de boa", alias="humor_neutro")

    @field_validator("seed", mode="before")
    @classmethod
    def _empty_seed(cls, value):
        # "${DW_SEED:-}" vira "" -> sem seed fixa (aleatória)
        return None if value in ("", None) else value


# --------------------------------------------------------------------------
# places/*.yaml
# --------------------------------------------------------------------------


class Palette(DataModel):
    main: HexColor = Field(alias="principal")
    secondary: HexColor = Field(alias="secundaria")
    light: HexColor = Field(alias="luz")
    night: HexColor | None = Field(None, alias="noite")


class Connection(DataModel):
    to: Id = Field(alias="para")
    # caminho: anda a pé. tunel: teletransporte (LED na parede entre telas).
    kind: Literal["caminho", "tunel"] = Field("caminho", alias="tipo")
    minutes: float = Field(alias="minutos", gt=0)


class Place(DataModel):
    id: Id
    name: str = Field(alias="nome", min_length=1)
    description: str = Field("", alias="descricao")
    region: Id | None = Field(None, alias="regiao")
    environment: Literal["interno", "externo"] = Field(alias="ambiente")
    # normal: qualquer um vai andando. especial: só por regra (Limbo, Céu?).
    # nunca: existe só na lenda (Mundo de Fora).
    access: Literal["normal", "especial", "nunca"] = Field("normal", alias="acesso")
    danger: Percent = Field(alias="perigo")
    danger_night: Percent | None = Field(None, alias="perigo_noite")
    sinister: bool = Field(False, alias="sinistro")
    palette: Palette = Field(alias="paleta")
    features: list[str] = Field(default_factory=list, alias="tem")
    connections: list[Connection] = Field(default_factory=list, alias="conexoes")
    actions: list[Id] = Field(default_factory=list, alias="acoes")


# --------------------------------------------------------------------------
# characters/*.yaml
# --------------------------------------------------------------------------


class Visual(DataModel):
    """Dicas para o placeholder 3D da Fase 5 (o .glb do João substitui tudo)."""

    color: HexColor = Field(alias="cor")
    secondary_color: HexColor = Field(alias="cor_secundaria")
    height: float = Field(1.0, alias="altura", gt=0.2, le=3)
    body: Literal["magro", "normal", "barrigudo", "enorme", "baixinho", "corcunda"] = Field(
        "normal", alias="corpo"
    )
    hat: str | None = Field(None, alias="chapeu")
    accessory: str | None = Field(None, alias="acessorio")


class Fear(DataModel):
    description: str = Field(alias="descricao")
    # palavra-chave que o código pode reconhecer (chuva, aranha, silencio...).
    trigger: Id | None = Field(None, alias="gatilho")


class NeedOverride(DataModel):
    initial: Percent | None = Field(None, alias="inicial")
    rate: Multiplier | None = Field(None, alias="taxa")  # multiplica a taxa do world.yaml


class RoutineBlock(DataModel):
    start: ClockTime = Field(alias="das")
    end: ClockTime = Field(alias="ate")
    action: Id = Field(alias="acao")
    place: Id | None = Field(None, alias="lugar")
    weight: float = Field(2.0, alias="peso", gt=0)

    def window(self) -> TimeWindow:
        return TimeWindow(das=self.start, ate=self.end)


class Relation(DataModel):
    with_: Id = Field(alias="com")
    affinity: Affinity = Field(alias="afinidade")
    kind: str = Field("conhecido", alias="tipo")
    note: str = Field("", alias="nota")


class RealLink(DataModel):
    channel: Literal[
        "nenhum", "ordens_civicas", "voz_do_criador", "homelab", "instrumento_real", "luz_do_quarto"
    ] = Field("nenhum", alias="canal")
    description: str = Field("", alias="descricao")
    optional: bool = Field(False, alias="opcional")


class Inheritance(DataModel):
    objects: list[str] = Field(default_factory=list, alias="objetos")
    quirks: list[str] = Field(default_factory=list, alias="manias")
    heirs: list[Id] = Field(default_factory=list, alias="herdeiros")


class Character(DataModel):
    id: Id
    name: str = Field(alias="nome", min_length=1)
    pronoun: Literal["ele", "ela"] = Field("ele", alias="pronome")
    group: Id | None = Field(None, alias="grupo")
    role: str = Field("", alias="papel")
    appearance: str = Field(alias="aparencia")
    movement: str = Field("", alias="movimento")
    visual: Visual
    traits: list[Id] = Field(alias="tracos", min_length=1)
    wants: str = Field("", alias="quer")
    fears: list[Fear] = Field(default_factory=list, alias="medos")
    flaw: str = Field("", alias="defeito")
    catchphrases: list[str] = Field(default_factory=list, alias="bordoes")
    secret: str = Field("", alias="segredo")
    daily_life: str = Field("", alias="dia_normal")
    profession: Id = Field(alias="profissao")
    workplace: Id | None = Field(None, alias="local_trabalho")
    home: Id = Field(alias="casa")
    routine: list[RoutineBlock] = Field(default_factory=list, alias="rotina")
    needs: dict[Id, NeedOverride] = Field(default_factory=dict, alias="necessidades")
    default_affinity: Affinity = Field(0, alias="afinidade_padrao")
    relations: list[Relation] = Field(default_factory=list, alias="relacoes")
    immunities: list[Id] = Field(default_factory=list, alias="imunidades")
    real_link: RealLink = Field(default_factory=RealLink, alias="ligacao_real")
    inheritance: Inheritance = Field(default_factory=Inheritance, alias="heranca")
    on_death: str = Field("", alias="se_morrer")


# --------------------------------------------------------------------------
# traits.yaml (traços, profissões e o "sorteio" dos nascimentos)
# --------------------------------------------------------------------------


class TraitEffects(DataModel):
    needs: dict[Id, Multiplier] = Field(default_factory=dict, alias="necessidades")
    actions: dict[Id, Multiplier] = Field(default_factory=dict, alias="acoes")


class Trait(DataModel):
    id: Id
    name: str = Field(alias="nome", min_length=1)
    description: str = Field("", alias="descricao")
    drawable: bool = Field(True, alias="sorteavel")
    opposites: list[Id] = Field(default_factory=list, alias="opostos")
    effects: TraitEffects = Field(default_factory=TraitEffects, alias="efeitos")


class Profession(DataModel):
    id: Id
    name: str = Field(alias="nome", min_length=1)
    activity: str = Field("", alias="atividade")  # vira a variável {trabalho} nas falas
    workplace: Id | None = Field(None, alias="local_trabalho")
    drawable: bool = Field(True, alias="sorteavel")
    important_role: bool = Field(False, alias="papel_importante")  # sucessão (Fase 3)


class AppearancePool(DataModel):
    colors: list[HexColor] = Field(alias="cores", min_length=1)
    bodies: list[str] = Field(alias="corpos", min_length=1)
    hats: list[str] = Field(default_factory=list, alias="chapeus")
    accessories: list[str] = Field(default_factory=list, alias="acessorios")
    descriptions: list[str] = Field(default_factory=list, alias="descricoes")


class BirthRules(DataModel):
    min_traits: int = Field(2, alias="tracos_min", ge=1)
    max_traits: int = Field(3, alias="tracos_max", ge=1)
    inherit_chance: float = Field(0.5, alias="chance_herdar_do_morto", ge=0, le=1)
    default_name: str = Field("Recém-chegado", alias="nome_padrao")

    @model_validator(mode="after")
    def _range(self) -> "BirthRules":
        if self.min_traits > self.max_traits:
            raise ValueError("tracos_min não pode ser maior que tracos_max")
        return self


class TraitsFile(DataModel):
    traits: list[Trait] = Field(alias="tracos", min_length=1)
    professions: list[Profession] = Field(alias="profissoes", min_length=1)
    appearance: AppearancePool = Field(alias="aparencias")
    birth: BirthRules = Field(default_factory=BirthRules, alias="nascimento")


# --------------------------------------------------------------------------
# actions/*.yaml
# --------------------------------------------------------------------------

CurveKind = Literal["linear", "potencia", "logistica", "degrau", "pontos"]


class Curve(DataModel):
    """Transforma uma entrada (ex.: fome de 0 a 100) num fator de 0 a 1.

    Ver `sim.curves` e a seção "Curvas" de docs/arquitetura.md.
    """

    kind: CurveKind = Field(alias="tipo")
    invert: bool = Field(False, alias="inverter")
    exponent: float | None = Field(None, alias="expoente", gt=0)
    midpoint: float | None = Field(None, alias="meio")
    steepness: float | None = Field(None, alias="inclinacao", gt=0)
    threshold: float | None = Field(None, alias="limite")
    points: list[tuple[float, float]] | None = Field(None, alias="pontos")
    floor: float = Field(0.0, alias="minimo", ge=0, le=1)

    @model_validator(mode="after")
    def _params(self) -> "Curve":
        if self.kind == "potencia" and self.exponent is None:
            raise ValueError("curva 'potencia' precisa de 'expoente' (ex.: 2)")
        if self.kind == "logistica" and self.midpoint is None:
            raise ValueError("curva 'logistica' precisa de 'meio' (ex.: 70)")
        if self.kind == "degrau" and self.threshold is None:
            raise ValueError("curva 'degrau' precisa de 'limite' (ex.: 50)")
        if self.kind == "pontos":
            if not self.points or len(self.points) < 2:
                raise ValueError("curva 'pontos' precisa de pelo menos 2 pontos [x, y]")
            xs = [p[0] for p in self.points]
            if xs != sorted(xs):
                raise ValueError("os pontos da curva precisam estar em ordem crescente de x")
            if any(not 0 <= p[1] <= 1 for p in self.points):
                raise ValueError("o y de cada ponto da curva precisa estar entre 0 e 1")
        return self


class Consideration(DataModel):
    # entradas válidas: necessidade.<id>, alvo_necessidade.<id>, afinidade,
    # hora, presentes, perigo, tensao (lista em sim.curves.INPUT_RANGES)
    input: str = Field(alias="entrada")
    curve: Curve = Field(alias="curva")
    note: str = Field("", alias="nota")


class TargetRule(DataModel):
    required: bool = Field(True, alias="obrigatorio")
    affinity_min: Affinity | None = Field(None, alias="afinidade_min")
    affinity_max: Affinity | None = Field(None, alias="afinidade_max")


class ActionConditions(DataModel):
    periods: list[Id] = Field(default_factory=list, alias="periodos")
    hours: list[TimeWindow] = Field(default_factory=list, alias="horarios")
    professions: list[Id] = Field(default_factory=list, alias="profissoes")
    traits: list[Id] = Field(default_factory=list, alias="tracos")
    characters: list[Id] = Field(default_factory=list, alias="personagens")
    min_needs: dict[Id, Percent] = Field(default_factory=dict, alias="necessidades_min")
    target: TargetRule | None = Field(None, alias="alvo")
    # "trabalho": só no local_trabalho do personagem; "casa": só na casa dele.
    # Nesses casos a ação não precisa estar na lista `acoes` do lugar.
    own_place: Literal["trabalho", "casa"] | None = Field(None, alias="lugar_proprio")


class ActionEffects(DataModel):
    # variação TOTAL ao longo da ação (negativo = satisfaz; positivo = custo)
    needs: dict[Id, float] = Field(default_factory=dict, alias="necessidades")
    target_needs: dict[Id, float] = Field(default_factory=dict, alias="alvo_necessidades")
    affinity: float = Field(0, alias="afinidade")  # minha afinidade com o alvo
    target_affinity: float = Field(0, alias="afinidade_do_alvo")  # a do alvo comigo


class ActionFailure(DataModel):
    chance: float = Field(ge=0, le=1)
    effects: ActionEffects = Field(default_factory=ActionEffects, alias="efeitos")
    speech: Id | None = Field(None, alias="fala")


class Action(DataModel):
    id: Id
    name: str = Field(alias="nome", min_length=1)
    description: str = Field("", alias="descricao")
    # individual | social (precisa de alvo) | movimento (passo de um plano, não é pontuado)
    kind: Literal["individual", "social", "movimento"] = Field(alias="tipo")
    active: bool = Field(True, alias="ativa")
    base_weight: float = Field(1.0, alias="peso", ge=0)
    duration_minutes: tuple[int, int] = Field(alias="duracao_minutos")
    anywhere: bool = Field(False, alias="em_qualquer_lugar")
    conditions: ActionConditions = Field(default_factory=ActionConditions, alias="condicoes")
    considerations: list[Consideration] = Field(default_factory=list, alias="consideracoes")
    effects: ActionEffects = Field(default_factory=ActionEffects, alias="efeitos")
    failure: ActionFailure | None = Field(None, alias="falha")
    speech: Id | None = Field(None, alias="fala")  # situação de falas em data/lines
    speech_chance: float = Field(0.5, alias="chance_fala", ge=0, le=1)
    tags: list[Id] = Field(default_factory=list)
    importance: int = Field(0, alias="importancia", ge=0, le=3)
    # Fase 1 ---------------------------------------------------------------
    # texto do Chat do Mundo quando a ação começa sem fala (balão) e quando
    # termina (ex.: dormir -> "{eu} acorda"). Mesmas variáveis das falas.
    narration: str | None = Field(None, alias="narracao")
    narration_end: str | None = Field(None, alias="narracao_fim")
    # quem está fazendo esta ação está dormindo: não pode ser alvo de conversa
    # e o sono não sobe sozinho enquanto isso
    sleeping: bool = Field(False, alias="dormindo")
    # a ação acontece num lugar VIZINHO sorteado (andar sem rumo: o Mike)
    wander: bool = Field(False, alias="vagar")
    # depois de terminar, não pode repetir antes de N minutos do mundo
    cooldown_minutes: float = Field(0, alias="cooldown_minutos", ge=0)
    # tipo de evento especial emitido no começo (no lugar de action_started)
    event: Literal["bell"] | None = Field(None, alias="evento")
    # ações sociais: o alvo responde com uma fala desta situação
    target_speech: Id | None = Field(None, alias="fala_alvo")
    target_speech_chance: float = Field(0.5, alias="chance_fala_alvo", ge=0, le=1)

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def _duration(cls, value):
        # aceita `duracao_minutos: 30` ou `duracao_minutos: [20, 40]`
        if isinstance(value, (int, float)):
            return (int(value), int(value))
        return value

    @model_validator(mode="after")
    def _checks(self) -> "Action":
        low, high = self.duration_minutes
        if low <= 0 or high < low:
            raise ValueError("duracao_minutos deve ser [minimo, maximo] com 0 < minimo <= maximo")
        if self.kind == "social" and self.conditions.target is None:
            raise ValueError("ação 'social' precisa de 'condicoes.alvo'")
        return self


class ActionsFile(DataModel):
    actions: list[dict] = Field(alias="acoes")  # cada item é validado como Action no loader


# --------------------------------------------------------------------------
# events/*.yaml (eventos do diretor e raros)
# --------------------------------------------------------------------------


class EventConditions(DataModel):
    periods: list[Id] = Field(default_factory=list, alias="periodos")
    hours: list[TimeWindow] = Field(default_factory=list, alias="horarios")
    tension_min: Percent = Field(0, alias="tensao_min")
    tension_max: Percent = Field(100, alias="tensao_max")
    min_population: int = Field(0, alias="populacao_min", ge=0)
    weather: list[str] = Field(default_factory=list, alias="climas")


class Goal(DataModel):
    """Objetivo temporário: multiplica a nota de uma ação (o diretor só cria situações)."""

    action: Id = Field(alias="acao")
    place: Id | None = Field(None, alias="lugar")
    bonus: float = Field(alias="bonus", gt=0)
    hours: float = Field(alias="duracao_horas", gt=0)
    who: Literal["todos", "presentes"] = Field("presentes", alias="para")


class EventEffects(DataModel):
    needs: dict[Id, float] = Field(default_factory=dict, alias="necessidades")
    goal: Goal | None = Field(None, alias="objetivo")
    weather: str | None = Field(None, alias="clima")


class WorldEvent(DataModel):
    id: Id
    name: str = Field(alias="nome", min_length=1)
    description: str = Field("", alias="descricao")
    kind: Literal["ritmo", "social", "clima", "criatura", "raro", "lendario"] = Field(alias="tipo")
    active: bool = Field(True, alias="ativo")
    weight: float = Field(1.0, alias="peso", ge=0)
    cooldown_hours: float = Field(0, alias="cooldown_horas", ge=0)
    # o que o evento faz com a tensão do mundo: o diretor usa isso para escolher
    tension: Literal["acalma", "agita", "neutro"] = Field("neutro", alias="tensao")
    places: list[Id] = Field(default_factory=list, alias="lugares")  # sorteia um; vazio = qualquer
    conditions: EventConditions = Field(default_factory=EventConditions, alias="condicoes")
    effects: EventEffects = Field(default_factory=EventEffects, alias="efeitos")
    text: str = Field(alias="texto")  # template do Chat do Mundo
    importance: int = Field(1, alias="importancia", ge=0, le=3)
    tags: list[Id] = Field(default_factory=list)


class EventsFile(DataModel):
    events: list[dict] = Field(default_factory=list, alias="eventos")


# --------------------------------------------------------------------------
# lines/*.yaml (templates de falas)
# --------------------------------------------------------------------------


class LineTemplate(DataModel):
    text: str = Field(alias="texto", min_length=1)
    characters: list[Id] = Field(default_factory=list, alias="personagens")
    traits: list[Id] = Field(default_factory=list, alias="tracos")
    places: list[Id] = Field(default_factory=list, alias="lugares")
    periods: list[Id] = Field(default_factory=list, alias="periodos")
    weather: list[str] = Field(default_factory=list, alias="climas")
    min_needs: dict[Id, Percent] = Field(default_factory=dict, alias="necessidades_min")
    weight: float = Field(1.0, alias="peso", ge=0)

    @model_validator(mode="before")
    @classmethod
    def _plain_string(cls, value):
        # atalho: uma fala pode ser só um texto, sem filtros
        return {"texto": value} if isinstance(value, str) else value

    @field_validator("text", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class LinesFile(DataModel):
    situations: dict[Id, list[LineTemplate]] = Field(alias="situacoes")
