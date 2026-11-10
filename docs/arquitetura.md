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
- **F4 ✅ (como ficou):** `server.runtime.Runtime` monta `Storage` + `World` e roda `World.run()`
  num thread ("simulacao"); o asyncio do uvicorn é o thread principal; o paho tem o seu thread
  (`loop_start`) e o LLM, outro. Decisão: **um processo, não dois** — a simulação é a dona do estado
  e a única que escreve no SQLite; a API lê (a) o snapshot (agora com os nomes atuais), (b) o Chat
  do Mundo numa conexão SQLite própria só de leitura por requisição (`Storage.reader`,
  `PRAGMA query_only`; o WAL deixa ler enquanto o mundo escreve) e (c) a ficha viva (`quem`), que
  precisa de memórias e relações, **pela fila de comandos** com um `concurrent.futures.Future` que o
  thread da simulação responde (`Command.reply`). Comandos são atendidos fora do tick também (no
  tempo real um tick é 1 minuto inteiro): o laço de `run()` drena a fila a cada volta. Dois
  processos teriam de trocar estado por arquivo/socket e disputar o SQLite — mais código e mais
  jeitos de quebrar.

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
  lifecycle.py      ✅ F3  morte, funeral, luto, herança, fantasmas, ressurreição, nascimentos, sucessão
  creatures.py      ✅ F3  criaturas noturnas e as da Sala do Servidor (homelab)
  weather.py        ✅ F3  Open-Meteo com cache e fallback; clima sorteado no tempo acelerado
  screens.py        ✅ F3  telas online/offline → névoa nos lugares
  director.py       ✅ F3  tensão do mundo e injeção de eventos de data/events
  commands.py       ✅ F4  comandos do Criador (chefe, medium, reviver, status, quem, raio...),
                           decretos, reuniões, assuntos do momento; estado em meta.society.creator
  llm.py            ✅ F4  cliente Ollama opcional (thread próprio, httpx, timeout, limite/hora)
  presence.py       ✅ F4  o olhar (coletivo) e a Aparição (sala/camera/pessoas)
  reload.py         ✅ F6  `recarregar`: data/ de novo sem perder o estado; cópia da última versão válida
server/
  runtime.py        ✅ F4  monta Storage + World + thread da simulação + LLM + MQTT; comandos com Future
  app.py            ✅ F4  FastAPI: REST + WebSocket + /chat
  ws.py             ✅ F4  Hub: conexões por tela, filtro por lugares da tela, mensagens derivadas
  mqtt_bridge.py    ✅ F4  paho-mqtt 2.x (CallbackAPIVersion.VERSION2), reconexão, LWT, respostas
  __main__.py       ✅ F4  `python -m server`: sobe tudo (uvicorn) e mostra o Chat no stdout
tools/
  validate.py       ✅ F0  `python -m tools.validate`
  run.py            ✅ F1  `python -m tools.run --speed 60 [--fast] [--horas N|--dias N] [--personagem id]
                           [--lugar id] [--movimento] [--debug] [--resumo] [--saida arq] [--novo]
                           [--seed N] [--inicio HH:MM] [--banco arq]`
  report.py         ✅ F3  `python -m tools.report --days 7 [--seed N] [--saida arq] [--estrito] [--sem-balanceamento]`:
                           variedade (F3) + saúde do mundo (F6: prisões, eventos sociais, diretor, mortes,
                           necessidades ≥ 95, ocupação dos lugares; limites em BALANCE_LIMITS)
  cli.py            ✅ F4  `python -m tools.cli chefe "..."` (fala com a API; status/quem/recarregar formatados; chat)
  backup.py         ✅ F6  `python -m tools.backup [--destino] [--manter N]`: cópia online do SQLite
viewer/
  chat.html         ✅ F4  Chat do Mundo na web (HTML+JS puro, sem build), servido em /chat
  index.html        ✅ F5  uma tela: /viewer/?screen=<id> (sem screen: lista das telas)
  layout.html       ✅ F5  mapa físico das telas e dos túneis (ao vivo)
  src/logic.js      ✅ F5  regras puras (animação por ação, clipes, balão, grade, dia/noite, túnel, aparência)
  src/main.js       ✅ F5  conexão WS, montagem da cena, mensagens, túnel, Aparição, laço com limite de FPS
  src/ps1.js        ✅ F5  materiais PS1 (flat + vertex snapping) e render em baixa resolução
  src/shapes.js     ✅ F5  primitivas low-poly e `bake` (junta malhas paradas por material)
  src/places.js     ✅ F5  cenários placeholder por lugar (+ genérico pela paleta), entulho, lápides
  src/characters.js ✅ F5  boneco placeholder pelo YAML, animação procedural, .glb do João
  src/environment.js ✅ F5 céu, sol/lua, névoa de distância, chuva, relâmpago, névoa de tela offline
  src/overlay.js    ✅ F5  balões, nomes, nomes dos lugares, relógio, risco de LED (HTML por cima)
  public/models/    ✅ F5  characters/<id>.glb e places/<id>.glb (servidos direto pelo servidor)
  test/             ✅ F5  `npm test` (node --test, sem navegador)
tools/exemplo_glb.py ✅ F5 gera um .glb de exemplo (totem com idle e walk) para testar a troca
tests/              pytest (um arquivo por módulo)
var/                (fora do git) SQLite, cache de clima, logs
```

## 3. Dados (`data/`) ✅ F0

### 3.1 Arquivos

| Arquivo | Conteúdo | Esquema |
|---|---|---|
| `world.yaml` | relógio, necessidades, Utility AI, limites, regiões, grupos, categorias do chat, clima, MQTT, Ollama, servidor, persistência, túnel, telas | `WorldConfig` |
| `events/criador.yaml` (F4) | `criador:` ordens do Chefe, vozes da Médium, resistência, decretos, reunião, reviver, assuntos, presença (só um arquivo pode ter) | `CreatorConfig` |
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

`load_data_or_raise()` lança `DataError` (usado pelo engine).

**F6 ✅ — recarregar (`sim/reload.py`).** Comando `recarregar` (CLI, `POST /api/commands`, MQTT
`world/commands`), executado no thread da simulação: `load_data(world.data_dir)`; com erro, nada muda,
evento `system` (importância 2) com os primeiros erros e resposta `ok: false`. Sem erro, `apply_data`
troca `world.data` (cópia rasa dos personagens, como no `__init__`) e acerta o estado vivo:
`relations.data`, `structures.data` (+ estruturas novas), `memories.cfg`, `weather.cfg`,
`director.watched`, `_mult_cache`, minutos de reavaliação, `refresh_blocked`, facções; reaplica as
sucessões (`lifecycle.apply_all_overrides`); quem estava fazendo uma ação/plano que sumiu para;
objetivos/criaturas/eventos sociais de tipos que sumiram somem; personagem com arquivo novo ganha
estado (`World.new_state`, em casa); personagem cujo arquivo sumiu continua com a definição antiga
(aviso `kept_old`). Salva, atualiza o snapshot e emite `data_reloaded` (o `Hub` do WebSocket
recalcula as telas e manda um `hello` novo a cada cliente: o viewer redesenha com nomes/cores/telas
novos sem F5). Seções que só valem ao ligar (`mqtt`, `servidor`, `persistencia`, `ollama`, fuso/passo
do `relogio`) são listadas em `restart_needed`. **Última versão válida:** `server.runtime.load_with_valid_copy`
guarda `data/` (sem os nascidos) em `<pasta do banco>/data_valido/` a cada start sem erro; se ao ligar
`data/` tiver erro e a cópia existir, liga com ela (`Runtime.using_valid_copy`, aviso no Chat) e o
`recarregar` continua lendo o `data/` de verdade (`world.data_dir`). `Runtime.data` virou propriedade
(`world.data`).

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
3. atualizar clima (sorteado, ou Open-Meteo numa thread a cada atualizar_minutos) ✅ F3
4. necessidades: para cada vivo, variar por taxa + efeito proporcional da ação em andamento  ✅ F1
5. memórias e relações: decaimento lento (1×/hora do mundo)  ✅ F2 (passo 9, junto do resto)
6. ações em andamento: terminar as que acabaram (emite action_finished)                      ✅ F1
7. movimento: avançar planos; chegadas e túneis; ao chegar, começa a ação                    ✅ F1
8. decisões: cada NPC livre decide; quem está ocupado é reavaliado (seção 6.5)               ✅ F1
   (ordem embaralhada pelo RNG; quem decidiu entra na contagem de "presentes" dos próximos)
9. sistemas: solturas (prisão/Limbo) e eventos sociais a cada tick; de hora em hora:
   memórias decaem, afinidades voltam, pontos da lei somem, facções, ideias de eventos ✅ F2
   F3 ✅: a cada tick funerais (fases) e criaturas vencidas; de hora em hora mortes "do dia",
   nascimentos, sucessões, lutos que acabaram, sustos/aparições de criaturas
   F4 ✅: a cada tick `commands.update` (ordens: prazo, obra pronta, reuniões, decretos e
   assuntos vencidos; de hora em hora o olhar coletivo de `presence`)
10. diretor: 1× a cada 10 min do mundo                        ✅ F3
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
  (F2: voltar direto para o lugar de onde acabou de vir vale ×0,25 — `CharacterState.prev_place`.)
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
  `interrompe_alvo`, `reacao_alvo` (ação automática do alvo, ex.: `emburrar` 3–8 min depois de
  uma bronca), `reconcilia`, `chance_perseguicao`, `conserta`, `assina`, `automatica`,
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
| F3 ✅ | `death`, `grief`, `inheritance`, `funeral_planned`, `funeral_started`, `funeral_procession`, `funeral_ended`, `grave`, `death_consequence`, `ghost`, `resurrection`, `birth`, `succession`, `election`, `creature_spawned`, `creature_gone`, `creature_fight`, `weather_changed`, `fog_on`, `fog_off`, `director_event`, `tension` (a cada hora; o terminal só mostra com --debug) |
| F4 ✅ | `creator_command` (o Criador mandou), `creator_order` (o Chefe recebeu / anunciou / reação da cidade / obra pronta / ordem perdida; `data.phase`), `creator_voice` (a Médium), `stare` (olhar coletivo), `apparition`; `resurrection` com `data.how = "criador"` |

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

LLM (F4 ✅, `sim.llm`): em `World.say`, uma fala de `importance >= ollama.importancia_min` numa
situação de `ollama.situacoes` vai para o LLM **só se** o mundo está no relógio real
(`World.realtime`, velocidade ≤ 10, não pausado) **e** o Ollama respondeu à última checagem
(`GET /api/tags` a cada `checar_a_cada_segundos`) **e** não passou de `max_por_hora`. Aí `say()`
não emite nada: o pedido vai para a fila do thread do LLM (`POST /api/generate`, timeout
`timeout_segundos`) e a resposta volta como comando interno `_llm_fala` pela fila do mundo; o
engine valida (até `max_caracteres`, só `{@id}` existentes, nenhuma outra variável) e emite com
`data.llm = true` — ou o template original com `data.llm = false`. O prompt leva: quem fala (id,
papel, traços, bordões, humor), lugar, clima, hora, as 3 memórias mais fortes, a situação e a frase
do template. Ollama fora do ar = a fala sai na hora, do template (sem esperar nada). O LLM também
tenta classificar ordens livres do Criador (`interpretar_ordens`); sem ele, "como dá". Só falas
que passam por `World.say` (sistemas: morte, funeral, ordens, Aparição...) são candidatas; as falas
das ações comuns nunca vão ao LLM.

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
-- F3 ✅ (migração 3)
CREATE TABLE graves (char_id TEXT PRIMARY KEY, born_ts TEXT, died_ts TEXT, cause TEXT, epitaph TEXT,
  data TEXT NOT NULL DEFAULT '{}');          -- {cause_name, resurrected}
CREATE TABLE director_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, tension REAL,
  chosen TEXT, reason TEXT);
CREATE TABLE weather_log (ts TEXT PRIMARY KEY, kind TEXT, label TEXT, temp REAL, source TEXT, forced TEXT);
-- a tabela cooldowns planejada não foi criada: o estado da vida (mortes, funerais, lutos,
-- vagas, papéis assumidos, objetos herdados), do clima, das telas, das criaturas e do
-- diretor (histórico da tensão, cooldowns) vai em meta.society (JSON), como na F2.
-- F4 ✅: sem migração nova. O estado do Criador (ordens com as respostas de cada um, decretos,
-- reuniões, assuntos do momento, presença/última Aparição) vai em meta.society.creator.
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

## 12. Fase 3 — vida, morte e diretor ✅

Números e textos ficam no YAML: `world.yaml > limites, clima, vida, morte, funeral, luto,
se_morrer, sucessao, criaturas, diretor`; `traits.yaml > nascimento`; `data/actions/vida.yaml`;
`data/events/diretor.yaml` e `creatures.yaml`; `data/lines/vida.yaml`. O código só tem as regras.

**Cópia dos dados.** `World.__init__` faz `dataclasses.replace(data, characters=dict(...))`:
nascimentos e sucessões alteram só o dicionário daquele mundo (nunca o `WorldData` de quem
chamou, nem os YAML originais).

### 12.1 Morte (`lifecycle.roll` / `kill`)
`morte.causas.<id>` tem `quando` (`diario` — sorteado de hora em hora com chance/24; vazio =
`limites.chance_morte_por_dia` —, `briga` — fim de uma briga, para o alvo e com metade da chance
para quem bateu —, `falha` — pastelão de uma das `acoes` —, `criatura` — por hora perto de uma
criatura, ×3 ao perder um enfrentamento —, `limbo` — ao ser mandado para o Limbo), `chance`,
`acoes`, `lugares`, `por_traco`. **Ninguém morre por sorteio se a cidade tem
`min_populacao` vivos** (sem extinção). `kill`: `alive=False`, corpo no cemitério, evento
`death` (falas `morte_<causa>`, {eu} = o morto, {outro} = quem brigou), metas/mandados/eventos
sociais do morto cancelados, viúvo(a) solteiro(a), memória permanente `morte` em todos os
vivos, luto, herança, vaga de papel, consequência (`se_morrer.<id>`) e funeral marcado.

### 12.2 Funeral
Marcado `funeral.depois_horas` depois, dentro de `comeca_entre` (dia). Cada vivo ganha dois
objetivos de `velar` (velório na Catedral `velorio_minutos` antes; enterro no Cemitério), com
`bonus = max(bonus_min, bonus_base + afinidade × bonus_por_afinidade)` — quem odiava quase não vai;
o traço `vaidoso` tem `velar: 3` (a Dama vai para ser vista), `vazio` 0,15 (o Mike não vai, passa).
Fases (`lifecycle.update`): `funeral_started` (clima forçado `clima_do_funeral` por
`max(minutos_de_chuva_no_funeral, até o fim)`; `se_morrer.fool.chuva_minutos: 1440`);
`funeral_procession` (quem está velando na Catedral é mandado andando até o Cemitério — o
cortejo); enterro; `funeral_ended` (participantes) + `grave` (lápide: nome, datas, causa,
epitáfio da situação `epitafio` com {eu} = o morto) + memória `funeral` + `death_consequence`.
A ação `velar` (`especial: funeral`) só vale onde há funeral agora; a fala sai de
`funeral_personalidade` (70%, se houver fala do personagem/traço — Fool piada, Florista canta,
Músico toca, Dama se exibe...) ou pela afinidade: `funeral_amigo` (≥ 40) / `funeral` /
`funeral_inimigo` (≤ −25). Quem passa pelo Cemitério durante o enterro sem velar sai em
`funeral_passante` (o Mike atravessa o funeral). Filtro novo nas falas: `mortos: [id]`.

### 12.3 Luto, herança, consequências
Intensidade = afinidade/100 × maior `luto.fator_por_tipo` dos tipos de relação (casal, filho...)
× `se_morrer.<morto>.luto_fator.<quem>`, até 1,5; entra em luto quem passa de
`luto.afinidade_min` (ou é parente). Na hora: `luto.choque` × intensidade; por
`luto.dias × intensidade` dias: taxas `luto.taxas` e notas `luto.acoes` (`1 + (m−1)×int.`).
Entrada nova `luto` (0..100) para curvas (`visitar_tumulo`). Só os 3 mais abalados aparecem no
Chat (`grief`). Herança: o primeiro herdeiro vivo (`heranca.herdeiros`) fica com o primeiro objeto;
sem herdeiro, quem o morto mais gostava fica com um sorteado (`inheritance`; `life.objects`).
`se_morrer.<id>`: chuva, atraso do funeral, `acoes`+`para`+`dias` (multiplicadores),
`objetivo` (ex.: velório de cerveja dos Cowboys), `texto`.

### 12.4 Fantasma e ressurreição (raros, pelo diretor)
`ghost`: um morto há ≥ 12 h (no máx. 1 vez a cada 3 dias por morto) aparece à noite para o vivo de
maior |afinidade do morto| (≥ 30): `fantasma_amor`/`fantasma_odio`/`fantasma_sonho` (se dorme);
medo e fé para quem vê, memória `fantasma` (vira fofoca). `resurrect(cid, how)`: volta no
cemitério com medo 85, traço novo, ~metade das memórias não permanentes esquecidas; o Padre
(quem tem a profissão) grita milagre, a Médium reivindica; memória permanente `ressurreicao`.
`how="criador"` fica pronto para o `reviver` da F4.

### 12.5 Nascimento
Chance por dia = `1/intervalo_nascimento_dias × (1 + bonus_por_vaga × max(0, mortes − nascimentos
nos últimos 30 dias))`, ×3 abaixo de `min_populacao`, 0 a partir de `max_populacao`; sorteada de
hora em hora. Comando `nascer [traços]`. Sorteia pronome, traços (`tracos_min..max`, `sorteavel`,
sem `opostos`), profissão `sorteavel`, aparência (`aparencias`), rotina-base
(`nascimento.rotina`); com `chance_herdar_do_morto` herda um objeto ou mania de quem morreu nos
últimos `vida.dias_morto_recente` dias (mania com texto entre aspas vira bordão: o filho do
Fool termina as frases com "...hehe."). Id `born_<n>`, nome `nome_padrao`/`nome_padrao_ela`
com `{n}`. Campos novos do personagem: `nascido_em`, `herdou: {de, objeto, mania}`.
**Pasta**: `DW_BORN_DIR` (lida em tempo de execução e pelo loader, sempre do ambiente real) >
`vida.pasta_nascidos` (relativa a `data/`). O loader lê a pasta mesmo fora de
`data/characters/`. `tools.run --nascidos PASTA`; sem isso, em simulação de teste (`--fast` ou
`--banco`) usa `var/nascidos/<banco>/` (esvaziada com `--novo`, nunca dentro de `data/`).
`tests/conftest.py` aponta `DW_BORN_DIR` para uma pasta temporária; `tools.report` também.

### 12.6 Sucessão
Profissão com `papel_importante` sem ninguém vivo para exercer abre uma vaga; depois de
`sucessao.papeis.<prof>.depois_horas`: `vocacao`/`sucessao` = sorteio ponderado por
`1 + bonus_herdeiro (herdeiros) + bonus_por_tipo (aprendiz, filho...) + 2 × traços em comum +
afinidade/50`; quem já tem papel importante não concorre. `eleicao` (o Chefe): convoca
assembleia (`assembleia`, objetivo para todos, 60 min na Praça) com os 3 melhores; cada um que
foi vota em quem mais gosta (candidato vota em si); `election` com a apuração. Quem assume:
profissão, local de trabalho e os blocos de rotina do papel (`trabalhar` + ações com
`condicoes.profissoes` do papel) — salvo em `life.overrides` e reaplicado ao carregar; vira líder
da facção se o papel é o do líder original (`World.leader_of`). Para isso as ações de papel
passaram de `personagens:` para `profissoes:` (ritual, recrutar, pregar, espiar_seita, confessar,
mandar_reconstruir).

### 12.7 Criaturas (`creatures.py`, `data/events/creatures.yaml`)
Ver o topo do YAML. De hora em hora, cada criatura comum nos `periodos` dela tem
`chance_por_hora` (no máx. `criaturas.max_ao_mesmo_tempo`, uma de cada tipo). Enquanto está
lá: `perigo` soma ao perigo do lugar (`World.danger_at`, usado pela entrada `perigo` e por
`perambular`), medo para quem está perto, sorteio de morte `criatura`. `enfrentar`
(`especial: criatura`) espanta com `chance_vencer` (×1,5 `especialistas`). `homelab: true`:
comando `homelab <serviço> down|up` (a F4 liga `homelab/servicos/#` nele) → criatura na Sala do
Servidor com `{objeto}` = serviço, objetivo de enfrentar para `chama_profissoes`; só some no `up`.
Imunidade `criaturas` (Mike): nem medo nem morte. Entrada nova `criatura` (0/1).

### 12.8 Clima (`weather.py`)
`clima.modo: auto` = real (Open-Meteo, `current=temperature_2m,weather_code`, thread separada,
cache em `cache_arquivo`, sem internet → cache → `clima_padrao`) só quando `World.realtime`
(run sem --fast), velocidade 1 e hora do mundo perto da real; senão sorteado com o RNG do mundo
(`simulado`), reproduzível. `tipos` mapeia códigos WMO em tipos com nome ({clima}) e
`chuva: true`. Clima forçado (`force`) ganha de tudo: funeral, eventos do diretor, comando
`clima <tipo> [min]`. `efeitos.<tipo|frio|calor>`: `necessidades` (taxas), `acoes` (notas),
`acoes_externas` (qualquer ação em lugar `externo`). `medos.gatilho` igual ao tipo (ou `chuva`
com chuva) → `medo_por_hora_com_gatilho`. Filtro `climas:` das falas aceita tipo ou nome;
entrada nova `chuva` (0/1). Evento `weather_changed` (falas `clima_<tipo>`, `clima_funeral`) e
`weather_log`.

### 12.9 Telas offline (`screens.py`)
Comando `tela <id> online|offline` (a F4 liga `telas/<id>/status`). Offline: `fog_on` em cada
lugar da tela (com quem ficou preso), `World.blocked_places`; o pathfinding evita, quem está
dentro só tem candidatos no próprio lugar, plano que ia atravessar desiste (`missed`,
`nevoa_barra`). `imunidades: [nevoa]` (Mike) ignora tudo. Online: `fog_off`.

### 12.10 Diretor (`director.py`)
Ver o topo do arquivo. Tensão = Σ `pesos_eventos` × eventos na `janela_horas` + medo e raiva
médios × peso + mortes recentes × `peso_morte_recente` + criaturas × `peso_criatura`
(0..100; o histórico é alimentado por um assinante do EventBus). `alvo` por período ± `margem`:
abaixo → `tensao: agita`, acima → `acalma`, com chance `chance_de_agir × distância/50`, limites
`max_eventos_diretor_por_hora/dia`, `cooldown_horas`, `condicoes`. Efeitos: necessidades (lugar
ou todos), objetivo (`para: todos|presentes`; sem `lugar` = qualquer lugar), clima forçado,
criatura, memória, `especial`. Raros (`tipo: raro|lendario`) sorteados à parte:
`fantasma` (`chance_fantasma_por_noite`), `ressurreicao` (`..._por_ano`), `desenho_do_criador`
(`chance_por_dia`). Cada escolha: `director_event` com `reason` ("tensão 12 < alvo 40: agita")
e linha em `director_log`. A tensão vai para a entrada `tensao` da Utility AI.

### 12.11 `tools.report`
Simula N dias num diretório temporário (banco e nascidos) e mostra: resumo (população, mortes,
nascimentos), ações mais/menos usadas e nunca usadas, falas exatas mais repetidas, narrações
repetidas (informativo), eventos por tipo, variedade por personagem e ALERTAS. Limite de
repetição: uma fala exata (texto final do Chat, com nomes) no máximo `max(3, dias × 0,5)` vezes
(justificativa no relatório da F3). `--estrito` sai com 1 se houver alerta.
**F6:** tabelas de balanceamento (`build_balance`): prisões por semana, eventos sociais
(planejados/sucesso/fracasso), eventos do diretor (fatia de cada um e os que nunca saíram), criaturas,
mortes por causa e pior janela de 7 dias, necessidades ≥ 95 (amostradas a cada troca de período, por
necessidade e por personagem) e ocupação média/máxima dos lugares. Alertas pelos limites de
`tools/report.py > BALANCE_LIMITS` (8 prisões/semana, 25% de sucesso mínimo, 30% de fatia máxima do
diretor, < 3 mortes em 7 dias, 15%/40% de necessidade ≥ 95). `--sem-balanceamento` desliga.

## 13. Fase 4 — Criador, API e integração ✅

Números, palavras e textos ficam no YAML: `data/events/criador.yaml` (`criador:` — ordens, vozes,
resistência, decretos, reunião, reviver, assuntos do momento, presença), `data/actions/criador.yaml`
(`anunciar_ordem`, `revelar_visao`, `reuniao`), `data/lines/criador.yaml`, `world.yaml > ollama`
(situações do LLM), `mqtt.topicos.respostas`, `leis.infracoes.decreto`, 4 tipos de memória novos
(`ordem_do_chefe`, `visao`, `reuniao`, `aparicao`). O código só tem as regras.

### 13.1 Comandos (`sim.commands`, `World.handle_command`)

Mesmo formato vindo da CLI, da API e do MQTT: `Command(cmd, arg, id)`. Todo comando devolve um
dicionário `{"ok": bool, ...}` (vai para o `Future` de quem pediu, para `World.command_log` —
`GET /api/commands` — e, no MQTT, para `world/commands/result`).

| cmd | arg | efeito |
|---|---|---|
| `chefe` | ordem livre | ver 13.1.1 |
| `medium` | mensagem | ver 13.1.2 |
| `reviver` | id | `lifecycle.resurrect(cid, "criador", medo, chance_esquecer)` + funeral pendente cancelado + assunto `ressurreicao` (a cidade comenta por dias). Vivo/inexistente: `ok: false` |
| `nascer` | traços opcionais | nascimento imediato (F3) |
| `pausar` / `continuar` / `velocidade n` | | (F1) |
| `status` | — | resumo: hora, clima, tensão, população, mortos, névoa, criaturas, ordens (com reações), decretos, assuntos, presença, LLM |
| `quem` | id | ficha viva: necessidades, humor, ação, plano, traços (+ganhos), facção, preso/Limbo/luto, 12 memórias mais fortes (frase), 5 de quem mais/menos gosta, objetivos ativos, última explicação de decisão |
| `presenca` | n | pessoas no quarto (MQTT `sala/camera/pessoas`), ver 13.6 |
| `aparicao` | — | força uma Aparição (teste) |
| `raio` | lugar | (teste) um raio destrói as estruturas do lugar — para ver uma reconstrução |
| `tela`, `homelab`, `clima` | | (F3), agora também pelo MQTT |
| `recarregar` | — | ✅ F6: seção 3.3 (data/ de novo, sem perder estado; erro = mantém a versão anterior) |

Internos (pela mesma fila, nunca pela API): `_llm_fala` (resposta do LLM) e `_ordem_interpretada`.

#### 13.1.1 `chefe "<ordem>"` — objetivo cívico, nunca mágica

1. **Entender**: o texto (minúsculo, sem acento) é comparado com as `palavras` de cada
   `chefe.interpretacoes` (pedaços no começo de palavra: `reconstru` pega "reconstruam"); ganha a
   com mais acertos. Sem acerto: o LLM classifica (se no ar), senão "como dá" (sorteio por
   `peso_sem_entender`, fala `ordem_confusa`). O lugar citado vem dos nomes de lugares/estruturas
   ("a ferraria", "a bigorna" → `forge`).
2. **Intuição**: quem tem a profissão `lider` (o sucessor também) recebe (`creator_order`
   `phase: received`, fala `ordem_intuicao`) e ganha um objetivo pessoal: `anunciar_ordem` (só vale
   para quem tem ordem pendente; só na Praça; não de madrugada; com sono alto, adia) com `bonus`
   por `horas`. Sem Chefe vivo, a ordem espera (`esperando`) até haver um. Não anunciou no prazo →
   `perdida`.
3. **Anúncio** (`especial: anuncio_criador`): fala `ordem_anuncio` (ou `regra_*`), memória para
   quem está na Praça e a ordem vira, para cada morador, uma **resposta** pela personalidade:
   `fator = Π resistencia.tracos × (1 + afinidade_com_o_Chefe/100 × peso_afinidade)`;
   `< resiste_abaixo` = resiste (sem objetivo; reclama em voz alta se está no lugar),
   `< atrasa_abaixo` = atrasa (`atraso_horas`), senão aceita; bônus pessoal = `1 + (bonus−1)×fator`.
   Resumo no Chat: "Reação à ordem (reconstrução): 16 aceitam, 2 vão atrasar, 3 resistem."
4. **Especiais**:
   - `reconstruir`: objetivo `construir` no lugar (o citado, ou o pior estrago) para quem aceitou.
     O conserto é o de sempre (ação `conserta`, aos poucos, manhã/tarde, falha de pastelão). Quem
     começa `construir` lá entra em `builders`. Pronto quando todas as estruturas do lugar
     voltam ao estado `inteiro` (`commands.needs_rebuild`): `creator_order phase: done` com os construtores, memória `mutirao`, +2 de
     afinidade com o Chefe. Prazo `horas` (72) → `abandonada`. Nada estragado → `ordem_sem_estrago`.
   - `festa`: `social_events.plan_now` (o Chefe organiza a `festa_taverna`; convidados, quórum e
     fracasso são os da F2).
   - `regra`: `proibido` / `liberado` + a ação (id, nome ou `apelidos`; sem ação, o Chefe inventa uma
     das `sugestoes`). **Decreto** por `horas`: proibido → a ação vira a infração `decreto` (ou mantém
     a sua) para o Fiscal, e a nota dela × `obediencia` (por traço: o rebelde faz MAIS, ×1,6);
     liberado → a lei não vê a infração e a nota ×`bonus_liberado`. Fim: `regra_fim`.
   - `reuniao`: assembleia na Praça daqui a `comeca_em_minutos`, objetivo `reuniao` para quem não
     resistiu; no fim, `creator_order phase: done` com os presentes e memória `reuniao`.
   - outras (`paz`, `trabalho`, `missa`): só `efeitos.objetivos` (com resistência; bônus < 1 vira
     objetivo `penalty`: "parem de brigar" deixa `brigar` menos atraente — mudança em
     `utility.goal_bonus`: objetivos com `penalty` multiplicam pelo menor bônus).
5. Assunto do momento `ordem` (as conversas comentam a ordem por 1,5 dia).

#### 13.1.2 `medium "<mensagem>"`

Igual ao Chefe, com `medium.*`: recebe como VOZ (`creator_voice`, `voz_recebida`; se dorme, ouve
em sonho), interpreta por palavras, e com `chance_erro` **entende errado de propósito**: troca a
interpretação por um dos `desastres` (castigo do céu, ritual no Cemitério, festa no meio do
ritual) e repete a mensagem torta (uma palavra trocada por uma de `palavras_trocadas`: "a lua pede
**sapos** na floresta"). Ao `revelar_visao` (em qualquer lugar), os `efeitos` valem: objetivos
para `quem_recebe` (ela), `seita` (os membros atuais), `igreja` ou `todos`, com a resistência dela
(devotos e burocratas ignoram); necessidades; evento social (`rave_secreta`).

### 13.2 REST (FastAPI, `server.app`) ✅

```
GET  /health                            simulação viva? ticks, erro, MQTT, LLM
GET  /api/state                         hora, período, clima, tensão, população, mortos, névoa, criaturas, pausado
GET  /api/characters                    lista (id, nome, lugar, ação, vivo, preso, facção, profissão)
GET  /api/characters/{id}               ficha viva (comando `quem`, pela fila; 404 se não existe)
GET  /api/places                        lugares + quem está lá + névoa + tela + estruturas
GET  /api/screens                       telas do world.yaml + offline
GET  /api/meta                          personagens, lugares, categorias, tipos, comandos (filtros do Chat)
GET  /api/chat?character=&place=&tag=&type=a,b&since=&until=&min_importance=&limit=&before_id=&after_id=&include_moves=
GET  /api/timeline?min_importance=2&limit=50&before_id=
POST /api/commands   {"cmd": "chefe", "arg": "reconstruam a ferraria", "id": "opcional"}
     → 202 {"id", "status": "feito"|"na_fila", "result"}   (espera até 2 s; `status`/`quem` até 5 s)
GET  /api/commands, /api/commands/{id}   últimos comandos e o resultado de cada um
GET  /api/models                        F5: {"characters": [ids], "places": [ids]} com .glb em viewer/public/models
GET  /chat (viewer/chat.html), / → /chat, /docs (OpenAPI do FastAPI)
GET  /viewer/ (viewer/dist, `npm run build`; sem build: página 503 explicando), /viewer/layout.html,
     /viewer/models/* (direto de viewer/public/models; DW_VIEWER_DIST e DW_MODELS_DIR mudam os caminhos)
```
`since`/`until` são horas do MUNDO em ISO (comparação de texto; o fuso é sempre o do world.yaml).
`/api/chat` esconde `tension` e os passos de caminhada (a não ser `include_moves=true`).
`Storage.query_events` ganhou `after_id`, `since`, `until`, `min_importance`, `exclude_types` e
vários tipos separados por vírgula.

### 13.3 WebSocket `/ws?screen=<id>` (contrato com o viewer) ✅

Implementado em `server/ws.py` (`Hub`). Servidor → cliente:

```jsonc
// 1) logo ao conectar
{"type": "hello", "screen": "parede_centro", "protocol": 1,
 "world": {"ts", "period", "is_night", "speed", "paused", "weather": {"label", "kind", "temp", "forced"}, "tension", "population"},
 "screens": [{"id", "name", "places": [], "position_cm": {"x", "y"}, "size_cm": {"width", "height"}}],
 "places": [{"id", "name", "palette": {"main", "secondary", "light", "night"}, "sinister", "environment",
             "fog", "connections": [{"to", "kind", "minutes"}], "structures": [{"id", "name", "place", "hp", "state"}]}],
 "characters": [{"id", "name", "place", "action", "moving", "visual": {"color", "secondary_color", "height", "body", "hat", "accessory"}}]}
// 2) fluxo: só o que toca os lugares desta tela (place, from/to, from_place/to_place) + o global (place nulo) + Aparição
{"type": "event", "event": { ...Event (seção 8) com text_rendered... }}
{"type": "bubble", "id": "chef_wife", "place": "...", "text": "A Cozinheira: \"Come que esfria!\"", "duration_s": 4}
{"type": "character", "id", "name", "place", "alive", "action", "moving", "visual"}   // depois de ação, chegada, morte...
{"type": "move", "id", "from", "to", "duration_s"}          // caminhada dentro da tela (minutos × 60 ÷ velocidade)
{"type": "teleport", "phase": "start"|"end", "id", "from_place", "to_place", "from_screen", "to_screen", "duration_s"}
{"type": "fog", "place": "forest", "on": true}
{"type": "weather", "label", "kind", "forced"}
{"type": "clock", "ts", "period", "is_night", "speed", "paused"}   // a cada 5 s reais e na troca de período
{"type": "apparition", "screen", "places": [...], "duration_s": 4}
```
(Diferenças do plano: `palette` usa as chaves em inglês do `Palette`; `clock` vai a cada 5 s reais,
não a cada minuto do mundo.)

**F5 — acréscimos ao contrato (protocolo continua 1, só campos novos):**
- `hello.screens[]` ganhou `max_fps`, `quality` e `offline`; `hello.config = {"visual": <world.yaml >
  visual>, "tunnel": {"led_speed_cm_per_s", "min_duration_s"}}`; `hello.place_names` (todos os
  lugares, para o portal dizer para onde vai); `hello.creatures` (`uid`, `kind`, `place`); `hello.dead`
  (lápides no Cemitério); `visual` de cada personagem traz também `appearance` e `movement` (texto).
- `bubble` ganhou `short` (sem o "Nome: " e as aspas, cortado em `visual.baloes.max_letras`) e
  `duration_s` proporcional ao texto (`segundos_minimos + letras × segundos_por_letra`, até o máximo).
- Mensagens novas: `{"type": "creature", "uid", "kind", "place", "on"}` (criatura aparece/some) e
  `{"type": "structures", "place", "structures": [{"id", "state", "hp"}]}` (depois de `structure_changed`).

Cliente → servidor: `{"type": "ping"}` → `pong`; `{"type": "resync"}` → `hello` de novo. Tela
inexistente: `{"type": "error", "screens": [...]}` e fecha. `/ws/chat` (e `/ws` sem `screen`):
`hello` com todos os lugares e depois **todos** os eventos (`{"type": "event"}`), menos `decision` e
`tension`. Cada cliente tem uma fila (2000); cliente lento perde mensagens, o mundo nunca espera.

### 13.4 MQTT (`server.mqtt_bridge`) ✅

paho-mqtt 2.x: `mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=...)`,
`connect_async` + `loop_start()`, `reconnect_delay_set(1, reconectar_segundos)`, LWT
`world/status = offline` (retido), `online` retido ao conectar e `offline` ao sair. Broker fora:
**um** aviso no log por queda e a simulação segue. O handler só converte o payload
(`parse_message`, testável sem broker) num `Command` e põe na fila.

| Tópico | Direção | Payload |
|---|---|---|
| `world/events` | publica | Event (seção 8, com `text_rendered`) com `importance >= 1` |
| `world/state` | publica, retido, a cada `estado_a_cada_minutos` (÷ velocidade, mín. 2 s reais) | `{"ts","period","is_night","weather","tension","population","alive","places":{id:[ids]},"fog","paused","speed"}` |
| `world/chat` | publica (toda fala) | `{"from","from_name","text","ts","meta":{"world_ts","place","to","situation","tags"}}` |
| `leds/tunnel` | publica | `{"phase":"start"|"end","char","from_screen","to_screen","from_cm":{x,y},"to_cm":{x,y},"duration_ms","color"}` |
| `world/status` | publica, retido | `online` / `offline` (LWT) |
| `world/commands/result` | publica | `{"id","cmd","arg","result","ts"}` (resposta de cada comando recebido) |
| `world/commands` | escuta | `{"cmd","arg","id"}` ou texto `chefe reconstruam a ferraria` |
| `sala/camera/pessoas` | escuta | `{"count": n}` (ou `pessoas`/`people`), número, `true/false` → `presenca n` |
| `homelab/servicos/#` | escuta | `{"status": "down"|"up"|"degraded", "name"?}` ou texto; o sufixo do tópico é o serviço → `homelab <serviço> <status>` |
| `telas/+/status` | escuta | `online`/`offline` (ou `{"status"}`, `on/off`, `1/0`) → `tela <id> online|offline` |

### 13.5 Docker ✅

`Dockerfile` (python:3.12-slim): instala o pacote, copia `data/` e `viewer/`, `EXPOSE 8000`,
`HEALTHCHECK` em `/health`, `CMD python -m server --porta 8000`. `docker-compose.yml`: **um serviço**
`world` (simulação + servidor no mesmo processo, seção 1.1), porta `${DW_SERVER_PORT:-8000}:8000`,
volumes `./data` e `./var`, `.env` opcional, `restart: unless-stopped`, `stop_grace_period: 20s`
(o SIGTERM do Docker faz o uvicorn desligar e o `Runtime.stop()` salvar). O Chat do Mundo também
sai no stdout (`docker compose logs -f world`; `--sem-chat` desliga). **F5:** o `Dockerfile` tem um
estágio `node:22-slim` que roda `npm ci && npm run build` e copia `viewer/dist` para a imagem final
(sem Node); `viewer/public/models` é volume no compose (troca de .glb sem rebuild).

### 13.6 O olhar e a Aparição (`sim.presence`) ✅

`presenca n` liga a "sensação" de gente no quarto por `presenca_expira_minutos`. Com presença: nota
de `encarar_tela` × `multiplicador_olhar` (fator "presença no quarto" na explicação) e o **olhar
coletivo** (de hora em hora, `limites.chance_olhar_por_hora` × `multiplicador_olhar_coletivo`; num
lugar visível numa tela, até `max_no_olhar_coletivo` acordados param e encaram; evento `stare`).
**Aparição**: a cada ENTRADA no quarto (0 → 1+), com `chance_aparicao` e cooldown
`limites.cooldown_aparicao_dias`: evento `apparition` (importância 3, tela com mais gente acordada),
reações (Padre `aparicao_padre`, Médium `aparicao_medium` — os dois mesmo dormindo —, quem é
`estranho` `aparicao_esquisito`, até 3 da seita `aparicao_seita`, 2 outros), medo +20 em todos, a
seita em êxtase (fé −30), memória permanente `aparicao` (quem dormia, mais fraca), objetivos de
`presenca.objetivos` (ritual, missa, encarar a tela) e assunto `aparicao` por 5 dias.

### 13.7 Assuntos do momento

`criador.assuntos.<id>` (`dias`, `chance`, `acoes`): depois de uma ressurreição, de uma Aparição ou
de uma ordem, quando alguém começa `conversar`, com `chance × (1 − tempo_passado/dias)` a fala sai
da situação `assunto_<id>` com `{terceiro}` = de quem se fala (nunca com ele mesmo).

## 14. Fase 5 — visual ✅

Guia dos modelos: `docs/guias/06_modelos_3d_e_design.md`. Tudo que é número ou mapeamento está em
`world.yaml > visual` (qualidades, balões, escala dos personagens, nomes, relógio, névoa,
`animacao_por_acao`, `animacao_por_evento`, `animacao_substituta`) e `telas[].fps_max/qualidade`.

- **Build e serviço:** Vite (`viewer/`, `base: /viewer/`, duas entradas: `index.html` e `layout.html`)
  gera `viewer/dist`, servido pelo FastAPI em `/viewer`. `npm run dev` (porta 5173) faz proxy de `/api`,
  `/ws`, `/chat` e `/health` para `DW_API` (padrão `http://localhost:8000`). `dist/` e `node_modules/`
  ficam fora do git; o Docker constrói.
- **Uma cena por tela:** os lugares da tela viram dioramas de 10 × 10 m numa grade automática
  (`logic.gridLayout`: colunas × linhas que deixam cada diorama maior na proporção da janela; a ordem é
  a de `telas[].lugares`). A câmera (perspectiva, ~53° de cima) é ajustada por busca binária para
  caber tudo. `?foco=<lugar>` enquadra um lugar só.
- **PS1:** canvas pequeno (`altura_render` da qualidade) ampliado com `image-rendering: pixelated`;
  `MeshLambertMaterial` com `flatShading` e um `onBeforeCompile` que arredonda `gl_Position` para uma
  grade (vertex snapping, um uniform só para todos); névoa linear do three na cor do céu. Malhas paradas
  de cada cenário são juntadas por material (`shapes.bake`): poucas chamadas de desenho.
- **Placeholders:** `characters.buildPlaceholder` lê `visual` + `appearance` + `movement` (palavras
  reconhecidas na seção 4 do guia). Pivôs em quadril, ombros e pescoço; grupo `pose` para deitar/cair/
  ajoelhar. `places.buildPlace` tem um construtor por id e um genérico por `ambiente` + `paleta`.
- **.glb:** `GET /api/models` diz quais existem (o Vite devolve HTML para arquivo inexistente; o
  servidor responde certo nos dois modos). `GLTFLoader` + `SkeletonUtils.clone`; materiais trocados
  por Lambert com snapping, texturas com `NearestFilter`; escala de segurança (fora de 0,3–6 m) e
  origem no chão. Animação: `logic.pickClip` (exato → começa com → contém → substitutas → idle);
  se não for exata, `proceduralRoot` completa no corpo inteiro.
- **Animação:** a da ação vem de `animacao_por_acao`; eventos (`slapstick`, `fight`, `stare`...) tocam
  uma animação curta por cima (`Actor.play`); na briga um vira para o outro; `stare` vira para a câmera;
  morte = tombo + afunda no chão. Cada personagem tem um ponto no diorama (fixo por id + ação, sem
  dois no mesmo ponto); `walk` sem caminho = passeio pelo lugar.
- **Movimento:** `move` (dentro da tela) = caminhada em linha reta (mínimo 0,8 s para dar para ver);
  `character` com lugar fora da tela = some.
- **Túnel:** cada conexão `tunel` vira um portal no diorama (anel roxo + nome do destino). `teleport
  start` na origem: anda até o portal, é "sugado" (estica e some) e um risco de luz corre até a borda
  da tela na direção da tela de destino (pelas `posicao_cm`). No destino o portal acende; o personagem
  aparece em `max(início + duration_s, fim)` (`logic.teleportAppearAt`): quando a luz de LED chegou
  E a simulação disse que saiu. O `leds/tunnel` no MQTT é o da F4 (origem, destino, cm, duração).
- **Ambiente:** hora local do mundo pelo `ts` (interpolada entre os `clock` com a velocidade),
  `daylight()` com amanhecer 5–7 h e anoitecer 17h30–19 h; céu e luz mudam, o chão vai para
  `paleta.noite`, janelas e lampiões acendem; céu puxado para azul de terror pela fração de lugares
  sinistros da tela. Chuva (linhas) por `rainIntensity` (garoa < chuva < tempestade; clima forçado ou
  funeral = forte, com relâmpagos). Neblina aproxima a névoa. `fog` (tela offline) = nuvens densas
  cobrindo o diorama, conteúdo e personagens escondidos, nome "— na névoa".
- **Balões e textos:** HTML por cima do canvas (nítido e legível de longe): balões com contorno
  grosso, empilhados para não se sobrepor, no máximo 4; nomes embaixo dos pés (o de trás some quando
  dois se encostam); nomes dos lugares; relógio e clima no canto.
- **Aparição:** só na tela do evento: uma silhueta escura feita de 6 cópias semitransparentes
  deslocadas (borrão) atravessa entre a câmera e o mundo em 1,7 s, a tela escurece nas bordas e todos
  os NPCs da tela fazem `stare` por `duration_s + 2`.
- **Desempenho:** limite de FPS por tela no laço (`requestAnimationFrame` pulando quadros), qualidade
  por tela, luzes pontuais só na `alta`. Medido no Chromium sem GPU (SwiftShader): 30 FPS na TV do
  centro (11 lugares, 21 personagens) e 20 na tela do homelab (limite dela).
- **`viewer/layout.html`:** SVG da parede (y para cima, em cm), telas com nome/lugares, linhas dos
  túneis entre telas com distância e duração do LED, cards com qualidade/FPS; ao vivo pelo `/ws/chat`
  (cada `teleport_started` corre um ponto de luz pela linha; telas na névoa ficam cinzas).
- **Depuração:** `window.__dw` (contadores de mensagens, FPS, atores, log de túnel e Aparição,
  `__dw.live()` com o estado na hora) — é o que os testes com Playwright leem.

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

- Layout interno dos lugares numa tela — F5 ✅: grade automática (seção 14).
- Esquema das criaturas — F3 ✅ (seção 12.7).
- F4 ✅: `world/commands`, `homelab/servicos/#` e `telas/+/status` ligados (`server.mqtt_bridge`);
  `reviver` usa `lifecycle.resurrect(cid, "criador")`; situações do LLM em `ollama.situacoes`.
- F5 ✅: o viewer consome o contrato da seção 13.3 (com os acréscimos da F5). Layout dos lugares
  numa tela continua automático; um campo `visual` no YAML do lugar (posição/tamanho na grade) fica
  para quando o João pedir.
- F6 ✅: `recarregar` (seção 3.3). Fase 6 também: entradas `presenca_lider.<facção>` e
  `afinidade_lider.<facção>` (missa e ritual seguem o líder ATUAL), aviso do validador para lugar com
  estruturas sem ação de conserto, `limites.dias_minimos_entre_mortes_naturais` e `limites.max_mortes_em_7_dias`/`causas_fora_do_limite` (teto semanal de mortes sorteadas, em `lifecycle.roll`), contração de nomes com
  artigo minúsculo ("em a bigorna" → "na bigorna"), `tools.backup`, material emissivo no `.glb` de
  personagem. Detalhes e balanceamento: `docs/relatorios/FASE_6.md`.
- Técnicos: continuam trabalhando na Sala do Servidor como profissão (manhã/tarde); um problema real
  (`homelab/servicos/<nome>` down, agora pelo MQTT) traz o Gremlin do Rack e o objetivo de
  enfrentar (F3). Fazer o trabalho deles depender SÓ de problema aberto ficou para a F6.
- Médium: com o `ritual` (F2) as noites dela são de ritual; o bloco provisório de `rezar` saiu.
- Diretor (F3) deve usar `World.add_goal` e `World.say` (mesmo mecanismo dos convites) e pode
  medir a tensão pelas contagens de `fight`/`argument`/`arrest` recentes.
- Limbo é raro numa semana (precisa de 6 pontos de infração); se o João quiser mais, baixe
  `leis.pontos_para_limbo`.
