# Relatório — Fase 3: Vida, morte e o Diretor

**Data:** 2026-11-10  ·  **Status:** concluída

## Resumo em 3 linhas
O mundo agora tem ciclo de vida: as pessoas morrem de verdade (de morte natural, numa briga que
passa do ponto, num acidente bobo, num choque na Sala do Servidor, pegas por uma criatura ou
perdidas no Limbo), são veladas na Catedral e enterradas no Cemitério debaixo de chuva, com cada
um reagindo do seu jeito; a cidade fica de luto, alguém herda as coisas, fantasmas aparecem de
noite, nasce gente nova (que vira YAML para o João editar) e os papéis vagos são assumidos. Um
Diretor mede a tensão e injeta eventos para manter o ritmo, e o clima segue Botucatu.

## O que foi feito
- **Morte permanente** (`sim/lifecycle.py`, `world.yaml > morte`): 6 causas configuráveis, cada
  uma com o momento do sorteio (`quando: diario | briga | falha | criatura | limbo`), chance, ações,
  lugares e multiplicadores por traço. Ninguém morre por sorteio se a cidade já tem
  `min_populacao` vivos. A morte gera o evento `death` (falas `morte_<causa>`), memória
  permanente em todos, luto, herança, vaga de papel, consequência específica e funeral.
- **Funeral**: velório na Catedral, **cortejo** até o Cemitério (quem estava velando é levado
  andando — eventos de movimento de verdade), enterro, lista de presentes e **lápide** (nome,
  datas, causa e epitáfio próprio de cada personagem: o do Ferreiro é «GRRR.», o do Fool «...hehe.»).
  **Sempre chove** (clima forçado, 24 h no do Fool). A vontade de ir é proporcional à afinidade
  com o morto; a Dama (`vaidoso`) vai para ser vista e o Mike (`vazio`) quase não vai — passa.
  Reações: `funeral_personalidade` (Fool faz piada, Florista canta e distribui flores, Músico
  toca, Dama se exibe, Padre conta segredo de confissão, Ganancioso de olho nas botas...),
  `funeral_amigo`, `funeral`, `funeral_inimigo` e `funeral_passante` (Mike atravessa o enterro).
- **Luto**: intensidade = afinidade × fator da relação (casal, filho, irmão...); choque nas
  necessidades e, por dias, taxas e vontades alteradas (festejar ×0,2, rezar ×2, visitar o túmulo).
  Nova ação `visitar_tumulo` e nova entrada de curva `luto`. **Herança** de objetos para o herdeiro
  da ficha (o Fool fica com o nariz rachado do Palhaço). **`se_morrer`** no `world.yaml` traduz o
  "Se morrer" de cada ficha da bible (cozinha fecha, Palhaço sem piada por uma semana, festa
  escondida pela morte do Fiscal, velório com cerveja dos Cowboys, partilha do esconderijo...).
- **Fantasmas** (raros, à noite, para quem o morto mais amava ou odiava — ou em sonho) e
  **ressurreição natural** raríssima (volta com traço novo, medo e buracos na memória; o Padre grita
  milagre, a Médium reivindica). `resurrect(cid, "criador")` já fica pronto para o `reviver` da F4.
- **Nascimentos**: taxa em `limites.intervalo_nascimento_dias`, mais provável quando há vagas
  abertas por mortes, nunca acima de `max_populacao`; ou o comando `nascer [traços]`. Traços,
  profissão, aparência e rotina sorteados de `traits.yaml`; às vezes herda um objeto ou uma mania de
  um morto recente (mania entre aspas vira bordão). O YAML vai para `data/characters/born/`
  (comentado, pronto para renomear) — ou para outra pasta em testes (ver "Decisões").
- **Sucessão de papéis**: profissão com `papel_importante` sem ninguém vivo abre vaga; depois de
  um tempo alguém assume por **eleição** (Chefe: assembleia na Praça, cada um vota em quem mais
  gosta), **vocação** (Padre, Médium, Fiscal: traços) ou **sucessão** (Ferreiro, Cozinheiro,
  Técnico: herdeiros, aprendiz, família). Quem assume ganha profissão, local e rotina do papel (o
  sino continua tocando) e, se for o caso, a liderança da Igreja/Seita.
- **Criaturas** (`sim/creatures.py`, bestiário inicial em `data/events/creatures.yaml`): 5
  noturnas (Olhos no Escuro, Coisa da Maré, Sombra do Túnel, Vulto do Portão, Bicho das Ruínas) e
  o **Gremlin do Rack**, que aparece na Sala do Servidor quando um serviço real cai
  (`homelab <serviço> down`) e chama os Técnicos; só some quando o serviço volta (`up`). Criaturas
  somam perigo ao lugar, assustam, podem matar e podem ser espantadas (ação `enfrentar`). O Mike é
  imune.
- **Clima** (`sim/weather.py`): Open-Meteo para Botucatu numa thread (nunca trava a simulação),
  cache em `var/clima.json`, sem internet → cache → `clima_padrao`. Com o tempo acelerado o clima é
  sorteado (reproduzível pela seed). Chuva, tempestade, frio e calor mudam taxas de necessidades,
  notas de ações (e de tudo em lugar externo); o Esquisito ganha medo com chuva. Falas filtram por
  clima; `weather_changed` no Chat.
- **Telas offline** (`sim/screens.py`): `tela <id> offline` → névoa nos lugares; ninguém entra,
  quem está dentro fica preso, quem estava a caminho desiste; o Mike passa. `online` desfaz.
- **Diretor** (`sim/director.py`, `data/events/diretor.yaml` com 17 eventos): tensão 0–100 por
  brigas/prisões/perseguições recentes, medo e raiva médios, mortes e criaturas; alvo por período;
  agita (festa, boato, maré estranha, tempestade...) quando está calmo demais e acalma (trégua,
  sopa quente, garoa mansa, missa de consolo...) quando está caótico; limites por hora/dia,
  cooldowns, raros com cooldown longo (fantasma, ressurreição, a figura desenhada do Criador).
  Todo evento sai com o motivo ("tensão 12 < alvo 40: agita") e fica em `director_log`.
- **`tools.report`**: `python -m tools.report --days 7` (ver "Como testar").
- `tools.run`: `--nascidos`, cores dos eventos novos, tabela "Resumo da vida e da morte"; o evento
  `tension` só aparece com `--debug`. `tools.validate` conta criaturas e causas de morte e valida
  tudo o que é novo. SQLite: migração 3 (`graves`, `director_log`, `weather_log`).
- Falas: 1.405 no total (eram 1.046), quase todas as novas em `data/lines/vida.yaml` (43 situações novas) e mais variações em `skate`,
  `tocar_sino`, `ritual`, `resposta_fiscal` (ajuste pelo relatório de variedade).

## Como testar (passo a passo)
```bash
cd divine-machinery-divineworld

# 1) dados e testes
.venv/bin/python -m tools.validate
#    "... 6 criaturas, 6 causas de morte, 31 tipos de memória, 4 telas."  "Tudo certo! 0 erros, 0 aviso(s)."
.venv/bin/python -m pytest -q
#    145 passed (~3 min)

# 2) o critério de aceite: 30 dias, duas seeds (cada uma ~6 min; dá para rodar as duas ao mesmo tempo)
.venv/bin/python -m tools.run --fast --dias 30 --novo --inicio 00:00 --seed 2026 \
    --banco var/f3_s2026.sqlite --saida var/f3_s2026.txt --resumo
.venv/bin/python -m tools.run --fast --dias 30 --novo --inicio 00:00 --seed 7 \
    --banco var/f3_s7.sqlite --saida var/f3_s7.txt --resumo
#    Termina com as tabelas "Resumo da sociedade" e "Resumo da vida e da morte (Fase 3)" e
#    "Mundo salvo em ... 43200 ticks." stderr vazio. Os nascidos vão para
#    var/nascidos/f3_s2026/ e var/nascidos/f3_s7/ (NÃO para data/characters/born).
#    Obs.: --inicio 00:00 é "hoje"; os números abaixo foram tirados com o mundo começando em
#    10/11/2026. Outro dia de início muda a história (o clima e o calendário mudam).

# 3) o funeral deste relatório, direto do chat salvo no passo 2 (seed 2026)
grep -n "Ferreiro" var/f3_s2026.txt | grep "0[12]/12" | grep -v "rumo\|chega \|túnel"

# 4) relatório de variedade (simula numa pasta temporária; nada fica em var/ nem data/)
.venv/bin/python -m tools.report --days 7 --seed 42
.venv/bin/python -m tools.report --days 30 --seed 5 --saida var/variedade30.txt   # ~6,5 min
#    termina com "Nenhum alerta de repetição." (use --estrito para sair com erro se houver alerta)

# 5) brincar com os comandos novos (num mundo de teste)
.venv/bin/python - <<'EOF'
from sim.loader import load_data_or_raise; from sim.engine import World, Command
import os; os.environ["DW_BORN_DIR"] = "var/nascidos/brincadeira"
w = World(load_data_or_raise("data"), None, seed=1)
w.bus.subscribe(lambda e: e.type != "decision" and print(e.render(w.names())))
for c in ("nascer alegre", "homelab jellyfin down", "tela monitor_esquerda offline", "clima tempestade 60"):
    w.submit(Command(*c.split(" ", 1)))
w.run(max_ticks=120, fast=True)
EOF
```
O que o João deve ver no Chat: mortes em vermelho com a causa; o anúncio do velório; chuva no
dia do enterro; o cortejo saindo da Catedral; cada um reagindo do seu jeito; a lápide; o luto
dos mais próximos; heranças; nascimentos ("O Recém-chegado nº 3..."); criaturas de madrugada;
o diretor mexendo nos dias parados; trocas de clima.

**Pasta dos nascidos** (para não sujar o repositório): `DW_BORN_DIR` (variável de ambiente) >
`vida.pasta_nascidos` do `world.yaml` (padrão `characters/born`, relativo a `data/`). O
`tools.run` aceita `--nascidos PASTA`; sem isso, se for simulação de teste (`--fast` ou
`--banco`), usa `var/nascidos/<nome do banco>/` e esvazia essa pasta com `--novo` (nunca apaga
nada dentro de `data/`). Os testes (`tests/conftest.py`) e o `tools.report` usam pasta
temporária. No uso normal (tempo real, banco padrão) os nascidos vão para `data/characters/born/`.

### Números dos 30 dias (código final, `--fast --dias 30 --inicio 00:00`, início 10/11/2026)

| seed | tempo real | vivos no fim | mortes (causas) | funerais | nascimentos | fantasmas | criaturas | eventos do diretor | erros |
|---|---|---|---|---|---|---|---|---|---|
| 2026 | 5 min 59 s | 21 (de 24) | 3 (morte natural, acidente bobo, briga) | 3 (13, 16 e 19 pessoas) | 3 | 2 | 34 | 123 | stderr vazio |
| 7 | 6 min 10 s | 22 (de 27) | 5 (choque, 3 morte natural, acidente bobo) | 5 (12 a 17 pessoas) | 6 | 2 | 34 | 126 | stderr vazio |

População nunca saiu de 19–23 (mín. 12, máx. 40 no YAML): sem extinção nem lotação. Numa rodada
anterior (com números um pouco mais altos de morte, depois baixados) houve 3 sucessões — "O
Ganancioso virou Fiscal", "O Esquisito virou Médium", "O Cowboy Magrelo virou Ferreiro" — e,
noutra, "Mike virou Fiscal" (vocação é sorteio ponderado, não garantia). Nas duas rodadas finais
nenhum papel importante ficou vago (morreram papéis que tinham outro titular ou sem papel).

### Relatório de variedade e o limite de repetição
**Limite: uma fala exata (o texto final do Chat, com os nomes já preenchidos) pode aparecer no
máximo `max(3, dias × 0,5)` vezes — 4 numa semana, 15 num mês.** Justificativa: o Chat do Mundo
tem ~2.100 eventos e ~240 falas por dia; o João olha a parede algumas vezes por dia. A mesma frase
com as mesmas pessoas mais de uma vez a cada dois dias já é notada, e o pilar da bible é "a cada
olhada, algo diferente". Contar o texto final (e não o template) é o que o João vê: "{eu} come
em silêncio" com dez pessoas diferentes são dez frases diferentes para quem lê. As narrações-padrão
das ações ("Mike anda sem rumo até a Praça") aparecem no relatório só como informação (cada ação tem
uma narração; ficam variadas pelas falas que saem junto).

Resultados (sem alertas depois do ajuste):
- `--days 7 --seed 42`: 1.571 falas, 1.357 textos diferentes, máximo 4 repetições ("A Cozinheira
  trabalha resmungando."), **nenhum alerta**.
- `--days 7 --seed 99`: primeiro deu 2 alertas (5×: "A Médium abre os braços: \"As vozes
  disseram...\"" e uma resposta do Fiscal). Ajustei só YAML (peso do bordão da Médium, +4 falas de
  ritual, +10 de `resposta_fiscal`); de novo: **nenhum alerta**.
- Antes, na seed 42, os alertas eram "O Ganancioso: \"É meu.\"" e "O Adolescente anda de skate e
  assusta uma galinha." (5×): baixei o peso de `{eu}: "{bordao}"` em `conversa` e escrevi +15 falas
  de skate e +8 do sino.
- `--days 30 --seed 5` (antes dos dois últimos ajustes de YAML): 7.299 falas, 5.029 textos
  diferentes, máximo 11 (limite 15), **nenhum alerta**.

## Amostra real — o funeral do Ferreiro (seed 2026)
Do `var/f3_s2026.txt` (passo 2), com os números de linha do arquivo. Ninguém escreveu esta
história. Na manhã de 1º de dezembro o Ferreiro conserta a mesa de sinuca da Taverna e forja
ferramentas; às 18h ele e o Músico (que a bible diz se darem mal com barulho) se atracam na
Ferraria. A briga passa do ponto (`morte.causas.briga`, 3%):
```
[14407] [01/12 18:00] (A Ferraria) O Ferreiro e o Músico se atracam e derrubam tudo que tinha na Ferraria.
[14408] [01/12 18:00] (A Ferraria) O Músico puxa o cabelo do Ferreiro. Golpe baixo.
[14411] [01/12 18:06] (A Ferraria) O Músico empurra, o Ferreiro bate a cabeça na Ferraria. Silêncio. Não era para ser assim.
[14412] [01/12 18:06] (O Campo) O Cowboy Magrelo: "Não pode ser. O Ferreiro? Não pode ser."
[14413] [01/12 18:06] (A Cozinha Comunitária) A Cozinheira acha uma coisa esquecida do Ferreiro e não consegue jogar fora.
[14414] [01/12 18:06] (A Feira) O Cozinheiro abraça a primeira pessoa que passa e não explica nada. É pelo Ferreiro.
[14415] [01/12 18:06] (O Campo) Agora avental de couro é do Cowboy Magrelo. Era do Ferreiro. Ainda tem o cheiro.
[14416] [01/12 18:06] (A Catedral) O Padre: "Deus me livre e guarde. Às 06:21, o velório do Ferreiro. Todo mundo de preto."
[14418] [01/12 18:07] (A Prefeitura) O Músico denuncia o Ferreiro. O Ferreiro saiu no tapa com o Músico na Ferraria, segundo o Músico.
```
(Quem sente na hora é quem gostava dele — o casal da cozinha é amigo dele na ficha; o avental
vai para quem o morto mais gostava naquele momento, já que a ficha dele não tem herdeiro. A linha 14418 era um defeito: o Músico
denunciou um morto. Corrigido depois desta rodada — `law.best_report` agora ignora mortos.)

Na manhã seguinte, às 06:21, o tempo de Botucatu (sorteado) estava firme, mas:
```
[14700] [02/12 06:21] O céu escurece e chove. É dia de enterro.
[14701] [02/12 06:21] (A Catedral) As velas acendem em volta do Ferreiro. Na primeira gota de chuva, o Padre começa a falar.
[14708] [02/12 06:24] (A Catedral) O Fool cochicha: "Quantas vezes eu fiz o Ferreiro rir? Onze. Doze, se contar a de hoje" ...hehe.
[14711] [02/12 06:26] (A Catedral) O Cozinheiro chora mais alto que todo mundo no funeral do Ferreiro: "Faltou... faltou o Ferreiro!"
[14712] [02/12 06:26] (A Catedral) A Cozinheira trouxe comida para o funeral do Ferreiro: "Come que esfria!" Ninguém consegue.
[14714] [02/12 06:26] (A Catedral) O Cowboy Magrelo tira o chapéu, cospe de lado e diz: "Vai com Deus, o Ferreiro. Ô loco, sô."
[14717] [02/12 06:26] (A Catedral) O Técnico murmura no funeral do Ferreiro: "Não encosta nisso..." e não explica para ninguém.
[14718] [02/12 06:27] (A Catedral) O Chefe vai ao funeral do Ferreiro porque todo mundo foi.
[14729] [02/12 06:32] (A Catedral) O Cowboy Velho chora no funeral do Ferreiro sem tentar esconder.
[14735] [02/12 06:46] (A Catedral) O Esquisito anota tudo do funeral do Ferreiro num caderninho, inclusive o formato das nuvens.
[14736] [02/12 06:56] (A Catedral) A Médium acende uma vela preta escondida no funeral do Ferreiro. O Padre finge que não viu.
[14737] [02/12 06:56] (A Catedral) Mike assina o livro do velório do Ferreiro com letra caprichada.
[14738] [02/12 07:01] (A Catedral) O Padre puxa o cortejo do Ferreiro pela rua de terra. O Recém-chegado nº 1, a Recém-chegada nº 2,
        o Cozinheiro, a Cozinheira, o Chefe, o Cowboy Barrigudo, o Cowboy Velho, o Cowboy Magrelo, a Florista, o Fool, o Ganancioso,
        a Dama, a Médium, Mike, o Aprendiz, o Técnico e o Esquisito seguem calados.
```
No Cemitério:
```
[14743] [02/12 07:07] (O Cemitério) O Cowboy Barrigudo segura a terra na mão e não consegue jogar na cova do Ferreiro.
[14744] [02/12 07:07] (O Cemitério) O Cowboy Velho repete baixinho: "Ô loco, sô." — era o que o Ferreiro mais ouvia.
[14745] [02/12 07:07] (O Cemitério) O Cowboy Magrelo derrama um gole de cerveja na terra do Ferreiro: "Essa é sua."
[14748] [02/12 07:07] (O Cemitério) O Ganancioso pergunta, no meio do enterro do Ferreiro, quem fica com as botas. "É meu."
[14749] [02/12 07:07] (O Cemitério) A Dama chora alto no funeral do Ferreiro, de olho em quem está olhando. Lágrima nenhuma.
[14752] [02/12 07:07] (O Cemitério) O Padre reza pela alma do Ferreiro e, no meio da reza, conta um segredo de confissão sem perceber.
[14753] [02/12 07:07] (O Cemitério) O Aprendiz pergunta alto, no meio do enterro do Ferreiro, se dá para ligar alguém de volta na tomada.
[14755] [02/12 07:07] (O Cemitério) O Esquisito pega uma pedrinha da cova do Ferreiro e sussurra: "...isso é importante..."
[14757] [02/12 07:07] (O Cemitério) A Recém-chegada nº 2 olha a chuva cair na cova do Ferreiro e pensa que todo mundo um dia vai ser esquecido.
[14762] [02/12 07:57] (O Cemitério) Mike conta pra ninguém em especial que o Ferreiro uma vez lhe deu bom dia.
[14766] [02/12 08:09] (O Cemitério) O Músico conta pra ninguém em especial que o Ferreiro uma vez lhe deu bom dia.
[14768] [02/12 08:09] (O Cemitério) O Fool: "Pelo menos agora o Ferreiro não precisa mais acordar cedo ...hehe." Silêncio total.
[14769] [02/12 08:10] (O Cemitério) Enterram o Ferreiro no Cemitério. Estavam lá: O Fool, o Cozinheiro, a Cozinheira, o Cowboy Barrigudo,
        o Cowboy Magrelo, o Padre, o Técnico, o Chefe, a Florista, o Recém-chegado nº 1, a Recém-chegada nº 2, o Ganancioso, a Dama,
        o Cowboy Velho, o Aprendiz, o Esquisito, a Médium, Mike e o Músico.
[14771] [02/12 08:10] (O Cemitério) A lápide nova no Cemitério: O Ferreiro, 10/11/2026 – 01/12/2026. Briga que passou do ponto. «GRRR.»
[14772] [02/12 08:10] (A Praça) Sem o Ferreiro, as reconstruções ficam lentíssimas.
[14777] [02/12 08:25] As nuvens vão embora. Céu limpo.
[15136] [02/12 19:10] (O Cemitério) O Cowboy Magrelo deixa um pedaço de pão no túmulo do Ferreiro. Por via das dúvidas.
[15291] [02/12 21:52] (O Cemitério) O Cozinheiro chora um pouquinho no túmulo do Ferreiro e depois ri de alguma lembrança.
```
O Músico, que matou o Ferreiro, só aparece no fim do enterro (é o último da lista); a chuva some 15 minutos
depois do enterro (o clima forçado acaba e o sorteado volta); os amigos voltam ao túmulo à noite
(luto → `visitar_tumulo`). E a consequência da ficha ("as reconstruções ficam lentíssimas") passa a
valer: `construir` ×0,4 por 7 dias.

## Decisões tomadas e por quê
- **Clima "auto"**: real só quando o mundo roda no relógio de verdade (`run` sem `--fast`,
  velocidade 1, hora do mundo a menos de 3 h da real); com tempo acelerado e nos testes, sorteado
  pelo RNG do mundo. A chuva de agora não faz sentido num dia simulado em 10 segundos, e assim os
  testes nunca vão à rede e a mesma seed dá a mesma história. A pergunta ao Open-Meteo roda numa
  thread (a simulação nunca espera a internet). Neste ambiente o Open-Meteo responde 403 pelo
  proxy: o fallback (cache → `clima_padrao`) foi exercitado de verdade e nos testes (com dublês).
- **Pasta dos nascidos por `DW_BORN_DIR`, lida sempre do ambiente real** (mesmo quando o loader
  recebe `environ={}`) e também no momento do nascimento: os testes que carregam `data/` uma vez por
  módulo continuam gravando na pasta temporária. `tools.run` deriva `var/nascidos/<banco>/` em
  simulação de teste.
- **O mundo trabalha numa cópia rasa dos dados** (`dataclasses.replace`): nascer e assumir papel
  muda só o `World`, não o `WorldData` compartilhado (os testes de módulo e a F4 dependem disso).
- **Ações de papel por profissão** (`ritual`, `recrutar` → `medium`; `pregar`, `espiar_seita`,
  `confessar` → `padre`; `mandar_reconstruir` → `lider`): sem isso a sucessão não teria efeito.
- **"velhice" chama-se "morte natural"** no Chat: ninguém tem idade na bible e um recém-nascido
  morrer "de velhice" ficava ridículo. O id continua `velhice` (com multiplicador para `experiente`
  e `cansado`).
- **Mortes ~3–5 por mês, nascimentos compensando**: começa em 1 a cada 9 dias e cada vaga aberta
  (mortes − nascimentos em 30 dias) soma 100% à chance. A primeira rodada (com chances mais altas) teve
  7 mortes em 30 dias; baixei só YAML (`chance_morte_por_dia` 0,004 → 0,0013, briga 0,04 → 0,03,
  acidente 0,008 → 0,006, criatura 0,02 → 0,01, criaturas `chance_por_hora` −40%).
- **Funeral de manhã/tarde** (`comeca_entre 07:00–18:00`, velório 40 min antes): o enterro cai
  de dia, com a cidade acordada. O velório só "vale" a partir da hora marcada (numa versão
  anterior as reações começavam 20 min antes, antes da chuva). Falas que falam de cova/terra só
  saem no Cemitério (filtro `lugares`).
- **Reações**: 70% pela personalidade quando o personagem tem fala própria, senão pela afinidade —
  assim o Fool faz piada quase sempre, mas às vezes só chora. Filtro novo `mortos: [id]` para
  falas que dependem de quem morreu (o Fool chora contando a piada favorita do irmão).
- **Só os 3 mais abalados anunciam o luto no Chat**: com todo mundo anunciando, a notícia virava
  15 linhas iguais.
- **Fantasma e ressurreição saem do diretor** (eventos `raro`/`lendario`), com as chances dos
  `limites` do world.yaml, como pede o prompt (eventos raros com cooldown longo).
- **O diretor estava ao contrário na F0** (`noite_animada` era "acalma"): pelo prompt, festa é
  para quando está calmo demais → virou "agita".
- **Personagem raro do Criador**: a bible deixa a ficha em branco; virou um evento lendário (`desenho_do_criador`,
  1%/dia, cooldown 30 dias): a cidade inteira para e olha uma figura "desenhada à mão". Quando o
  desenho existir, é só trocar o texto (ou criar o personagem).
- **Homelab sem MQTT ainda**: o comando `homelab <serviço> down|up` faz tudo; a F4 só liga o tópico
  nele. Idem `tela <id> online|offline` para `telas/<id>/status`.
- **Limite de repetição pelo texto final** (ver "Relatório de variedade"): é o que o João vê.

## Arquivos principais criados ou alterados
- `sim/lifecycle.py` (novo) — morte, funeral, luto, herança, consequências, fantasma, ressurreição,
  nascimento (YAML), sucessão/eleição.
- `sim/creatures.py`, `sim/weather.py`, `sim/screens.py`, `sim/director.py` (novos).
- `sim/engine.py` — liga tudo (tick, especiais `funeral/tumulo/criatura/assembleia`, mortes em brigas
  e pastelão, névoa, multiplicadores de clima/luto, comandos `nascer`, `tela`, `homelab`, `clima`,
  persistência, snapshot com clima/tensão/população/névoa/criaturas).
- `sim/schemas.py`, `sim/loader.py` — esquemas e validação de tudo que é novo; leitura da pasta dos
  nascidos. `sim/utility.py` (entradas `luto`, `criatura`, `chuva`; perigo com criaturas; névoa),
  `sim/needs.py`, `sim/speech.py` (filtros `mortos`, `profissoes`, clima por tipo), `sim/text.py`
  (contração no começo da frase: "Em O Subterrâneo" → "No Subterrâneo"), `sim/factions.py` (líder
  atual), `sim/law.py` (morte no Limbo; morto não é denunciado), `sim/persistence.py` (migração 3).
- `tools/report.py` (novo), `tools/run.py`, `tools/validate.py`.
- `data/world.yaml` (clima, vida, morte, funeral, luto, se_morrer, sucessao, criaturas, diretor,
  7 tipos de memória), `data/traits.yaml` (nascimento, efeitos em `velar`/`enfrentar`/`visitar_tumulo`),
  `data/actions/vida.yaml` (novo: velar, visitar_tumulo, enfrentar, assembleia), `data/actions/fe.yaml` e
  `sociais.yaml` (papéis por profissão), `data/events/diretor.yaml` (17 eventos),
  `data/events/creatures.yaml` (novo), `data/lines/vida.yaml` (novo) e outros `lines/`, `data/places/*`.
- `tests/test_life.py` (27 testes novos), `tests/conftest.py` (pasta temporária de nascidos, clima sem rede).
- `docs/arquitetura.md` (seções 2, 4.1, 8, 10, 12 reescrita, 16), `README.md`, `.env.example`.

## Testes
- 145 testes, 145 passando (`.venv/bin/python -m pytest -q`, ~3 min). 27 novos em `tests/test_life.py`:
  morte permanente e memória, população mínima, luto por afinidade e tipo de relação, herança, funeral
  completo (chove durante todo ele, cortejo, ≥ 6 presentes, reações, lápide com nome/data/causa,
  memória), reação pela personalidade, nascimento gravando YAML na pasta temporária (e nunca em
  `data/characters/born`), YAML que valida e carrega, cópia dos dados, mania herdada virando bordão,
  taxa de nascimento (vagas, teto), comando `nascer`, sucessão do Padre (rotina do sino, liderança da
  Igreja), eleição do Chefe, fantasma para quem o morto mais amava/odiava, ressurreição, criatura
  (perigo, espantada), Mike imune, homelab (criatura, objetivo dos Técnicos, só some no `up`), clima
  (códigos, real com dublê + cache offline, sorteado, efeito em lugar externo, medo de chuva), névoa
  (preso, ninguém entra, Mike passa), diretor (agita/acalma, limites, `director_log`, tensão na Utility
  AI), persistência da vida, e três dias violentos sem `{variável}` sobrando.
- Os 118 das fases anteriores continuam passando (sem mudar nenhum).
- Além dos testes: 30 dias com as seeds 2026 e 7 (tabela acima), `tools.report` 7 dias (seeds 42 e 99)
  e 30 dias (seed 5).

## Limitações e problemas conhecidos
- **Morte natural é sorteio**: não há idade; o recém-nascido tem a mesma chance de quem tem
  `experiente`. Mortes vêm em rajadas às vezes (seed 7: 3 em 4 dias no começo de dezembro).
- **O Aprendiz morre de choque com frequência** (nas duas seeds finais, no começo do mês): ele `fuça`
  todo dia e leva choque toda semana, como na bible. Se for demais, `morte.causas.choque.chance`.
- **Criaturas: ~1 por noite** (34 em 30 dias) e **o diretor usa muito `boato_na_feira` e `tregua`**
  (20+ e ~15 por mês): ajustáveis por `peso`/`cooldown_horas` no YAML.
- **Ações de presença ainda citam ids fixos**: `missa` olha `presenca.priest`, `participar_ritual`
  olha `presenca.medium`; se o Padre morrer, o sucessor toca o sino e prega, mas a missa ainda
  procura o Padre original. Não aconteceu nas rodadas finais.
- Quem morre continua aparecendo nas fofocas antigas (memórias) — é coerente, mas às vezes estranho.
- Alguns textos antigos ainda tropeçam: "dá a última martelada em a mesa de sinuca" (nome de
  estrutura em minúscula não contrai), "Vai com Deus, o Ferreiro" (vocativo com artigo).
- 7 nascimentos seguidos saíram "Recém-chegada" numa rodada de testes (sorte do sorteio: 1 em 128;
  conferido que o sorteio é 50/50).
- Cada rodada de 30 dias leva ~6 min em `--fast` (o prompt pede < 15): não otimizei.

## Pendências (o que ficou para depois)
- Ligar MQTT `homelab/servicos/#` e `telas/+/status` aos comandos `homelab`/`tela` — Fase 4 (os
  comandos já fazem tudo).
- `reviver` do Criador — Fase 4 (`lifecycle.resurrect(cid, "criador")` e as falas
  `ressurreicao_criador` já existem).
- Personagem raro do Criador como personagem de verdade — depende do desenho do João (bible).
- `missa`/`participar_ritual` seguirem o líder ATUAL (entrada `presenca_lider.<facção>`) — pequena,
  ficou para a F6 (balanceamento).
- Relíquias do Esquisito virando itens de ritual (pendência da F2) — continua: a herança existe,
  mas o objeto não muda nada no ritual.

## Onde o João pode mexer sem programar
- `data/world.yaml`:
  - `limites` — chance de morte natural, fantasma por noite, ressurreição por ano, intervalo de
    nascimento, chuva do funeral, população mínima/máxima;
  - `morte.causas` — as causas, quando sorteiam, chances e traços que aumentam/diminuem;
  - `funeral` — atraso, horário, velório, duração, quem conduz, vontade de ir;
  - `luto` — quem entra, quanto dura, o choque e o que muda;
  - `se_morrer` — o que a morte de cada personagem da bible muda (crie um bloco para os nascidos!);
  - `sucessao` — como cada papel é assumido, em quanto tempo e quem tem preferência;
  - `clima` — modo, tipos e nomes, sorteio, efeitos, medo de chuva;
  - `diretor` — pesos da tensão, alvo por período, margem, chance de agir;
  - `vida` — pasta dos nascidos, bônus por vaga, herança.
- `data/traits.yaml > nascimento` — traços, herança, nome provisório, rotina de quem nasce.
- `data/characters/born/*.yaml` — os nascidos: troque `nome`, traços, aparência, bordões.
- `data/events/diretor.yaml` — eventos do diretor (copie um bloco para criar outro).
- `data/events/creatures.yaml` — o bestiário (nomes, lugares, chances, textos).
- `data/lines/vida.yaml` — falas de morte, funeral (por personagem/traço), luto, lápide (epitáfio
  de cada um), fantasmas, nascimentos, sucessão, criaturas e clima.
- `data/actions/vida.yaml` — ir ao funeral, visitar túmulo, enfrentar criatura, assembleia.

## Revisão do orquestrador
Revisão feita em 2026-11-10, com seeds novas (314 e 11), com o código final (depois das últimas correções do subagente).

| Critério de aceite | Resultado | Evidência |
|---|---|---|
| 30 dias sem erro, nascimentos e mortes plausíveis, sem extinguir nem lotar | ✅ passou | `tools.run --fast --dias 30 --novo --inicio 00:00 --seed 314 --nascidos <tmp>` → saiu com código 0, stderr vazio, 19 096 linhas de chat. 3 mortes (2 naturais, 1 briga), 3 funerais, 3 nascimentos, 1 sucessão (o Adolescente virou Médium), 21 vivos no fim de 24 que existiram. |
| Relatório de variedade sem fala acima do limite | ✅ passou | `tools.report --days 7 --seed 11` → "Nenhum alerta de repetição." (limite `max(3, dias×0,5)`, justificado no relatório). O subagente também rodou `--days 30 --seed 5` sem alertas. |
| Funeral real contado a partir dos logs | ✅ passou | Seção do relatório (seed 2026, o Ferreiro). Na minha rodada (seed 314) o funeral da Médium também saiu coerente: "[22/11 06:20] Começa a chover. Como em todo funeral.", "A Florista canta uma música alegre demais para o funeral da Médium", "A Dama chega atrasada ao funeral da Médium para todo mundo ver o vestido." |

Também conferido: `pytest` → 145 passed; `tools.validate` → 0 erros; `data/characters/born/` só com `.gitkeep` (os nascidos da revisão foram para a pasta temporária via `--nascidos`).
Observações para a Fase 6: morte natural às vezes vem em rajada; o Diretor repete `boato_na_feira`/`tregua`; Open-Meteo devolve 403 neste sandbox, então só o caminho cache → plano B foi exercitado.
