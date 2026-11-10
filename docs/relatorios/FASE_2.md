# Relatório — Fase 2: Sociedade (relações, memória e conflito)

**Data:** 2026-11-10  ·  **Status:** concluída

## Resumo em 3 linhas
Os NPCs agora gostam e odeiam (afinidade viva), lembram (memórias que aparecem nas falas), fofocam
(e a fofoca chega torta), discutem, brigam de pastelão, fazem as pazes, roubam, são presos e vão
para o Limbo; a Igreja e a Seita disputam fiéis, as coisas quebram e são consertadas, e os próprios
NPCs organizam festas, raves, rodeios, procissões, casamentos e mutirões — que dão certo ou fracassam.
Nada disso é roteiro: sai de necessidades, traços, afinidades, memórias e de regras pequenas no YAML.

## O que foi feito
- **Relações** (`sim/relations.py`): afinidade −100..100 por par (direcionada), começa no YAML, muda
  por ações, memórias, fofocas e eventos, e volta devagar ao valor inicial
  (`relacoes.retorno_por_hora`). Cruzar o limite de amizade/inimizade gera `relation_changed`.
- **Memória** (`sim/memory.py`): 24 tipos em `world.yaml > memoria.tipos` (briga, discussão, pazes,
  pegadinha, tombo, roubo, sumiço, prisão, Limbo, festa, ritual, casamento...), com intensidade,
  sentimento, decaimento por dia e `permanente`. Quem viveu lembra forte, testemunha lembra mais
  fraco, quem ouviu (fofoca) mais fraco ainda. Memórias viram a variável `{lembranca}` nas falas
  ("Desde aquela briga na Cozinha Comunitária que você me deve uma!") e entradas da Utility AI.
- **Fofoca** (`sim/gossip.py`): conta a memória mais "suculenta" (notícia ruim corre mais) sobre um
  terceiro que o ouvinte ainda não sabe; 20% de chance de chegar torta (40% para o traço
  `fofoqueiro`: Padre e Dama) — quem fez vira outra pessoa. **Confissão**: quem fez algo errado
  confessa ao Padre; o segredo só vaza pela boca dele (situação `fofoca_confissao`).
- **Conflito e reconciliação** (só YAML + 3 regras genéricas): `discutir` (afinidade em U: briga-se
  com quem se odeia e com quem se ama), `brigar` (pastelão, infração, chance de perseguição),
  `pedir_desculpas` (vai atrás da pessoa), `abracar`, `consolar`, e a reação automática `emburrar`.
  As pazes dependem de memória de conflito × afinidade *inicial* × pouca raiva: o casal e os Cowboys
  fazem as pazes rápido; o Ganancioso e os Cozinheiros, nunca. A **briga das três da tarde** é só um
  bloco de rotina `discutir` às 15:00 na Cozinha; com quem (às vezes é o Chefe!), como escala e
  quando fazem as pazes (≈ 15:05–15:10) sai da simulação.
- **Humor de pastelão**: ações com `falha` e traços que multiplicam a chance (`desastrado` ×1,8,
  `irritado` ×1,6): `pregar_peca` do Palhaço (45% dá errado nele), `andar_de_skate` do Adolescente,
  `fazer_malabarismo` do Fool, `fucar` (o choque do Aprendiz), o tombo no meio da briga, o Ferreiro
  quebrando o que consertava. Evento `slapstick`.
- **Construções vivas** (`sim/structures.py`): 17 estruturas nos lugares (`estruturas:`), com
  resistência e estado inteiro/danificado/destruído. Brigas, festas, `quebrar`, pichação e acidentes
  estragam; `construir` conserta; o Chefe manda reconstruir (objetivo para todos); o Ferreiro (e
  quem é protetor/perfeccionista) organiza mutirões.
- **Leis e punição** (`sim/law.py`): o Fiscal registra infrações (pichar, roubar, barulho só de
  madrugada, brigar, quebrar, baderna) por **flagrante**, **assinatura** (o Adolescente assina a
  pichação) ou **denúncia** (ação `denunciar`, ou fofoca contada a ele). Pontos por gravidade:
  advertência → prisão (12 h, só pode fazer coisas na cela) → Limbo (3 dias fora das telas; volta com
  um traço novo sorteado). Infrator longe = mandado; o Fiscal vai atrás (`prender`) e o infrator pode
  fugir.
- **Facções** (`sim/factions.py`): Igreja (Padre) × Seita (Médium) em `world.yaml > faccoes`. Missa
  de dia na Catedral, ritual à noite na floresta/subterrâneo (a Médium conduz; os outros entram na
  roda onde ela está), o Padre espia a seita, recruta e prega; entrar/sair pela afinidade com os
  líderes. O Adolescente começa sem facção, rondando.
- **Ganância** (no engine): o Ganancioso rouba os `objetos` dos lugares, esconde e às vezes esquece
  onde; quem perambula acha (o Esquisito declara sagrado); quem trabalha no lugar percebe o sumiço e
  **escolhe um suspeito** entre quem passou por lá — pelo desafeto, então às vezes erra.
- **Eventos sociais organizados pelos NPCs** (`sim/social_events.py` + `data/events/sociais.yaml`):
  festa na Taverna, rave secreta, rodeio, procissão, casamento (com par de afinidade mútua ≥ 92,
  nunca entre parentes) e mutirão. Um NPC com vontade alta tem a ideia, marca hora e lugar, convida
  pela afinidade (os convidados ganham um objetivo), e o evento acontece com quórum ou fracassa.
- **Objetivos** na Utility AI (convites, ordem do Chefe; o diretor da F3 vai usar o mesmo) e **ir
  atrás de alguém em outro lugar** (`ir_atras`), pendência da F1.
- **Falas**: 1046 falas em 80 situações (eram 75 em 19). Todas as situações comuns têm ≥ 15
  variações (conversa 45, trabalhar 28, discussão 26, comer 23, fofoca 22, briga 21...).
- **Gênero nas narrações** (pendência da F1): `{o|a}` usa o pronome de quem fala, `{outro:o|a}` o do
  alvo, `{terceiro:o|a}` o de quem se fala ("A Dama acorda do cochilo, meio perdida").
- **`--resumo`** ganhou a tabela "Resumo da sociedade": contagem de cada tipo de acontecimento e a
  lista de eventos organizados com quem organizou e o resultado.
- `docs/arquitetura.md` (seções 2, 4.1, 6, 7, 8, 9, 10, 11 reescrita e 16), `README.md`,
  `data/characters/_MODELO.yaml` (campo `faccao`).

## Como testar (passo a passo)
```bash
cd divine-machinery-divineworld

# 1) dados e testes
.venv/bin/python -m tools.validate
#    "... 1046 falas em 80 situações, 3 eventos, 6 eventos sociais, 24 tipos de memória, 4 telas."
#    "Tudo certo! 0 erros, 0 aviso(s)."
.venv/bin/python -m pytest
#    118 passed (~90 s; o teste da semana inteira sozinho leva ~50 s)

# 2) o critério de aceite: uma semana a --speed 3600 (≈ 2 min 50 s reais)
.venv/bin/python -m tools.run --speed 3600 --dias 7 --novo --inicio 00:00 --seed 2026 \
    --banco var/fase2.sqlite --saida var/fase2_chat.txt --resumo
#    Termina com "Mundo salvo em var/fase2.sqlite — hora do mundo 2026-11-16T00:00:00-03:00,
#    10080 ticks." e a tabela "Resumo da sociedade (Fase 2)" (números exatos na Amostra real).
#    stderr vazio.

# 3) a mesma semana, o mais rápido possível (~60 s) — dá EXATAMENTE a mesma tabela
.venv/bin/python -m tools.run --fast --dias 7 --novo --inicio 00:00 --seed 2026 \
    --banco var/f.sqlite --saida var/f.txt --resumo

# 4) outras sementes (troque 42 por 7, 99, 1234, 5...)
.venv/bin/python -m tools.run --fast --dias 7 --novo --inicio 00:00 --seed 42 \
    --banco var/s42.sqlite --saida var/s42.txt --resumo

# 5) as histórias deste relatório, direto do chat salvo no passo 2
grep -n "pinga\|Teje\|Limbo" var/fase2_chat.txt | head -40
grep -n "\] (A Cozinha Comunitária)" var/fase2_chat.txt | grep " 15:[0-1][0-9]\]"
grep -n "saco de feijão\|Fool" var/fase2_chat.txt | grep -i "feijão\|preso\|cadeia\|prisão"

# 6) só a vida de um personagem, com o porquê de cada decisão
.venv/bin/python -m tools.run --fast --horas 16 --novo --inicio 00:00 --seed 2026 \
    --banco var/d.sqlite --personagem chef_wife --debug
```
O que o João deve ver: no Chat do Mundo, além da rotina, discussões e brigas (em vermelho), pazes
(verde), fofocas (amarelo, às vezes com o culpado errado), o Fiscal anotando, advertindo, prendendo
e — com azar — mandando alguém pro Limbo; rituais da Médium toda noite, missas de dia; festas
anunciadas com hora marcada, que acontecem ou não; estruturas rachando e mutirões consertando.

Contagens de uma semana (`--fast --dias 7 --inicio 00:00`, código final), por semente:

| seed | brigas | discussões | pazes | fofocas | prisões | rituais | Limbo | eventos organizados que deram certo |
|---|---|---|---|---|---|---|---|---|
| 2026 | 6 | 49 | 25 | 69 | 10 | 30 | 1 | 4 |
| 42 | 5 | 55 | 16 | 76 | 13 | 37 | 0 | 6 |
| 7 | 4 | 51 | 15 | 45 | 10 | 24 | 0 | 7 |
| 99 | 7 | 51 | 28 | 52 | 11 | 39 | 1 | 6 |
| 1234 | 5 | 43 | 24 | 66 | 10 | 39 | 0 | 7 |
| 5 | 7 | 52 | 30 | 79 | 13 | 34 | 0 | 5 |

## Amostra real
Saída real do passo 2 (`--speed 3600`, seed 2026), 2 min 48 s reais, 10080 ticks, stderr vazio.
Tabela do fim de `var/fase2_chat.txt`:
```
│ discussões                       │      49 │                                                        │
│ brigas (pastelão)                │       6 │                                                        │
│ pazes (desculpas/abraço)         │      25 │                                                        │
│ fofocas                          │      69 │ 18 chegaram tortas; 4 eram segredo de confissão        │
│ pegadinhas                       │       9 │                                                        │
│ tombos e trapalhadas             │      59 │                                                        │
│ perseguições                     │       1 │                                                        │
│ roubos                           │      15 │                                                        │
│ sumiços percebidos               │       9 │ 6 com o suspeito errado                                │
│ infrações registradas            │      27 │ + 7 advertências                                       │
│ prisões                          │      10 │                                                        │
│ idas ao Limbo                    │       1 │                                                        │
│ solturas                         │      10 │                                                        │
│ rituais da seita                 │      30 │                                                        │
│ mudanças de facção               │       0 │                                                        │
│ estruturas que mudaram de estado │      14 │                                                        │
│ amizades/inimizades novas        │      13 │                                                        │
│ missas assistidas                │      39 │                                                        │
│ eventos organizados por NPCs     │      14 │ 4 deram certo, 9 fracassaram                           │
│   · procissão                    │         │ 09/11 08:00, pelo Padre: fracassou                     │
│   · rodeio dos Cowboys           │         │ 09/11 14:01, pelo Cowboy Velho: fracassou              │
│   · festa na Taverna             │         │ 09/11 19:00, pela Florista: sucesso (18 pessoas)       │
│   · rave secreta no Subterrâneo  │         │ 09/11 22:02, pelo Músico: fracassou                    │
│   · mutirão                      │         │ 10/11 07:04, pelo Ferreiro: fracassou                  │
│   · festa na Taverna             │         │ 11/11 19:00, pelo Palhaço: sucesso (18 pessoas)        │
│   · mutirão                      │         │ 12/11 07:01, pelo Ferreiro: fracassou                  │
│   · rave secreta no Subterrâneo  │         │ 12/11 22:03, pelo Músico: fracassou                    │
│   · rodeio dos Cowboys           │         │ 13/11 14:02, pelo Cowboy Velho: sucesso (4 pessoas)    │
│   · festa na Taverna             │         │ 13/11 19:02, pelo Palhaço: fracassou                   │
│   · casamento                    │         │ 15/11 10:02, pelo Cowboy Magrelo: fracassou            │
│   · festa na Taverna             │         │ 15/11 19:03, pelo Cowboy Magrelo: sucesso (19 pessoas) │
│   · rave secreta no Subterrâneo  │         │ 15/11 22:02, pelo Músico: fracassou                    │
│   · mutirão                      │         │ 16/11 07:03, pelo Cozinheiro: planejado                │
```

### Três histórias que emergiram (do mesmo `var/fase2_chat.txt`)
Ninguém escreveu nenhuma delas. As linhas abaixo são copiadas do arquivo (números de linha do
arquivo entre colchetes no começo de cada bloco, para conferir com `sed -n`).

**1. A pinga do confessionário (09/11 e 10/11).** O Ganancioso rouba uma garrafa de pinga de manhã,
vai se confessar com o Padre... e o Padre (fofoqueiro) conta para o Fiscal na hora do almoço. Preso
ao meio-dia; solto à meia-noite; cinco horas depois já está roubando de novo — e quem o entrega dessa
vez é a Dama, repetindo a história da pinga que ela ouviu do Padre na véspera.
```
[linhas 79, 127, 197, 199, 200]
[09/11 07:07] (A Taverna) O Ganancioso enfia uma garrafa de pinga no casaco, de fininho.
[09/11 09:48] (A Catedral) O Ganancioso chora no confessionário falando sobre aquele sumiço de uma garrafa de pinga na Taverna. O Padre escuta com atenção demais.
[09/11 12:07] (A Prefeitura) O Padre conta pro Fiscal que o Ganancioso roubou uma garrafa de pinga na Taverna. "Deus me livre e guarde!"
[09/11 12:07] (A Prefeitura) O Fiscal agradece a denúncia do Padre e afia o lápis. O Ganancioso está encrencado.
[09/11 12:07] (A Prefeitura) O Fiscal anuncia: "O Ganancioso, você está preso por roubo!" e aponta o caminho da cela.
[linhas 625, 649, 653, 691, 701–703]
[10/11 00:07] (A Prisão) O Ganancioso sai da prisão mais sábio. Ou não.
[10/11 05:25] (A Cozinha Comunitária) O Ganancioso enfia uma linguiça defumada no casaco, de fininho.
[10/11 05:33] (A Cozinha Comunitária) O Ganancioso perde uma linguiça defumada no próprio esconderijo. Um clássico.
[10/11 06:36] (A Cozinha Comunitária) A Cozinheira bate a colher de pau na mesa: "Sumiu uma linguiça defumada! Eu CONTEI! Foi o Ganancioso!"
[10/11 06:48] (A Taverna) A Dama jura pro Fiscal que o Ganancioso roubou uma garrafa de pinga na Taverna. Pode ser verdade. Pode não ser.
[10/11 06:48] (A Taverna) O Fiscal abre uma ficha nova: "O Ganancioso — roubo — segundo a Dama".
[10/11 06:48] (A Taverna) O Fiscal leva o Ganancioso preso. No caminho, um passarinho faz cocô no Fiscal. Justiça poética.
```
(Dali em diante a cidade não esquece: ele é preso de novo na mesma noite, por denúncia da
Cozinheira, e no dia 14 os pontos acumulados mandam ele pro Limbo — ver a história 3.)

**2. A briga das três da tarde (13/11).** A rotina da Cozinheira só diz "às 15:00, vontade de
discutir na Cozinha". O resto saiu sozinho: o marido revida, fica emburrado (reação automática),
e oito minutos depois é ele quem abraça. Logo depois, já em paz, ela cochicha uma fofoca para ele —
errada (ver a história 3).
```
[linhas 2956–2958, 2963, 2964, 2969]
[13/11 15:00] (A Cozinha Comunitária) A Cozinheira começa a discutir com o Cozinheiro e esquece no meio por que começou.
[13/11 15:00] (A Cozinha Comunitária) O Cozinheiro responde com uma lista de defeitos da Cozinheira, em ordem alfabética.
[13/11 15:00] (A Cozinha Comunitária) O Cozinheiro cruza os braços e vira a cara.
[13/11 15:08] (A Cozinha Comunitária) O Cozinheiro abraça a Cozinheira e já esquece por que estavam brigando.
[13/11 15:10] (A Cozinha Comunitária) A Cozinheira puxa o Cozinheiro pelo braço: "Você não ouviu isso de mim, mas o Fool pegou um saco de feijão da Cozinha Comunitária, certeza."
[13/11 15:17] (A Cozinha Comunitária) A Cozinheira e o Cozinheiro se abraçam e prometem nunca mais brigar. Até amanhã.
```
Em outros dias o mesmo bloco de rotina deu outra coisa: no dia 10, o Cozinheiro não estava e ela
brigou com quem estava lá — `[10/11 15:15] (A Cozinha Comunitária) A Cozinheira sacode a colher de
pau na cara do Chefe: "Come que esfria!" Começou a briga das três da tarde.`; no dia 12 foi ele quem
pediu desculpas às 15:03 ("e jura que nunca mais. A Cozinheira já ouviu isso antes").

**3. O saco de feijão e o Fool inocente (13/11 e 14/11).** O Fiscal pega o Ganancioso em flagrante
roubando feijão na Cozinha e o prende na hora. Mas a Cozinheira não estava lá: quando volta ao
trabalho, percebe o sumiço e desconfia de quem passou pela cozinha — e escolhe o Fool. Conta pro
marido, depois denuncia ao Fiscal, que vai atrás do Fool até o Cemitério e o prende pelo mesmo
roubo pelo qual o Ganancioso já estava preso. No dia seguinte, o Cozinheiro (que tinha visto o
roubo com os próprios olhos: no banco, a memória dele não tem `heard_from`) espalha a versão certa; ela chega ao Fiscal pelo Adolescente e pelo próprio Cozinheiro,
e os pontos do Ganancioso passam do limite: Limbo. A cidade, claro, não concorda sobre quem mandou.
```
[linhas 2846–2848, 2897, 3158, 3160, 3198, 3199, 3270, 3396]
[13/11 12:15] (A Cozinha Comunitária) O Ganancioso enfia um saco de feijão no casaco, de fininho.
[13/11 12:15] (A Cozinha Comunitária) O Fiscal saca o bloquinho na frente do Ganancioso: "Infração: roubo. Anotado."
[13/11 12:15] (A Cozinha Comunitária) O Fiscal fecha a grade atrás do Ganancioso: "Doze horas pra pensar no que fez."
[13/11 13:36] (A Cozinha Comunitária) A Cozinheira anota num papel: "um saco de feijão — sumiu — O Fool??" e sublinha o nome.
[13/11 19:13] (O Mar) A Cozinheira denuncia o Fool pro Fiscal: O Fool pegou um saco de feijão da Cozinha Comunitária, certeza. "Faça alguma coisa!"
[13/11 19:13] (O Mar) O Fiscal ouve a história e escreve no bloquinho: O Fool, roubo. Testemunha: A Cozinheira.
[13/11 19:38] (O Cemitério) O Fiscal encontra o Fool: "Teje preso!"
[13/11 19:38] (O Cemitério) O Fiscal conduz o Fool pra cadeia com toda a pompa de uma procissão.
[13/11 21:04] (A Prisão) O Fool conta pro Chefe uma piada sobre morte. Ninguém ri ...hehe.
[14/11 07:38] (A Prisão) O Fool deixa a prisão e promete nunca mais. Promessa fraca.
[linhas 3489, 3493, 3817, 3818, 3829, 3830, 4171, 4175, 4248]
[14/11 11:14] (A Feira) O Cozinheiro comenta com o Adolescente, como quem não quer nada: "O Ganancioso roubou um saco de feijão na Cozinha Comunitária, né?"
[14/11 11:28] (A Prefeitura) O Adolescente conta pro Fiscal que o Ganancioso roubou um saco de feijão na Cozinha Comunitária. "Tanto faz."
[14/11 19:22] (A Prisão) O Cozinheiro conta pro Fiscal que o Ganancioso roubou um saco de feijão na Cozinha Comunitária. "Faltou sal... faltou SAL!"
[14/11 19:22] (A Prisão) O Fiscal ouve a fofoca e transforma em processo: O Ganancioso, roubo.
[14/11 19:33] (A Praça) O Fiscal chega bufando: "O Ganancioso, em nome do regulamento!"
[14/11 19:33] (A Praça) O Fiscal manda o Ganancioso pro Limbo por roubo. A cidade inteira fica quieta.
[15/11 12:25] (A Praça) A Florista diz pra Dama: "Não sou de fofoca, mas o Ganancioso foi mandado pro Limbo pelo Aprendiz."
[15/11 12:29] (A Praça) A Dama conta pro Fool que o Ganancioso foi mandado pro Limbo pelo Cowboy Velho. "Que gentalha."
[15/11 14:39] (A Feira) A Florista desenha no chão pro Palhaço explicar como o Ganancioso foi mandado pro Limbo pela Médium.
```
(As versões "pelo Aprendiz", "pelo Cowboy Velho", "pela Médium" são fofocas que chegaram tortas.)

## Decisões tomadas e por quê
- **Não existe Carteiro na bible** (o prompt cita "o Carteiro e o Padre"): não inventei personagem.
  Quem espalha mais é o traço `fofoqueiro` (Padre e Dama); um Carteiro futuro é só ganhar o traço.
- **Comportamentos especiais com nome no YAML** (`especial: fofoca | confissao | denuncia | prender |
  roubar | recrutar | ordem_reconstruir`) em vez de código por ação: o João liga, desliga, renomeia e
  reequilibra no YAML; a regra fica em um lugar só (`World._special_before/_after`).
- **Discussão separada de briga**: brigar exige muita raiva; discutir acontece com quem se odeia *e*
  com quem se ama (curva em U) — é assim que o casal e os Cowboys brigam sem se odiar.
- **Pazes pela afinidade *inicial***: a nova entrada `afinidade_inicial` é o "amor de fundo"; quem
  sempre se gostou faz as pazes, quem nunca se gostou fica no rancor.
- **`reacao_alvo: emburrar`** (3–8 min): sem isso o alvo de uma discussão abraçava no mesmo minuto;
  com isso, as pazes do casal caem perto das 15:05, como na bible.
- **`interrompe_alvo`**: briga/pegadinha/discussão fazem o alvo largar o que fazia e sentir na hora,
  senão ele continuava cozinhando no meio do tapa.
- **Barulho só conta das 22h às 6h, reincidência de 6 h e no máximo 2 flagrantes por olhada**: na
  primeira versão o Fiscal foi a uma festa e multou 18 pessoas de uma vez.
- **Traços de raiva/medo invertidos (correção de dados da F0)**: raiva e medo são do modo "retorna",
  então multiplicador maior = passa mais rápido. `tranquilo` (0,6→1,6), `calmo` (0,5→2,0),
  `otimista` (medo 0,7→1,5) e `bravo`/`briguento`/`irritado`/`ranzinza`/`sensivel`/`inseguro`/
  `desconfiado` estavam ao contrário; corrigido e explicado no topo de `traits.yaml`.
- **Fofoca prefere notícia ruim** (`0,3 + 1,2×ruim + 0,3×bom`): com o peso simétrico, a cidade só
  falava de festa boa. E quem participou de uma festa guarda a mesma memória (sem "com quem"), senão
  ninguém "já sabia" e a mesma notícia rodava para sempre.
- **Suspeito ponderado por `40 − afinidade`** entre quem passou pelo lugar: o culpado é o mais
  provável, não o garantido (na amostra, 6 de 9 sumiços tiveram suspeito errado).
- **Lembranças começam com "aquele/aquela"** (`world.yaml > memoria.tipos.*.lembranca`): fica certo
  depois de "desde", "por", "sobre" sem precisar de contração com artigo minúsculo.
- **Persistência simplificada**: memórias e estruturas em tabelas (campos em JSON); objetos
  roubados, objetivos, leis e eventos sociais em `meta.society`. As tabelas `objects`/`goals` do
  plano não foram criadas (menos migração, mesmo resultado). Parar e continuar continua dando a
  mesma história (teste de 20 h cortado ao meio).
- **Sem evento `memory_formed`**: cada briga gera memória em todas as testemunhas e inundaria o Chat;
  as memórias aparecem nas falas e ficam no banco.
- **O casal do YAML (`tipo: casal`) já nasce casado** e irmão/pai/mãe/filho/aprendiz/mentor nunca
  casam entre si; o Adolescente está fora dos casamentos (numa versão intermediária o Palhaço casou
  com ele — cortado).
- **Perambular evita voltar direto por onde veio** (×0,25): o Mike ficava preso em 3 biomas vizinhos
  e o teste da F1 ("≥ 5 lugares num dia") passou a falhar por azar de seed.
- **Rave e rodeio com `bonus: 10`**: competem com a festa de sempre na Taverna (rotina dos
  convidados); com 5 eles nunca tinham plateia. Mesmo assim falham bastante — é bom que falhem às vezes.
- **Ajustes só em YAML depois de rodar semanas**: pesos de `discutir` (1,0), `brigar` (1,6),
  `denunciar` (1,2, a qualquer hora: antes só se denunciava no expediente e houve semana sem prisão),
  `confessar` (1,5), cooldowns (discutir 90 min, brigar 180, roubar 300, fofocar 45), dano de brigas
  e festas nas estruturas, `afinidade_para_entrar` da Seita 62 (o Adolescente entrava na 1ª hora).

## Arquivos principais criados ou alterados
- `sim/memory.py`, `sim/relations.py`, `sim/gossip.py`, `sim/law.py`, `sim/factions.py`,
  `sim/structures.py`, `sim/social_events.py` — os sistemas novos.
- `sim/engine.py` — liga tudo: consequências de cada ação (memórias, lei, efeitos no alvo, pichação,
  observar), especiais, ganância/sumiços/achados, fugas e perseguições, objetivos, tick de hora em
  hora, persistência da sociedade.
- `sim/utility.py` — entradas novas, objetivos, `ir_atras`, ações automáticas, regras de preso.
- `sim/speech.py`, `sim/text.py` — variáveis novas, filtro `memoria`, concordância `{o|a}`.
- `sim/schemas.py`, `sim/loader.py`, `sim/curves.py` — esquemas e validação de tudo que é novo.
- `sim/persistence.py` — migração 2 (`memories`, `structures`), `extra_traits`.
- `tools/run.py` — cores dos eventos novos, tabela "Resumo da sociedade"; `tools/validate.py` — conta
  eventos sociais e tipos de memória.
- `data/world.yaml` (memoria, fofoca, relacoes, leis, faccoes, estruturas, roubos),
  `data/actions/*.yaml` (21 ações novas, 7 ligadas), `data/events/sociais.yaml` (novo),
  `data/lines/*.yaml` (conflito, fofoca, lei, ganancia, pastelao novos; os outros expandidos),
  `data/places/*.yaml` (estruturas, objetos, ações), `data/characters/*.yaml` (facções, rotina do
  Fiscal, da Cozinheira, do Palhaço e da Médium), `data/traits.yaml`.
- `tests/test_society.py` (25 testes novos).
- `docs/arquitetura.md`, `README.md`, `data/characters/_MODELO.yaml`.

## Testes
- 118 testes, 118 passando (`.venv/bin/python -m pytest`, ~90 s). 25 novos nesta fase
  (`tests/test_society.py`); os 93 da F1 continuam passando.
- Cobrem: memória (formar, reforçar, decair, permanente, frase com tokens, filtro `memoria` nas
  falas, conflito só entre os dois), afinidade voltando ao inicial, fofoca (cópia mais fraca,
  "já sabe", distorção forçada), segredo de confissão (só vaza pelo fofoqueiro), briga (interrompe o
  alvo, memória do alvo e da testemunha), desculpas (precisa de conflito e de amor de fundo; o
  Ganancioso não), reconciliação enfraquecendo memórias, pastelão (choque do Aprendiz, testemunha
  lembra), estruturas (dano, estado, conserto só onde precisa, ordem do Chefe vira objetivo de
  todos), lei (advertência → prisão → Limbo, reincidência, preso só age na prisão, soltura, volta do
  Limbo com traço novo), mandado e `prender` indo atrás, barulho só de madrugada, pichação assinada
  descoberta depois, roubo → sumiço → suspeito, facções (YAML, entrada por afinidade, ritual só onde
  a Médium está), festa planejada → acontece → memória, festa sem ninguém → fracassa, casamento (amor
  mútuo, nunca entre irmãos, casal do YAML já casado), concordância de gênero, sociedade sobrevivendo
  a reiniciar, história idêntica parando no meio (20 h), e **a semana inteira (seed 42)** com brigas,
  discussões, pazes, fofocas, evento organizado que deu certo, prisão e rituais, sem `{variável}`
  sobrando em nenhum texto.
- Além dos testes: semanas completas com as seeds 2026 (também a `--speed 3600`), 42, 7, 99, 1234
  e 5 — todas com brigas, pazes, fofocas, ≥ 4 eventos organizados que deram certo, ≥ 10 prisões e
  ≥ 24 rituais (tabela no "Como testar").

## Limitações e problemas conhecidos
- **Quem é solto dormindo continua dormindo na cela** e acorda "na Prisão" (a soltura não mexe na
  ação em andamento). Cosmético.
- Gente livre às vezes perambula até a Prisão e conversa com os presos (a Prisão é um lugar normal
  do grafo). Às vezes rende cena; às vezes só fica estranho.
- **Prisões talvez demais** (10–13 por semana): o Ganancioso rouba ~15–20 vezes por semana e a
  cidade denuncia. Se cansar, `roubar.cooldown_minutos` ou `leis.pontos_para_prisao`.
- **Raves e casamentos quase sempre fracassam** (a rave compete com a Taverna; o casamento é marcado
  com até 20 h de antecedência e os convidados esquecem). É emergência, mas dá para ajustar os
  `bonus`/`antecedencia_horas` em `data/events/sociais.yaml`.
- Mudança de facção é rara (0–2 por semana) e o Adolescente nem sempre entra na Seita numa semana.
- Algumas falas genéricas ainda soam masculinas em situações sem `{o|a}` (revisei as narrações das
  ações e as falas novas; sobra uma ou outra das antigas).
- Fofoca distorcida pode trocar até o autor de uma confissão ("Coitado do X, veio me confessar que
  o X..." com um X que nunca confessou): é a fofoca torta, mas pode confundir.
- O texto do Chat continua começando nomes de objeto/estrutura com minúscula no meio de frases
  depois de travessão ("— O Ganancioso??" fica maiúsculo); a contração de artigos só trata nomes que
  começam com artigo maiúsculo.

## Pendências (o que ficou para depois)
- Morte, funeral, luto, fantasmas, criaturas, clima real, diretor — Fase 3 (o diretor deve usar os
  `goals` e o `World.say` desta fase; a tensão pode vir das contagens de brigas/prisões).
- Comandos do Criador (Chefe/Médium) e API — Fase 4; o Chefe já sabe "mandar reconstruir", então a
  ordem do Criador pode reaproveitar o `especial: ordem_reconstruir`.
- O Palhaço trocar a luz real do quarto como pegadinha (bible: opcional) — depende do MQTT (F4).
- Herança de objetos roubados/achados e "relíquias" do Esquisito virando itens de ritual — o achado
  sagrado já existe (memória e fala), mas o objeto não vai para a seita; ficou para a F3 (herança).
- Eleição do Chefe (evento social da bible) — depende de morte/sucessão (F3).

## Onde o João pode mexer sem programar
- `data/world.yaml`:
  - `memoria.tipos` — cada tipo de memória: força, sentimento, quanto dura, quanto muda a afinidade,
    se é prova de infração, e as frases (`fato` da fofoca e `lembranca` das falas);
  - `fofoca.chance_distorcao` e o traço fofoqueiro; `relacoes.retorno_por_hora`;
  - `leis` — infrações (nome, gravidade, horários), pontos para prisão e Limbo, quanto dura um
    mandado, reincidência, o que o preso pode fazer; `limites.horas_de_prisao` e `dias_no_limbo`;
  - `faccoes` — líderes e afinidade para entrar/sair; `estruturas.danificado_abaixo`;
  - `roubos` — chance de testemunha notar, de esquecer o esconderijo, de achar, quem acha "sagrado".
- `data/events/sociais.yaml` — os eventos que os NPCs organizam: quem pode organizar, com que
  vontade, chance por hora, janela de horário, antecedência, duração, quórum, convidados, bônus,
  textos. Dá para criar um novo (ex.: "noite do causo") copiando um bloco.
- `data/actions/sociais.yaml` e `fe.yaml` — pesos, curvas, falhas (pastelão), memórias, infrações,
  `ir_atras`, `reacao_alvo`, efeitos por traço. Explicação de cada campo no topo de `sociais.yaml`.
- `data/places/<id>.yaml > estruturas` e `objetos` — o que pode quebrar e o que pode ser roubado.
- `data/characters/<id>.yaml > faccao` e `rotina` (a "briga das três" é a linha `discutir` da
  Cozinheira; tirar a linha = o casal só briga quando a raiva mandar).
- `data/traits.yaml` — `efeitos.falha` (quem é mais desastrado), e os multiplicadores de ação.
- `data/lines/*.yaml` — falas com `{o|a}` para concordância e `memoria: [...]` para falas que
  lembram do passado.

## Revisão do orquestrador
Revisão feita em 2026-11-10, com uma seed nova (777), diferente das usadas pelo subagente.

Comando: `tools.run --fast --dias 7 --novo --inicio 00:00 --seed 777 --resumo` → saiu com código 0, 4618 linhas de chat, stderr vazio.

| Critério de aceite | Resultado | Evidência (seed 777) |
|---|---|---|
| Brigas | ✅ passou | 43 discussões, 5 brigas de pastelão |
| Pazes | ✅ passou | 27 pazes (desculpas/abraço) |
| Fofocas | ✅ passou | 87 fofocas, 22 distorcidas, 1 segredo de confissão |
| Pelo menos uma festa organizada por NPCs | ✅ passou | Festa na Taverna em 09/11 19:00, organizada pelo Palhaço (sucesso, 18 pessoas), e outra em 11/11, pelo Cowboy Velho (19 pessoas); 13 eventos organizados no total, 7 com sucesso |
| Uma prisão | ✅ passou | 13 prisões, 1 ida ao Limbo |
| Um ritual da seita | ✅ passou | 36 rituais (ex.: "[10/11 18:47] (O Cemitério) A Médium acende as velas no Cemitério. O ritual começa.") |
| Nada roteirizado | ✅ passou | Seeds diferentes produzem sequências diferentes; os eventos vêm de necessidades/rotinas/regras em YAML (conferido em `data/events/sociais.yaml` e nas ações), sem sequências fixas de história. |
| 3 histórias reais no relatório | ✅ passou | Seção de histórias com linhas citadas do `var/fase2_chat.txt` |

Também conferido: `pytest` → 118 passed; `tools.validate` → 0 erros, 0 avisos.
Ponto de atenção para a Fase 6: 13 prisões por semana parece muito para 21 NPCs — ajustar no YAML no balanceamento.
