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


class WeatherKind(DataModel):
    """Um tipo de clima (limpo, chuva...). `codigos`: códigos WMO do Open-Meteo que viram este tipo."""

    name: str = Field(alias="nome", min_length=1)  # vira a variável {clima} das falas
    codes: list[int] = Field(default_factory=list, alias="codigos")
    rain: bool = Field(False, alias="chuva")  # conta como chuva (efeitos, medo de chuva)


class WeatherEffect(DataModel):
    """O que um clima (ou o frio/calor) faz: multiplica taxas de necessidades e notas de ações."""

    needs: dict[Id, Multiplier] = Field(default_factory=dict, alias="necessidades")
    actions: dict[Id, Multiplier] = Field(default_factory=dict, alias="acoes")
    # multiplica a nota de QUALQUER ação em lugar com ambiente: externo
    outdoor: Multiplier = Field(1.0, alias="acoes_externas")


class SimulatedWeather(DataModel):
    """Clima sorteado (quando o mundo não está no tempo real ou sem internet)."""

    change_hours: tuple[float, float] = Field((2, 6), alias="troca_a_cada_horas")
    weights: dict[Id, float] = Field(default_factory=dict, alias="pesos")
    temp_day: tuple[float, float] = Field((20, 30), alias="temperatura_dia")
    temp_night: tuple[float, float] = Field((14, 20), alias="temperatura_noite")


class WeatherConfig(DataModel):
    city: str = Field(alias="cidade")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    refresh_minutes: int = Field(30, alias="atualizar_minutos", ge=5)
    cache_file: str = Field(alias="cache_arquivo")
    timeout_seconds: float = Field(5, alias="timeout_segundos", gt=0)
    # tipo de clima (id em `tipos`) quando não há internet, nem cache, nem sorteio
    fallback: str = Field("nublado", alias="clima_padrao")
    # Fase 3 ------------------------------------------------------------------
    # auto: clima real (Open-Meteo) quando o mundo segue o relógio real; sorteado
    #       quando o tempo está acelerado (testes, --fast). real | simulado | fixo
    mode: Literal["auto", "real", "simulado", "fixo"] = Field("auto", alias="modo")
    url: str = Field("https://api.open-meteo.com/v1/forecast", alias="url")
    kinds: dict[Id, WeatherKind] = Field(default_factory=dict, alias="tipos")
    simulated: SimulatedWeather = Field(default_factory=SimulatedWeather, alias="simulado")
    cold_below: float = Field(14, alias="frio_abaixo")
    hot_above: float = Field(30, alias="calor_acima")
    # efeitos por tipo de clima e também "frio" / "calor"
    effects: dict[Id, WeatherEffect] = Field(default_factory=dict, alias="efeitos")
    # quem tem medo (medos.gatilho) do clima atual ganha isso de medo por hora
    fear_per_hour: float = Field(12, alias="medo_por_hora_com_gatilho", ge=0)
    # o clima do funeral (sempre chove)
    funeral_kind: Id = Field("chuva", alias="clima_do_funeral")


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


# --------------------------------------------------------------------------
# Fase 2: sociedade (memória, fofoca, relações, leis, facções, estruturas)
# --------------------------------------------------------------------------


class MemoryKind(DataModel):
    """Um tipo de memória (briga, roubo, festa...). Frases usam {quem} (quem fez),
    {alvo} (com quem/em quem), {lugar} e {objeto}."""

    name: str = Field(alias="nome", min_length=1)
    intensity: Percent = Field(50, alias="intensidade")  # intensidade ao formar (0..100)
    sentiment: float = Field(0, alias="sentimento", ge=-1, le=1)  # -1 ruim, +1 bom
    decay_per_day: float = Field(10, alias="decai_por_dia", ge=0)  # pontos de intensidade por dia
    permanent: bool = Field(False, alias="permanente")  # nunca some (morte, casamento, Limbo)
    # quem lembra muda a afinidade com quem fez ({quem}) neste tanto ao formar
    affinity: float = Field(0, alias="afinidade")
    # frase de fofoca (terceira pessoa): "{quem} brigou com {alvo} em {lugar}"
    fact: str = Field(alias="fato", min_length=1)
    # como quem estava envolvido fala dela: "aquela briga em {lugar}"
    recollection: str = Field(alias="lembranca", min_length=1)
    # a lei vê esta memória como prova desta infração (contra {quem})
    infraction: Id | None = Field(None, alias="infracao")


class MemoryConfig(DataModel):
    kinds: dict[Id, MemoryKind] = Field(default_factory=dict, alias="tipos")
    max_per_npc: int = Field(40, alias="max_por_npc", ge=5)
    forget_below: float = Field(5, alias="esquecer_abaixo", ge=0)
    # quem só viu (testemunha) ou só ouviu falar (fofoca) lembra mais fraco
    witness_factor: float = Field(0.6, alias="fator_testemunha", ge=0, le=1)
    gossip_factor: float = Field(0.7, alias="fator_fofoca", ge=0, le=1)


class GossipConfig(DataModel):
    # chance de a fofoca chegar torta: troca quem fez por outra pessoa
    distortion_chance: float = Field(0.2, alias="chance_distorcao", ge=0, le=1)
    # traço que distorce o dobro e espalha segredo de confissão
    gossiper_trait: Id | None = Field("fofoqueiro", alias="traco_fofoqueiro")


class RelationsConfig(DataModel):
    # a afinidade volta devagar para o valor inicial (rancor dura, mas passa)
    return_per_hour: float = Field(0.2, alias="retorno_por_hora", ge=0)
    enemies_below: float = Field(-50, alias="inimigos_abaixo")
    friends_above: float = Field(60, alias="amigos_acima")


class Infraction(DataModel):
    name: str = Field(alias="nome", min_length=1)
    severity: float = Field(1, alias="gravidade", gt=0)
    # só conta nestes horários (ex.: barulho só de madrugada); vazio = sempre
    hours: list[TimeWindow] = Field(default_factory=list, alias="horarios")


class LawConfig(DataModel):
    enforcer_profession: Id = Field("fiscal", alias="profissao_fiscal")
    infractions: dict[Id, Infraction] = Field(default_factory=dict, alias="infracoes")
    prison_points: float = Field(2, alias="pontos_para_prisao", gt=0)
    limbo_points: float = Field(6, alias="pontos_para_limbo", gt=0)
    points_decay_per_day: float = Field(1, alias="pontos_somem_por_dia", ge=0)
    warrant_hours: float = Field(24, alias="mandado_horas", gt=0)
    # a mesma pessoa pela mesma infração não é registrada de novo antes disso
    repeat_hours: float = Field(6, alias="reincidencia_horas", ge=0)
    # numa olhada só, o Fiscal registra no máximo esta quantidade de flagrantes
    max_per_look: int = Field(2, alias="max_por_olhada", ge=1)
    prison: Id = Field("prison", alias="prisao")
    limbo: Id = Field("limbo", alias="limbo")
    limbo_return: Id = Field("town_square", alias="volta_do_limbo")
    # o que o preso pode fazer na cela (mesmo que a Prisão não ofereça a ação)
    prison_actions: list[Id] = Field(default_factory=lambda: ["comer"], alias="acoes_na_prisao")
    # quanto tempo depois de entrar o preso ganha uma "visita" do Fiscal (não usado)
    flee_action: Id = Field("fugir", alias="acao_fuga")
    chase_action: Id = Field("perseguir", alias="acao_perseguicao")


class Faction(DataModel):
    name: str = Field(alias="nome", min_length=1)
    leader: Id = Field(alias="lider")
    # entra quando a afinidade com o líder passa disso (e é maior que a com o líder rival)
    join_affinity: float = Field(40, alias="afinidade_para_entrar")
    # sai quando a afinidade com o líder cai abaixo disso
    leave_affinity: float = Field(-10, alias="afinidade_para_sair")


class TheftConfig(DataModel):
    """Ganância: o que acontece com o que é roubado."""

    witness_notice_chance: float = Field(0.6, alias="chance_testemunha_notar", ge=0, le=1)
    # o ladrão esconde e esquece onde escondeu (o objeto fica perdido em algum lugar)
    forget_chance: float = Field(0.3, alias="chance_esquecer", ge=0, le=1)
    # quem perambula por um lugar com objeto perdido pode achar
    find_chance: float = Field(0.3, alias="chance_achar", ge=0, le=1)
    # quem tem um destes traços declara que o achado é SAGRADO
    sacred_traits: list[Id] = Field(default_factory=list, alias="tracos_que_acham_sagrado")
    # quem trabalha no lugar percebe o sumiço ao começar a trabalhar
    anger_on_notice: float = Field(25, alias="raiva_ao_perceber", ge=0)


class StructuresConfig(DataModel):
    damaged_below: float = Field(70, alias="danificado_abaixo", ge=0, le=100)


# --------------------------------------------------------------------------
# Fase 3: vida, morte, criaturas, diretor
# --------------------------------------------------------------------------


class DeathCause(DataModel):
    """Uma causa de morte. `quando` diz em que momento o mundo sorteia:

    diario   — uma vez por dia, para cada vivo (chance vazia = limites.chance_morte_por_dia)
    briga    — quando uma briga termina, para o alvo (e, com metade da chance, para quem bateu)
    falha    — quando uma das `acoes` dá errado (pastelão)
    criatura — por hora, para quem está no lugar de uma criatura (e ao perder um enfrentamento)
    limbo    — uma vez por ida ao Limbo (não volta)
    """

    name: str = Field(alias="nome", min_length=1)
    when: Literal["diario", "briga", "falha", "criatura", "limbo"] = Field(alias="quando")
    chance: float | None = Field(None, ge=0, le=1)
    actions: list[Id] = Field(default_factory=list, alias="acoes")
    places: list[Id] = Field(default_factory=list, alias="lugares")
    by_trait: dict[Id, Multiplier] = Field(default_factory=dict, alias="por_traco")
    situation: Id | None = Field(None, alias="fala")  # situação de data/lines da notícia (padrão: morte_<id>)


class DeathConfig(DataModel):
    causes: dict[Id, DeathCause] = Field(default_factory=dict, alias="causas")
    memory: Id = Field("morte", alias="memoria")  # memória permanente de todos os vivos
    # para onde o corpo vai (o cemitério)
    body_place: Id = Field("cemetery", alias="lugar_do_corpo")


class FuneralConfig(DataModel):
    delay_hours: tuple[float, float] = Field((2, 5), alias="depois_horas")
    window: TimeWindow = Field(default_factory=lambda: TimeWindow(das="07:00", ate="19:00"), alias="comeca_entre")
    wake_place: Id = Field("cathedral", alias="local_velorio")
    wake_minutes: int = Field(40, alias="velorio_minutos", ge=0)
    burial_place: Id = Field("cemetery", alias="local_enterro")
    duration_minutes: tuple[int, int] = Field((60, 90), alias="duracao_minutos")
    action: Id = Field("velar", alias="acao")
    # vontade de ir: bonus = base + afinidade_com_o_morto × por_afinidade (mínimo `bonus_min`)
    bonus_base: float = Field(3, alias="bonus_base", gt=0)
    bonus_per_affinity: float = Field(0.05, alias="bonus_por_afinidade", ge=0)
    bonus_min: float = Field(0.4, alias="bonus_min", gt=0)
    memory: Id | None = Field("funeral", alias="memoria")
    # quem conduz (o primeiro vivo com uma destas profissões)
    leaders: list[Id] = Field(default_factory=lambda: ["padre", "lider"], alias="quem_conduz")


class GriefConfig(DataModel):
    affinity_min: float = Field(20, alias="afinidade_min")  # abaixo disso não entra em luto
    days: float = Field(5, alias="dias", gt=0)  # duração com intensidade 1 (afinidade 100)
    kind_factor: dict[str, float] = Field(default_factory=dict, alias="fator_por_tipo")
    shock: dict[Id, float] = Field(default_factory=dict, alias="choque")  # somado na hora × intensidade
    rates: dict[Id, Multiplier] = Field(default_factory=dict, alias="taxas")  # taxas × (1 + (m-1)×int.)
    actions: dict[Id, Multiplier] = Field(default_factory=dict, alias="acoes")  # notas × (1 + (m-1)×int.)


class DeathConsequence(DataModel):
    """O que a morte de um personagem específico muda (bible: "Se morrer")."""

    rain_minutes: int | None = Field(None, alias="chuva_minutos", ge=0)
    funeral_delay_hours: float | None = Field(None, alias="funeral_depois_horas", ge=0)
    text: str | None = Field(None, alias="texto")  # narração logo depois do funeral (ou da morte)
    actions: dict[Id, Multiplier] = Field(default_factory=dict, alias="acoes")
    who: list[Id] = Field(default_factory=list, alias="para")  # vazio = todos
    days: float = Field(7, alias="dias", gt=0)
    goal: "Goal | None" = Field(None, alias="objetivo")
    grief_factor: dict[Id, float] = Field(default_factory=dict, alias="luto_fator")
    importance: int = Field(2, alias="importancia", ge=0, le=3)


class SuccessionRole(DataModel):
    mode: Literal["eleicao", "vocacao", "sucessao"] = Field(alias="modo")
    after_hours: tuple[float, float] = Field((12, 36), alias="depois_horas")
    traits: list[Id] = Field(default_factory=list, alias="tracos")  # vocação: quem tem estes traços
    place: Id | None = Field(None, alias="lugar")  # eleição: onde a cidade se junta
    duration_minutes: int = Field(60, alias="duracao_minutos", gt=0)  # eleição: assembleia


class SuccessionConfig(DataModel):
    roles: dict[Id, SuccessionRole] = Field(default_factory=dict, alias="papeis")
    heir_bonus: float = Field(4, alias="bonus_herdeiro", ge=0)
    kind_bonus: dict[str, float] = Field(default_factory=dict, alias="bonus_por_tipo")
    assembly_action: Id = Field("assembleia", alias="acao_assembleia")
    assembly_bonus: float = Field(4, alias="bonus_assembleia", gt=0)


class LifeConfig(DataModel):
    # pasta dos nascidos, relativa a data/ (a variável DW_BORN_DIR tem prioridade)
    born_dir: str = Field("characters/born", alias="pasta_nascidos")
    # cada vaga aberta (mortes - nascimentos nos últimos 30 dias) aumenta a chance de nascer
    vacancy_bonus: float = Field(1.0, alias="bonus_por_vaga", ge=0)
    # luto, fantasmas e herança olham para os mortos destes últimos dias
    recent_dead_days: float = Field(20, alias="dias_morto_recente", gt=0)
    ghost_memory: Id = Field("fantasma", alias="memoria_fantasma")
    resurrection_memory: Id = Field("ressurreicao", alias="memoria_ressurreicao")


class CreaturesConfig(DataModel):
    max_active: int = Field(3, alias="max_ao_mesmo_tempo", ge=0)
    fight_action: Id = Field("enfrentar", alias="acao_enfrentar")
    memory: Id = Field("criatura", alias="memoria")
    win_memory: Id = Field("criatura_vencida", alias="memoria_vitoria")


class DirectorConfig(DataModel):
    every_minutes: int = Field(10, alias="a_cada_minutos", ge=1)
    window_hours: float = Field(6, alias="janela_horas", gt=0)
    # tensão = Σ peso × contagem na janela (tipos de evento) + medo/raiva médios × peso + ...
    event_weights: dict[str, float] = Field(default_factory=dict, alias="pesos_eventos")
    fear_weight: float = Field(0.3, alias="peso_medo_medio")
    anger_weight: float = Field(0.3, alias="peso_raiva_media")
    death_weight: float = Field(15, alias="peso_morte_recente")
    death_window_hours: float = Field(48, alias="janela_morte_horas", gt=0)
    creature_weight: float = Field(8, alias="peso_criatura")
    # tensão que o diretor persegue em cada período do dia
    target: dict[Id, float] = Field(default_factory=dict, alias="alvo")
    margin: float = Field(10, alias="margem", ge=0)
    # chance de agir numa checagem = min(1, distância/50) × isto
    act_chance: float = Field(0.25, alias="chance_de_agir", ge=0, le=1)
    log_every_minutes: int = Field(60, alias="registrar_tensao_a_cada_minutos", ge=1)


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
    # Fase 2
    memory: MemoryConfig = Field(default_factory=MemoryConfig, alias="memoria")
    gossip: GossipConfig = Field(default_factory=GossipConfig, alias="fofoca")
    relations: RelationsConfig = Field(default_factory=RelationsConfig, alias="relacoes")
    law: LawConfig = Field(default_factory=LawConfig, alias="leis")
    factions: dict[Id, Faction] = Field(default_factory=dict, alias="faccoes")
    structures: StructuresConfig = Field(default_factory=StructuresConfig, alias="estruturas")
    theft: TheftConfig = Field(default_factory=TheftConfig, alias="roubos")
    # Fase 3
    life: LifeConfig = Field(default_factory=LifeConfig, alias="vida")
    death: DeathConfig = Field(default_factory=DeathConfig, alias="morte")
    funeral: FuneralConfig = Field(default_factory=FuneralConfig, alias="funeral")
    grief: GriefConfig = Field(default_factory=GriefConfig, alias="luto")
    consequences: dict[Id, DeathConsequence] = Field(default_factory=dict, alias="se_morrer")
    succession: SuccessionConfig = Field(default_factory=SuccessionConfig, alias="sucessao")
    creatures: CreaturesConfig = Field(default_factory=CreaturesConfig, alias="criaturas")
    director: DirectorConfig = Field(default_factory=DirectorConfig, alias="diretor")

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
    # Fase 2: prédios/objetos com estado (inteiro, danificado, destruído)
    structures: list["StructureDef"] = Field(default_factory=list, alias="estruturas")
    # coisas que dá para roubar aqui (texto livre)
    objects: list[str] = Field(default_factory=list, alias="objetos")


class StructureDef(DataModel):
    id: Id
    name: str = Field(alias="nome", min_length=1)


Place.model_rebuild()


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


class Inherited_(DataModel):
    """O que um nascido herdou de um morto recente."""

    from_: Id = Field(alias="de")
    object: str | None = Field(None, alias="objeto")
    quirk: str | None = Field(None, alias="mania")


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
    faction: Id | None = Field(None, alias="faccao")  # Fase 2: igreja, seita... (world.yaml > faccoes)
    # Fase 3: só nos nascidos (data/characters/born/)
    born_at: str | None = Field(None, alias="nascido_em")  # data/hora do mundo do nascimento
    inherited: "Inherited_ | None" = Field(None, alias="herdou")


# --------------------------------------------------------------------------
# traits.yaml (traços, profissões e o "sorteio" dos nascimentos)
# --------------------------------------------------------------------------


class TraitEffects(DataModel):
    needs: dict[Id, Multiplier] = Field(default_factory=dict, alias="necessidades")
    actions: dict[Id, Multiplier] = Field(default_factory=dict, alias="acoes")
    # multiplica a chance de falha (pastelão) de qualquer ação com `falha`
    failure: Multiplier = Field(1.0, alias="falha")


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
    # nome de quem nasce ({n} = número do nascimento); o João renomeia depois no YAML
    default_name: str = Field("O Recém-chegado nº {n}", alias="nome_padrao")
    default_name_she: str = Field("A Recém-chegada nº {n}", alias="nome_padrao_ela")
    home: Id = Field("houses", alias="casa")
    appears_at: Id = Field("town_square", alias="aparece_em")
    default_affinity: Affinity = Field(10, alias="afinidade_padrao")
    # rotina-base de quem nasce (trabalhar sem lugar = no local de trabalho da profissão)
    routine: list[RoutineBlock] = Field(default_factory=list, alias="rotina")

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
    # Fase 2: o alvo precisa ser um destes personagens / ter uma destas profissões
    characters: list[Id] = Field(default_factory=list, alias="personagens")
    professions: list[Id] = Field(default_factory=list, alias="profissoes")


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
    # Fase 2: só quem é de uma destas facções (world.yaml > faccoes)
    factions: list[Id] = Field(default_factory=list, alias="faccoes")


class ActionEffects(DataModel):
    # variação TOTAL ao longo da ação (negativo = satisfaz; positivo = custo)
    needs: dict[Id, float] = Field(default_factory=dict, alias="necessidades")
    target_needs: dict[Id, float] = Field(default_factory=dict, alias="alvo_necessidades")
    affinity: float = Field(0, alias="afinidade")  # minha afinidade com o alvo
    target_affinity: float = Field(0, alias="afinidade_do_alvo")  # a do alvo comigo
    # Fase 2 ---------------------------------------------------------------
    # minha afinidade com personagens específicos (ex.: ir à missa -> {priest: 2})
    affinity_with: dict[Id, float] = Field(default_factory=dict, alias="afinidade_com")
    # efeito extra para quem tem um traço (ex.: briguento bebe e fica esquentado)
    by_trait: dict[Id, dict[Id, float]] = Field(default_factory=dict, alias="por_traco")
    # dano numa estrutura do lugar (ao terminar)
    structure_damage: float = Field(0, alias="dano_estrutura", ge=0)


class ActionFailure(DataModel):
    chance: float = Field(ge=0, le=1)
    effects: ActionEffects = Field(default_factory=ActionEffects, alias="efeitos")
    speech: Id | None = Field(None, alias="fala")
    narration: str | None = Field(None, alias="narracao")  # texto do Chat quando dá errado
    # memória que quem viu forma de quem falhou (ex.: tombo)
    memory: Id | None = Field(None, alias="memoria")


class Observation(DataModel):
    """Quem faz a ação forma uma memória sobre alguém no lugar que esteja fazendo
    uma ação com esta tag (ex.: o Padre espiando o ritual -> memória ritual_visto)."""

    memory: Id = Field(alias="memoria")
    tag: Id


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
    event: Literal["bell", "fight", "argument", "reconcile", "gossip", "prank", "theft", "arrest",
                   "faction", "chase", "ritual", "slapstick"] | None = Field(None, alias="evento")
    # ações sociais: o alvo responde com uma fala desta situação
    target_speech: Id | None = Field(None, alias="fala_alvo")
    target_speech_chance: float = Field(0.5, alias="chance_fala_alvo", ge=0, le=1)
    # Fase 2 ---------------------------------------------------------------
    # automática: nunca é escolhida pela Utility AI, só disparada pelo mundo (fugir, perseguir)
    automatic: bool = Field(False, alias="automatica")
    # ação social: também vale ir atrás do alvo em outro lugar
    seek_target: bool = Field(False, alias="ir_atras")
    # o alvo (e quem viu) forma esta memória sobre quem fez
    memory: Id | None = Field(None, alias="memoria")
    # é infração (world.yaml > leis.infracoes): o Fiscal registra se vir
    infraction: Id | None = Field(None, alias="infracao")
    # fazer as pazes: enfraquece as memórias ruins entre os dois
    reconciles: bool = Field(False, alias="reconcilia")
    # chance de, ao terminar, o alvo sair correndo e quem fez ir atrás
    chase_chance: float = Field(0, alias="chance_perseguicao", ge=0, le=1)
    # conserta estruturas danificadas do lugar (pontos ao longo da ação);
    # só vale em lugar com estrutura danificada
    repairs: float = Field(0, alias="conserta", ge=0)
    # o alvo larga o que estava fazendo e sente o efeito na hora (briga, pegadinha)
    interrupts_target: bool = Field(False, alias="interrompe_alvo")
    # ...e reage com esta ação automática (ex.: emburrar por uns minutos)
    target_reaction: Id | None = Field(None, alias="reacao_alvo")
    # deixa assinatura numa estrutura do lugar (pichação): o Fiscal descobre depois
    signs: bool = Field(False, alias="assina")
    # comportamentos especiais (regra no código, documentada em docs/arquitetura.md)
    special: Literal["fofoca", "confissao", "denuncia", "prender", "roubar", "recrutar", "ordem_reconstruir",
                     "funeral", "tumulo", "criatura", "assembleia"] | None = Field(
        None, alias="especial")
    # recrutar: para qual facção
    faction: Id | None = Field(None, alias="faccao")
    observe: Observation | None = Field(None, alias="observa")

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
    # quem sente as `necessidades`: quem está no lugar, ou a cidade inteira
    needs_for: Literal["lugar", "todos"] = Field("lugar", alias="necessidades_para")
    goal: Goal | None = Field(None, alias="objetivo")
    weather: str | None = Field(None, alias="clima")  # força um tipo de clima (world.yaml > clima.tipos)
    weather_minutes: int = Field(120, alias="clima_minutos", gt=0)
    creature: Id | None = Field(None, alias="criatura")  # faz aparecer uma criatura (creatures.yaml)
    # regras raras com código próprio: fantasma, ressurreição natural
    special: Literal["fantasma", "ressurreicao"] | None = Field(None, alias="especial")
    memory: Id | None = Field(None, alias="memoria")  # quem sentiu o evento lembra (tipo de memória)


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
    # eventos raros/lendários não entram na conta da tensão: são sorteados sozinhos
    # com esta chance por dia (fantasma e ressurreição usam os `limites` do world.yaml)
    chance_per_day: float | None = Field(None, alias="chance_por_dia", ge=0, le=1)


class CreatureTexts(DataModel):
    appears: list[str] = Field(alias="aparece", min_length=1)
    leaves: list[str] = Field(alias="some", min_length=1)
    beaten: list[str] = Field(default_factory=list, alias="vencida")
    attack: list[str] = Field(default_factory=list, alias="ataque")


class CreatureDef(DataModel):
    """Uma criatura do bestiário (data/events/creatures.yaml)."""

    id: Id
    name: str = Field(alias="nome", min_length=1)
    description: str = Field("", alias="descricao")
    places: list[Id] = Field(alias="lugares", min_length=1)
    periods: list[Id] = Field(default_factory=list, alias="periodos")
    chance_per_hour: float = Field(0, alias="chance_por_hora", ge=0, le=1)  # nos períodos acima
    duration_minutes: tuple[int, int] = Field((60, 180), alias="duracao_minutos")
    fear: float = Field(30, alias="medo", ge=0)  # medo de quem está lá quando aparece (metade por hora)
    danger: float = Field(30, alias="perigo", ge=0)  # soma ao perigo do lugar enquanto está lá
    win_chance: float = Field(0.4, alias="chance_vencer", ge=0, le=1)
    experts: list[Id] = Field(default_factory=list, alias="especialistas")  # profissões que vencem mais
    # homelab: só aparece quando um serviço real cai (homelab/servicos/#) e só some quando volta
    homelab: bool = Field(False, alias="homelab")
    goal_professions: list[Id] = Field(default_factory=list, alias="chama_profissoes")
    goal_bonus: float = Field(6, alias="bonus_objetivo", gt=0)
    texts: CreatureTexts = Field(alias="textos")
    importance: int = Field(2, alias="importancia", ge=0, le=3)


class OrganizerRule(DataModel):
    """Quem pode ter a ideia de organizar (vale quem bate com QUALQUER item)."""

    characters: list[Id] = Field(default_factory=list, alias="personagens")
    traits: list[Id] = Field(default_factory=list, alias="tracos")
    professions: list[Id] = Field(default_factory=list, alias="profissoes")
    groups: list[Id] = Field(default_factory=list, alias="grupos")
    factions: list[Id] = Field(default_factory=list, alias="faccoes")


class SocialEventTexts(DataModel):
    planned: list[str] = Field(alias="planejado", min_length=1)
    started: list[str] = Field(alias="comeca", min_length=1)
    failed: list[str] = Field(alias="fracassa", min_length=1)
    ended: list[str] = Field(alias="termina", min_length=1)


class SocialEventDef(DataModel):
    """Evento organizado pelos NPCs (festa, rave, rodeio, casamento, mutirão...).

    Um NPC que bate com `organizadores` e tem as `vontade` altas pode ter a ideia
    (`chance_por_hora`). Ele marca lugar e hora, convida pela afinidade, e os
    convidados ganham um objetivo (bônus na nota da `acao` naquele lugar e hora).
    Na hora, acontece se houver `quorum` pessoas lá; senão, fracassa."""

    id: Id
    name: str = Field(alias="nome", min_length=1)
    action: Id = Field(alias="acao")
    place: Id | None = Field(None, alias="lugar")
    # "dano": o lugar é onde há uma estrutura danificada (mutirão)
    where: Literal["fixo", "dano"] = Field("fixo", alias="onde")
    organizers: OrganizerRule = Field(alias="organizadores")
    desire: dict[Id, Percent] = Field(default_factory=dict, alias="vontade")
    chance_per_hour: float = Field(alias="chance_por_hora", ge=0, le=1)
    start_window: TimeWindow = Field(alias="comeca_entre")
    lead_hours: tuple[float, float] = Field((1, 3), alias="antecedencia_horas")
    duration_hours: tuple[float, float] = Field((2, 3), alias="duracao_horas")
    invite_affinity_min: float = Field(20, alias="convite_afinidade_min")
    max_guests: int = Field(8, alias="max_convidados", ge=0)
    quorum: int = Field(3, ge=1)
    bonus: float = Field(4, gt=0)
    cooldown_hours: float = Field(24, alias="cooldown_horas", ge=0)
    # casamento: precisa de um par com afinidade mútua mínima (o par vira {outro})
    partner_affinity_min: float | None = Field(None, alias="par_afinidade_min")
    # o par não pode ter com o organizador uma relação destes tipos (irmao, mae...)
    partner_forbidden_kinds: list[str] = Field(default_factory=list, alias="par_tipos_proibidos")
    # quem nunca entra como par (nem organiza) neste evento
    excluded: list[Id] = Field(default_factory=list, alias="excluidos")
    memory: Id | None = Field(None, alias="memoria")
    failure_memory: Id | None = Field(None, alias="memoria_fracasso")
    texts: SocialEventTexts = Field(alias="textos")
    importance: int = Field(2, alias="importancia", ge=0, le=3)
    tags: list[Id] = Field(default_factory=lambda: ["evento"])

    @model_validator(mode="after")
    def _place(self) -> "SocialEventDef":
        if self.where == "fixo" and self.place is None:
            raise ValueError("evento social com onde: fixo precisa de 'lugar'")
        return self


class EventsFile(DataModel):
    events: list[dict] = Field(default_factory=list, alias="eventos")
    social_events: list[dict] = Field(default_factory=list, alias="eventos_sociais")
    creatures: list[dict] = Field(default_factory=list, alias="criaturas")


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
    # Fase 2: só se quem fala lembra de algo deste tipo envolvendo o alvo (ou
    # qualquer um, se não houver alvo). A memória vira a variável {lembranca}.
    memory: list[Id] = Field(default_factory=list, alias="memoria")
    # Fase 3: só quando o morto da situação (funeral, luto, fantasma) é um destes
    dead: list[Id] = Field(default_factory=list, alias="mortos")
    # Fase 3: só para quem tem uma destas profissões (vale para quem assumir o papel)
    professions: list[Id] = Field(default_factory=list, alias="profissoes")

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


DeathConsequence.model_rebuild()
Character.model_rebuild()
