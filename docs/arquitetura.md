# Arquitetura — Divine Machinery: o Mundo Vivo

> Documento vivo. Escrito na Fase 0 como **plano** das fases 1 a 5; cada fase atualiza a seção
> correspondente com o que foi de fato implementado (e marca o que mudou em relação ao plano).
> Legenda de estado: ✅ implementado · 🟡 parcial · 📐 planejado.

## 1. Visão geral

```
                 ┌──────────────────────── processo único (homelab, Docker) ───────────────────────┐
 data/*.yaml ──► │ sim.loader ──► WorldData (somente leitura, recarregável)                         │
                 │                     │                                                            │
                 │                     ▼                                                            │
                 │  sim.engine.World  (thread da simulação, dona do estado)                         │
                 │     tick: relógio → necessidades → decisões → ações → sistemas → diretor          │
                 │     │ publica Event                                  ▲ consome Command            │
                 │     ▼                                                │                            │
                 │  sim.events.EventBus ──► persistência (SQLite)       │                            │
                 │        │      │      └─► terminal (tools.run, rich)  │                            │
                 │        │      └────────► server.ws (WebSocket /ws?screen=)  ◄── viewer (telas)    │
                 │        └───────────────► server.mqtt_bridge ◄──────────────► Mosquitto           │
                 │                               (só enfileira comandos)        (world/*, leds/*)   │
                 │  server.app (FastAPI REST) ── lê snapshot / envia Command ───┘                    │
                 └──────────────────────────────────────────────────────────────────────────────────┘
 Opcionais: Ollama (sim.llm, timeout curto) · Open-Meteo (sim.weather, com cache)
```

Princípios que guiam tudo (ver `CLAUDE.md`): a simulação é a fonte da verdade e roda sem nenhuma
tela; dados fora do código; `id` estável e `nome` editável; funciona sem LLM, sem MQTT e sem
internet; toda decisão é explicável no log.

### 1.1 Processos e threads (Fase 1 e 4)

- **Um processo só.** `python -m tools.run` (Fases 1-3) roda a simulação headless com o Chat do
  Mundo no terminal. `python -m server` (Fase 4) roda a mesma simulação **e** a API/WebSocket/MQTT.
  Nunca dois processos escrevendo no mesmo SQLite.
- **Thread da simulação** (`sim.engine.World.run_forever`): é a única que altera o estado. Laço
  síncrono, simples de ler e de testar.
- **Entrada de comandos:** `queue.Queue[Command]`. API HTTP, CLI e o handler MQTT só colocam
  comandos na fila (regra do ecossistema: nada pesado dentro de handler MQTT). O tick drena a fila
  no começo.
- **Saída de eventos:** `EventBus` com assinantes. Assinantes rodam no thread da simulação e
  precisam ser rápidos: o do WebSocket faz `loop.call_soon_threadsafe(queue.put_nowait, ev)` para
  o asyncio do FastAPI; o do MQTT chama `client.publish` (não bloqueia com `loop_start()`).
- **Leitura pela API:** `World.snapshot()` devolve um dicionário imutável (cópia) protegido por um
  `threading.Lock` curto. A API nunca toca no estado vivo.

## 2. Estrutura de pastas e módulos

```
sim/                      simulação (Python puro, sem rede, exceto weather/llm)
  schemas.py        ✅ F0  esquemas pydantic de tudo que mora em data/
  loader.py         ✅ F0  lê data/, expande ${ENV}, valida, cruza referências, monta o grafo
  curves.py         ✅ F0  curvas de resposta da Utility AI
  text.py           ✅ F0  templates: variáveis, tokens {@id}, render com nomes atuais
  clock.py          ✅ F1  relógio do mundo (passo fixo), períodos, dia/noite, hora inicial
  rng.py            ✅ F1  random.Random com seed; salvar/restaurar estado; sorteio ponderado
  state.py          ✅ F1  dataclasses do estado vivo: CharacterState, Activity, Plan, MoveStep
  needs.py          ✅ F1  variação das necessidades por tick (taxas, traços, dia/noite), {humor}
  pathfinding.py    ✅ F1  Dijkstra no grafo (minutos), ignora névoa e lugares sem acesso
  utility.py        ✅ F1  candidatos, nota, escolha ponderada, explicação, nota da ação atual
  speech.py         ✅ F1  escolhe template por situação/filtros, evita repetição recente
  events.py         ✅ F1  Event + EventBus + tipos
  persistence.py    ✅ F1  SQLite: schema, migrações simples, salvar/carregar, consulta do chat
  engine.py         ✅ F1  World: monta tudo, tick(), run(), catch_up(), snapshot(), comandos
                           (o "executor de planos" planejado em actions.py ficou dentro do
                           engine: é pouco código e depende de tudo do World)
  relations.py      ✅ F2  afinidade viva por par, volta devagar ao valor inicial
  memory.py         ✅ F2  memórias com intensidade, sentimento, decaimento e frases
  gossip.py         ✅ F2  repasse de memórias com distorção; segredos de confissão
  structures.py     ✅ F2  construções com estado (inteiro/danificado/destruído) e assinaturas
  law.py            ✅ F2  infrações, pontos, advertência, mandado, prisão, Limbo
  factions.py       ✅ F2  Igreja × Seita: entrar/sair pela afinidade com os líderes
  social_events.py  ✅ F2  eventos organizados pelos NPCs (festa, rave, rodeio, procissão,
                           casamento, mutirão)
                           (ganância — roubo, esconderijo, sumiço, achado — e as
                           perseguições ficaram no engine: dependem de tudo do World)
  lifecycle.py      📐 F3  morte, funeral, luto, fantasmas, nascimentos, sucessão
  creatures.py      📐 F3  criaturas noturnas e as da Sala do Servidor (homelab)
  weather.py        📐 F3  Open-Meteo com cache e fallback
  screens.py        📐 F3  telas online/offline → névoa nos lugares
  director.py       📐 F3  tensão do mundo e injeção de eventos de data/events
  commands.py       📐 F4  comandos do Criador (chefe, medium, reviver, nascer, ...)
  llm.py            📐 F4  cliente Ollama opcional (httpx, timeout curto, limite/hora)
  presence.py       📐 F4  o olhar e a Aparição (sala/camera/pessoas)
server/
  app.py            📐 F4  FastAPI: REST + WebSocket
  ws.py             📐 F4  gerência de conexões por tela, filtro por lugares da tela
  mqtt_bridge.py    📐 F4  paho-mqtt 2.x (CallbackAPIVersion.VERSION2), reconexão, LWT
  __main__.py       📐 F4  `python -m server`: sobe World + uvicorn + MQTT
tools/
  validate.py       ✅ F0  `python -m tools.validate`
  run.py            ✅ F1  `python -m tools.run --speed 60 [--fast] [--horas N|--dias N] [--personagem id]
                           [--lugar id] [--movimento] [--debug] [--resumo] [--saida arq] [--novo]
                           [--seed N] [--inicio HH:MM] [--banco arq]`
  report.py         📐 F3  `python -m tools.report --days 7`: relatório de variedade
  cli.py            📐 F4  `python -m tools.cli chefe "..."` (fala com a API)
viewer/             📐 F5  Three.js + Vite; index.html?screen=<id>, chat.html, layout.html
tests/              pytest (um arquivo por módulo)
var/                (fora do git) SQLite, cache de clima, logs
```

## 3. Dados (`data/`) ✅ F0

### 3.1 Arquivos

| Arquivo | Conteúdo | Esquema |
|---|---|---|
| `world.yaml` | relógio, necessidades, Utility AI, limites, regiões, grupos, categorias do chat, clima, MQTT, Ollama, servidor, persistência, túnel, telas | `WorldConfig` |
| `places/<id>.yaml` | um lugar por arquivo | `Place` |
| `characters/<id>.yaml` e `characters/born/<id>.yaml` | um personagem por arquivo | `Character` |
| `actions/*.yaml` | `acoes: [ ... ]` (vários por arquivo, por tema) | `Action` |
| `events/*.yaml` | `eventos: [ ... ]` | `WorldEvent` |
| `lines/*.yaml` | `situacoes: {<situacao>: [falas]}` (situações de vários arquivos se somam) | `LineTemplate` |
| `traits.yaml` | `tracos`, `profissoes`, `aparencias`, `nascimento` | `TraitsFile` |

Arquivos que começam com `_` são ignorados (ex.: `characters/_MODELO.yaml`).

### 3.2 Convenções

- **Chaves do YAML em português sem acento; atributos Python em inglês** (via `alias` do pydantic,
  com `populate_by_name=True`). Ex.: `Character.name` ⇄ `nome`, `Character.traits` ⇄ `tracos`,
  `Relation.with_` ⇄ `com`. A fonte da verdade do mapeamento é `sim/schemas.py`. Erros de
  validação sempre citam a chave do YAML.
- **Ids:** `^[a-z][a-z0-9_]*$`. Personagens e lugares em inglês (`chef_wife`, `town_square`);
  vocabulário de conteúdo em português snake_case (ações `brigar`, necessidades `fome`, traços
  `preguicoso`, períodos `noite`, categorias `seita`). Personagens e lugares compartilham o mesmo
  espaço de ids (o validador garante), por causa dos tokens `{@id}`.
- **Nomes nunca são chave de nada.** Relações, herdeiros, rotina, falas, banco e memória usam ids.
  Renomear = editar a linha `nome:` de um arquivo (teste `tests/test_rename.py`).
- **Variáveis de ambiente** só no `world.yaml`: `${VAR}` e `${VAR:-padrão}` (`sim.loader.expand_env`).
  Nada de IP, senha ou caminho absoluto no repositório. `.env.example` lista as variáveis.
- `campo desconhecido` é erro (`extra="forbid"`): pega erro de digitação e sugere a chave certa.

### 3.3 Carregador e validador

`sim.loader.load_data(pasta) -> (WorldData | None, Report)`. Nunca para no primeiro erro. Valida
cada arquivo (e cada item de listas) separadamente, depois cruza referências:

- ids repetidos; personagem × lugar com mesmo id;
- referências inexistentes (traço, profissão, lugar, ação, necessidade, personagem, período,
  grupo, região), com sugestão (`Você quis dizer...?`) e detecção de **nome usado no lugar de id**;
- grafo: conexão para lugar inexistente, conexão consigo mesmo, declarações conflitantes dos dois
  lados, **lugar `normal` sem conexão**, **lugar isolado** (sem caminho até `lugar_central`);
- telas: lugar em duas telas, lugar inexistente; avisos para `tunel` dentro da mesma tela e
  `caminho` atravessando telas;
- ações: entradas de consideração válidas (`afinidade` só com alvo), situação de fala existente;
- falas e textos de eventos: variáveis conhecidas, `{@id}` existente, chaves balanceadas; **aviso**
  quando um nome de personagem está escrito por extenso (não acompanharia uma renomeação).

`WorldData` expõe: `places`, `characters`, `actions`, `traits`, `professions`, `lines`, `events`,
`graph` (não direcionado: `dict[place_id, list[Edge(to, kind, minutes)]]`), `names()`,
`name_of(id)`, `screen_of(place)`, `affinity(a, b)` (afinidade **inicial**).

`load_data_or_raise()` lança `DataError` (usado pelo engine). Recarregar (Fase 6): carregar de
novo; se tiver erro, manter o `WorldData` anterior e publicar evento `system` com o relatório.

## 4. Relógio e tick ✅ F1

- `world_time = âncora_mundo + (agora_real − âncora_real) × multiplicador`, no fuso
  `relogio.fuso`. Com multiplicador 1, o mundo segue o relógio real (dia e noite reais).
  `World.run()` refaz a âncora quando a velocidade muda ou ao despausar.
- **Passo fixo:** cada tick avança `passo_minutos` (padrão 1 min do mundo). O intervalo real entre
  ticks é `passo×60/multiplicador` segundos; `--fast` (testes, `tools.report`) não dorme.
  Se a máquina atrasar, o laço faz vários ticks seguidos para alcançar (máx. 600 por rodada).
  Medido: um dia inteiro (1440 ticks, 21 NPCs) leva ~4 s em `--fast`.
- **Mundo novo:** começa na hora real (ou `--inicio`). Quem tem um bloco de rotina de uma ação
  `dormindo: true` valendo naquela hora já começa dormindo em casa até o fim do bloco (senão um
  mundo criado às 3h teria a cidade inteira acordada).
- **Retomada:** o tempo do mundo salvo no SQLite é a âncora. Com multiplicador 1, ao religar, simula
  em modo rápido até `max_recuperacao_horas` do tempo perdido; o resto é pulado com um evento
  `system` ("o mundo cochilou por N horas"). Com outro multiplicador (testes) continua da hora
  salva. Seed, estado do RNG, cooldowns, próxima reavaliação e falas recentes também são salvos:
  parar e continuar dá exatamente a mesma história que rodar direto (teste).
- Período = último `relogio.periodos[*].das` ≤ hora. `é_noite` = hora ≥ `noite_comeca` ou <
  `dia_comeca`. Mudança de período gera evento `period_changed`.

### 4.1 Ordem de um tick

```
1. drenar comandos (fila)                                   ✅ F1 (pausar/continuar/velocidade), F4 (resto)
2. avançar relógio; emitir period_changed se mudou           ✅ F1
3. atualizar clima (cache; no máx. a cada atualizar_minutos) F3
4. necessidades: para cada vivo, variar por taxa + efeito proporcional da ação em andamento  ✅ F1
5. memórias e relações: decaimento lento (1×/hora do mundo)  ✅ F2 (passo 9, junto do resto)
6. ações em andamento: terminar as que acabaram (emite action_finished)                      ✅ F1
7. movimento: avançar planos; chegadas e túneis; ao chegar, começa a ação                    ✅ F1
8. decisões: cada NPC livre decide; quem está ocupado é reavaliado (seção 6.5)               ✅ F1
   (ordem embaralhada pelo RNG; quem decidiu entra na contagem de "presentes" dos próximos)
9. sistemas: solturas (prisão/Limbo) e eventos sociais a cada tick; de hora em hora:
   memórias decaem, afinidades voltam, pontos da lei somem, facções, ideias de eventos ✅ F2
   criaturas, morte/nascimento, telas                                                  F3
10. diretor: 1× a cada 10 min do mundo                        F3
11. snapshot para a API; commit dos eventos; salvar estado a cada salvar_a_cada_minutos (e ao sair)  ✅ F1
```
(Na implementação, movimento vem antes das decisões — diferente do plano — para quem chega
num lugar já começar a ação no mesmo tick e quem fica livre já decidir. Na F2 os sistemas
(passo 9) rodam antes das decisões, pelo mesmo motivo: quem acabou de ser solto ou chegou
numa festa já decide no mesmo tick.)

## 5. Necessidades ✅ F1

Definidas em `world.yaml > necessidades` (hoje: `fome, sono, social, fe, tedio, raiva, medo`).
Valor 0..100; **maior = mais urgente**.

```
taxa_base = taxa_noite se é_noite senão taxa_dia
mult      = personagem.necessidades[n].taxa (padrão 1) × Π traço.efeitos.necessidades[n]
modo acumula: valor += taxa_base × mult × dt_horas
modo retorna: valor se aproxima de base em taxa_base × mult × dt_horas (sem passar)
efeito da ação em andamento: += efeito_total × (dt / duração)
clamp 0..100
```

Personagem numa ação com `dormindo: true` (`dormir`, `cochilar`) não ganha sono. Cada
necessidade pode ter `humor` (ex.: fome → "faminto"): a variável `{humor}` das falas usa a
necessidade mais alta acima de 60, ou `humor_neutro`. (Os alertas `need_alert` planejados ficaram
para quando houver quem os use.)

## 6. Utility AI ✅ F1

### 6.1 Candidatos

Para um NPC livre, gera pares (ação, lugar[, alvo]):

- ações com `ativa: true` e `tipo != movimento`;
- lugar candidato = atual ou qualquer lugar alcançável (sem névoa, sem `acesso: especial/nunca`
  salvo regra explícita). A ação vale num lugar se: `em_qualquer_lugar`, ou está em `place.acoes`,
  ou `condicoes.lugar_proprio` = `trabalho` (lugar = `local_trabalho`) / `casa` (lugar = `casa`);
- `condicoes`: `periodos`, `horarios` (qualquer janela), `profissoes`, `tracos` (tem algum),
  `personagens` (é um deles), `necessidades_min` (todas acima);
- ações `social`: um candidato por alvo **presente no lugar atual**, acordado (não está numa
  ação `dormindo`), parado (não está andando), fora do Limbo, que passa em `afinidade_min/max`
  e em `alvo.personagens`/`alvo.profissoes` (F2). Com `ir_atras: true` (F2) o alvo pode estar
  em qualquer lugar alcançável: o candidato é (ação, lugar do alvo, alvo) com o custo da
  viagem; se ao chegar o alvo já saiu, sai o evento `missed` ("procura e não acha");
- ações `automatica: true` (F2: `fugir`, `perseguir`) nunca são candidatas: o mundo as dispara;
- ações com `especial` (F2) têm uma regra de validade: só há `fofocar` se houver fofoca nova
  para aquele ouvinte, `prender` se o alvo tem mandado, `denunciar` se lembro de uma infração
  ainda não contada, `confessar` se tenho algo meu para confessar, `recrutar` se o alvo não é
  da facção, `roubar` se o lugar ainda tem `objetos`, `mandar_reconstruir` se há estrago; ações
  com `conserta` só valem em lugar com estrutura danificada;
- **preso** (F2): só valem ações no lugar `leis.prisao` (a "casa" vira a cela e
  `leis.acoes_na_prisao` — comer — vale lá);
- ações `em_qualquer_lugar` (conversar, encarar a tela) e `vagar` (perambular) valem só no lugar
  atual — mais o lugar de um bloco de rotina ativo com essa ação, se o bloco der `lugar`;
- `cooldown_minutos`: a ação não é candidata até passar esse tempo desde que terminou (o sino
  toca uma vez por janela).

### 6.2 Nota

```
nota = peso
     × Π curva_i(entrada_i)                    # considerações do YAML (cada uma 0..1)
     × Π traço.efeitos.acoes[ação]             # traços do personagem
     × rotina                                  # bloco ativo com essa ação (e lugar, se dado): × peso
     × objetivos                               # maior bônus entre os objetivos ativos ✅ F2
     × viagem                                  # 0.5 ^ (minutos_de_viagem / meia_vida_viagem_minutos)
     × repetição                               # × penalidade_repeticao se foi a última ação
```

Entradas (`sim.curves.INPUT_RANGES`): `necessidade.<id>` (0..100), `alvo_necessidade.<id>`
(0..100), `afinidade` (−100..100), `hora` (0..24 com fração), `presentes` (0..20), `perigo`
(0..100; usa `perigo_noite` à noite), `tensao` (0..100; 50 até a Fase 3). Novas entradas
(ex.: `clima`) entram em `INPUT_RANGES` + `utility.read_input` + validador
(`curves.DOTTED_INPUTS`/`TARGET_INPUTS`).

Entradas da F2 ✅: `afinidade_inicial` (a do YAML com o alvo: o "amor de fundo"),
`afinidade_com.<id>`, `presenca.<id>` (0/1: alguém está no lugar candidato), `faccao.<id>`
(0/1), `conflito_alvo` (minha memória ruim mais forte de algo entre mim e o alvo),
`memoria.<tipo>`, `memoria_alvo.<tipo>`, `fofoca` (suculência da melhor fofoca para o alvo),
`denuncia` (memória de infração ainda não contada), `dano` (estrago do lugar candidato),
`dano_cidade` (pior estrago do mundo), `mandado` (0/1).

**Objetivos** (F2 ✅): `World.goals` é uma lista de `{who, action, place, bonus, start, end,
source}` (`who`/`place` = None vale para todos/qualquer lugar). Na nota entra o **maior** bônus
ativo para (quem, ação, lugar). Quem cria: os convites dos eventos sociais e a ordem do Chefe
(`mandar_reconstruir`); o diretor (F3) e os comandos (F4) vão usar o mesmo mecanismo. No minuto
em que um objetivo começa, quem ele cobre é reavaliado (é assim que os convidados largam o que
fazem e vão para a festa).

### 6.3 Curvas (`sim.curves`)

```yaml
consideracoes:
  - entrada: necessidade.fome
    curva: {tipo: pontos, pontos: [[0, 0], [30, 0.1], [60, 0.6], [85, 1]]}   # liga os pontos (valor cru)
  - entrada: perigo
    curva: {tipo: linear, inverter: true, minimo: 0.05}    # normaliza pela faixa da entrada
  - entrada: necessidade.raiva
    curva: {tipo: logistica, meio: 70, inclinacao: 0.12}   # S em torno de 70 (valor cru)
  - entrada: necessidade.raiva
    curva: {tipo: potencia, expoente: 2}                   # normalizada, x²
  - entrada: necessidade.fe
    curva: {tipo: degrau, limite: 50}                      # 0 abaixo, 1 a partir de 50 (valor cru)
```

`inverter` faz `1 − y`; `minimo` é o piso do fator. Saída sempre em `[minimo, 1]`.

### 6.4 Escolha e explicação

1. descarta notas < `nota_minima`; ordena (nota, depois rótulo, para ser estável); pega as `top_n`;
2. das `top_n`, descarta as que valem menos que `melhor × fracao_da_melhor` (0.4): sem isso, nas
   horas mornas o 3º lugar (às vezes bobo) saía com frequência demais;
3. sorteia proporcional a `nota^(1/temperatura)` com o RNG do mundo;
4. se não sobrou nada: a ação `vagar` (perambular), ou ficar parado 10 min (`_parado`).

Toda decisão gera log `debug` (logger `sim.engine`) e o evento `decision` (não vai para o SQLite
nem para o MQTT; `tools.run --debug` mostra). Saída real:

```
[09/11 06:00] (A Prisão) O Padre escolheu tocar_sino@cathedral (126.13) | top3:
tocar_sino@cathedral 126.13, trabalhar@cathedral 0.62, comer@community_kitchen 0.21
    tocar_sino: peso×30.00 × rotina×5.00 × viagem 5min×0.84
```

`utility.explain()` monta esse texto; o evento `decision` traz a mesma coisa como estrutura
(`data.top = [[rótulo, nota]]`, `data.factors = [[fator, valor]]`), e
`CharacterState.last_explanation` guarda a última (para o `quem <id>` da Fase 4).

### 6.5 Reavaliação e interrupção (detalhe da F1)

Uma ação em andamento não é sagrada. Quem está ocupado (e parado) é reavaliado a cada
`reavaliar_a_cada_minutos` (10; espalhado por personagem) **e** nos minutos em que começa um bloco
da sua rotina ou uma janela `horarios` de ação que ele pode fazer (é isso que põe o Padre no sino
às 06:00 em ponto, quando ele está por perto):

- `nota_atual` = nota da ação em andamento agora (sem viagem nem repetição; 0 se as condições
  deixaram de valer, ex.: acabou o período de trabalho);
- se `nota_atual < nota_minima`: para e decide de novo (ex.: quem ainda dorme às 10h sem rotina
  de dormir acorda);
- se a melhor outra opção ≥ `max(nota_para_interromper, nota_atual × fator_interrupcao)`, larga a
  atual (`action_finished` com `interrupted: true`) e faz a nova. Para quem está **dormindo**, o
  mínimo é `nota_para_acordar` (2.0): só a rotina de trabalho ou o sino acordam alguém.

## 7. Ações e planos ✅ F1

- Uma decisão vira um **plano**: `[andar/viajar ..., ação]`. O caminho vem de `pathfinding`
  (Dijkstra pelos `minutos`; evita névoa e acesso especial/nunca).
- Cada passo de movimento dura os `minutos` da conexão. Conexão `caminho` → eventos
  `move_started` / `move_arrived`. Conexão `tunel` → `teleport_started` (com `from_place`,
  `to_place`, `from_screen`, `to_screen`, `duration_s` real calculada pela distância física entre
  as telas ÷ `tunel.velocidade_led_cm_por_s`, mínimo `duracao_minima_s`) e `teleport_finished`.
- Ação: duração sorteada em `duracao_minutos`; efeitos aplicados aos poucos (seção 5); ao começar,
  com `chance_fala`, sai uma fala da situação `fala`. Ações sociais aplicam `alvo_necessidades` e
  as afinidades no fim. `falha` (F2): sorteio no início; se falhar, aplica `falha.efeitos` e a fala
  `falha.fala` no lugar dos normais (traço `desastrado` aumenta a chance — regra no código).
- `perambular` (`vagar: true`): sorteia um lugar vizinho (sem névoa, acesso normal), com peso
  `(1 − perigo/100)²` — lugares perigosos atraem menos, **exceto para quem tem a imunidade
  `criaturas`** (o Mike vai a qualquer lugar com a mesma chance). É o comportamento do Mike.
- Campos novos das ações (F1): `narracao` / `narracao_fim` (texto do Chat do Mundo no começo e no
  fim; sem `narracao`, "{eu} vai <nome da ação> em {lugar}."), `dormindo`, `vagar`,
  `cooldown_minutos`, `evento: bell` (o começo da ação vira um evento `bell` em vez de
  `action_started`), `fala_alvo` + `chance_fala_alvo` (o alvo de uma ação social responde).
- Durante a ação, o efeito em `necessidades` é aplicado aos poucos; no fim (ou na interrupção),
  `alvo_necessidades` e as afinidades são aplicados proporcionalmente ao tempo que durou.
- Afinidade viva: `World.affinities` guarda só os pares que mudaram desde o YAML (tabela
  `relations`, já criada na F1). A F2 cuida do retorno lento e da memória.
- Interrupção (F2 ✅): ação com `interrompe_alvo: true` (discutir, brigar, pregar uma peça)
  faz o alvo largar o que estava fazendo e aplica `alvo_necessidades` na hora; o alvo decide de
  novo no mesmo tick (e pode revidar, fugir, pedir ajuda...). Prisão, Limbo, fuga e perseguição
  também interrompem.
- `falha` (F2 ✅): sorteada no começo com `chance × Π traço.efeitos.falha` (máx. 95%). Se falha:
  evento `slapstick`, fala `falha.fala`, `falha.efeitos` no lugar dos efeitos normais, nada no
  alvo, memória `falha.memoria` (ex.: `tombo`) para quem viu.
- Campos novos das ações (F2), todos no YAML: `ir_atras`, `memoria`, `infracao`,
  `interrompe_alvo`, `reconcilia`, `chance_perseguicao`, `conserta`, `assina`, `automatica`,
  `especial`, `faccao`, `observa: {memoria, tag}`, `efeitos.afinidade_com`,
  `efeitos.por_traco`, `efeitos.dano_estrutura`, e `evento` aceita `fight, argument,
  reconcile, gossip, prank, theft, arrest, faction, chase, ritual, slapstick`. Explicação de
  cada um no topo de `data/actions/sociais.yaml`.
- Hoje nenhuma ação está `ativa: false` (a F2 ligou `ritual`, `brigar`, `fofocar`, `consolar`,
  `roubar`, `construir`, `quebrar`).

## 8. Eventos ✅ F1

Tudo que acontece é um `Event` (dataclass), publicado no `EventBus`, gravado no SQLite e enviado
ao WebSocket/MQTT. Formato JSON (chaves em inglês, como no resto do ecossistema):

```json
{
  "id": 18234,
  "ts": "2026-11-09T15:02:00-03:00",
  "real_ts": "2026-11-09T18:02:11Z",
  "type": "speech",
  "tags": ["conversa"],
  "importance": 0,
  "actors": ["chef_wife", "chef_husband"],
  "place": "community_kitchen",
  "text": "{@chef_wife}: \"Come que esfria!\"",
  "text_rendered": "A Cozinheira: \"Come que esfria!\"",
  "data": {"situation": "conversa", "action": "conversar"}
}
```

- `ts` é o tempo do **mundo** (ISO com fuso); `real_ts`, o tempo real (UTC).
- `actors[0]` é quem faz; os demais são alvos/participantes. Sempre ids.
- `text` guarda **tokens de id** (`{@id}`); `text_rendered` é gerado na saída com os nomes atuais
  (`sim.text.render`). O banco guarda só `text`: renomear muda até o histórico.
- `importance`: 0 rotina · 1 interessante · 2 marcante · 3 grande acontecimento (linha do tempo).
- `tags`: ids de `world.yaml > categorias_chat` (filtros do Chat do Mundo).
- `id` é sequencial por mundo (`meta.last_event_id`), dado pelo `World` (não pelo SQLite).
- `render()` também faz as contrações do português quando o nome começa com artigo
  ("em A Praça" → "na Praça", "rumo a A Praça" → "rumo à Praça"; `sim.text.contract`).

`data` por tipo (F1): `action_started`/`bell`: `action, target, minutes, score, spoke` (se saiu
fala junto) · `action_finished`: `action, interrupted, minutes` · `speech`: `situation, action`
(+ `reply_to` na resposta) · `move_*`: `from, to, minutes, destination, final` ·
`teleport_*`: o mesmo + `from_place, to_place, from_screen, to_screen, duration_s` (distância
entre os centros das telas ÷ `velocidade_led_cm_por_s`, mínimo `duracao_minima_s`) ·
`period_changed`: `period, is_night` · `system`: livre.

`data` da F2: começo de ação com `evento` (`fight`, `argument`...): o mesmo de `action_started`
+ `failed` · `gossip`: `memory_kind, about, true_subject, distorted, secret` · `infraction`:
`infraction, offender, how (flagrante|assinatura|denuncia), reporter, points, verdict`
(a advertência que segue traz `warning: true`) · `arrest`/`limbo_in`: `offender, infraction` ·
`suspicion`: `object, suspect, thief, right` (o suspeito acertou?) · `structure_changed`:
`structure, from, to, hp` · `faction`: `faction, change (join|leave)` · `social_event_*`:
`social_event, instance, organizer, guests, start, participants, result (sucesso|fracasso)` ·
`relation_changed`: `affinity, initial, mark (amigos|inimigos)`.

Tipos (`type`) planejados:

| Fase | Tipos |
|---|---|
| F1 | `system`, `period_changed`, `decision` (debug), `action_started`, `action_finished`, `speech`, `move_started`, `move_arrived`, `teleport_started`, `teleport_finished`, `bell` |
| F2 ✅ | `relation_changed`, `gossip`, `argument`, `fight`, `reconcile`, `prank`, `slapstick`, `chase`, `theft`, `suspicion`, `found`, `missed`, `structure_changed`, `infraction`, `arrest`, `released`, `limbo_in`, `limbo_out`, `faction`, `ritual`, `social_event_planned`, `social_event_started`, `social_event_ended` (o `memory_formed` planejado não foi criado: cada briga gera memórias em todas as testemunhas e inundaria o Chat; as memórias ficam no banco e aparecem nas falas) |
| F3 | `death`, `funeral_started`, `funeral_ended`, `grief`, `ghost`, `birth`, `succession`, `creature_spawned`, `creature_gone`, `weather_changed`, `fog_on`, `fog_off`, `director_event`, `tension` |
| F4 | `creator_command`, `creator_order`, `creator_voice`, `resurrection`, `stare`, `apparition` |

## 9. Falas ✅ F1

`sim.speech.pick(situação, falante, alvo, lugar, contexto)`:

1. junta `lines[situação]`; filtra por `personagens`, `tracos`, `lugares`, `periodos`, `climas`,
   `necessidades_min` (filtro vazio = vale para todos);
2. falas específicas do personagem ganham prioridade natural pelo `peso` (o YAML decide);
3. remove as usadas nos últimos N eventos do mesmo falante (anti-repetição, N=8);
4. sorteia por `peso`; preenche variáveis com `sim.text.fill` (ids viram `{@id}`).

Falas que pedem o que não existe agora são puladas: `{outro}`/`{bordao_outro}` sem alvo,
`{bordao}` de quem não tem bordão (o Aprendiz), `{morto}`/`{objeto}` (Fases 2-3). As recentes de
cada personagem ficam em `CharacterState.recent_lines` (salvas no banco). Se todas as opções
foram usadas recentemente, aceita repetir. Clima na F1: `clima.clima_padrao` (real na F3).

Variáveis (`sim.text.TEMPLATE_VARS`): `{eu} {outro} {lugar} {hora} {periodo} {clima} {humor}
{bordao} {bordao_outro} {trabalho} {morto} {objeto}` e `{@id}` para citar alguém pelo id. Se não
sair fala (chance ou falta de template), o Chat do Mundo mostra a `narracao` da ação.

F2 ✅:
- variáveis de situação `{terceiro}` (de quem se fala), `{fato}` (o que a fofoca conta),
  `{lembranca}`, `{objeto}`, `{evento}`, `{infracao}`, `{faccao}`, `{traco}`, `{convidados}`.
  Fala que usa uma variável que a situação não tem é pulada;
- filtro `memoria: [briga, discussao]`: a fala só sai se quem fala lembra de algo desses tipos
  envolvendo o alvo; a frase `lembranca` do tipo (world.yaml) vira `{lembranca}` ("Desde
  aquela briga na Cozinha Comunitária...");
- **concordância de gênero**: `{o|a}` escolhe pela `pronome` de quem fala, `{outro:o|a}` pelo
  do alvo, `{terceiro:o|a}` pelo de quem se fala ("meio perdid{o|a}" → "meio perdida"). Sem
  pronome, fica a primeira forma. Vale nas falas, narrações e textos dos eventos sociais;
- `World.say(...)` é o atalho que os sistemas usam: escolhe a fala de uma situação, cai num
  `fallback` se não houver nenhuma e publica o evento do tipo pedido.

LLM (F4): `sim.llm.enrich(evento, contexto)` reescreve só falas de `importance >= 1` em situações
listadas no `world.yaml`, com timeout `ollama.timeout_segundos` e limite `max_por_hora`. Falhou →
fica o template. O LLM recebe o template preenchido, bordões, humor, memórias recentes e ids; a
resposta só pode citar personagens por `{@id}` (validado com `text.check_template`, senão
descarta).

## 10. Persistência (SQLite) ✅ F1 (tabelas F2-F3 📐)

Arquivo em `persistencia.banco` (`${DW_DB_PATH:-var/world.sqlite}`). `sqlite3` da biblioteca
padrão, `PRAGMA journal_mode=WAL`. Tabela `meta.schema_version` + migrações simples em
`persistence.py` (lista de SQL por versão). Salva periodicamente e ao sair (Ctrl+C / SIGTERM).

```sql
-- F1 (migração 1 em sim/persistence.py)
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
  -- schema_version, world_time, seed, rng_state (json), speed, paused, last_event_id
CREATE TABLE characters (
  id TEXT PRIMARY KEY,               -- id do YAML (nome NUNCA é salvo aqui)
  alive INTEGER NOT NULL DEFAULT 1,
  place TEXT NOT NULL,
  needs TEXT NOT NULL,               -- json {fome: 42.1, ...}
  current TEXT,                      -- json da ação/plano em andamento
  last_action TEXT,
  extra_traits TEXT NOT NULL DEFAULT '[]',  -- traços ganhos (Limbo, ressurreição)
  flags TEXT NOT NULL DEFAULT '{}',  -- F1: cooldowns, next_review, recent_lines; F2+: preso_ate, luto...
  born_at TEXT, died_at TEXT, death_cause TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, real_ts TEXT NOT NULL,
  type TEXT NOT NULL, importance INTEGER NOT NULL DEFAULT 0,
  place TEXT, text TEXT, data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE event_actors (event_id INTEGER, char_id TEXT, role INTEGER, PRIMARY KEY (event_id, char_id));
CREATE TABLE event_tags (event_id INTEGER, tag TEXT, PRIMARY KEY (event_id, tag));
CREATE INDEX events_ts ON events(ts);  CREATE INDEX actors_char ON event_actors(char_id);
CREATE TABLE relations (a TEXT, b TEXT, affinity REAL NOT NULL, updated_at TEXT, PRIMARY KEY (a, b));
  -- criada já na F1 (as conversas mudam a afinidade); só os pares que mudaram desde o YAML
-- F2 ✅ (migração 2) — mais simples que o plano: os campos ficam em JSON
CREATE TABLE memories (id INTEGER PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
  data TEXT NOT NULL);   -- json do sim.memory.Memory: subject, object, place, intensity,
                         -- sentiment, permanent, ts, minute, heard_from, distorted, detail,
                         -- reported, secret. Regravada inteira a cada save (~40 por NPC).
CREATE INDEX memories_owner ON memories(owner);
CREATE TABLE structures (id TEXT PRIMARY KEY, place TEXT NOT NULL, hp REAL NOT NULL,
  data TEXT NOT NULL DEFAULT '{}',   -- {"marks": [[quem, infração], ...]} (pichações assinadas)
  updated_at TEXT);
-- objetos roubados, objetivos, leis (pontos, mandados, reincidência), eventos sociais ativos,
-- visitantes recentes por lugar, amizades/inimizades já anunciadas e a próxima "hora":
-- tudo em meta.society (JSON). As tabelas objects/goals planejadas não foram criadas.
-- characters.flags ganhou: faction, jailed_until, limbo_until, spouse; extra_traits passa a ser usado.
-- F3
CREATE TABLE graves (char_id TEXT PRIMARY KEY, born_ts TEXT, died_ts TEXT, cause TEXT, epitaph TEXT);
CREATE TABLE cooldowns (key TEXT PRIMARY KEY, until_ts TEXT NOT NULL);
CREATE TABLE director_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, tension REAL,
  chosen TEXT, reason TEXT);
CREATE TABLE weather_log (ts TEXT PRIMARY KEY, code INTEGER, label TEXT, temp REAL, raw TEXT);
```

Na F1: `events.id` é dado pelo `World` (não é AUTOINCREMENT); eventos `decision` não são gravados;
os eventos são confirmados (commit) a cada tick e o estado completo a cada
`salvar_a_cada_minutos` e ao sair (Ctrl+C / SIGTERM). `Storage.query_events(character=, place=,
tag=, type=, limit=, before_id=)` é a base do `/api/chat` da F4.

Personagem morto **continua com o YAML** em `data/characters/` (a lápide mostra o nome atual).
Personagem que está no SQLite mas sumiu do YAML: fica congelado e gera aviso (não apaga nada).
Personagem novo no YAML: entra no mundo na `casa`, com as necessidades iniciais.

## 11. Fase 2 — sociedade ✅

Tudo o que é número, texto ou regra de conteúdo está nos YAML (`world.yaml > memoria, fofoca,
relacoes, leis, faccoes, estruturas, roubos`; `data/actions/*.yaml`; `data/events/sociais.yaml`;
`data/lines/*.yaml`; `estruturas`/`objetos` nos lugares; `faccao` nos personagens). O código só
tem as regras genéricas abaixo.

### 11.1 Relações (`sim.relations`)
Afinidade −100..100 por par **direcionado** (a de A com B ≠ a de B com A), começa pelo YAML.
Muda por: efeitos das ações (`afinidade`, `afinidade_do_alvo`, `afinidade_com`), memórias que se
formam (`memoria.tipos.<t>.afinidade` × força), fofocas, eventos sociais (+3 com quem organizou),
prisão (−5 com o Fiscal). Volta para o valor inicial a `relacoes.retorno_por_hora` (0,2/h: um
rancor de −40 leva ~8 dias). Cruzar `inimigos_abaixo`/`amigos_acima` vindo do outro lado gera
`relation_changed` (uma vez por par).

### 11.2 Memória (`sim.memory`)
`Memory(owner, kind, subject, object, place, intensity, sentiment, permanent, ts, heard_from,
distorted, detail, reported, secret)`. Tipos em `memoria.tipos` (24 hoje). Quem forma:
- **quem fez e com quem foi** (força 1) e **testemunhas** acordadas no lugar
  (`fator_testemunha`, 0,6): ação com `memoria`, falha com `falha.memoria`, eventos sociais;
- **quem ouviu** (fofoca, denúncia, confissão): `fator_fofoca`, com `heard_from`.
A mesma coisa (tipo + pessoas) no mesmo dia reforça em vez de duplicar. Decai
`decai_por_dia`; some abaixo de `esquecer_abaixo`; `permanente` fica (Limbo, casamento; F3:
mortes). No máximo `max_por_npc` (esquece a mais fraca). As frases `fato` (3ª pessoa, para
fofoca) e `lembranca` (para quem lembra) usam `{quem} {alvo} {lugar} {objeto}`.

### 11.3 Fofoca (`sim.gossip`)
`fofocar` (`especial: fofoca`) escolhe a memória mais suculenta
(`intensidade × (0,5 + |sentimento|) × 1,3 se é infração`) sobre um terceiro que o ouvinte ainda
não sabe. Com `fofoca.chance_distorcao` (o dobro para o traço `fofoqueiro`) quem fez vira outra
pessoa → acusação errada. Segredos de confissão (`confessar` → memória `secret` no Padre) só
saem de quem é fofoqueiro, na situação `fofoca_confissao`. Contar ao Fiscal uma infração vira
denúncia. **Não existe Carteiro na bible**: quem "espalha mais" é o traço `fofoqueiro` (Padre e
Dama); um Carteiro futuro é só dar esse traço a ele.

### 11.4 Conflito, reconciliação e pastelão (só YAML + 3 regras)
Ações: `discutir` (afinidade em U: briga-se com quem se odeia e com quem se ama), `brigar`
(pastelão, infração, falha = tombo, `chance_perseguicao`), `pedir_desculpas` (`ir_atras`),
`abracar`, `consolar`, `pregar_peca` (falha 45%: dá errado nele), `andar_de_skate`,
`fazer_malabarismo`, `fucar` (choque no Aprendiz), `fugir`/`perseguir` (automáticas). As pazes
dependem de `conflito_alvo` × `afinidade_inicial` × pouca raiva: o casal e os Cowboys (afinidade
inicial alta) fazem as pazes rápido; o Ganancioso e os Cozinheiros, não. A "briga das três da
tarde" é só um bloco de rotina `discutir` às 15:00 na Cozinha (peso 12): com quem, se escala e
quando fazem as pazes sai da simulação. Raiva vem de: discussões, brigas, pegadinhas, sumiços
percebidos (`roubos.raiva_ao_perceber`), advertências, festa furada e efeitos por traço
(`festejar` deixa o `briguento` esquentado; `trabalhar` irrita o `irritado`).
Regras no código: `interrompe_alvo`, `reconcilia` (memórias ruins entre os dois ×0,3) e a
perseguição (o alvo foge para um vizinho por caminho, quem fez vai atrás com `perseguir`).

### 11.5 Estruturas (`sim.structures`)
`estruturas` em cada lugar (17 hoje). Resistência 0..100; estados `inteiro` (≥ 70),
`danificado`, `destruido` (0). Dano: `efeitos.dano_estrutura` ao terminar (brigar 18, quebrar
35, festejar 4, pichar 6; falha de `construir` 12), numa estrutura sorteada do lugar. Conserto:
`construir` (`conserta: 45` por ação, aos poucos). Mudou de estado → `structure_changed`.
`mandar_reconstruir` (Chefe) cria um objetivo para todos (`construir` no pior lugar, ×3 por
8 h). O `mutirao` (evento social do Ferreiro e de quem é `protetor`/`perfeccionista`) marca
hora e chama gente.

### 11.6 Leis (`sim.law`)
Infrações em `leis.infracoes` (nome, gravidade, `horarios` opcionais — barulho só 22h–6h).
Chegam ao Fiscal (profissão `leis.profissao_fiscal`) por flagrante (está acordado no lugar
quando começa, ou chega e ainda está acontecendo; máximo `max_por_olhada`), assinatura
(`assina: true` deixa marca na estrutura) ou denúncia (`denunciar` com `ir_atras`, ou fofoca
contada a ele). Mesma pessoa e infração: só uma vez a cada `reincidencia_horas`. Pontos somam a
gravidade e somem `pontos_somem_por_dia`: < `pontos_para_prisao` = advertência; ≥ = prisão
(`limites.horas_de_prisao`); ≥ `pontos_para_limbo` = Limbo (`limites.dias_no_limbo`, pontos
zeram). Infrator longe → mandado (`mandado_horas`) e o Fiscal vai atrás (`prender`); a falha de
`prender` (30%) é a fuga. Preso: só faz coisas na Prisão. No Limbo: `away` (fora das telas, sem
decidir, necessidades congeladas); volta em `volta_do_limbo` com um traço sorteado de
`traits.yaml` (`sorteavel`, sem `opostos`) em `extra_traits` e memória permanente.

### 11.7 Facções (`sim.factions`)
`faccoes` no world.yaml (Igreja: `priest`; Seita: `medium`). Começa pelo `faccao` do YAML.
Entra quem passa de `afinidade_para_entrar` com o líder e gosta mais dele que do líder rival;
sai quem cai abaixo de `afinidade_para_sair`. Conferido de hora em hora e depois de
`recrutar`/`pregar` (`especial: recrutar`). A afinidade sobe indo à `missa` (dia, Catedral, com
o Padre presente) e a `participar_ritual` (noite, onde a Médium está: `presenca.medium`). O
`ritual` em si é da Médium (rotina: floresta 21h–2h, subterrâneo 2h–4h). O Padre espia
(`espiar_seita`, `observa`) e vira fofoca. O Adolescente começa sem facção (o traço `rebelde`
e a afinidade com a Médium o puxam; entrar exige 62).

### 11.8 Ganância e sumiços (engine)
`roubar` (traço `ganancioso`) pega um dos `objetos` do lugar; testemunhas notam com
`roubos.chance_testemunha_notar`. Ao terminar, esconde num lugar sorteado e, com
`chance_esquecer`, esquece onde (objeto perdido). Quem `perambular` por lá pode achar
(`chance_achar`); quem tem traço de `tracos_que_acham_sagrado` declara sagrado. Quem começa a
`trabalhar` no próprio local de trabalho percebe o sumiço e escolhe um **suspeito** entre quem
passou por lá desde o roubo, com peso `40 − afinidade` (o culpado é provável, não garantido):
memória `sumico` → raiva, fofoca, denúncia, prisão — às vezes do inocente.

### 11.9 Eventos sociais (`sim.social_events`)
Ver o topo de `data/events/sociais.yaml`. De hora em hora, para cada tipo sem evento ativo e
fora do cooldown, cada NPC que bate com `organizadores` (qualquer de: personagens, traços,
profissões, grupos, facções) e com `vontade` tem `chance_por_hora` de ter a ideia. Marca hora
(`antecedencia_horas`, dentro de `comeca_entre`), convida os `max_convidados` de maior afinidade
(≥ `convite_afinidade_min`) e cria objetivos (`bonus`, ×1,5 para quem organiza) de 30 min antes
até o fim. Começa se houver `quorum` pessoas no lugar (com o organizador, ou 15 min depois sem
ele); 45 min sem quórum = fracasso (memória `memoria_fracasso`, raiva, −4 de afinidade com
convidados que faltaram). Fim: `memoria` para todos que passaram por lá, +3 com quem organizou.
Casamento: precisa de par com afinidade mútua ≥ `par_afinidade_min`, sem relação proibida
(`par_tipos_proibidos`) e fora de `excluidos`; o casal vira `spouse`. Tipos: festa na Taverna,
rave secreta, rodeio, procissão, casamento, mutirão.

### 11.10 Verificação
`tools.run --resumo` mostra a tabela "Resumo da sociedade" (contagens por tipo e a lista de
eventos organizados com o resultado). `tests/test_society.py` cobre cada sistema e roda uma
semana (seed 42) conferindo o critério de aceite.

## 12. Fase 3 — vida, morte e diretor 📐

- **Morte**: chance base `limites.chance_morte_por_dia` por personagem + causas (briga, acidente,
  criatura, velhice, choque na Sala do Servidor, Limbo), cada uma com chance no YAML.
  `death` (importance 3) → `alive=0`, lápide em `graves`, memória permanente em todos.
- **Funeral**: objetivo coletivo (ir ao cemitério) + clima forçado `chuva` por
  `minutos_de_chuva_no_funeral`; reações via falas filtradas por personagem e afinidade com o morto.
- **Luto**: `flags.luto = {de, ate, intensidade}` proporcional à afinidade; multiplica taxas.
- **Fantasmas**: à noite, `chance_fantasma_por_noite`, perto de quem o morto mais amava/odiava.
- **Nascimentos**: a cada ~`intervalo_nascimento_dias` (ou comando), sorteio em `traits.yaml`
  (traços respeitando `opostos`, profissão `sorteavel`, aparência), herança de objeto/mania de morto
  recente (`chance_herdar_do_morto`). Salva YAML em `data/characters/born/<id>.yaml` com id
  `born_<n>` e `nome: nascimento.nome_padrao` para o João renomear.
- **Sucessão**: profissão com `papel_importante` vaga → objetivo de eleição/vocação; quem assume
  ganha a profissão em `characters.flags` (o YAML original não é alterado).
- **Criaturas**: `data/events/creatures.yaml` (chave `criaturas:`, esquema a criar na F3);
  homelab (`homelab/servicos/#`) → criatura na Sala do Servidor; Técnicos ganham objetivo de
  `trabalhar` lá até resolver.
- **Clima**: Open-Meteo (`latitude/longitude` do YAML), cache em `clima.cache_arquivo`, fallback
  `clima_padrao`. Rótulos em português a partir do weather code. Entra como filtro de falas,
  condição de eventos e multiplicador de necessidades (chuva → medo do Esquisito).
- **Telas offline** (`screens.py`): `telas/<id>/status = offline` → `fog_on` em todos os lugares
  da tela; ninguém entra (pathfinding ignora), quem está dentro fica preso (exceto `imunidades:
  [nevoa]`, o Mike).
- **Diretor** (`director.py`): `tensao` 0..100 = f(brigas recentes, mortes recentes, criaturas,
  tédio médio). Alvo de tensão oscila no dia. Se tensão < alvo, escolhe evento `tensao: agita`; se >,
  `acalma`. Respeita `condicoes`, `cooldown_horas`, `max_eventos_diretor_por_hora/dia`. Só cria
  situações (`efeitos.necessidades`, `efeitos.objetivo`, `efeitos.clima`); registra o motivo em
  `director_log`.
- **`tools.report --days N`**: roda N dias em `--fast` num banco temporário e gera relatório:
  ações mais/menos usadas, falas repetidas (limite justificado no relatório da F3), eventos por
  tipo, mortes/nascimentos, personagens parados.

## 13. Fase 4 — Criador, API e integração 📐

### 13.1 Comandos (`sim.commands`)

Mesmo formato vindo da CLI, da API e do MQTT: `{"cmd": "<nome>", "arg": "<texto>", "id": "<opcional>"}`.

| cmd | arg | efeito |
|---|---|---|
| `chefe` | ordem livre | o Chefe recebe um objetivo cívico (palavras-chave: reconstruir, festa, regra, reunião; LLM opcional); repassa à cidade como `goals`; personalidades podem atrasar/resistir |
| `medium` | mensagem | chega como "voz"; a Médium interpreta (chance de erro configurável) e age/convence a seita |
| `reviver` | id | ressurreição lendária (traço novo, memórias faltando ou medo de morrer); reações do Padre/Médium/cidade |
| `nascer` | traços opcionais | nascimento imediato |
| `pausar` / `continuar` | — | |
| `velocidade` | n | multiplicador |
| `status` | — | resumo |
| `quem` | id | ficha viva: necessidades, ação, plano, humor, memórias, relações, última explicação de decisão |
| `recarregar` | — | (F6) recarrega `data/` sem perder estado |

### 13.2 REST (FastAPI, `server.app`)

```
GET  /api/state                         resumo: hora, período, clima, tensão, população, pausado
GET  /api/characters                    lista (id, nome, lugar, ação, vivo)
GET  /api/characters/{id}               ficha viva (igual a `quem`)
GET  /api/places                        lugares + quem está lá + névoa + tela
GET  /api/screens                       telas do world.yaml + status
GET  /api/chat?character=&place=&tag=&since=&until=&limit=&before_id=   histórico filtrado
GET  /api/timeline?min_importance=2     grandes acontecimentos
POST /api/commands   {"cmd": "chefe", "arg": "reconstruam a ferraria"}  → 202 + id do comando
```

### 13.3 WebSocket `/ws?screen=<id>` (contrato com o viewer)

Mensagens JSON com campo `type`. Servidor → cliente:

```jsonc
// 1) logo ao conectar
{"type": "hello", "screen": "parede_centro", "protocol": 1,
 "world": {"ts": "...", "period": "tarde", "is_night": false, "speed": 1, "weather": {"label": "chuva fraca", "code": 61}},
 "screens": [{"id": "...", "places": ["..."], "position_cm": {"x": 0, "y": 0}, "size_cm": {"width": 0, "height": 0}}],
 "places": [{"id": "town_square", "name": "A Praça", "palette": {...}, "sinister": false, "environment": "externo",
             "fog": false, "connections": [{"to": "forest", "kind": "tunel"}], "structures": []}],
 "characters": [{"id": "clown", "name": "O Palhaço", "place": "market", "action": "trabalhar",
                 "visual": {"color": "#e63946", "secondary_color": "#f1faee", "height": 1.05, "body": "magro", "hat": "nenhum", "accessory": "nariz vermelho"},
                 "moving": null}]}
// 2) depois, fluxo (só o que interessa aos lugares desta tela, mais o global)
{"type": "event", "event": { ...Event com text_rendered... }}
{"type": "clock", "ts": "...", "period": "noite", "is_night": true}          // 1×/min do mundo
{"type": "weather", "label": "chuva", "code": 63, "forced": "funeral"}
{"type": "character", "id": "clown", "name": "...", "place": "...", "action": "...", "visual": {...}}  // mudança de estado/renomeação
{"type": "move", "id": "clown", "from": "market", "to": "tavern", "duration_s": 3.0}  // dentro da tela
{"type": "teleport", "phase": "start"|"end", "id": "clown", "from_place": "...", "to_place": "...",
 "from_screen": "...", "to_screen": "...", "duration_s": 4.2}
{"type": "fog", "place": "forest", "on": true}
{"type": "bubble", "id": "chef_wife", "text": "Come que esfria!", "duration_s": 4}  // balão (fala)
{"type": "apparition", "places": ["..."], "duration_s": 3}
```

Cliente → servidor: `{"type": "ping"}` (o servidor responde `pong`) e `{"type": "resync"}` (reenvia
`hello`). Sem comandos pelo WebSocket (comandos só via REST/MQTT/CLI). `/ws/chat` (sem `screen`)
manda todos os eventos para a página do Chat do Mundo.

### 13.4 MQTT (`server.mqtt_bridge`)

paho-mqtt 2.x com `mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2,
client_id=...)`, `loop_start()`, reconexão a cada `reconectar_segundos`, LWT em `world/status`
(`offline`, retido) e `online` retido ao conectar. Broker fora: loga aviso **uma vez** por queda e
segue. Tópicos vêm de `world.yaml > mqtt.topicos`.

| Tópico | Direção | Payload |
|---|---|---|
| `world/events` | publica | Event (JSON da seção 8) com `importance >= 1` (rotina não, para não inundar) |
| `world/state` | publica, retido, a cada `estado_a_cada_minutos` | `{"ts","period","is_night","weather","tension","population","alive","places":{id:[ids]}}` |
| `world/chat` | publica | `{"from": "<id>", "from_name": "...", "text": "...", "ts": "<real>", "meta": {"world_ts", "place", "to": "<id>|null", "situation", "tags"}}` (mesmo molde de `npc/<id>/fala`) |
| `leds/tunnel` | publica | `{"phase": "start"|"end", "char": "<id>", "from_screen", "to_screen", "from_cm": {x,y}, "to_cm": {x,y}, "duration_ms", "color": "#hex"}` |
| `world/status` | publica, retido | `online` / `offline` |
| `world/commands` | escuta | `{"cmd": "...", "arg": "..."}` (seção 13.1) |
| `sala/camera/pessoas` | escuta | `{"count": n}` ou número puro; `count > 0` = presença |
| `homelab/servicos/#` | escuta | `{"status": "down"|"up"|"degraded", "name": "..."}` (o sufixo do tópico é o serviço) |
| `telas/+/status` | escuta | `online` / `offline` (o `+` é o id da tela) |

Os NPCs do mundo **não** publicam em `npc/<id>/fala` por padrão (evita o Grilo responder a cada
fala do mundo); dá para ligar depois com uma opção no `world.yaml`.

### 13.5 Docker

`Dockerfile` (python:3.12-slim) + `docker-compose.yml`: um serviço `sim` com `./data` e `./var`
como volumes e `.env` para endereços. F1 ✅ mudou o comando para `python -m tools.run` (tempo real,
`restart: unless-stopped`; `tzdata` no pyproject garante o fuso na imagem enxuta); F4 para
`python -m server` com a porta `${DW_SERVER_PORT:-8000}` publicada e `restart: unless-stopped`.
O viewer (F5) é servido como estático pelo próprio FastAPI (`viewer/dist`), sem segundo container.

## 14. Fase 5 — visual 📐

- `viewer/` com Vite; `index.html?screen=<id>` conecta em `/ws?screen=<id>`, desenha só os lugares
  da tela (layout dos lugares dentro da tela: grade automática, sobrescrevível por um campo futuro
  `visual` no YAML do lugar).
- Estética PS1: render em baixa resolução + upscale `image-rendering: pixelated`, vertex snapping
  no shader, flat shading, névoa de distância, paleta vinda de `place.paleta`.
- Placeholders por primitivas a partir de `character.visual` (corpo, altura, cores, chapéu,
  acessório). Se existir `viewer/public/models/characters/<id>.glb` (ou `places/<id>.glb`), usa o
  modelo. Animações por nome: `idle, walk, talk, work, sleep, fall, fight, pray, dance, stare`
  (fallback procedural). Ação → animação: tabela no viewer (`trabalhar→work`, `brigar→fight`...).
- Balões a partir de `bubble`; dia/noite por `clock`; chuva por `weather`; névoa por `fog`;
  teletransporte: some na saída, aparece na tela de destino em `teleport end`.
- `viewer/layout.html`: mapa físico das telas (`posicao_cm`, `tamanho_cm`) e conexões de túnel.
- `viewer/chat.html`: Chat do Mundo ao vivo com filtros (usa `/api/chat` + `/ws/chat`).

## 15. Determinismo, logs e testes

- Um único `random.Random(seed)` por mundo (`seed` do YAML; vazio = aleatório e registrado no
  `meta`). Nenhum módulo usa `random` global. Com a mesma seed, dados e `--fast`, a sequência de
  eventos é idêntica (teste da F1).
- Log com `logging` (`nivel_log` do world.yaml; em `debug` traz as explicações de decisão e as
  interrupções). `tools.run --debug` mostra as decisões no próprio Chat do Mundo (eventos
  `decision`). O chat usa `rich` e vai para o stdout; o log, para o stderr.
- Testes por módulo em `tests/`; os que precisam de mundo usam uma cópia de `data/` (fixture
  `data_copy`) e banco SQLite em `tmp_path`. MQTT e Ollama são testados com dublês (sem rede).

## 16. Decisões em aberto (para as próximas fases)

- Layout interno dos lugares numa tela (posições 3D) — F5 decide; pode ganhar campo no YAML.
- Esquema das criaturas — F3 cria e documenta aqui (o dos eventos sociais está na seção 11.9).
- Lista de situações reescritas pelo LLM — F4.
- Técnicos: na F1 trabalham na Sala do Servidor como qualquer profissão (manhã/tarde). Quando a F4
  ligar `homelab/servicos/#`, o trabalho deles deve depender de objetivo (problema real aberto).
- Médium: com o `ritual` (F2) as noites dela são de ritual; o bloco provisório de `rezar` saiu.
- Diretor (F3) deve usar `World.add_goal` e `World.say` (mesmo mecanismo dos convites) e pode
  medir a tensão pelas contagens de `fight`/`argument`/`arrest` recentes.
- Limbo é raro numa semana (precisa de 6 pontos de infração); se o João quiser mais, baixe
  `leis.pontos_para_limbo`.
