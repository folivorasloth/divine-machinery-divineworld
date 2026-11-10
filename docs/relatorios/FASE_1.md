# Relatório — Fase 1: Núcleo da simulação (headless)

**Data:** 2026-11-10  ·  **Status:** concluída

## Resumo em 3 linhas
O mundo já vive sozinho, em texto: os 21 NPCs têm necessidades que sobem com o tempo, escolhem o
que fazer por Utility AI (com o motivo de cada escolha no log), andam pelo grafo de lugares (com
túneis), trabalham, comem, dormem, conversam e festejam; o Mike perambula e o Padre toca o sino às
6h, 12h e 18h. Tudo aparece no Chat do Mundo no terminal (`python -m tools.run`) e fica salvo em
SQLite: ao religar, o mundo continua de onde parou.

## O que foi feito
- **Relógio e tick** (`sim/clock.py`, `sim/engine.py`): passo fixo de 1 minuto do mundo; tempo
  real × multiplicador (`--speed`), ou o mais rápido possível (`--fast`). Períodos (madrugada,
  manhã, tarde, noite), dia/noite, evento `period_changed`. Ao religar em tempo real, recupera até
  `max_recuperacao_horas` e pula o resto com "O mundo cochilou por N horas".
- **Necessidades** (`sim/needs.py`): taxas de dia/noite do `world.yaml` × multiplicador do
  personagem × traços; modos `acumula` e `retorna`; efeito da ação em andamento aplicado aos poucos;
  quem dorme não ganha sono. Nova variável `{humor}` nas falas (a necessidade mais alta).
- **Utility AI** (`sim/utility.py`): candidatos (ação × lugar × alvo), nota = peso × curvas ×
  traços × rotina × viagem × repetição, sorteio ponderado entre as 3 melhores (só as que valem ≥ 40%
  da melhor), explicação com top 3 e cada fator. Quem está ocupado é reavaliado a cada 10 minutos
  e no começo de cada bloco da rotina: troca de ação se algo valer muito mais (é assim que o Padre
  larga a missa para tocar o sino na hora certa e que as pessoas acordam).
- **Ações** (YAML): `trabalhar`, `comer`, `dormir`, `cochilar`, `conversar`, `festejar`, `rezar`,
  `perambular`, `encarar_tela`, `tocar_sino`. Novos campos opcionais nas ações (todos no YAML):
  `narracao`, `narracao_fim`, `dormindo`, `vagar`, `cooldown_minutos`, `evento: bell`,
  `fala_alvo`/`chance_fala_alvo` (o alvo de uma conversa responde).
- **Movimento** (`sim/pathfinding.py`): Dijkstra pelos minutos das conexões, evitando lugares
  `especial`/`nunca` (e, na Fase 3, a névoa). Caminho → `move_started`/`move_arrived`; túnel →
  `teleport_started`/`teleport_finished` com `from_place`, `to_place`, `from_screen`,
  `to_screen` e `duration_s` (distância entre as telas ÷ velocidade do LED).
- **Conversa e falas** (`sim/speech.py`): dois NPCs acordados no mesmo lugar conversam; a fala sai
  de templates por situação com filtros (personagem, traço, lugar, período, clima, necessidade),
  bordões, anti-repetição e uma resposta do alvo. Novas situações/falas: `resposta` (12 falas) e
  +14 em `conversa`.
- **Chat do Mundo no terminal** (`tools/run.py`): cores por tipo de evento (`rich`), filtros por
  personagem e lugar, e opções para uso não interativo: `--horas N`/`--dias N` (roda e sai),
  `--fast`, `--novo`, `--seed`, `--inicio HH:MM`, `--saida arquivo`, `--resumo` (tabela do dia de
  cada personagem), `--debug` (cada decisão com top 3 e motivos), `--movimento`.
- **Persistência** (`sim/persistence.py`): SQLite com migrações (`meta`, `characters`, `events`,
  `event_actors`, `event_tags`, `relations`). Salva hora do mundo, seed, estado do RNG, estado de
  cada personagem (por id), ações em andamento e o Chat do Mundo inteiro (consultável por
  personagem, lugar, tag e tipo). Ctrl+C e SIGTERM salvam antes de sair.
- **Nomes com artigo** (`sim/text.py`): "em A Praça" vira "na Praça", "rumo a A Praça" vira
  "rumo à Praça", "com O Músico" vira "com o Músico" — sem mudar nada nos YAML.
- **Docker**: o serviço `sim` agora roda `python -m tools.run` em tempo real (`restart:
  unless-stopped`); `tzdata` entrou nas dependências para o fuso funcionar na imagem enxuta.
- `docs/arquitetura.md` atualizado (seções 2, 4 a 10, 15 e 16).

## Como testar (passo a passo)
```bash
cd divine-machinery-divineworld
.venv/bin/pip install -e ".[dev]"      # tzdata é dependência nova

# 1) dados e testes
.venv/bin/python -m tools.validate      # "Tudo certo! 0 erros, 0 aviso(s)."
.venv/bin/python -m pytest              # "93 passed" (~20 s)

# 2) um dia inteiro em ~4 segundos, do zero, com resumo no fim
.venv/bin/python -m tools.run --fast --dias 1 --novo --inicio 00:00 --seed 42 \
    --banco var/teste.sqlite --resumo
#    O chat rola do 00:00 ao 24:00 e termina com a tabela "Resumo por personagem":
#    todo mundo com dormir ≥ 1, comer ≥ 2; quem tem profissão com trabalhar ≥ 1 (Mike 0);
#    Mike com a coluna "perambular" muito maior que as outras;
#    legenda "Sino tocado às: 06:00, 12:05, 18:00" (com a seed 42).

# 3) o critério de aceite: --speed 600 por 5 minutos reais (≈ 2 dias do mundo)
.venv/bin/python -m tools.run --speed 600 --novo --inicio 00:00 --seed 2026 \
    --banco var/aceite.sqlite --saida var/aceite_chat.txt --resumo
#    deixe rodar 5 minutos e aperte Ctrl+C (ou use `--dias 1`, que sai sozinho em ~2,4 min).
#    Deve sair "Ctrl+C: salvando o mundo...", a tabela e "Mundo salvo em var/aceite.sqlite".
#    Sem erros. var/aceite_chat.txt guarda o chat sem cores.

# 4) continuar de onde parou (não use --novo): a hora do mundo segue da salva
.venv/bin/python -m tools.run --fast --horas 2 --banco var/aceite.sqlite
#    a primeira linha mostra a hora do mundo salva e termina com "(continuando)";
#    no banco fica o evento de sistema "O mundo acorda de onde parou."

# 5) filtros e explicação das decisões
.venv/bin/python -m tools.run --fast --horas 1 --novo --inicio 05:50 --seed 42 \
    --banco var/demo.sqlite --personagem priest --debug
#    mostra "O Padre escolheu tocar_sino@cathedral (150.00) | top3: ..." com os fatores
#    (peso×30.00 × rotina×5.00) e "SINO O Padre toca o sino da Catedral: são 06:00."
.venv/bin/python -m tools.run --fast --horas 6 --banco var/demo.sqlite --lugar tavern --movimento

# 6) tempo real (o modo do homelab); Ctrl+C salva
.venv/bin/python -m tools.run           # ou --speed 60 (1 hora do mundo por minuto)
```
Sem `--banco`, o arquivo é o do `world.yaml` (`var/world.sqlite`, ou `DW_DB_PATH`). Sem
`--inicio`, um mundo novo começa na hora real. MQTT e Ollama não são usados nesta fase.

## Amostra real
Saída real de `tools.run --speed 600 --novo --inicio 2026-11-09T00:00 --seed 2026 --saida
var/aceite_chat.txt --resumo`, rodado por 5 minutos reais (`timeout 300`): 2996 ticks (de 09/11
00:00 a 11/11 01:56), 1195 linhas no chat, nenhum erro no stderr, saída final "Mundo salvo em
var/aceite.sqlite". Trecho do Chat do Mundo, almoço do primeiro dia (copiado do arquivo):
```
[09/11 11:51] (O Mar) Mike sai do túnel no Mar.
[09/11 11:51] (O Mar) Mike anda sem rumo até o Mar.
[09/11 11:53] (A Feira) O Músico senta para comer na Feira.
[09/11 11:54] (A Praça) A Dama sai do túnel na Praça.
[09/11 11:54] (A Praça) A Dama fecha os olhos um pouquinho na Praça.
[09/11 11:57] (A Catedral) O Fool faz truques para as crianças na Catedral.
[09/11 11:58] (A Praça) O Adolescente anda sem rumo até a Praça.
[09/11 11:59] (A Cozinha Comunitária) O Aprendiz e a Cozinheira falam do tempo: nublado.
[09/11 11:59] (A Cozinha Comunitária) A Cozinheira ri do que o Aprendiz disse.
[09/11 12:00] Começa a tarde.
[09/11 12:00] (A Catedral) SINO O Padre toca o sino da Catedral: são 12:00.
[09/11 12:00] (A Catedral) O Padre puxa a corda do sino com força demais e tropeça na batina. "Deus me livre e guarde!"
[09/11 12:01] (A Feira) O Ferreiro come um prato fundo de sopa na Feira.
[09/11 12:01] (O Mar) O Ganancioso pergunta pra Mike, desconfiado, o que tem nos bolsos. "É meu."
[09/11 12:01] (O Mar) Mike concorda com a cabeça e não diz nada.
[09/11 12:06] (A Cozinha Comunitária) O Cozinheiro cozinha para a cidade na Cozinha Comunitária.
[09/11 12:06] (O Mar) O Ganancioso cochila sentado.
[09/11 12:10] (A Feira) O Padre senta para comer na Feira.
[09/11 12:12] (A Cozinha Comunitária) O Cowboy Magrelo senta para comer na Cozinha Comunitária.
[09/11 12:15] (A Feira) O Chefe senta para comer na Feira.
[09/11 12:16] (A Cozinha Comunitária) O Adolescente senta para comer na Cozinha Comunitária.
[09/11 12:17] (A Praça) A Dama acorda do cochilo, meio perdido.
```
Sinos do mesmo run: `grep SINO var/aceite_chat.txt`
```
[09/11 06:05] (A Catedral) SINO O Padre toca o sino da Catedral: são 06:05.
[09/11 12:00] (A Catedral) SINO O Padre toca o sino da Catedral: são 12:00.
[09/11 18:00] (A Catedral) SINO O Padre toca o sino da Catedral: são 18:00.
[10/11 06:00] (A Catedral) SINO O Padre toca o sino da Catedral: são 06:00.
[10/11 12:00] (A Catedral) SINO O Padre toca o sino da Catedral: são 12:00.
[10/11 18:00] (A Catedral) SINO O Padre toca o sino da Catedral: são 18:00.
```
O dia 10/11 inteiro de alguns personagens, tirado do banco do mesmo run (ações iniciadas):
```
Padre:  05:46 acorda · reza (catedral) · 06:00 SINO · 06:03 trabalha · 10:26 come (cozinha) · 11:05 trabalha
        · 12:00 SINO · 12:05 trabalha · 14:38 come (feira) · 14:50 conversa · 15:13 trabalha · 18:00 SINO
        · 18:08 come · 18:25 trabalha · 19:08 reza · 20:10 festeja (taverna) · 21:01 conversa · 21:25 dorme
Chefe:  07:40 acorda · 07:47 come · 08:05 trabalha (prefeitura) · 11:34 come · 12:18 perambula
        · 13:37 trabalha · 15:28 cochila · 15:53 conversa · 16:00 trabalha · 18:29 come (cozinha)
        · 18:50 conversa · 19:09 cochila · 19:35 festeja (taverna) · 21:37 dorme
Cowboy Velho: 07:46 acorda · come · 08:11 trabalha (campo) · 11:08 conversa · 13:42 come · 14:23 trabalha
        · 16:11 conversa · 17:34 conversa · 18:44 come · 19:51 festeja (taverna) · 21:47 festeja · 22:47 dorme
Adolescente: 03:00 acorda · come · 03:44 dorme · 12:00 acorda · perambula ... (5 conversas) · 18:28 come
        · 19:05 festeja (taverna) · 22:11 dorme
Mike:   08:21 acorda · come · perambula: mar, feira, praça, prefeitura, sala do servidor, prefeitura,
        sala do servidor, ... (26 vezes, 10 lugares) · 17:00 come · 21:47 dorme
```
Resumo do run (contagem nos ~2 dias; trecho da tabela real): Mike perambular 43, trabalhar 0,
conversar 0+2; Padre tocar_sino 6, trabalhar 13; todos com dormir ≥ 2, comer ≥ 5; quem tem
profissão trabalhou 7 a 14 vezes; 110 viagens por túnel.

## Decisões tomadas e por quê
- **Reavaliação com interrupção** (`reavaliar_a_cada_minutos`, `fator_interrupcao`,
  `nota_para_interromper`, `nota_para_acordar` no world.yaml) — sem isso, uma ação longa (dormir 8h,
  trabalhar 3h) cega o NPC: o Padre perdia o sino e ninguém acordava para trabalhar. Para acordar
  quem dorme o motivo precisa ser mais forte (2.0), para não acordarem por qualquer coisa.
- **Reavaliação também no minuto em que começa um bloco de rotina ou a janela do sino** — mantém o
  sino em 06:00/12:00/18:00 em ponto quando o Padre está perto, sem código especial para o sino.
- **`fracao_da_melhor: 0.4`** — com só "top 3 proporcional", nas horas mornas a 3ª opção (às vezes
  boba) saía demais. Ainda há variedade, mas ninguém escolhe algo que vale menos da metade.
- **Campos novos nas ações em vez de código por ação** (`dormindo`, `vagar`, `narracao`,
  `cooldown_minutos`, `evento: bell`, `fala_alvo`) — o João muda comportamento no YAML.
- **`perambular` vai para um vizinho sorteado, evitando lugares perigosos, exceto para quem tem a
  imunidade `criaturas` (o Mike)** — ele vai a qualquer bioma; os outros ficam mais na cidade.
- **Mundo novo de madrugada começa com quem tem rotina de dormir já dormindo** — senão o primeiro
  dia de um mundo criado às 3h tinha a cidade toda acordada.
- **O "executor de planos" ficou no `engine.py`** (o plano previa `actions.py`) — é pouco código e
  depende de tudo do mundo; separar só espalharia a leitura.
- **Ids de evento dados pelo mundo e o estado do RNG salvo** — parar e continuar produz exatamente a
  mesma história que rodar direto (há teste).
- **Contrações automáticas de artigos nos nomes** — "O Chefe chega em A Praça" ficava feio; agora é
  na exibição (`render`), então renomear continua sem efeito colateral.
- **Ajustes de balanceamento só em YAML**, depois de rodar dias de verdade:
  `sono.taxa_dia` 4→3 e `taxa_noite` 7→6; custo de sono de `trabalhar` 8→3; `dormir` 7–10 h e
  curva de hora mais forte; `cochilar` só de dia; curva de `comer` mais exigente; `festejar` saiu
  da Praça e da Feira (fica na Taverna, Campo, Mar, Floresta, Subterrâneo); `rezar` saiu da Prisão;
  traço `vazio` (Mike) com `festejar` e `rezar` ×0.2; notívagos com sono mais lento (Cowboys,
  Músico, Palhaço 0.8, Médium 0.5, Adolescente 0.6); Esquisito com mais peso em encarar a tela;
  Padre reza na Catedral das 05:20 às 06:00 (fica perto do sino); Médium reza na floresta à noite
  enquanto o ritual não existe; atividade dos Técnicos e Vaqueiros reescrita para a frase ficar
  natural.
- **Clima fixo `nublado`** (`clima_padrao`) nas falas — o clima real é da Fase 3.

## Arquivos principais criados ou alterados
- `sim/clock.py`, `sim/rng.py`, `sim/state.py`, `sim/needs.py`, `sim/pathfinding.py`,
  `sim/utility.py`, `sim/speech.py`, `sim/events.py`, `sim/persistence.py`, `sim/engine.py` — o núcleo.
- `sim/schemas.py` — campos novos (ações, decisão, humor); `sim/loader.py` — valida os campos
  novos; `sim/text.py` — `{humor}` e contrações.
- `tools/run.py` — `python -m tools.run` (Chat do Mundo no terminal).
- `data/world.yaml`, `data/actions/*.yaml`, `data/lines/social.yaml`, `data/lines/fe.yaml`,
  `data/traits.yaml`, alguns `data/characters/*.yaml` e `data/places/*.yaml` — ajustes acima.
- `tests/test_clock_needs.py`, `tests/test_pathfinding.py`, `tests/test_utility_speech.py`,
  `tests/test_engine.py` (+ ajustes em `test_rename.py`, `test_curves_text.py`).
- `docs/arquitetura.md`, `README.md`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`.

## Testes
- 93 testes, 93 passando (`.venv/bin/python -m pytest`, ~20 s). 43 novos nesta fase.
- Cobrem: relógio (períodos, noite, meia-noite), necessidades (taxas dia/noite, traços, modo
  retorna, sono não sobe dormindo, limites, humor); caminhos (menor caminho, túneis, lugares
  especiais, bloqueio); Utility AI (comer com fome no almoço, trabalho só no local e com profissão,
  sino só nas janelas e com cooldown, conversa só com quem está acordado no mesmo lugar, afinidade
  mínima, escolha reproduzível com seed, corte relativo, explicação com top 3 e fatores, o Padre
  largando o trabalho para tocar o sino); falas (filtros, bordões, falas sem alvo puladas,
  anti-repetição); um dia inteiro (todo NPC dorme, come ≥ 2, trabalha se tem profissão, quase todos
  conversam, ninguém fica parado num lugar só, dormir só à noite), Mike perambulando por ≥ 5 lugares,
  sino às 06/12/18 dentro da janela, eventos de túnel com dados para os LEDs, falas sem variáveis
  sobrando; persistência (eventos gravados e consultáveis, continuar de onde parou, mesma história
  parando no meio, renomear muda até o histórico, personagem sumido do YAML fica congelado, recuperação
  de tempo perdido); comandos pausar/velocidade; e a CLI rodando sem interação.
- Além dos testes, rodei 10 seeds de um dia inteiro: sino sempre entre 06:00–06:05, 12:00–12:07 e
  18:00–18:06; Mike perambulou 15–27 vezes; ninguém sem trabalhar ou com menos de 2 refeições.

## Limitações e problemas conhecidos
- **Concordância de gênero**: algumas narrações são no masculino ("A Dama acorda do cochilo, meio
  perdido"). O campo `pronome` existe nos personagens, mas os templates ainda não o usam.
- **Refeições nem sempre no horário da rotina**: a rotina multiplica a nota, mas a fome manda; o
  Padre almoçou às 10:26 num dia. É emergência, mas dá para apertar as curvas se incomodar.
- Às vezes alguém se perde longe de casa e dorme depois da meia-noite (numa das 10 seeds a Dama foi
  perambular no Deserto e só dormiu às 00:01).
- A Médium e o Adolescente dormem mais à noite do que a bible pede (sem ritual e rave, que são da
  Fase 2, a noite deles tem pouco o que fazer).
- Os Técnicos trabalham na Sala do Servidor todo dia como profissão normal; na Fase 4 o trabalho
  deve depender dos problemas reais do homelab.
- `--speed 600` por 5 minutos dá ~2 dias do mundo (600× = 10 minutos do mundo por segundo), não
  um; usei os 5 minutos inteiros como o critério pede.
- Clima é sempre o `clima_padrao` (nublado) — Fase 3.

## Pendências (o que ficou para depois)
- Pronome nos templates de fala/narração — Fase 2 (que expande as falas).
- Ir atrás de alguém em outro lugar para conversar, ritual, brigas, fofoca, memória — Fase 2.
- Comandos do Criador além de pausar/continuar/velocidade, MQTT e API — Fase 4 (a fila de comandos
  e o `snapshot()` já existem).

## Onde o João pode mexer sem programar
- `data/world.yaml > necessidades` — o quão rápido cada necessidade sobe de dia e de noite, e a
  palavra de `humor`; `humor_neutro`.
- `data/world.yaml > decisao` — `top_n`, `temperatura`, `fracao_da_melhor` (variedade × coerência),
  `meia_vida_viagem_minutos`, `penalidade_repeticao`, `reavaliar_a_cada_minutos`,
  `fator_interrupcao`, `nota_para_interromper`, `nota_para_acordar`.
- `data/actions/*.yaml` — peso, duração, curvas, efeitos, `narracao`/`narracao_fim` (o texto do
  Chat), `cooldown_minutos`, `fala`/`fala_alvo` e as chances.
- `data/characters/<id>.yaml > rotina` (horários e pesos: a rotina puxa, não obriga) e
  `necessidades` (ex.: `sono: {taxa: 0.5}` para um notívago).
- `data/places/<id>.yaml > acoes` — o que dá para fazer em cada lugar.
- `data/lines/*.yaml` — falas; a situação `resposta` é o que o alvo de uma conversa responde.

## Revisão do orquestrador
Revisão feita em 2026-11-10, rodando tudo de novo com seeds diferentes das do relatório.

| Critério de aceite | Resultado | Evidência |
|---|---|---|
| `--speed 600` por 5 minutos sem erros, com dia plausível para todos | ✅ passou | `timeout -s INT 300 tools.run --speed 600 --novo --inicio 00:00 --seed 5`: 2995 ticks (09/11 00:00 → 11/11 01:55), 1202 linhas de chat, stderr vazio, zero "Traceback/error", terminou com "Mundo salvo". Rodada extra `--fast --dias 1 --seed 99`: tabela de resumo com todos dormindo ≥1, comendo ≥3, quem tem profissão trabalhando (Mike 0). |
| Mike perambula sem objetivo | ✅ passou | Seed 99: Mike com 17 perambulações, 0 trabalho ("Mike anda sem rumo até a Praça", "Mike come. Só isso."). |
| O Padre toca o sino nos horários | ✅ passou | Seed 99: 06:05, 12:00, 18:02. Seed 5 (2 dias): 06:05, 12:00, 18:00, 06:06, 12:00, 18:02. |
| Relatório traz trecho real do Chat do Mundo | ✅ passou | Seção "Amostra real", copiada de `var/aceite_chat.txt`. |

Também conferido: `pytest` → 93 passed; `tools.validate` → 0 erros; retomar o banco salvo (`--fast --horas 2` sem `--novo`) continua da hora salva (11/11 01:55).
Observação: a 600× cinco minutos são ~2 dias do mundo, não 1 (o critério do prompt arredondou); cobrimos os dois.
