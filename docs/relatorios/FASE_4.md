# Relatório — Fase 4: O Criador, a API e a integração

**Data:** 2026-11-10  ·  **Status:** concluída

## Resumo em 3 linhas
O João agora fala com o mundo: `chefe "reconstruam a ferraria"` vira uma "intuição" que o Chefe
anuncia na Praça e que cada morador aceita, adia ou ignora pela personalidade — e a Ferraria só fica
de pé quando os NPCs escolhem consertá-la. A Médium ouve a voz do Criador (e às vezes entende tudo
errado, de propósito), os mortos podem ser revividos e a cidade comenta por dias. `python -m server`
(ou `docker compose up`) sobe o mundo com API, WebSocket para as telas, ponte MQTT e o Chat do Mundo
na web, com filtros e linha do tempo. Sem Ollama e sem MQTT, tudo continua igual.

## O que foi feito
- **Comandos do Criador** (`sim/commands.py`), pela CLI (`tools/cli.py`), pela API
  (`POST /api/commands`) e pelo MQTT (`world/commands`), todos pela mesma fila do mundo, cada um com
  resposta (`{"ok": ...}`) e histórico (`GET /api/commands`):
  - `chefe "<ordem>"`: palavras-chave em `data/events/criador.yaml` (reconstruir, festa, regra,
    reunião, paz, trabalho, missa), o lugar citado ("a ferraria", "a bigorna" → `forge`), LLM
    opcional e, sem nada, "como dá". O Chefe recebe a **intuição** (`creator_order`), ganha o
    objetivo de ir à Praça **anunciar** (ação `anunciar_ordem`: preguiçoso com sono adia; de
    madrugada não vai) e, ao anunciar, cada morador **aceita, atrasa ou resiste** (traços × afinidade
    com o Chefe; "Reação à ordem: 16 aceitam, 2 vão atrasar, 3 resistem"). Reconstruir = objetivo
    `construir` no lugar para quem aceitou; pronto quando as estruturas voltam a "inteiro" pelo
    conserto normal das ações (com os nomes de quem pegou no pesado). Festa = o Chefe organiza a
    festa da F2. Regra = **decreto** de 3 dias: "proibido andar de skate" vira infração para o Fiscal
    e a nota da ação cai (o Adolescente, rebelde, faz MAIS); "liberem o skate" faz o contrário.
    Reunião = assembleia na Praça com quem não resistiu. Sem Chefe vivo, a ordem espera o sucessor.
  - `medium "<mensagem>"`: a Médium ouve uma **voz** (`creator_voice`), interpreta (ritual,
    espalhar a palavra, paz, reconstruir, festa) e com `chance_erro` (30%) entende errado — de
    preferência um "desastre" (castigo do céu, ritual no Cemitério, festa no meio do ritual) e
    repete a mensagem torta ("a lua pede **sangue de beterraba** na floresta"). Ao revelar a visão,
    ela e a seita ganham os objetivos.
  - `reviver <id>`: o morto volta com traço novo, medo 85 e metade das memórias perdidas; o funeral
    marcado é cancelado; o Padre grita milagre, a Médium diz que foi ela; memória permanente em
    todos e o **assunto do momento** `ressurreicao`: por 4 dias, parte das conversas é sobre isso.
  - `nascer`, `pausar`, `continuar`, `velocidade`, `status` (resumo com ordens, decretos, assuntos,
    presença, LLM), `quem <id>` (ficha viva: necessidades, humor, ação, plano, memórias, de quem gosta
    mais e menos, objetivos, a última explicação de decisão), `tela`, `homelab`, `clima`, e dois de
    teste: `raio <lugar>` (destrói as estruturas, para ver uma reconstrução) e `aparicao`.
- **O olhar e a Aparição** (`sim/presence.py`): `sala/camera/pessoas` → `presenca n`. Com gente no
  quarto, `encarar_tela` vale ×3 e o **olhar coletivo** (um grupo para e encara a tela) fica 4× mais
  provável. A cada entrada no quarto, 3% de chance (cooldown 7 dias) da **Aparição**: silhueta
  borrada, a seita em êxtase, o Padre fala em milagre, o Esquisito anota tudo, memória permanente,
  objetivos (ritual, missa) e assunto por 5 dias.
- **LLM opcional** (`sim/llm.py`): thread próprio, `httpx`, checagem de vida (`/api/tags`), timeout
  curto, `max_por_hora`, só com o mundo no relógio real; reescreve falas importantes (lista em
  `world.yaml > ollama.situacoes`) com contexto real (quem, papel, traços, bordões, humor, lugar,
  clima, hora, 3 memórias fortes) e valida a resposta (só `{@id}` existentes). Também tenta entender
  ordens livres. Fora do ar = template na hora.
- **Servidor** (`server/`): `runtime.py` (simulação num thread + LLM + MQTT, comandos com
  `Future`), `app.py` (REST: estado, personagens, ficha, lugares, telas, meta, chat com filtros de
  personagem/lugar/tipo/categoria/período/importância, linha do tempo, comandos; `/health`; `/chat`),
  `ws.py` (`/ws?screen=<id>`: `hello` com os lugares da tela, depois só o que interessa a ela —
  eventos, balões, movimento, teletransporte, névoa, clima, hora, Aparição; `/ws/chat`: tudo),
  `mqtt_bridge.py` (publica `world/events`, `world/state` retido, `world/chat`, `leds/tunnel`,
  `world/status` com LWT e `world/commands/result`; escuta `world/commands`,
  `sala/camera/pessoas`, `homelab/servicos/#`, `telas/+/status`) e `__main__.py`.
  **Pendências da F3 resolvidas:** `homelab/servicos/#` → comando `homelab`, `telas/+/status` →
  comando `tela`, e `reviver` via `lifecycle.resurrect(cid, "criador")`.
- **Chat do Mundo web** (`viewer/chat.html`, em `/chat`): fluxo ao vivo pelo WebSocket, histórico
  pela API, filtros (personagem, lugar, tipo, período "de/até", só importantes), linha do tempo dos
  grandes acontecimentos, "carregar mais antigos", letra grande ajustável, tema claro/escuro, sem
  build. Parâmetros na URL para deixar uma tela fixa: `/chat?tipo=morte&fonte=28&tema=escuro`.
- **Docker**: `Dockerfile` com `python -m server`, `HEALTHCHECK`, `EXPOSE 8000`; `docker-compose.yml`
  com um serviço `world` (simulação + servidor), volumes `./data` e `./var`. O Chat do Mundo também
  sai no `docker compose logs -f world`.
- **Balanceamento por YAML** (para a ordem fazer diferença e para o relatório de variedade):
  `construir` peso 0,7 → 0,12 (bible: "o que é destruído só volta se eles quiserem ou se o Chefe
  mandar"), traço `protetor` (Ferreiro) `construir ×2`, `vazio` (Mike) `construir ×0,1`; falas novas
  para `tombo_skate`, `trabalhar` do Fiscal e do Esquisito, `resposta_fiscal`; situação nova
  `estrutura_reerguida` (destruído → de pé de novo; "consertado" só quando fica inteiro).

## Como testar (passo a passo)
```bash
cd divine-machinery-divineworld

# 1) dados e testes
.venv/bin/python -m tools.validate
#    "21 personagens, 20 lugares, 47 ações, 54 traços, 14 profissões, 1565 falas em 157 situações,
#     ... 35 tipos de memória, 4 telas."
#    "Tudo certo! 0 erros, 0 aviso(s)."
.venv/bin/python -m pytest -q -o addopts=""
#    "184 passed in 189.03s" (~3 min). O teste de MQTT de ponta a ponta usa o `mosquitto` se estiver
#    instalado (apt install mosquitto); sem ele, esse teste é pulado ("183 passed, 1 skipped").

# 2) o mundo com a API, no relógio acelerado, sem MQTT nem Ollama
.venv/bin/python -m server --novo --banco var/f4.sqlite --nascidos var/nascidos/f4 \
    --speed 300 --seed 21 --inicio 08:00 --porta 8000 --sem-mqtt --sem-llm
#    abre http://localhost:8000/chat  (o Chat do Mundo também passa no terminal)

# 3) noutro terminal: o critério de aceite da reconstrução
.venv/bin/python -m tools.cli raio forge
#    ok: {"place": "forge", "destroyed": ["forge_anvil", "forge_bellows"]}
.venv/bin/python -m tools.cli chefe "reconstruam a ferraria"
#    ok: {"order": 1, "kind": "reconstruir", "how": "palavras", "place": "forge", "receiver": "chief", ...}
.venv/bin/python -m tools.cli status          # repita até a ordem ficar "cumprida" (~1 min real a 300×)
#    ordem #1 (chefe): "reconstruam a ferraria" -> reconstruir [palavras] · cumprida · aceitam 16,
#    atrasam 3, resistem 2 · construíram: ...
.venv/bin/python -m tools.cli chat --lugar forge --limite 40    # quem consertou, minuto a minuto
.venv/bin/python -m tools.cli chat --tipo criador --limite 30   # a intuição, o anúncio, as reações, a obra pronta

# 4) os outros comandos
.venv/bin/python -m tools.cli medium "a lua pede velas na floresta"
.venv/bin/python -m tools.cli quem chief
.venv/bin/python -m tools.cli chefe "proibido andar de skate"
.venv/bin/python -m tools.cli nascer alegre curioso
.venv/bin/python -m tools.cli reviver blacksmith       # "não: O Ferreiro está vivo." (reviver só morto)
curl -s localhost:8000/api/state; curl -s "localhost:8000/api/chat?tag=criador&limit=5"
#    a API inteira, documentada: http://localhost:8000/docs

# 5) Docker (no homelab; aqui no sandbox a imagem foi construída com o certificado do proxy, ver "Decisões")
docker compose up -d --build
docker compose ps                        # dw-world ... Up (healthy)   0.0.0.0:8000->8000/tcp
curl -s localhost:8000/health            # {"ok":true,"simulating":true,...,"mqtt":{"conectado":false,...},"llm":{"no_ar":false,...}}
docker compose exec world python -m tools.cli status
docker compose logs -f world             # o Chat do Mundo ao vivo
docker compose down
```
O que o João deve ver: na Praça o Chefe sobe no caixote; quem gosta dele e é trabalhador vai para a
Ferraria; o Adolescente e o Mike ignoram; o conserto aparece aos poucos ("começa a reerguer a
bigorna", "deixa a bigorna em ordem") e no fim o Chefe corta uma fita imaginária e diz quem pegou no
pesado. No `/chat`, cada linha nova chega sozinha.

**Reviver de verdade** (num mundo rápido, até alguém morrer — a seed 2026 mata o Palhaço no dia 18):
o script de verificação está descrito em "Amostra real"; em resumo: `World(...)` com seed 2026,
`tick()` até o primeiro `death`, esperar o enterro, `handle_command(Command("reviver", id))` e rodar
mais 3 dias.

## Amostra real

**1. `docker compose up` e a reconstrução da Ferraria (imagem construída aqui, `docker compose
exec world python -m tools.cli ...`)** — o mundo começou no relógio real (08:44), depois
`velocidade 300`, `raio forge`, `chefe "reconstruam a ferraria"`, `medium "a lua pede velas na
floresta"`:
```
$ docker compose ps
dw-world   divine-world:dev   "python -m server --…"   world   12 seconds ago   Up 12 seconds (healthy)   0.0.0.0:8000->8000/tcp
$ curl -s localhost:8000/health
{"ok":true,"simulating":true,"ticks":0,"ts":"2026-11-10T08:44:00-03:00","error":null,"mqtt":{"ativo":true,"conectado":false,"host":"mqtt.local",...},"llm":{"ativo":true,"no_ar":false,...}}
$ docker compose logs world
WARNING server.mqtt: MQTT fora do ar (mqtt.local:1883); a simulação continua e tenta de novo.
WARNING sim.llm: Ollama fora do ar (ConnectError): falas pelos templates.
WARNING sim.weather: clima: Open-Meteo indisponível ([Errno -2] Name or service not known); usando cache ou clima_padrao
[10/11 08:45] (As Casas) O Músico ouve o Fool e responde com três notas na viola. ♪
[10/11 08:45] (As Casas) O Fool responde e termina com um "...hehe".
$ docker compose exec -T world python -m tools.cli chat --tipo criador --limite 40
[10/11 08:48] Um raio cai do nada na Ferraria. Destruído: a bigorna e o fole da forja.
[10/11 08:52] O Criador fala com o Chefe: "reconstruam a ferraria"
[10/11 08:52] O Chefe para no meio do caminho, ajeita os óculos e murmura: "reconstruam a ferraria... de onde veio isso?"
[10/11 08:55] O Chefe sobe num caixote na Praça e pede silêncio.
[10/11 08:55] O Chefe aprova a própria ordem em voz alta: "reconstrução, a Ferraria. Aprovado. Vamo vê isso aí."
[10/11 08:55] O Cowboy Velho já sai andando para cumprir: reconstrução. Ô loco, sô.
[10/11 08:55] O Cowboy Magrelo já sai andando para cumprir: reconstrução. Ê trem bão.
[10/11 08:55] A Florista já sai andando para cumprir: reconstrução. Que dia LINDO!
[10/11 08:55] Reação à ordem (reconstrução): 16 aceitam, 2 vão atrasar, 3 resistem.
[10/11 08:56] O Criador fala com a Médium: "a lua pede velas na floresta"
[10/11 08:56] A Médium para, olhos brancos: "a lua pede sangue de beterraba na floresta"... As vozes disseram.
[10/11 08:57] A Médium fecha os olhos, abre os braços e começa a falar devagar nas Casas.
[10/11 08:57] A Médium grita nas Casas: "a lua pede sangue de beterraba na floresta!" e a seita entra em pânico: festa no meio do ritual.
[10/11 08:57] Reação à visão (festa no meio do ritual): 2 aceitam, 0 vão atrasar, 0 resistem.
[10/11 12:13] O Chefe anuncia que acabou a obra da Ferraria. Quem pegou no pesado: O Ferreiro, o Cozinheiro e o Ganancioso.
$ docker compose exec -T world python -m tools.cli chat --lugar forge --limite 80   (sem os passos de caminhada)
[10/11 08:48] Um raio cai do nada na Ferraria. Destruído: a bigorna e o fole da forja.
[10/11 08:58] O Músico arregaça as mangas e conserta o que dá na Ferraria.
[10/11 08:59] O Músico começa a reerguer a bigorna, tábua por tábua.
[10/11 09:00] O Músico tira o entulho e levanta o que sobrou de o fole da forja. Falta muito, mas começou.
[10/11 09:01] A Médium arregaça as mangas e conserta o que dá na Ferraria.
[10/11 09:22] O Ganancioso arregaça as mangas e conserta o que dá na Ferraria.
[10/11 10:25] O Ferreiro arregaça as mangas e conserta o que dá na Ferraria.
[10/11 10:32] O Cozinheiro arregaça as mangas e conserta o que dá na Ferraria.
[10/11 10:42] O Ferreiro termina de arrumar o fole da forja e assina embaixo, com orgulho.
[10/11 10:42] Depois de muito prego e muita fé, o Cozinheiro deixa a bigorna em ordem.
```
A Médium entendeu errado (os 30% de `chance_erro`): a voz pedia velas, ela ouviu "sangue de
beterraba" e a seita marcou uma rave no meio do ritual. Essa rodada no Docker usou a imagem
anterior à última correção (a ordem terminava com o estrago ≤ 5; hoje termina quando tudo volta a
"inteiro", ver "Decisões") — por isso o "acabou a obra" saiu às 12:13 e não às 10:42. A rodada 1b,
abaixo, é com o código final (fora do Docker); a imagem final também foi reconstruída e subiu
`healthy` (ver "Testes").

**1b. Os passos 2–3 do "Como testar", rodados com o código final** (`python -m server --speed 300
--seed 21 --inicio 08:00 ...`, depois `tools.cli raio forge` e `tools.cli chefe "reconstruam a
ferraria"`):
```
ok: {"place": "forge", "destroyed": ["forge_anvil", "forge_bellows"]}
ok: {"order": 1, "kind": "reconstruir", "how": "palavras", "place": "forge", "receiver": "chief", "status": "recebida"}
$ python -m tools.cli status
Hora do mundo: 2026-11-10T10:49:00-03:00 (Manhã) · clima: nublado
  ordem #1 (chefe): "reconstruam a ferraria" -> reconstruir [palavras] · cumprida · aceitam 16, atrasam 3, resistem 2 · construíram: O Ganancioso, O Esquisito, O Fool
$ python -m tools.cli chat --tipo criador
[10/11 08:16] Um raio cai do nada na Ferraria. Destruído: a bigorna e o fole da forja.
[10/11 08:18] O Criador fala com o Chefe: "reconstruam a ferraria"
[10/11 08:18] O Chefe esfrega a barriga, preocupado: a intuição mandou "reconstruam a ferraria".
[10/11 08:21] O Chefe sobe num caixote na Praça e pede silêncio.
[10/11 08:21] O Chefe junta coragem e grita na Praça: "reconstrução, a Ferraria!" Depois precisa sentar.
[10/11 08:21] O Ganancioso diz que vai cuidar de reconstrução assim que terminar uma coisa. Que coisa? Ninguém sabe.
[10/11 08:21] Reação à ordem (reconstrução): 16 aceitam, 3 vão atrasar, 2 resistem.
[10/11 10:38] O Chefe junta o Ganancioso, o Esquisito e o Fool na frente da Ferraria: "Obra entregue. Ninguém se machucou. Muito."
$ python -m tools.cli chat --lugar forge     (sem os passos de caminhada)
[10/11 08:16] Um raio cai do nada na Ferraria. Destruído: a bigorna e o fole da forja.
[10/11 08:50] O Ganancioso arregaça as mangas e conserta o que dá na Ferraria.
[10/11 08:51] O Ganancioso começa a reerguer a bigorna, tábua por tábua.
[10/11 09:51] O Ganancioso arregaça as mangas e conserta o que dá na Ferraria.
[10/11 09:51] O Ganancioso mede tudo duas vezes e corta errado uma.
[10/11 09:55] O Esquisito arregaça as mangas e conserta o que dá na Ferraria.
[10/11 10:00] O Ferreiro bufa: "Isso não fica assim." Marca um mutirão na Ferraria às 11:08 e chama a Cozinheira, Mike, ...
[10/11 10:13] O Fool arregaça as mangas e conserta o que dá na Ferraria.
[10/11 10:38] Depois de muito prego e muita fé, o Fool deixa o fole da forja em ordem.
[10/11 10:38] O Ganancioso pinta por cima, prega o que faltava, e a bigorna volta a servir.
```
O Ganancioso disse que ia atrasar ("assim que terminar uma coisa") — e mesmo assim foi o primeiro a
aparecer, meia hora depois: o atraso dele era de poucas horas e a vontade de consertar já estava lá.
A obra termina no minuto em que as duas estruturas voltam a "inteiro" (10:38).

**2. A ordem faz diferença (mesma seed, Ferraria destruída às 07:00, com e sem a ordem)** —
`World` direto, `tick()` até as duas estruturas da Ferraria voltarem a "inteiro", código final:

| seed | com `chefe "reconstruam a ferraria"` | sem ordem |
|---|---|---|
| 1 | 2,2 h | 2,9 h |
| 2 | 3,0 h | 6,8 h |
| 3 | 2,1 h | 3,0 h |
| 4 | 2,6 h | 3,1 h |
| 5 | 1,7 h | 2,5 h |
| 6 | 2,4 h | 6,2 h |

Sem a ordem a cidade também conserta, mais devagar: o Chefe da F2 tem a própria iniciativa
(`mandar_reconstruir`, que saiu às 07:07 em todas as seeds) e o Ferreiro marca mutirão. É o "se eles
quiserem" da bible. A ordem do Criador junta mais gente mais cedo.

**3. A Médium entendendo errado (seed 2, `medium "façam as pazes, parem de brigar"` às 19:00)** —
com as decisões explicadas (eventos `decision`):
```
[10/11 19:00] O Criador fala com a Médium: "façam as pazes, parem de brigar"
[10/11 19:00] A Médium para, olhos brancos: "façam as pazes, sapos de brigar"... As vozes disseram.
[10/11 19:01] A Médium anuncia, tremendo: "As vozes disseram: façam as pazes, sapos de brigar! É ritual no Cemitério!" Não era isso. Ninguém sabe.
[10/11 19:01] O Esquisito se arrepia inteiro com a visão e promete obedecer.
[10/11 19:01] Reação à visão (ritual no Cemitério): 2 aceitam, 0 vão atrasar, 0 resistem.
[10/11 19:02] A Médium escolheu ritual@cemetery (4.73) | top3: ritual@cemetery 4.73, conversar(weirdo)@houses 0.33, ritual@forest 0.26
    ritual: peso×0.80 × necessidade.fe=49→0.49 × perigo=50→1.00 × traço misterioso×1.30 × objetivo criador#1×11.50 × viagem 6min×0.81
[10/11 19:08] A Médium acende as velas no Cemitério. O ritual começa.
[10/11 19:12] O Esquisito escolheu participar_ritual@cemetery (2.72) | ...
[10/11 19:18] O Esquisito entra na roda do ritual no Cemitério.
```

**4. `reviver` (seed 2026: o Palhaço morre em 18/11 às 16:13; depois do enterro, `reviver clown`)**:
```
{'ok': True, 'revived': 'clown', 'traits': ['debochado', 'imprevisivel', 'carente', 'conciliador'], 'fear': 85.0}
[19/11 14:29] creator_command  O Criador estende a mão sobre o Cemitério: reviver o Palhaço.
[19/11 14:29] resurrection     A lápide do Palhaço racha ao meio e o Palhaço sai, tossindo, vivo. Alguém lá de fora quis assim.
[19/11 14:29] speech           O Padre chora na escadaria da Catedral: O Palhaço ressuscitou. Promete missa por uma semana.
[19/11 14:29] speech           A Médium abre os braços: "Fui EU. As vozes me ensinaram como trazer o Palhaço de volta."
[19/11 14:30] speech           A Cozinheira: "Se o Palhaço voltou, quem mais volta?" O Cozinheiro não quer pensar nisso.
[19/11 14:33] speech           O Recém-chegado nº 2 conta para o Padre que o Palhaço agora dorme de luz acesa.
[19/11 16:51] speech           O Recém-chegado nº 2 e o Cozinheiro discutem quem trouxe o Palhaço de volta: o padre diz milagre, a médium diz que foi ela.
[19/11 20:31] speech           A Médium lembra ao Esquisito: "Fui eu que trouxe o Palhaço. As vozes disseram."
[20/11 12:16] speech           O Esquisito cochicha com o Cozinheiro: "Você viu o Palhaço? Voltou do cemitério. Não está certo."
[20/11 14:09] speech           O Adolescente pergunta ao Músico se o Palhaço ainda tem cheiro de terra.
[21/11 18:52] speech           O Fool para o Chefe: "Eu juro que o Palhaço não pisca mais."
[21/11 20:07] speech           O Esquisito e o Cowboy Magrelo discutem quem trouxe o Palhaço de volta: o padre diz milagre, a médium diz que foi ela.
```
(Voltou mais `conciliador` — o traço novo sorteado. 24 comentários em 3 dias, cada vez mais raros.)

**5. MQTT com um Mosquitto local** (`python -m server` com `MQTT_HOST=127.0.0.1 MQTT_PORT=18830`,
`mosquitto_sub -t '#' -v`, e `mosquitto_pub` nos quatro tópicos escutados):
```
world/status online
world/state {"ts": "2026-11-10T10:00:00-03:00", "period": "manha", "is_night": false, "weather": {...}, "tension": 50.0, "population": 21, "alive": [...
world/chat {"from": "lady", "from_name": "A Dama", "text": "A Dama pergunta pro Chefe se é impressão ou a tela está olhando pra gente.", ..., "meta": {"world_ts": "2026-11-10T10:01:00-03:00", "place": "houses", "to": "chief", "situation": "conversa", ...}}
world/commands {"cmd":"chefe","arg":"façam uma festa na taverna","id":"mqtt-1"}
homelab/servicos/jellyfin {"status":"down"}
telas/monitor_esquerda/status offline
sala/camera/pessoas {"count": 1}
world/commands/result {"id": "mqtt-1", "cmd": "chefe", "arg": "façam uma festa na taverna", "result": {"ok": true, "order": 1, "kind": "festa", "how": "palavras", "place": "tavern", "receiver": "chief", "status": "recebida"}, ...}
world/events {"id": 80, ..., "type": "creature_spawned", ..., "place": "server_room", "text": "Um guincho elétrico em {@server_room}. jellyfin parou e alguma coisa pequena ri no esc...
world/events {"id": 81, ..., "type": "fog_on", ..., "place": "forest", "text": "Uma névoa espessa engole {@forest}.", ...
world/events {"id": 109, ..., "type": "social_event_planned", ..., "place": "tavern", "text": "{@chief} sai espalhando que vai ter festa na Taverna hoje às 19:04. ...
leds/tunnel {"phase": "start", "char": "tech_apprentice", "from_screen": "parede_centro", "to_screen": "tela_homelab", "from_cm": {"x": 210.0, "y": 155.0}, "to_cm": {"x": 435.0, "y": 70.0}, "duration_ms": 4010, "color": "#219ebc"}
world/events {"id": 123, ..., "type": "action_started", ..., "place": "server_room", "text": "{@tech_old} respira fundo e vai pra cima de jellyfin.", ...
```
(O jellyfin caiu → Gremlin na Sala do Servidor → os Técnicos atravessam o túnel — o LED no
`leds/tunnel` — e vão enfrentar.)

**6. Chat do Mundo web com Playwright (Chromium headless) contra o container** — script
`check.js`: abre `/chat`, espera "ao vivo", manda `chefe` pela API e espera a linha aparecer sem
recarregar; depois testa os filtros:
```
status ao vivo; eventos no histórico: 57
comando: {"ok":true,"order":3,"kind":"reconstruir","how":"palavras","place":"forge","receiver":"chief","status":"recebida"}
o evento do comando apareceu AO VIVO (WebSocket), sem recarregar a página
eventos novos ao vivo: 5
    09:29 10/11 O Criador fala com o Chefe: "reconstruam a ferraria"
    09:29 10/11 A Prefeitura Uma intuição cai em cima do Chefe feito um balde de água: "reconstruam a ferraria". Vamo vê isso aí.
    09:32 10/11 A Praça O Chefe sobe no caixote: "Atenção, povo! A partir de agora: reconstrução! A Ferraria!" Vamo vê isso aí.
    09:32 10/11 A Praça A Florista arregaça as mangas: "Ordem é ordem."
    09:32 10/11 A Praça Reação à ordem (reconstrução): 17 aceitam, 2 vão atrasar, 3 resistem.
filtro personagem=chief: 10 linhas
filtro tipo=criador: 17 linhas; todas com tag-criador: true
linha do tempo: 8 itens
erros de JS na página: nenhum
```

## Decisões tomadas e por quê
- **Um processo (simulação + servidor), não dois.** A simulação continua sendo a única dona do estado
  e a única que escreve no SQLite. A API lê o snapshot (cópia sob lock, agora com os nomes atuais), lê
  o Chat do Mundo numa conexão SQLite só de leitura por requisição (o WAL deixa) e pede a ficha viva
  (`quem`, que precisa de memórias e relações) pela fila de comandos, com um `Future` respondido pelo
  thread da simulação. Dois processos teriam de trocar estado por arquivo ou socket e disputar o banco.
  O compose tem um serviço (`world`) por isso.
- **A ordem não age direto: passa pelo Chefe.** Ele recebe uma intuição e só depois de ANUNCIAR na
  Praça (uma ação como outra qualquer, com sono e preguiça na nota) a cidade ganha objetivos. Assim o
  atraso e a recusa saem do comportamento, e o que os NPCs fazem é sempre uma decisão da Utility AI
  ("objetivo criador#1×11.50" aparece na explicação). Quem resiste reclama em voz alta (só quem estava
  na Praça, no máximo 3 falas).
- **Resistência = traços × afinidade com quem manda** (`resistencia` no YAML): rebelde 0,3, vazio
  0,05, soberbo 0,4, preguiçoso 0,6; protetor, leal, burocrata e empolgado acima de 1. Atraso de 2 a 10 h.
- **"Reconstruir" termina quando tudo volta a "inteiro"** (estado da F2, ≥ 70). O conserto até 100 é
  lento (a vontade de consertar cai com o estrago) e numa rodada a última lasca levou 54 h; o resto
  do capricho fica para a cidade, como sempre. Prazo da ordem: 72 h.
- **`construir` peso 0,7 → 0,12** (mais Ferreiro ×2, Mike ×0,1): antes, uma Ferraria destruída ficava
  pronta em 40 minutos sem ninguém mandar, com o Mike carregando tijolo — a ordem não fazia diferença e
  contrariava a bible. A tabela da "Amostra real" mostra a diferença hoje.
- **Comando `raio <lugar>`** para o teste de aceite: não existe comando para "quebrar a Ferraria" e
  esperar uma briga destruir tudo é sorte; o raio destrói (evento `structure_changed`, tags criador e
  mistério) e daí em diante só os NPCs consertam. Também serve para o João brincar.
- **Objetivos "penalty"** (bônus < 1 que vale): "parem de brigar" deixa `brigar` menos atraente. Só
  objetivos marcados `penalty` (os bônus < 1 do funeral da F3 continuam sem efeito, como antes).
- **Assuntos do momento** (`criador.assuntos`): a forma de "a cidade comenta por dias" sem roteiro —
  só muda o assunto de algumas conversas (`conversar`), com chance que cai com o tempo, e nunca com a
  própria pessoa de quem se fala. As memórias permanentes (`ressurreicao`, `aparicao`) continuam lá.
- **LLM só no relógio real e fora do thread da simulação.** Num dia simulado em segundos, esperar 4 s
  por fala não faz sentido; e o mundo nunca espera a rede: a fala vai para o LLM e sai quando ele
  responder (como comando interno), ou sai o template na hora se ele está fora do ar. Testado com um
  Ollama falso (http.server local); não há Ollama de verdade neste sandbox.
- **A Médium erra "de propósito"** trocando a interpretação por um dos `desastres` e uma palavra da
  mensagem por uma de `palavras_trocadas`; o status mostra "entendeu ERRADO" para o João saber.
- **Aparição**: na tela com mais gente acordada; Padre e Médium reagem mesmo dormindo (acordam com a
  gritaria); quem é `estranho` anota tudo (o Esquisito, e um nascido estranho também anotaria).
- **Olhar coletivo silencioso**: quem para e encara não fala sozinho; sai uma linha só no Chat ("Na
  Feira, todo mundo para ao mesmo tempo e encara a tela: o Palhaço e o Esquisito"). Na primeira versão
  cada um dizia a mesma frase.
- **`world/commands/result`** (tópico novo, `mqtt.topicos.respostas`): quem manda comando pelo MQTT
  (Node-RED, o Grilo) recebe a resposta. `npc/<id>/fala` continua desligado (seção 13.4).
- **Comandos atendidos na hora no tempo real**: no relógio real um tick é um minuto; sem isso, `status`
  pela API esperava até 60 s. O laço de `run()` drena a fila a cada volta (no modo `--fast` nada muda,
  e a seed continua reproduzível).
- **O servidor também imprime o Chat do Mundo** (como o `tools.run`), para o `docker compose logs`;
  o log de acesso do uvicorn foi desligado (o healthcheck a cada 30 s poluía).
- **Docker no sandbox**: o Docker Hub devolveu 429; a imagem base veio de `mirror.gcr.io` e foi
  marcada como `python:3.12-slim`. O `pip install` dentro do build precisa do certificado do proxy do
  sandbox: construí com uma cópia do `Dockerfile` que só acrescenta `COPY --from=ca ca.crt` e
  `PIP_CERT` na linha do pip (`docker buildx build --build-context ca=...`). O `Dockerfile` do
  repositório não tem nada disso (no homelab não precisa). Depois, `docker compose up -d` com o
  `docker-compose.yml` do repositório, sem mudar nada.
- **Desempate de palavras-chave**: ganha a interpretação com mais pedaços encontrados; empate = a que
  vem primeiro no YAML ("a lua quer uma festa" → ritual, porque `lua` e `festa` empatam e ritual vem
  antes). O João muda a ordem ou as palavras no YAML.

## Arquivos principais criados ou alterados
- `sim/commands.py` (novo) — comandos do Criador, ordens, decretos, reunião, assuntos, `status`, `quem`, `raio`.
- `sim/presence.py` (novo) — presença no quarto, olhar coletivo, Aparição.
- `sim/llm.py` (novo) — cliente Ollama opcional (thread, checagem, limite, prompt com contexto).
- `sim/engine.py` — `Command.payload/reply`, `handle_command` devolvendo resultado, `command_log`,
  ganchos (anúncio, reunião, assuntos, decretos na lei e na nota, presença), LLM no `say`,
  `estrutura_reerguida`, snapshot com nomes, fila drenada no tempo real.
- `sim/schemas.py`, `sim/loader.py` — `CreatorConfig` (`data/events/criador.yaml`) e validação
  cruzada; `ollama.situacoes` etc.; `mqtt.topicos.respostas`; especiais `anuncio_criador`, `reuniao_criador`.
- `sim/utility.py` (objetivos `penalty`), `sim/persistence.py` (`Storage.reader`, filtros novos),
  `sim/lifecycle.py` (`resurrect` com medo/esquecimento e funeral cancelado), `sim/social_events.py`
  (`plan_now`), `sim/events.py` (tipos novos).
- `server/runtime.py`, `server/app.py`, `server/ws.py`, `server/mqtt_bridge.py`, `server/__main__.py` (novos).
- `tools/cli.py` (novo), `tools/run.py` (cores dos tipos novos).
- `viewer/chat.html` (novo).
- `data/events/criador.yaml`, `data/actions/criador.yaml`, `data/lines/criador.yaml` (novos);
  `data/world.yaml` (ollama, mqtt, 4 memórias, infração `decreto`), `data/places/town_square.yaml`,
  `data/traits.yaml`, `data/actions/sociais.yaml`, `data/lines/pastelao.yaml|rotina.yaml|lei.yaml`.
- `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `.env.example`, `README.md`.
- `docs/arquitetura.md` (1.1, 2, 3.1, 4.1, 8, 9, 10, 13 reescrita, 16).
- `tests/test_creator.py` (20), `tests/test_server.py` (7), `tests/test_mqtt.py` (6), `tests/test_llm.py` (6).

## Testes
- **184 testes, 184 passando** (`.venv/bin/python -m pytest -q -o addopts=""` → "184 passed in 189.03s"). 39 novos:
  - `test_creator.py` (20): palavras-chave, lugar e ação da ordem; ordem sem palavra ("como dá");
    **o critério de aceite** (Ferraria destruída, ordem, o Chefe anuncia na Praça, ≥ 2 NPCs começam
    `construir` lá, o conserto é feito por eles, a obra termina com a lista de construtores, o
    Adolescente e o Mike resistem, o Ferreiro aceita, alguém atrasa); sem Chefe a ordem espera; festa
    organizada pelo Chefe; decreto (infração `decreto`, rebelde faz mais, Fiscal obedece, liberar tira
    a infração); reunião com ≥ 3; objetivo `penalty`; a Médium (voz, visão, objetivos da seita) e o erro
    de propósito (desastre + mensagem torta); reviver (traço novo, medo, Padre e Médium, funeral
    cancelado, memória, assunto, conversas sobre ele e nunca com ele, vivo não revive); `status` e
    `quem`; comando desconhecido; `Future` + histórico; presença (×3), olhar coletivo, Aparição
    (reações, memória em todos, objetivos, assunto), chance na entrada do quarto + cooldown;
    persistência do estado do Criador; validação do `criador.yaml`.
  - `test_server.py` (7): `/health`, `/api/state`, personagens, ficha, lugares, telas, meta, comandos
    (202, resultado, histórico, 400), chat com filtros (tipo, categoria, personagem, lugar, período),
    linha do tempo, pausar/continuar, `/chat` servido, `/ws/chat` ao vivo (um nascimento), `/ws?screen=`
    (hello só com os lugares da tela, ping/pong, névoa ao vivo, filtro por lugar, tela inexistente).
  - `test_mqtt.py` (6): conversão de todos os tópicos escutados; cliente falso (VERSION2, LWT, assinaturas,
    `online` retido, `world/state` retido); mensagens → comandos → efeitos no mundo + respostas;
    publicação de eventos (só importância ≥ 1), chat e LED do túnel; **sem broker o mundo segue**;
    **ponta a ponta com um Mosquitto de verdade** (comando, resposta, estado, homelab, `offline` no fim).
  - `test_llm.py` (6): com um Ollama falso, a fala importante sai do LLM com o contexto no prompt;
    resposta inválida → template; falas de rotina e tempo acelerado nunca vão ao LLM; limite por hora;
    Ollama fora do ar → template na hora; LLM interpretando ordem livre.
- Os 145 das fases anteriores continuam passando (nenhum teste antigo foi alterado). Uma
  dependência de ordem entre arquivos de teste apareceu (rodando `test_society.py` antes de
  `test_life.py`, os nascidos da semana simulada numa fixture de módulo iam para a pasta global e o
  `test_life` os carregava como personagens): `tests/conftest.py` ganhou uma pasta de nascidos por
  módulo (`_isolated_born_per_module`). Conferido: `pytest tests/test_society.py tests/test_life.py`
  → 52 passed.
- Além dos testes: `docker compose up` com a imagem do código final (`Up (healthy)`, API, CLI dentro
  do container — `raio forge` + `chefe "reconstruam a ferraria"` → "cumprida · aceitam 16, atrasam 2,
  resistem 3 · construíram: O Ferreiro, O Cozinheiro, O Cowboy Velho" e "[10/11 11:27] O Chefe declara
  a obra da Ferraria terminada..." —, Playwright no `/chat`: "o evento do comando apareceu AO VIVO",
  filtros ok, "erros de JS na página: nenhum"),
  servidor com Mosquitto local, 7 dias `tools.run --fast` (seed 404: stderr vazio, 4.868 linhas de
  chat, 10 olhares para a tela) e `tools.report --days 7` nas seeds 42 e 99 (ver "Limitações").

## Limitações e problemas conhecidos
- **A cidade também conserta sem ordem** (o Chefe da F2 manda reconstruir sozinho; o Ferreiro faz
  mutirão): a ordem do Criador acelera e junta mais gente, mas não é a única causa (tabela acima).
- **A seita é pequena** (a Médium e o Esquisito; o Adolescente entra às vezes): visões mexem com pouca
  gente. Aumentar `faccoes.seita.afinidade_para_entrar` mais baixo traz mais gente.
- **Ordens repetidas se acumulam**: dois `chefe "reconstruam a ferraria"` seguidos viram duas ordens
  (as duas terminam juntas). Não atrapalha, mas aparece duas vezes no status.
- **Proibir algo que já é infração** (ex.: `brigar`) só muda a vontade, não a lei.
- **LLM só verificado com um Ollama falso** (não há Ollama no sandbox). O caminho "Ollama fora do ar"
  foi verificado de verdade (container e testes).
- **Open-Meteo** continua inacessível aqui (403 pelo proxy; no container, sem DNS): só o plano B.
- **MQTT dentro do Docker não foi testado** (o broker de teste rodava no loopback do host); a ponte foi
  verificada com o processo direto + Mosquitto local e no teste de ponta a ponta.
- O relatório de variedade, depois do peso novo de `construir`, apontou quatro falas acima do limite
  numa semana (tombo de skate, régua do Fiscal, tampinha do Esquisito, resposta do Fiscal), uma de
  cada vez: só acrescentei variações no YAML. **Resultado final**: `tools.report --days 7 --seed 42`
  → 1.652 falas, 1.445 textos diferentes, "Nenhum alerta de repetição."; `--seed 99` → 1.410 falas,
  1.276 diferentes, "Nenhum alerta de repetição." O de 30 dias não foi refeito nesta fase (~6 min).
- Textos antigos: "levanta o que sobrou de o fole da forja" (nome de estrutura em minúscula não
  contrai), "O Padre chora...: O Palhaço ressuscitou" (maiúscula depois de dois-pontos).
- O `clock` do WebSocket vai a cada 5 s reais; o `bubble` leva o texto inteiro (o viewer encurta).

## Pendências (o que ficou para depois)
- `recarregar` (recarregar `data/` sem reiniciar) — F6, como no plano.
- Testar com um Ollama de verdade — não existe neste sandbox; o João testa no homelab (`OLLAMA_URL`).
- O Palhaço mexer na luz real do quarto (bible: opcional) — precisa decidir o tópico do WLED/lâmpada; F6.
- O trabalho dos Técnicos depender só de problema real aberto — F6 (balanceamento).
- `missa`/`participar_ritual` seguirem o líder atual e relíquias do Esquisito como itens de ritual —
  continuam da F3 para a F6.
- O viewer 3D — F5 (o contrato do WebSocket já está pronto e testado).

## Onde o João pode mexer sem programar
- `data/events/criador.yaml`:
  - `chefe.interpretacoes` — que palavras viram reconstrução, festa, regra, reunião, paz...; o que cada
    uma faz (`efeitos.objetivos`, `necessidades`, `evento_social`), prazo e força;
  - `chefe.resistencia` / `medium.resistencia` — quem obedece, quem atrasa e quem ignora (por traço);
  - `chefe.regra` — palavras de proibir/liberar, apelidos das ações ("skate" → andar de skate),
    regras que o Chefe inventa, quanto cada traço obedece;
  - `chefe.reuniao` — onde, quando e por quanto tempo;
  - `medium.chance_erro`, `desastres`, `palavras_trocadas` — o quanto e como a Médium erra;
  - `reviver` — medo e quanto esquece; `assuntos` — por quantos dias e com que chance a cidade comenta;
  - `presenca` — o olhar, a chance e as consequências da Aparição.
- `data/lines/criador.yaml` — todas as falas desta fase (intuição, anúncio, reações, voz, visão, olhar,
  Aparição, assuntos do momento).
- `data/actions/criador.yaml` — anunciar ordem, revelar visão, reunião (sono, horários, narração).
- `data/world.yaml` — `ollama` (endereço, modelo, timeout, limite por hora, `situacoes` que o LLM pode
  reescrever), `mqtt` (endereço e tópicos), `limites.chance_olhar_por_hora` e `cooldown_aparicao_dias`,
  `leis.infracoes.decreto`.
- `.env` — `MQTT_HOST`, `OLLAMA_URL`, `DW_OLLAMA_ATIVO=false` (nem tenta o Ollama), `DW_SERVER_PORT`.
- `/chat?personagem=...&lugar=...&tipo=...&fonte=28&tema=escuro` — deixar uma tela fixa no Chat do Mundo.

## Revisão do orquestrador
Revisão feita em 2026-11-10 com a imagem `divine-world:dev` já construída (o `docker compose up -d` usou o `docker-compose.yml` commitado, sem alteração).

| Critério de aceite | Resultado | Evidência |
|---|---|---|
| Com `docker compose up`, o mundo vive, a API responde e o Chat web mostra eventos ao vivo | ✅ passou | Container `dw-world` "Up", `/health` → `{"ok":true,"simulating":true,...}`, `/api/state` com 21 vivos. Playwright em `http://localhost:8000/chat`: mandei `medium "VERIFICACAO-ORQ ..."` por `POST /api/commands` e a linha apareceu na página sem recarregar; zero erros de JS. Print: `docs/relatorios/img/fase4_chat_web.png`. |
| `chefe "reconstruam a ferraria"` leva a cidade a reconstruir pelo comportamento | ✅ passou | Dentro do container: `raio forge` (bigorna e fole destruídos 09:15) → `chefe ...` 09:19 → Chefe anuncia na Praça 09:22 ("16 aceitam, 2 vão atrasar, 3 resistem") → mutirão do Ferreiro com Ganancioso, Técnico, Fool → "O Ferreiro dá a última martelada em a bigorna" 11:41 → status "cumprida · construíram: O Ganancioso, O Ferreiro, O Técnico, O Fool". |
| `reviver` funciona e gera reações coerentes | ✅ passou (por teste + rodada do subagente) | `test_revive_is_legendary_and_the_city_talks` passa; `reviver blacksmith` em vivo responde "O Ferreiro está vivo." Não repeti a rodada de 18 dias até uma morte; vale a do subagente (seed 2026, Palhaço). |
| Sem Ollama e sem MQTT tudo funciona | ✅ passou | No container, `/health` mostra `mqtt.conectado:false` e `llm.no_ar:false`, e o mundo seguiu simulando e atendendo comandos. |

Também conferido: `pytest` → 184 passed; `tools.validate` → 0 erros.
Ressalvas: (1) o build da imagem no sandbox precisou de um Dockerfile temporário com o certificado do proxy e de uma imagem base do `mirror.gcr.io` (Docker Hub deu 429) — no homelab o `docker compose up -d --build` padrão deve funcionar, mas não foi provado aqui; (2) a contração "em a bigorna" ainda aparece em uma fala (registrado em Limitações).
