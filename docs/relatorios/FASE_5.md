# Relatório — Fase 5: Visual 3D low-poly (placeholders prontos para trocar)

**Data:** 2026-11-10  ·  **Status:** concluída

## Resumo em 3 linhas
Cada tela da parede abre `http://<servidor>:8000/viewer/?screen=<id>` e mostra, ao vivo, os lugares
dela em 3D com cara de PS1: dioramas pixelados, bonecos reconhecíveis montados a partir do YAML (o chapéu
de palha do Chefe, a batina do Padre, o nariz do Palhaço), balões de fala, dia e noite, chuva, a névoa
de uma tela desligada, a Aparição e o túnel: quem entra numa tela some, a luz corre para a borda e ele
sai do portal da outra tela quando o LED chega. Um `.glb` solto na pasta troca o boneco sem mexer em código.

## O que foi feito
- **Viewer (Three.js 0.170 + Vite 6)** em `viewer/`: `index.html?screen=<id>` (sem `screen`, lista as
  telas), `layout.html` (mapa da parede). `npm run build` gera `viewer/dist`, servido pelo
  `python -m server` em `/viewer`; `npm run dev` (porta 5173) faz proxy de `/api`, `/ws`, `/chat` para
  o servidor. Reconecta sozinho se o servidor cair (e redesenha com o `hello`).
- **Estética PS1/PS2:** imagem interna pequena (240 px de altura na qualidade média) ampliada sem
  suavizar; *vertex snapping* no shader (os vértices tremem); sombreamento flat; névoa de distância na
  cor do céu; cores das `paleta` dos lugares; à noite o chão vai para `paleta.noite`; telas com lugares
  `sinistro` puxam o céu para o azul de terror.
- **Placeholders por código:** personagens com corpo/cabeça/braços/pernas e chapéu, acessório e roupa
  lidos de `visual` + `aparencia` + `movimento` (batina e vestido viram saia; macacão de bolinhas;
  poncho; avental de couro; casaco cheio de bolsos; capuz; velas no cabelo; capacete com lanterna;
  carrinho do Esquisito; chapéu de chef torto...). 17 cenários feitos à mão (Praça com chafariz e coreto,
  Catedral com torre central e vitrais, Prefeitura com colunas e bandeira, Feira, Cozinha, Taverna,
  Ferraria com forja acesa, Casas, Prisão, Campo com espantalho, Cemitério com cripta e névoa rasteira,
  Floresta com círculo de pedras, Montanha, Mar com ondas e barco, Deserto com ruínas, Céu de nuvens
  com portão dourado, Sala do Servidor com racks piscando e dois olhos no fundo, Subterrâneo com
  cristais e luzes de rave) + um genérico pela paleta para lugares novos. Entulho com fita de obra
  quando estruturas estão danificadas; lápides novas no Cemitério a cada enterro; criaturas com olhos
  acesos.
- **Assets substituíveis:** `viewer/public/models/characters/<id>.glb` e `places/<id>.glb` substituem
  o placeholder; `GET /api/models` lista o que existe; os arquivos são servidos direto da pasta (sem
  rebuild; no Docker é volume). Animações por nome (`idle walk talk work sleep fall fight pray dance
  stare`), com substitutas e movimento procedural para o que faltar. Guia:
  `docs/guias/06_modelos_3d_e_design.md` (escala, eixos, origem nos pés, nomes, tamanho do diorama).
  `python -m tools.exemplo_glb <id>` gera um `.glb` de teste (totem com `idle` e `walk`).
- **Animação procedural:** andar com balanço (e o jeito de cada um: o Palhaço e a Florista pulam, o
  Adolescente desliza de skate, o Chefe anda com as mãos nas costas, a Dama desfila de nariz empinado, o
  Esquisito em zigue-zague, o Ganancioso curvado), conversar, trabalhar, dormir deitado, tropeçar e cair
  (pastelão), brigar (um vira para o outro), dançar, rezar ajoelhado e encarar a câmera (o olhar). Ação
  → animação em `world.yaml > visual.animacao_por_acao`; eventos → `animacao_por_evento`.
- **Balões** em HTML por cima do 3D (nítidos, contorno grosso, letra proporcional à altura da tela),
  sem o "Nome:" e encurtados; duração proporcional ao texto (`visual.baloes`); empilham em vez de se
  sobrepor; no máximo 4 ao mesmo tempo. Nomes embaixo dos pés (opcionais) e nome de cada lugar.
- **Ambiente:** dia e noite pelo relógio do mundo (interpolado com a velocidade), amanhecer e
  entardecer, janelas e lampiões acendendo; chuva por clima (garoa < chuva < tempestade, com
  relâmpago); **chuva forte no funeral** (clima forçado ou evento `funeral_started`); neblina aproxima a
  névoa; **tela offline** = nuvens densas cobrindo cada lugar dela ("— na névoa").
- **Teletransporte:** portal em cada lugar com túnel (com o nome do destino). Na origem o personagem
  anda até o portal, é sugado, e uma luz corre até a borda da tela na direção física da outra tela. No
  destino o portal acende e ele sai quando a luz do LED chegou **e** a simulação disse que saiu
  (`max(início + duration_s, fim)`). O `leds/tunnel` (origem, destino, cm, duração) é o da F4.
- **Layout:** `world.yaml > telas` (já tinha posição/tamanho em cm, `fps_max`, `qualidade`);
  `/viewer/layout.html` desenha a parede, as telas, os túneis entre telas com distância e duração do
  LED, e acende a linha ao vivo a cada teletransporte (telas na névoa ficam cinzas).
- **Desempenho:** limite de FPS por tela e três níveis de qualidade em `world.yaml > visual.qualidades`
  (altura da imagem, gotas de chuva, tremidinha, luzes extras, detalhe). Malhas paradas são juntadas
  por material (poucas chamadas de desenho). URL para testar: `?qualidade=baixa&fps=15`.
- **A Aparição:** só na tela do evento, uma silhueta escura borrada (6 cópias deslocadas) atravessa
  entre a câmera e a cidade em 1,7 s, as bordas escurecem e **todos os NPCs da tela viram e encaram**.
- **Servidor:** `hello` ganhou `max_fps`, `quality`, `offline` por tela, `config.visual`,
  `config.tunnel`, `place_names`, `creatures`, `dead`, e `appearance`/`movement` no visual; `bubble`
  ganhou `short` e duração proporcional; mensagens novas `creature` e `structures`. Esquema
  `VisualConfig` validado pelo `tools.validate` (animação inexistente = erro; ação inexistente = erro).
- **Docker:** estágio `node:22-slim` constrói o viewer; a imagem final leva só `viewer/dist`.

## Como testar (passo a passo)
```bash
cd divine-machinery-divineworld

# 1) dados, testes Python e do viewer
.venv/bin/python -m tools.validate                 # "Tudo certo! 0 erros, 0 aviso(s)."
.venv/bin/python -m pytest -q -o addopts=""        # "189 passed" (~3 min)
cd viewer && npm ci && npm test && npm run build && cd ..
#   npm test: "# pass 8 / # fail 0";  build: "✓ built in ~1.8s" (gera viewer/dist)

# 2) o mundo acelerado, sem MQTT nem Ollama
.venv/bin/python -m server --novo --banco var/f5.sqlite --nascidos var/nascidos/f5 \
    --speed 300 --seed 21 --inicio 07:30 --porta 8000 --sem-mqtt --sem-llm
#   http://localhost:8000/viewer/                      -> lista das telas
#   http://localhost:8000/viewer/?screen=parede_centro -> a TV do centro (11 lugares)
#   http://localhost:8000/viewer/?screen=tela_homelab  -> outra aba: Sala do Servidor e Subterrâneo
#   http://localhost:8000/viewer/layout.html           -> mapa da parede (as linhas acendem a cada túnel)

# 3) o critério do túnel: deixe as duas abas lado a lado. Em ~1 minuto o Aprendiz/Técnico vai da Sala
#    do Servidor para a Prefeitura (ou o Mike do Cemitério para o Subterrâneo): na aba de origem ele
#    entra no portal roxo e some (uma luz corre até a borda); na outra, o portal pisca e ~4 s depois
#    (o tempo do LED: 241 cm ÷ 60 cm/s) ele sai do portal e anda até o lugar dele.
#    Automático (precisa do Playwright):  node viewer/e2e/aceite_tunel.cjs docs/relatorios/img parede_centro tela_homelab

# 4) o critério do .glb (noutro terminal, com o servidor rodando)
.venv/bin/python -m tools.exemplo_glb chief       # cria viewer/public/models/characters/chief.glb
#   recarregue a aba (F5): o Chefe vira um totem verde e amarelo com nariz vermelho (com idle/walk)
curl -s localhost:8000/api/models                 # {"characters":["chief"],"places":[]}
rm viewer/public/models/characters/chief.glb      # recarregue: o Chefe de chapéu de palha volta

# 5) o resto, pelos comandos do Criador
.venv/bin/python -m tools.cli tela monitor_direita offline   # a aba do monitor_direita vira névoa
.venv/bin/python -m tools.cli tela monitor_direita online
.venv/bin/python -m tools.cli clima tempestade 60            # chuva forte e relâmpagos
.venv/bin/python -m tools.cli aparicao                       # silhueta + todos encaram a tela
.venv/bin/python -m tools.cli velocidade 1                   # para olhar com calma
#   ?foco=tavern (só um lugar), ?qualidade=baixa, ?fps=15, ?nomes=0, ?relogio=0

# 6) desenvolvimento do viewer (com o servidor da etapa 2 rodando)
cd viewer && npm run dev                          # http://localhost:5173/viewer/?screen=parede_centro

# 7) Docker (o build já roda o npm)
docker compose up -d --build                      # http://<homelab>:8000/viewer/?screen=<id>
```

## Amostra real
Mensagens reais do WebSocket durante a verificação (servidor `--speed 300 --seed 21`, horários em ms
relativos ao início do teletransporte; arquivo completo: `docs/relatorios/fase5_aceite_tunel.json`):

```jsonc
// aba tela_homelab (origem) e aba parede_centro (destino) recebem as duas fases:
{"t": 0,   "type": "teleport", "phase": "start", "id": "tech_apprentice", "from_place": "server_room",
 "to_place": "town_hall", "from_screen": "tela_homelab", "to_screen": "parede_centro", "duration_s": 4.01}
{"t": 985, "type": "teleport", "phase": "end",   "id": "tech_apprentice", ...}
// log do viewer de destino: apareceu quando a luz chegou (4,01 s), não quando a simulação terminou (0,98 s)
{"at": 4017, "kind": "appeared", "id": "tech_apprentice", "place": "town_hall", "now": "cathedral"}
// resultado: {"inOriginBefore": true, "inDestDuring": false, "appearedInDest": true, "inOriginAfter": false, "errors": []}
```
(`now: cathedral`: no tempo acelerado, enquanto o LED corria, a simulação já mandou o Aprendiz da
Prefeitura para a Catedral; ele sai do portal da Prefeitura e anda até lá.) Segunda rodada, outro par
de telas: a Dama, Feira → Mar (`parede_centro` → `monitor_direita`, LED 2,29 s), apareceu em 2.314 ms.

Outras mensagens reais (`/ws?screen=parede_centro`):
```json
{"type": "teleport", "phase": "start", "id": "medium", "from_place": "forest", "to_place": "town_square", "from_screen": "monitor_esquerda", "to_screen": "parede_centro", "duration_s": 2.38}
{"type": "move", "id": "medium", "from": "town_square", "to": "community_kitchen", "duration_s": 0.6}
{"type": "bubble", "id": "greedy", "place": "prison", "text": "O Ganancioso come e reclama do sal. Depois repete.", "short": "O Ganancioso come e reclama do sal. Depois repete.", "duration_s": 5.5}
```
`hello` (trecho): `{"id": "parede_centro", "max_fps": 30, "quality": "media", "offline": false}` e o Chefe com
`"hat": "chapéu de palha", "appearance": "Senhor barrigudo, colete de lã, chapéu de palha, óculos na ponta do nariz..."`.

### Prints (deviceScaleFactor 2, Chromium headless com SwiftShader, sem GPU)
| | |
|---|---|
| Duas abas, mesmo mundo: ![](img/fase5_aba_parede_centro.png) | ![](img/fase5_aba_tela_homelab.png) |
| Túnel 1 — o Aprendiz entra no portal (homelab): ![](img/fase5_tunel_1_origem_entrando.png) | Túnel 2 — o portal da Prefeitura acende (centro): ![](img/fase5_tunel_2_destino_portal_aceso.png) |
| Túnel 3 — ele saiu do portal na outra tela: ![](img/fase5_tunel_3_destino_chegou.png) | Túnel 4 — e não está mais na origem: ![](img/fase5_tunel_4_origem_depois.png) |
| `.glb`: antes (Chefe placeholder, chapéu de palha) ![](img/fase5_glb_1_sem_glb.png) | depois (totem de `tools.exemplo_glb`, sem mudar código) ![](img/fase5_glb_2_com_glb.png) |
| TV do centro, dia: ![](img/fase5_centro_dia.png) | qualidade baixa: ![](img/fase5_centro_qualidade_baixa.png) |
| Cozinha (chapéu de chef, avental): ![](img/fase5_foco_community_kitchen.png) | Campo (os três Cowboys): ![](img/fase5_foco_fields.png) |
| Praça: ![](img/fase5_foco_town_square.png) | Catedral (Padre de batina): ![](img/fase5_foco_cathedral.png) |
| Monitor esquerdo: ![](img/fase5_monitor_esquerda.png) | Monitor direito: ![](img/fase5_monitor_direita.png) |
| Tela do homelab: ![](img/fase5_tela_homelab.png) | Tela offline (névoa): ![](img/fase5_nevoa_tela_offline.png) |
| Tempestade: ![](img/fase5_tempestade.png) | A Aparição passando: ![](img/fase5_aparicao.png) |
| Todos encarando depois da Aparição: ![](img/fase5_aparicao_todos_olhando.png) | Mapa da parede: ![](img/fase5_layout.png) |

## Decisões tomadas e por quê
- **Uma cena por tela com os lugares em grade** (dioramas de 10 × 10 m), em vez de um mapa contínuo:
  a TV do centro tem 11 lugares e os outros 2–3; a grade (colunas que deixam cada diorama maior na
  proporção da janela) funciona em qualquer tela sem configurar posição. Lugares internos aparecem em
  corte (chão + paredes do fundo e lateral), senão ninguém dentro da Taverna seria visto.
- **Textos em HTML por cima do canvas**, não no 3D: o 3D é pixelado de propósito, mas o balão precisa
  ser lido do outro lado do quarto.
- **Personagem aparece no destino em `max(início + duração do LED, fim na simulação)`**: no tempo
  real o túnel da simulação (5 min do mundo) dura mais que o LED (4 s) e manda; no acelerado o LED manda.
  Assim a luz na parede e o personagem combinam. No acelerado, se ele já foi adiante, sai do portal e
  anda até onde está; se entrou de novo no túnel antes de "chegar", a chegada é cancelada.
- **`GET /api/models` em vez de tentar baixar cada `.glb`**: no `npm run dev` o Vite responde 200 com
  HTML para arquivo inexistente; a lista vem do servidor e vale nos dois modos.
- **Modelos servidos direto de `viewer/public/models`** (montado antes do `/viewer`): soltar o arquivo
  vale sem rebuild e sem reiniciar. No compose é volume.
- **O `.glb` usa o tamanho que veio** (1 unidade = 1 m) e **não** recebe a `altura` do YAML (senão um
  modelo já alto ficaria gigante); só `escala_personagens` vale para todos. Rede de segurança: altura
  fora de 0,3–6 m é ajustada e a origem descida até o chão, com aviso no console.
- **`escala_personagens: 1.3`**: com a escala real os bonecos ficavam com ~10 px de altura na TV do
  centro; 1,3 deixa reconhecível sem quebrar a proporção dos cenários.
- **Palavras da aparência viram peças** (`batina`, `vestido`, `macacão`, `bolinhas`...): o João muda o
  boneco mudando o texto da ficha, sem campo novo no YAML. A lista está no guia.
- **Noite legível**: na primeira versão a noite ficou preta demais na parede; a luz da noite agora é um
  luar azul (dá para ver os dioramas, com lampiões e janelas acesos).
- **`dist/` fora do git**: o servidor mostra uma página 503 explicando `npm ci && npm run build` se o
  viewer não estiver construído; o Docker constrói num estágio com Node.
- **Teste de ponta a ponta com Playwright fica em `viewer/e2e/`** (fora do `npm test`, porque precisa
  de navegador): o `npm test` cobre as regras puras (`node --test`, sem dependências).
- **`/viewer/chat.html` continua respondendo** (endereço da F4; agora com rota própria, porque `/viewer`
  passou a ser o `dist`).

## Arquivos principais criados ou alterados
- `viewer/package.json`, `package-lock.json`, `vite.config.js`, `index.html`, `layout.html` (novos).
- `viewer/src/logic.js` (regras puras), `main.js` (conexão, cena, mensagens, túnel, Aparição, laço),
  `ps1.js` (materiais e render), `shapes.js` (primitivas e `bake`), `places.js` (cenários),
  `characters.js` (bonecos, animação, `.glb`), `environment.js` (céu, chuva, névoa), `overlay.js`
  (balões, nomes, relógio), `layout.js` (mapa), `style.css`.
- `viewer/test/logic.test.js` (8 testes), `viewer/e2e/aceite_tunel.cjs`, `viewer/e2e/aceite_glb.cjs`.
- `viewer/public/models/` (`README.md`, `characters/`, `places/`).
- `server/ws.py` (hello, balão, criaturas, estruturas), `server/app.py` (`/viewer` = dist, modelos,
  `/api/models`, página de "não construído"), `sim/schemas.py` (`VisualConfig`), `sim/loader.py`
  (validação do `visual`), `sim/engine.py` (`uid` das criaturas no snapshot).
- `data/world.yaml` (seção `visual`).
- `tools/exemplo_glb.py` (novo), `tests/test_viewer.py` (novo, 5 testes).
- `Dockerfile` (estágio Node), `.dockerignore` (novo), `docker-compose.yml` (volume dos modelos), `README.md`.
- `docs/guias/06_modelos_3d_e_design.md` (novo), `docs/arquitetura.md` (2, 13.2, 13.3, 13.5, 14, 16).

## Testes
- **Python: 189 testes, 189 passando** (`.venv/bin/python -m pytest -q -o addopts=""`; os 184 de antes
  + 5 em `tests/test_viewer.py`: o `hello` com tudo que o viewer usa, balão curto com duração
  proporcional, `/api/models` + modelos servidos + páginas `/viewer`, a página 503 sem build, e o
  `visual` inválido no YAML virando erro). O teste antigo de `/viewer/chat.html` pegou a quebra do
  endereço da F4 e ela foi corrigida.
- **Viewer: `npm test` → 8 passando** (ação → animação, escolha de clipe com prefixo do Blender e
  substitutas, corte e duração do balão, grade, hora/dia/noite, chuva do funeral, momento de aparecer
  no túnel, aparência → peças).
- **`npm run build`** → "✓ built in ~1.8s" (aviso de bundle de 645 kB: é o Three.js; ~174 kB gzip).
- **`tools.validate`** → "Tudo certo! 0 erros, 0 aviso(s)."
- **Verificação real, Chromium headless (SwiftShader) contra o servidor rodando**:
  - Túnel entre duas abas (`viewer/e2e/aceite_tunel.cjs`): duas vezes, dois pares de telas (homelab →
    centro e centro → monitor direito); prints `fase5_tunel_*` e o JSON acima. Zero erros de JS.
  - `.glb` (`viewer/e2e/aceite_glb.cjs`): sem arquivo, `/api/models` vazio e o Chefe placeholder; com
    `chief.glb`, `GET /viewer/models/characters/chief.glb` 200, `__dw.characterModels = ["chief"]`,
    clipes `["idle", "walk"]` e o totem no lugar do Chefe (prints `fase5_glb_*`). Arquivo apagado depois.
  - Névoa (`tela monitor_direita offline` → `__dw.fog = ["sea","desert","sky"]`), tempestade
    (`__dw.rain = 1`), Aparição (`{"screen": "parede_centro", "witnesses": 18}` → 18 personagens em
    `stare` na aba), mapa da parede, lista de telas.
  - FPS medido: 30–31 na TV do centro (limite 30), 20–21 no homelab (limite 20) — o limite por tela funciona.
  - `npm run dev` (5173) com proxy: a aba do homelab recebeu o `hello` pelo WebSocket via Vite.
  - **Docker**: imagem construída (no sandbox, com o certificado do proxy como na F4, só para o
    `npm ci`/`pip`); o container serviu `/viewer/` (o `index.html` do build), `/viewer/layout.html` e
    `/api/models`, e uma aba do Playwright na porta do container desenhou a TV do centro a 31 FPS.

## Limitações e problemas conhecidos
- **Desempenho medido só sem GPU (SwiftShader)**, num computador rápido. Num celular velho de verdade
  não foi testado; a `qualidade: baixa` + `fps_max: 20` é o ponto de partida.
- **A chuva cai também sobre os lugares internos** (Taverna, Sala do Servidor): é uma camada só por
  tela. Fica estranho só em telas com muito lugar interno.
- **No tempo acelerado (300×)** tudo acontece rápido demais para o visual: caminhadas de 0,4 s
  (o viewer segura em 0,8 s), balões se acumulam (o limite de 4 segura). No tempo real o ritmo é o certo.
- **O caminho do LED no `layout.html` é uma linha reta** entre os centros das telas (a duração usa a
  mesma conta da simulação). Se a fita de LED fizer curva na parede, a duração real será outra: é só
  ajustar `tunel.velocidade_led_cm_por_s`.
- **A Aparição é discreta** (silhueta escura semitransparente por 1,7 s); com muito sol pode passar
  despercebida. É um ajuste fino de opacidade/duração.
- **Personagens dormindo em casa** ficam enfileirados na rua das Casas (não há "dentro" das casas).
- Os placeholders das criaturas são genéricos (bolota com espinhos e olhos); a bible ainda não definiu
  as criaturas.

## Pendências (o que ficou para depois)
- **Sons ambientes por lugar** — a bible deixa para o João criar (F6 ou depois).
- **Posição de cada lugar na grade pelo YAML** (`visual` no lugar) — a grade automática atendeu; fica
  para quando o João quiser arrumar a TV do centro à mão.
- **Teste num celular/notebook velho de verdade e numa tela transparente** — não existe aqui.
- **Guia completo do Blender (passo a passo com prints)** — a convenção está pronta em
  `docs/guias/06_modelos_3d_e_design.md`; o passo a passo é da Fase 6.
- **Rodar o MQTT/WLED com o viewer ao mesmo tempo** — o `leds/tunnel` já existe e foi testado na F4;
  aqui as verificações usaram `--sem-mqtt`.

## Onde o João pode mexer sem programar
- `data/world.yaml > telas[]` — que lugares cada tela mostra (e a ordem na grade), posição e tamanho
  na parede (cm), `fps_max` e `qualidade`.
- `data/world.yaml > visual` — níveis de qualidade (`altura_render`, `gotas_de_chuva`,
  `tremer_vertices`, `luzes_extras`, `detalhe`), balões (`segundos_minimos`, `segundos_por_letra`,
  `segundos_maximos`, `max_letras`), `escala_personagens`, `mostrar_nomes`, `mostrar_relogio`, névoa
  de distância, `animacao_por_acao`, `animacao_por_evento`, `animacao_substituta`.
- `data/world.yaml > tunel` — velocidade da luz de LED (muda quanto tempo o personagem fica no túnel).
- `data/characters/<id>.yaml` — `visual` (cor, cor secundária, altura, corpo, chapéu, acessório),
  `aparencia` e `movimento`: o boneco muda junto (palavras reconhecidas no guia).
- `data/places/<id>.yaml > paleta` — as cores do diorama (e `noite` à noite); `sinistro: true` deixa o
  céu da tela mais frio.
- `viewer/public/models/characters/<id>.glb` e `places/<id>.glb` — os modelos dele (guia).
- Na URL da tela: `?qualidade=`, `?fps=`, `?altura=`, `?foco=<lugar>`, `?nomes=0`, `?relogio=0`.

## Revisão do orquestrador
Revisão feita em 2026-11-10 com um servidor próprio (porta 8001, seed 33, `--speed 300`, sem MQTT/LLM) e os scripts de aceite copiados apontando para essa porta.

| Critério de aceite | Resultado | Evidência |
|---|---|---|
| Duas abas com telas diferentes mostram lugares diferentes do mesmo mundo, e um personagem atravessa pelo túnel | ✅ passou | `aceite_tunel.cjs`: aba A `parede_centro` com 11 lugares e 20 atores; aba B `tela_homelab` com `server_room`/`underground`. `teleport start` do **O Técnico** (`town_hall` → `server_room`, 4,01 s); `inOriginBefore: true`, `appearedInDest: true` (~4,0 s depois), `inOriginAfter: false`, `errors: []`. |
| Um `.glb` na pasta substitui o placeholder sem mudar código | ✅ passou | Sem arquivo: `models: []`. Após `python -m tools.exemplo_glb chief`: `/api/models` → `{"characters":["chief"]}`, o viewer baixou `/viewer/models/characters/chief.glb` (200) e reportou `clips: {"chief":["idle","walk"]}`; o totem aparece no lugar do Chefe. Arquivo removido em seguida (`/api/models` volta a `[]`). |
| Prints das telas no relatório | ✅ passou | 21 imagens em `docs/relatorios/img/fase5_*.png`; conferi visualmente a TV do centro (11 lugares legíveis, balões, nomes, portais) e a troca pelo `.glb`. |

Também conferido: `pytest` → 189 passed; `npm test` → 8 pass / 0 fail; `npm run build` → "built in 1.89s"; `tools.validate` → 0 erros.
Não verificado aqui: desempenho em hardware antigo real (só SwiftShader, 20–31 FPS) e WLED/MQTT junto com o viewer.
