# Relatório — Fase 6: Polimento, balanceamento e guias para o João

**Data:** 2026-11-10  ·  **Status:** concluída

## Resumo em 3 linhas
O João agora muda nomes, falas, pesos, telas e personagens **só editando YAML** e aplica com
`python -m tools.cli recarregar`, sem desligar o mundo e sem perder nada; se o YAML estiver errado, nada
muda e o mundo avisa (e, se o homelab reiniciar com o erro, liga com a última versão válida). O mundo foi
balanceado num teste de 60 dias (menos prisões, eventos sociais que dão certo, sem rajadas de morte, tédio
sob controle) e dez guias passo a passo em `docs/guias/` explicam tudo para quem não lembra do código.

## O que foi feito
- **`recarregar`** (`sim/reload.py`; CLI, `POST /api/commands`, MQTT `world/commands`): relê `data/`,
  valida e troca os dados do mundo **mantendo o estado** (lugar, necessidades, memórias, relações vivas,
  ação em andamento, prisão, luto, sucessões). Nomes, aparência, traços, rotina, falas, pesos, eventos,
  telas e quase todo o `world.yaml` valem no próximo minuto. Personagem com arquivo novo entra em casa;
  arquivo que sumiu = continua com a versão antiga (aviso). Com erro no YAML: **nada muda**, aviso no Chat
  (importância 2) e a resposta lista os erros. Seções que só valem ao ligar (`mqtt`, `servidor`,
  `persistencia`, `ollama`, fuso/passo do relógio) aparecem em "só vale depois de reiniciar".
- **As telas redesenham sozinhas** depois do `recarregar`: o servidor manda um `hello` novo para cada
  WebSocket (o viewer já redesenhava num `hello`). Nomes, cores, bonecos, lugares por tela, posições.
- **Última versão válida ao ligar**: a cada start sem erro, `data/` (sem os nascidos) é copiado para
  `<pasta do banco>/data_valido/` (`var/data_valido/` no Docker). Se o servidor ligar com `data/` quebrado
  e a cópia existir, ele sobe com ela e avisa no Chat; o `recarregar` continua lendo o `data/` de verdade.
- **Robustez verificada de verdade**: Mosquitto real derrubado e religado com o mundo rodando; Ollama
  apontando para um endereço morto; YAML quebrado no `recarregar` e no start; o servidor morto com
  `kill -9` e religado (retoma do último salvamento); servidor parado com uma aba 3D aberta (a aba
  reconectou sozinha); tela offline/online pelo MQTT (seção "Robustez").
- **`tools.report` mede a saúde do mundo** (além da variedade): prisões por semana, eventos sociais
  (planejados × sucesso × fracasso), eventos do diretor (fatia e os que nunca saíram), criaturas, mortes
  por causa e pior janela de 7 dias, necessidades ≥ 95 (por necessidade e por personagem) e ocupação dos
  lugares, com alertas por limites explicados em `BALANCE_LIMITS`.
- **Balanceamento em YAML** (seção "Balanceamento"), com o teste de 60 dias sem erros e sem alertas.
- **Pendências baratas das fases anteriores**:
  - contração de nomes com artigo minúsculo: "em a bigorna" → "na bigorna", "de o fole" → "do fole"
    (estruturas), em todo o Chat (inclusive o histórico);
  - missa e ritual seguem o **líder atual** da facção: entradas novas `presenca_lider.<facção>` e
    `afinidade_lider.<facção>` (se o Padre morre, a missa segue quem assumiu a Igreja);
  - o validador avisa lugar com estruturas sem ação de conserto (era a causa dos mutirões impossíveis);
  - `limites.dias_minimos_entre_mortes_naturais` (YAML) contra as rajadas de morte;
  - material emissivo do Blender continua aceso no `.glb` de personagem (olhos, lanterna).
- **`tools.backup`**: cópia online do SQLite (segura com o mundo rodando), mantendo os N mais novos.
- **Guias** `docs/guias/01` a `10` (o 06 foi estendido com o Blender passo a passo, cenários, paleta,
  checklist e teste) e o **README** com a visão geral e o índice dos guias. Cada comando, campo e número
  citado foi conferido no código/dados; os exemplos YAML dos guias 02 e 04 foram validados numa cópia de
  `data/` (o Coveiro, a ação `contar_causo`, o evento `quermesse`, a `noite_do_causo`).

## Como testar (passo a passo)
```bash
cd divine-machinery-divineworld
.venv/bin/python -m tools.validate                    # "Tudo certo! 0 erros, 0 aviso(s)."
.venv/bin/python -m pytest -q -o addopts=""           # "199 passed" (~4 min)
(cd viewer && npm ci && npm test && npm run build)    # "# pass 8 / # fail 0", "✓ built"

# 1) o critério do guia 01 (renomear sem reiniciar)
.venv/bin/python -m server --novo --banco /tmp/dw.sqlite --nascidos /tmp/dw_nasc --speed 300 --seed 21 \
    --inicio 08:00 --porta 8000 --sem-mqtt --sem-llm
#   abra http://localhost:8000/viewer/?screen=parede_centro e http://localhost:8000/chat
#   noutro terminal, siga o guia 01: troque "nome: O Palhaço" por "nome: O Bozó" em data/characters/clown.yaml
.venv/bin/python -m tools.validate
.venv/bin/python -m tools.cli recarregar                # "clown: O Palhaço -> O Bozó"
#   em ~1 s a aba 3D mostra "O Bozó" embaixo dele (sem F5); o Chat mostra o aviso e as falas novas
#   automático (Playwright): node viewer/e2e/aceite_renomear.cjs <pasta> clown "O Bozó" parede_centro 120
#   DESFAÇA a troca do nome e rode recarregar de novo

# 2) YAML com erro: nada muda
#   ponha um traço inexistente em clown.yaml (tracos: [debochadoo, ...]) e rode recarregar
#   -> "NÃO recarregou ... 'debochadoo' não existe. Você quis dizer 'debochado'?"  (desfaça)

# 3) o teste longo (cada um ~15 min)
.venv/bin/python -m tools.report --days 60 --seed 42 --saida /tmp/balanco.txt   # "Nenhum alerta"
.venv/bin/python -m tools.run --fast --dias 60 --novo --inicio 00:00 --seed 2026 \
    --banco /tmp/l60.sqlite --nascidos /tmp/l60_nasc --resumo                   # sai com 0, stderr vazio

# 4) backup
.venv/bin/python -m tools.backup --banco /tmp/dw.sqlite --destino /tmp/bk
```

## Verificação dos critérios de aceite

| Critério | Resultado | Evidência |
|---|---|---|
| Seguindo só o guia 01, alguém renomeia um personagem e vê o nome novo no Chat do Mundo e no visual, sem reiniciar | ✅ | Servidor (`--speed 300 --seed 21 --sem-mqtt --sem-llm`) rodando; aba Playwright (Chromium headless, SwiftShader) aberta em `parede_centro` antes da troca: `ANTES {"name":"O Palhaço","place":"market","hellos":1,"dom":["O Palhaço"]}`. Passos do guia: `sed` na linha `nome:`, `tools.validate` → "Tudo certo! 0 erros", `tools.cli recarregar` → "clown: O Palhaço -> O Bozó". A MESMA aba, sem recarregar a página: `DEPOIS {"name":"O Bozó","place":"market","hellos":2,"dom":["O Bozó"]}, "pageLoads":1, "errs":[]` (o `hello` novo chegou; o rótulo no DOM mudou). Chat (`tools.cli chat --personagem clown` e `/api/chat`): "O Ganancioso pergunta pro Bozó se viu alguma coisa estranha hoje." / "O Bozó responde só com uma buzina. *FOM*" / "Os dados do mundo foram recarregados. O Palhaço agora se chama o Bozó." (o texto do aviso foi depois corrigido para `"O Bozó"` entre aspas, para não perder a maiúscula). `/api/characters` → `{'id': 'clown', 'name': 'O Bozó', ...}`. Prints: `img/fase6_renomear_1_antes.png`, `img/fase6_renomear_2_depois.png` (o "O Bozó" na Feira). Renomeação desfeita e recarregada ("clown: O Bozó -> O Palhaço"). |
| 60 dias simulados sem erros, com o relatório de variedade dentro dos limites | ✅ (rodada de correção 1) | **Relatório (config final, depois da correção 1):** `tools.report --days 60` em três seeds, em paralelo, todas com stderr vazio e **"Nenhum alerta (repetição e balanceamento)."** — **seed 808**: 13.203 falas (7.294 diferentes), 8 mortes (acidente 2, briga 2, criatura 2, natural 1, choque 1), pior janela de 7 dias **2**, população 19–22, 3,1 prisões/semana, procissão 3/6 (50%), rave 44%, mutirão 67%, rodeio 92%, casamento 1/1, tédio ≥ 95 em 9,4%, diretor ≤ 12%; **seed 7**: 5 mortes (criatura 4, acidente 1), pior janela **2**, população 20–23, 1,6 prisões/semana, procissão 6/8 (75%), rave 45%, rodeio 47%, mutirão 65%, casamento 1/1, tédio 11,4%; **seed 42**: 4 mortes (natural 2, choque 1, briga 1), pior janela **1**, população 21–25, 4,0 prisões/semana, procissão 3/4 com sucesso (75%), rave 59%, mutirão 57%, casamento 1/2, tédio 11,9%. **Simulação:** `tools.run --fast --dias 60 --novo --inicio 00:00 --seed 2026 --banco <tmp> --nascidos <tmp> --resumo` → código 0, stderr vazio, 40.830 linhas de Chat (rodada anterior à correção; a revisão do orquestrador repetiu com a seed 808: código 0). **Histórico:** antes da correção, `--seed 808` dava 5 mortes em 7 dias e procissão 1/6, e `--seed 7` 3 mortes em 7 dias — daí o teto semanal de mortes e a troca da ação da procissão (seção Balanceamento). Relatórios gerados em pasta temporária (fora do repositório). |

## Robustez

| Situação | Como foi testado | Resultado |
|---|---|---|
| MQTT caindo | Mosquitto real (porta local), servidor com MQTT ligado; `pkill mosquitto` por ~20 s; depois religado | Log: "MQTT desconectado ... tentando de novo a cada 30.0s" e **um** "MQTT fora do ar ... a simulação continua e tenta de novo". Ticks continuaram (60 → 160 durante a queda). Religado: "MQTT conectado" sozinho (`/health` → `conectado: true`, publicadas 34 → 110). Depois: `recarregar`, `status` e `telas/monitor_direita/status = offline` pelo MQTT funcionaram (resposta em `world/commands/result`; névoa em `desert, sea, sky`). |
| Ollama sumindo | `OLLAMA_URL` para uma porta morta, `DW_OLLAMA_ATIVO=true` | "WARNING sim.llm: Ollama fora do ar (ConnectError): falas pelos templates."; `/health` → `llm.no_ar: false`; o mundo seguiu (os testes `test_llm.py` cobrem timeout, limite por hora e volta). |
| YAML com erro | `recarregar` com traço inexistente; start com `world.yaml` quebrado | `recarregar` → "NÃO recarregou ... 'debochadoo' não existe. Você quis dizer 'debochado'?"; o mundo seguiu com a versão anterior. Start quebrado com cópia válida → liga com ela e avisa; sem cópia → `DataError` com a lista (como antes). Testes em `tests/test_reload.py`. |
| Tela desconectando | aba 3D aberta, servidor parado com SIGTERM e religado ~45 s depois | A aba reconectou sozinha (`hellos: 1 → 2`, `connected: true`, zero erros de JS). Tela offline/online pelo MQTT: névoa liga e desliga. |
| Reinício do homelab | `kill -9` no servidor (como falta de luz) e religar sem `--novo` | "O mundo acorda de onde parou." Hora antes do kill: 19:24; retomou de 19:21 (último salvamento, a cada 5 min do mundo); 21 vivos, nada perdido além de 3 minutos do mundo. Parada normal (SIGTERM) salva tudo ("Application shutdown complete"). |

## Balanceamento

Medido com `tools.report` (seeds 42, 7 e 99; 7, 14 e 60 dias). Tudo em YAML, com um comentário
"Fase 6: era X" no lugar de cada mudança.

| Problema (medido) | Mudança | Arquivo | Depois |
|---|---|---|---|
| **Tédio explodindo**: ≥ 95 em 26% das amostras; Ferreiro, Aprendiz e Cozinheira > 45% do tempo (7 dias, seed 42) — a necessidade parou de diferenciar quem está entediado | `tedio.taxa_noite` 4 → 2 (a noite é de sono); `dormir` agora tira 35 de tédio | `world.yaml`, `actions/basicas.yaml` | ~11% e ninguém travado (60 dias, seeds 42 e 7) |
| **Prisões demais** (~13/semana na F2; 8/semana na primeira medição desta fase) — um roubo sozinho já prendia | `leis.pontos_para_prisao` 2 → 2.5 (roubo sozinho = advertência; roubo + outra coisa prende); `barulho.gravidade` 0.5 → 0.3 (com as raves dando certo, barulho virou a maior causa) | `world.yaml` | 2,9–3,4/semana (60 dias) |
| **Rave quase sempre fracassava** (0/3) | janela 22:00–01:30 → 21:00–23:30; antecedência 1–4 h → 0,5–2 h; bônus 10 → 30 | `events/sociais.yaml` | 53–62% (60 dias) |
| **Rodeio fracassava** (0/3): `festejar` quase não vale à tarde e o trabalho ganhava | janela 14–17 h → 16–18 h; bônus 10 → 20 | `events/sociais.yaml` | 71–85% (60 dias) |
| **Casamento nunca dava certo** (marcado com até 20 h de antecedência) | antecedência 6–20 h → 2–6 h; bônus 5 → 10; ação `missa` → `rezar` (correção 1, mesmo motivo da procissão) | `events/sociais.yaml` | 3 de 5 em três rodadas de 60 dias (raro de propósito: precisa de um par com afinidade ≥ 92) |
| **Procissão fracassava** (1/6 na seed 808): a ação era `missa`, que só vale onde o líder da Igreja está e **não vale para o próprio Padre** (ele é o líder) — o organizador nunca ia, e ninguém ia sem ele | ação `missa` → `rezar` (vale para todos na Catedral, inclusive o Padre); janela 08–16 h → 10–16 h; antecedência 2–6 h → 1–3 h; bônus 3 → 12 | `events/sociais.yaml` | 50–75% (60 dias, seeds 808, 7, 42) |
| **Mutirão fracassava** (0/13 numa seed): o lugar mais estragado era o Subterrâneo (as raves quebram as caixas de som), onde `construir` não existia; ideias da madrugada caíam às 07:00 | `construir` nas `acoes` do Subterrâneo, Cemitério, Mar e Prisão (e aviso novo no validador); janela 07:00 → 09:00–16:00; bônus 5 → 25 | `places/*.yaml`, `events/sociais.yaml` | 53–73% (60 dias) |
| **Mortes em rajada** (3 em 4 dias na F3; 5 em 7 dias na seed 808 — natural, 2 acidentes, Limbo, choque) | `limites.dias_minimos_entre_mortes_naturais: 8` (sem morte natural logo depois de outra morte); **regra nova genérica `limites.max_mortes_em_7_dias: 2`** (com 2 mortes nos últimos 7 dias, nenhuma causa sorteada mata — o acidente, o choque, a briga e o Limbo acontecem, mas a pessoa sobrevive; `causas_fora_do_limite: []` lista exceções, validadas); `acidente` 0.006 → 0.004 | `world.yaml`, `sim/lifecycle.roll` | pior janela de 7 dias: 2, 2 e 1 (seeds 808, 7, 42); 4 a 8 mortes em 60 dias |
| **O Aprendiz morrendo de choque todo mês** | `choque.chance` 0.03 → 0.012 | `world.yaml` | 0 choques nas duas rodadas finais de 60 dias |
| **Diretor repetindo `boato_na_feira`** (21% de tudo em 60 dias) | `cooldown_horas` 20 → 32 | `events/diretor.yaml` | 13% (seeds 42 e 7) |
| **Cidade crescendo** (10 nascimentos × 4 mortes em 60 dias: 21 → 28) | `intervalo_nascimento_dias` 9 → 12 | `world.yaml` | 21 → 22 (máx. 24) e 21 → 23 (máx. 25); `tools.run`: 22 vivos |
| Falas repetidas acima do limite (14 dias): o bezerro dos Cowboys (8×), a missa da Dama (8×) | +5 falas de trabalho dos Cowboys, +4 da Dama na missa, peso 3 → 1 | `lines/rotina.yaml`, `lines/fe.yaml` | sem alerta |

Observações que **não** viraram mudança (são emergência, não defeito):
- A Montanha, o Céu e o Mundo de Fora quase não recebem gente (a Montanha é "para quem quer ficar
  sozinho", o Céu "ninguém sabe se dá pra chegar", o Mundo de Fora é `acesso: nunca`).
- `tarde_mansa`, `fantasma`, `ressurreicao_natural` e `desenho_do_criador` não saíram em 60 dias numa
  seed: são raros/lendários de propósito (fantasmas apareceram pelo caminho próprio: 10 no `tools.run`).
- O Ganancioso virou Médium numa rodada (sucessão por vocação: o candidato soma pontos por ser herdeiro,
  pelo tipo de relação, pela afinidade com o morto e pelos traços de `sucessao.papeis.medium.tracos`; sem
  ninguém com os traços, ganha quem gostava mais dela). É engraçado e coerente com as regras; para a
  vocação pesar mais, o número está em `sucessao` (`bonus_herdeiro`, `bonus_por_tipo`) e no código
  (`2 × traços em comum`, `lifecycle._candidate_score`).

## Amostra real
Trechos reais da rodada oficial de 60 dias (`tools.run --seed 2026`, config final):

```
[19/11 18:00] (O Subterrâneo) O Músico cochicha: rave secreta no Subterrâneo hoje, 21:01, não conta pro Fiscal. Só pro Cowboy Magrelo, o Cowboy Barrigudo, o Fool, a Cozinheira e o Adolescente.
[19/11 21:16] (O Subterrâneo) Grave batendo no Subterrâneo: a rave secreta no Subterrâneo do Músico começou com a Cozinheira, o Cowboy Barrigudo, o Fool, a Médium e o Adolescente.
[19/11 21:26] (O Subterrâneo) O Adolescente sobe na mesa e é convencido a descer.
[19/11 21:57] (As Casas) O Fiscal vai dormir nas Casas.
[20/11 00:16] (O Subterrâneo) A rave secreta no Subterrâneo do Músico acaba com o dia nascendo lá fora. O Recém-chegado nº 2, a Cozinheira, o Cowboy Barrigudo, o Cowboy Magrelo, o Fool, a Médium e o ...
[23/11 07:00] (A Taverna) O Cozinheiro bufa: "Isso não fica assim." Marca um mutirão na Taverna às 09:02 e chama a Cozinheira, o Adolescente, o Chefe, o Ferreiro, o Padre e o Palhaço.
[23/11 09:47] (A Taverna) O Cozinheiro apareceu na Taverna com a caixa de ferramentas. O mutirão foi só ele e um martelo.
[24/11 06:00] (A Taverna) O Cozinheiro bate o martelo na bigorna: mutirão às 09:04 na Taverna! Vêm a Cozinheira, o Adolescente, o Chefe, o Ferreiro e o Padre.
[24/11 09:33] (A Taverna) Começa o mutirão na Taverna: O Cozinheiro manda, a Cozinheira e o Fool carregam tábua.
[24/11 11:52] (A Taverna) Fim do mutirão. O Cozinheiro e o Ferreiro, a Cozinheira e o Fool olham o serviço com orgulho (e um dedo machucado).
```
Da primeira rodada de 60 dias (o tipo de frase que antes saía "em o balcão"; a contração de nomes com
artigo minúsculo é desta fase):
```
[16/11 07:26] (A Taverna) O Aprendiz dá a última martelada no balcão da Taverna e limpa o suor da testa. Pronto.
```

O critério do guia 01 (servidor `--seed 21`, Playwright e CLI, 10/11):
```
ANTES {"name":"O Palhaço","place":"market","hellos":1,"dom":["O Palhaço"]}
$ tools.cli recarregar
Recarregado: 21 personagens, 20 lugares, 47 ações, 1564 falas.
  clown: O Palhaço -> O Bozó
DEPOIS {"after":{"name":"O Bozó","place":"market","hellos":2,"dom":["O Bozó"]},"pageLoads":1,"errs":[],"seconds":12.458}
[10/11 10:38] O Ganancioso pergunta pro Bozó se viu alguma coisa estranha hoje.
[10/11 10:38] O Bozó responde só com uma buzina. *FOM*
[10/11 13:04] O Bozó pergunta pro Músico se é impressão ou a tela está olhando pra gente.
```
Robustez (MQTT real derrubado e religado; log do servidor):
```
INFO server.mqtt: MQTT conectado em 127.0.0.1:18830
WARNING server.mqtt: MQTT desconectado (Unspecified error); tentando de novo a cada 30.0s.
WARNING server.mqtt: MQTT fora do ar (127.0.0.1:18830); a simulação continua e tenta de novo.
INFO server.mqtt: MQTT conectado em 127.0.0.1:18830
world/commands/result {"id": "", "cmd": "recarregar", "arg": "", "result": {"ok": true, "renamed": [], ... "characters": 21, "places": 20, "actions": 47, "lines": 1564, "warnings": []}, ...}
```

## Estado de cada fase

| Fase | Estado | O que entrega | O que ficou de fora |
|---|---|---|---|
| 0 — Preparação | ✅ | `data/` com a bible inteira em YAML, esquemas e validador com sugestões, arquitetura | personagem raro do Criador (aguarda o desenho) |
| 1 — Núcleo | ✅ | relógio, necessidades, Utility AI explicável, ações, grafo com túneis, falas, SQLite, `tools.run` | — |
| 2 — Sociedade | ✅ | afinidades, memória, fofoca, conflitos, pastelão, estruturas, leis/prisão/Limbo, Igreja × Seita, ganância, eventos sociais | relíquias do Esquisito como itens de ritual |
| 3 — Vida, morte, diretor | ✅ | morte, funeral, luto, herança, fantasmas, nascimentos, sucessão, criaturas, clima real, névoa, diretor, `tools.report` | — (balanceado na F6) |
| 4 — Criador e API | ✅ | comandos do Criador, API, WebSocket, MQTT, Chat web, Docker, LLM opcional, o olhar e a Aparição | Ollama real não testado (não existe no sandbox); luz real do quarto |
| 5 — Visual | ✅ | viewer 3D PS1 por tela, placeholders do YAML, `.glb` sem código, túnel com LED, layout | sons; hardware antigo real; animação de cenário `.glb` |
| 6 — Polimento | ✅ | `recarregar`, versão válida, robustez verificada, balanceamento de 60 dias, saúde no `tools.report`, `tools.backup`, 10 guias, README | ver "Pendências" |

## Decisões tomadas e por quê
- **Recarregar no mesmo `World`, trocando o `WorldData`** (não recriar o mundo a partir do banco): o
  mundo nunca para, os assinantes (WebSocket, MQTT, SQLite) e a fila de comandos continuam, e funciona
  também sem banco (testes). O que depende dos dados (caches, estruturas novas, sucessões, ações que
  sumiram) é acertado num lugar só (`sim/reload.apply_data`).
- **Personagem sem arquivo continua** com a versão antiga no `recarregar` (em vez de sumir): apagar o
  arquivo por engano com o mundo ligado não pode "matar" ninguém. Remover de verdade continua sendo com o
  servidor parado (fica congelado no banco, como desde a F1).
- **A cópia válida mora ao lado do banco** (`var/data_valido/`), não em `data/`: é dado de execução (fora
  do git) e no Docker `var/` já é volume. Os nascidos ficam de fora (a pasta deles é sempre a real).
- **Hello novo para todas as telas** no `data_reloaded`, em vez de mensagens de diferença: o viewer já
  sabia redesenhar tudo num `hello` (reconexão); é o caminho mais simples e cobre nomes, cores, telas e
  lugares de uma vez.
- **Limites de balanceamento no código do relatório** (`BALANCE_LIMITS`, com o porquê de cada um), não no
  `world.yaml`: são critérios de análise para quem mexe nos números, não regras do mundo.
- **Um campo novo em vez de mexer na chance de morte** (`dias_minimos_entre_mortes_naturais`): baixar
  a chance diminuiria as mortes, mas não as rajadas; o intervalo resolve a rajada mantendo a média.
- **`pontos_para_prisao: 2.5`** (em vez de mudar o roubo): a ganância do Ganancioso continua igual (é o
  personagem), mas uma infração isolada vira advertência, como um Fiscal razoável faria.
- **`construir` em mais lugares** em vez de mudar o código do mutirão: o mutirão escolhe o lugar mais
  estragado; se a cidade não pode consertar lá, o certo é poder (e o validador agora avisa).
- **Missa/ritual pelo líder atual com entradas novas** (`presenca_lider`, `afinidade_lider`), em vez de
  trocar ids no YAML na sucessão: o João continua lendo "missa onde está o líder da Igreja".
- **Contração para nomes com artigo minúsculo** no `render` (só no nome substituído, nunca no texto do
  template): resolve "em a bigorna" em todo o Chat, inclusive o histórico, sem risco de mexer em frases.
- **Sem WLED pronto**: a receita está no guia 07; um script sem a fita real para calibrar seria chute.

## Arquivos principais criados ou alterados
- `sim/reload.py` (novo) — `recarregar` e a cópia válida.
- `sim/engine.py` — comando `recarregar`, `World.new_state`, `data_dir`; `sim/events.py` — `data_reloaded`.
- `server/runtime.py` — `load_with_valid_copy`, `Runtime.data` (propriedade); `server/ws.py` — telas
  recalculadas e `hello` novo; `server/app.py` — `recarregar` espera a resposta.
- `tools/cli.py` — `recarregar` formatado; `tools/report.py` — saúde do mundo; `tools/backup.py` (novo).
- `sim/text.py` (contração), `sim/utility.py` + `sim/curves.py` (`presenca_lider`, `afinidade_lider`),
  `sim/loader.py` (aviso de conserto; `causas_fora_do_limite` validado), `sim/schemas.py` + `sim/lifecycle.py` (intervalo de mortes naturais e teto semanal de mortes).
- `viewer/src/characters.js` (emissivo), `viewer/src/main.js` (`__dw.live().names`),
  `viewer/e2e/aceite_renomear.cjs` (novo).
- `data/world.yaml`, `data/actions/basicas.yaml`, `data/actions/fe.yaml`, `data/events/sociais.yaml`,
  `data/events/diretor.yaml`, `data/places/{underground,cemetery,sea,prison}.yaml`,
  `data/lines/{rotina,fe}.yaml` — balanceamento.
- `docs/guias/01`–`10` (01–05 e 07–10 novos; 06 estendido), `README.md`, `GUIA_POS_MAX.md` (aponta para
  os guias), `docker-compose.yml` (comentário do volume `data/`), `docs/arquitetura.md` (2, 3.3, 12.11,
  13.1, 16).
- `tests/test_reload.py` (novo, 10 testes); `tests/test_society.py` (2 testes adaptados ao
  `pontos_para_prisao: 2.5`).
- `docs/relatorios/img/fase6_renomear_{1_antes,2_depois}.png`.

## Testes
- **Python: 199 testes, 199 passando** (`.venv/bin/python -m pytest -q -o addopts=""`; 189 de antes,
  com 2 de `test_society.py` ajustados ao limiar novo de prisão — eles fixavam "2 pichações = prisão" e
  "1 roubo denunciado = mandado" — e 10 novos em `tests/test_reload.py` (o décimo: o teto semanal de mortes poupa todos menos as causas de `causas_fora_do_limite`): renomear sem perder estado
  (lugar, necessidades, memórias, relações, relógio) e falas novas já com o nome novo; YAML quebrado
  mantém a versão anterior e avisa; falas/pesos/personagem novo aplicados; arquivo sumido mantém o
  personagem; `Runtime` manda `hello` com o nome novo, guarda a cópia válida, liga com ela quando `data/`
  quebra (e o mundo salvo continua) e sobe `DataError` sem ela; `tools.backup` (cópia consistente e
  limpeza); missa/ritual seguindo o líder atual; contração de nomes de estrutura sem mexer na maiúscula do resto da frase).
- **Viewer:** `npm test` → 8 passando; `npm run build` → ✓.
- **`tools.validate`** → "Tudo certo! 0 erros, 0 aviso(s)."
- **Verificações reais**: o critério do guia 01 com Playwright; o teste de 60 dias (`tools.run` e
  `tools.report`); MQTT com Mosquitto real; reinício com `kill -9`; reconexão da aba 3D; telas novas pelo
  `recarregar` (uma tela `tablet_teste` com o Cemitério apareceu em `/api/screens` e saiu da
  `parede_centro`, com os avisos certos de "caminho a pé atravessa telas"; desfeito depois).

## Limitações e problemas conhecidos
- **O `recarregar` não reabre conexões**: mudar `mqtt`, `servidor`, `persistencia`, `ollama` ou o fuso
  exige reiniciar (o comando avisa). Relações do YAML só mudam a afinidade **inicial** (a viva fica).
- **Personagem removido com o mundo ligado continua** até reiniciar (decisão, ver acima).
- **Mutirão quase todo dia** em 60 dias (42 planejados): as festas e raves quebram coisas e o Ferreiro
  conserta. É coerente, mas pode cansar no Chat; `mutirao.chance_por_hora` (0.15) ou `cooldown_horas`.
- **Tédio ainda é a necessidade mais alta** (~10% das amostras ≥ 95), puxado pelos que trabalham o dia
  todo; abaixo do limite, mas é o primeiro número a olhar se a cidade parecer "parada".
- **Lugares remotos quase vazios** (Montanha, Céu, Deserto, Subterrâneo fora das raves): a
  `meia_vida_viagem_minutos` (20) segura todo mundo perto. É a bible (cidade no centro), mas se o João
  quiser os biomas mais vivos, é o número para mexer (guia 05).
- **Teste de Ollama de verdade** e de **WLED/tela física real** continuam impossíveis aqui.
- A primeira mensagem do `data_reloaded` foi "agora se chama o Bozó" (artigo minúsculo pela regra de
  contração); corrigido com aspas (`agora se chama "O Bozó"`).
- **O teto de 2 mortes por semana salva gente que "devia" morrer**: num acidente ou choque com o teto cheio, a pessoa sobrevive (o tombo/choque acontece e aparece no Chat). É de propósito (a cidade não aguenta uma praga por semana); para semanas trágicas, suba `limites.max_mortes_em_7_dias` ou ponha a causa em `causas_fora_do_limite`.
- A contração de nomes minúsculos foi refinada depois das rodadas de 60 dias (a primeira versão punha
  "A mesa de sinuca" maiúsculo depois de dois-pontos). Só muda a exibição do texto, não a simulação;
  coberto por teste.

## Pendências (o que ficou para depois), por prioridade
1. **Script/automação do WLED** (`leds/tunnel` → fita) — precisa da fita instalada para calibrar; a receita
   está no guia 07.
2. **Testar no homelab de verdade**: Ollama real, MQTT dentro do Docker, telas físicas (celular/TV box
   velhos, tela transparente) — não existem no sandbox.
3. **Trabalho dos Técnicos dependendo só de problema real** (F4) — mexe na profissão e nas criaturas do
   homelab; precisa decidir com o João o que eles fazem quando nada está quebrado.
4. **A luz real do quarto** (pegadinha do Palhaço) e o instrumento real do Músico — precisam do tópico
   MQTT decidido (guia 08, seção 6).
5. **Sons ambientes por lugar** e **animação de cenário `.glb`** no viewer (guia 06 registra a convenção).
6. **Relíquias do Esquisito como itens de ritual** (F2/F3) — a herança existe, o objeto não muda o ritual.
7. **Criaturas com modelo próprio** no viewer (hoje genéricas) — depende de a bible definir as criaturas.
8. Pequenos: quem é solto dormindo acorda "na Prisão" (F2); falas antigas que citam `{@priest}` por id
   (ex.: "escuta o Padre falar mal da seita") continuam citando o Padre original depois de uma sucessão.

## Próximos passos que o João consegue fazer sozinho
1. **Dar nomes de verdade** aos 21 personagens e aos nascidos (guia 01) — só YAML + `recarregar`.
2. **Montar a parede**: medir, ajustar `telas` no `world.yaml`, conferir em `/viewer/layout.html` (guia 07).
3. **Subir no homelab** com `docker compose up -d --build`, `.env` com o MQTT e o Ollama, e um backup
   diário no crontab com `tools.backup` (guia 09).
4. **Ligar o MQTT real**: a câmera em `sala/camera/pessoas`, o Uptime Kuma/Home Assistant em
   `homelab/servicos/<nome>`, as telas em `telas/<id>/status` (guia 08).
5. **Escrever falas** (é o que mais dá vida): rodar `tools.report --days 7` de vez em quando e acrescentar
   variações onde ele apontar repetição (guia 03).
6. **Criar personagens** a partir do `_MODELO.yaml` (o Coveiro do guia 02 é um bom primeiro) e
   **eventos sociais** novos (a "noite do causo" do guia 04).
7. **Modelar no Blender** os personagens mais importantes (uma família de corpo base) e a Catedral (guia 06).
8. **Ajustar o ritmo** pelo guia 05, uma mudança por vez, medindo com a mesma seed.
9. A automação da fita de LED no Home Assistant/Node-RED pela receita do guia 07.

## Onde o João pode mexer sem programar
- Tudo de antes (`data/`), agora aplicado com `tools.cli recarregar` sem reiniciar.
- `data/world.yaml > limites.dias_minimos_entre_mortes_naturais`, `max_mortes_em_7_dias` e `causas_fora_do_limite` (novos).
- Entradas novas nas considerações das ações: `presenca_lider.<facção>`, `afinidade_lider.<facção>`.
- `tools.report --days N --seed S` mede a saúde do mundo depois de cada ajuste (guia 05).

## Revisão do orquestrador
Revisão feita em 2026-11-10, com servidor, seeds e personagem diferentes dos usados pelo subagente.

| Critério de aceite | Resultado | Evidência |
|---|---|---|
| 60 dias simulados sem erros | ✅ passou | `tools.run --fast --dias 60 --novo --inicio 00:00 --seed 808 --nascidos <tmp>` → código 0, stderr vazio, 35 770 linhas de chat, 9 mortes, 8 nascimentos, 20 vivos no fim (mín–máx 17–22). |
| Relatório de variedade dentro dos limites | ✅ passou (após 1 rodada de correção) | Primeira revisão: `tools.report --days 60 --seed 808` deu 2 alertas ("rajada de mortes: 5 em 7 dias" e "procissão 1/6"). Correção: regra `limites.max_mortes_em_7_dias` no YAML + procissão/casamento usando `rezar`. Depois: `tools.report --days 60` nas seeds **808** e **2027** (nova) → "Nenhum alerta (repetição e balanceamento)." O subagente também conferiu 7 e 42. |
| Seguindo só o guia 01, renomear aparece no Chat e no visual sem reiniciar | ✅ passou | Servidor rodando (porta 8002, seed 21); aba 3D aberta antes (`ANTES {"name":"A Florista","hellos":1}`). Segui o guia: troquei `nome:` em `florist.yaml` para "A Rosinha" → `tools.validate` (0 erros) → `tools.cli recarregar` ("florist: A Florista -> A Rosinha"). Na mesma aba, sem recarregar: `DEPOIS {"name":"A Rosinha","hellos":2,"dom":["A Rosinha"]},"pageLoads":1,"errs":[]` em 12 s. Chat: "[10/11 16:26] A Rosinha anda sem rumo até a Feira." Revertido depois. |

Correção feita pelo orquestrador: `tests/test_reload.py::test_reload_renames_without_losing_state` falhava conforme a hora real do dia (o mundo do teste começava "agora" e, à noite, o Palhaço só dormia nas 6 h seguintes). O teste agora fixa o início às 08:00.
Também conferido: `pytest` → 199 passed; `tools.validate` → 0 erros; `npm test` → 8 pass; `npm run build` ok; nenhum nascido, `.glb` de teste ou arquivo de `var/` no repositório.
