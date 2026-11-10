# Guia 05 — Balanceamento: os números que mudam o mundo

> Quase todo o "jeito" do mundo está em `data/world.yaml` (e um pouco nas ações e eventos). Este guia
> lista os números que mais pesam, o que acontece se você subir ou descer cada um, e como medir antes
> e depois. Regra de ouro: **mude uma coisa de cada vez e meça.**

## 0. Como medir

```bash
.venv/bin/python -m tools.report --days 14 --seed 42          # ~2,5 min; mesma seed = comparação justa
.venv/bin/python -m tools.report --days 60 --seed 42 --saida var/balanco.txt   # ~12 min, o teste longo
```
O relatório simula num banco temporário (não mexe no seu mundo) e mostra, além das falas repetidas, a
**saúde do mundo** (Fase 6):

| Tabela | Olhe para | Alerta quando |
|---|---|---|
| Balanceamento — saúde do mundo | prisões por semana, mortes (e a pior janela de 7 dias), população, criaturas | > 8 prisões/semana; ≥ 3 mortes em 7 dias; população fora de `min/max_populacao` |
| Eventos sociais | planejados × sucesso × fracasso | < 25% de sucesso (com 3+ tentativas); nunca organizado em 30+ dias |
| Diretor: eventos injetados | o mais repetido; os que nunca saíram | um evento > 30% de tudo |
| Necessidades ≥ 95 | necessidades "explodindo" e quem vive travado nelas | > 15% da cidade; um personagem > 40% do tempo |
| Ocupação dos lugares | média e máximo de gente em cada lugar | (só informação: lugar sempre vazio, lugar lotado) |
| Personagens: variedade | quem faz poucas coisas diferentes | < 5 ações diferentes |

Os limites dos alertas estão em `tools/report.py > BALANCE_LIMITS` (explicados lá). Compare duas ou três
seeds: uma seed só pode enganar (sorte). Depois de ajustar o YAML, `tools.cli recarregar` aplica no mundo
que está rodando.

## 1. Necessidades (`necessidades`)

Cada uma vai de 0 a 100 (maior = mais urgente). `acumula` sobe sozinha (`taxa_dia`/`taxa_noite` em pontos
por hora do mundo); `retorna` volta para a `base` (raiva, medo).

| Número | Sobe → | Desce → |
|---|---|---|
| `fome.taxa_dia` (6) | mais idas à Cozinha, mais roubo de comida | come menos, mais tempo para o resto |
| `sono.taxa_dia/noite` (3/6) | dormem mais cedo, cochilos | noites longas, festas até tarde |
| `social.taxa_dia` (5) | mais conversa, fofoca, festa | cidade mais calada |
| `fe.taxa_dia` (1.5) | missas e rituais cheios | Igreja e Seita esvaziam |
| `tedio.taxa_dia/noite` (6/2) | mais festa, pegadinha, skate, perambular; e briga | cidade mais "trabalhadora" |
| `raiva.taxa_*` (8) | é a VOLTA à calma: maior = esfria mais rápido, menos brigas | rancor dura, mais brigas |
| `medo.taxa_*` (10/6) | idem para o medo (criaturas, Aparição) | o susto dura mais |

Cada personagem multiplica no próprio arquivo (`necessidades: {sono: {taxa: 0.8}}`) e os traços também.
Os efeitos das ações (`efeitos.necessidades`) são o outro lado da conta: o `dormir` tira 95 de sono (e,
desde a Fase 6, 35 de tédio).

## 2. Como escolhem (`decisao`)

| Número | O que faz | Mais alto | Mais baixo |
|---|---|---|---|
| `top_n` (3) | sorteia entre as N melhores ações | mais variedade, menos coerência | previsível (1 = sempre a melhor) |
| `temperatura` (1.0) | quão proporcional é o sorteio | caótico | sempre a melhor das N |
| `fracao_da_melhor` (0.4) | só sorteia o que vale ≥ 40% da melhor | mais coerente | mais aleatório |
| `meia_vida_viagem_minutos` (20) | a nota cai pela metade a cada N min de caminho | andam mais pelo mundo | ficam onde estão (biomas vazios) |
| `penalidade_repeticao` (0.6) | multiplica a ação que acabou de fazer | repetem mais | variam mais |
| `reavaliar_a_cada_minutos` (10) | de quanto em quanto tempo quem está ocupado olha em volta | reage devagar | reage rápido (mais CPU) |
| `fator_interrupcao` (3), `nota_para_interromper` (0.5) | quanto melhor algo precisa ser para largar o que faz | teimosos | largam tudo à toa |
| `nota_para_acordar` (2.0) | o motivo precisa ser forte para acordar alguém | dormem até o fim | acordam com qualquer coisa |

## 3. Vida e morte (`limites`, `morte`, `vida`)

| Número | Efeito |
|---|---|
| `limites.chance_morte_por_dia` (0.0013) | morte natural por pessoa/dia (~0,8 por mês com 21) |
| `limites.dias_minimos_entre_mortes_naturais` (8) | **Fase 6**: sem morte natural se alguém morreu há menos dias (evita rajadas) |
| `limites.max_mortes_em_7_dias` (2) | **Fase 6**: teto da semana. Com 2 mortes nos últimos 7 dias, nenhuma causa sorteada mata (o acidente, o choque, a briga e o Limbo acontecem, mas a pessoa sobrevive). 0 = sem teto. Subir = semanas trágicas possíveis |
| `limites.causas_fora_do_limite` (`[]`) | causas que matam mesmo com o teto cheio (ex.: `[criatura]` para as noites de terror continuarem perigosas) |
| `morte.causas.<causa>.chance` | briga (0.03 por briga), acidente (0.004 por falha), choque (0.012 por falha ao fuçar), criatura (0.01) |
| `morte.causas.<causa>.por_traco` | quem morre mais disso (`desastrado: 1.5`) |
| `limites.min_populacao` (12) / `max_populacao` (40) | ninguém morre por acaso com 12; ninguém nasce com 40 |
| `limites.intervalo_nascimento_dias` (12; era 9 até a Fase 6) | nascimento médio; `vida.bonus_por_vaga` acelera depois de mortes |
| `limites.chance_fantasma_por_noite` (0.12), `chance_ressurreicao_natural_por_ano` (0.05) | o sobrenatural |
| `luto.*`, `funeral.*`, `se_morrer.<id>` | quanto e por quanto tempo a morte mexe com a cidade |

## 4. Lei e ordem (`leis`, `limites`)

| Número | Efeito |
|---|---|
| `leis.infracoes.<id>.gravidade` | pontos por infração (roubo 2, briga 1.5, barulho 0.3...) |
| `leis.pontos_para_prisao` (2.5) | **Fase 6** (era 2): um roubo sozinho dá advertência; roubo + outra coisa prende |
| `leis.pontos_para_limbo` (6) | o castigo grave |
| `leis.pontos_somem_por_dia` (1) | perdão com o tempo |
| `leis.reincidencia_horas` (6), `max_por_olhada` (2) | o Fiscal não registra a mesma coisa duas vezes |
| `limites.horas_de_prisao` (12), `dias_no_limbo` (3) | tempo de castigo |
| ação `roubar`: `peso`, `cooldown_minutos` | quanto o Ganancioso rouba (a maior fonte de prisões) |

## 5. Sociedade (`relacoes`, `fofoca`, `faccoes`, `memoria`)

| Número | Efeito |
|---|---|
| `relacoes.retorno_por_hora` (0.2) | afinidades voltam devagar ao valor do YAML (maior = rancor esquece rápido) |
| `relacoes.inimigos_abaixo` / `amigos_acima` | quando o Chat anuncia "viraram inimigos/amigos" |
| `fofoca.chance_distorcao` (0.2) | fofoca torta (troca quem fez) |
| `faccoes.<id>.afinidade_para_entrar/sair` | Igreja × Seita: mais baixo = facção cresce |
| `memoria.tipos.<tipo>.intensidade/dias` | quanto tempo lembram de cada coisa (rancor, saudade) |

## 6. Eventos sociais (`data/events/sociais.yaml`)

Para cada um: `chance_por_hora` (quantas vezes alguém tem a ideia), `vontade` (necessidade mínima de quem
organiza), `comeca_entre` (janela), `antecedencia_horas`, `quorum`, `bonus` (o quanto o convite pesa contra
o que o convidado faria), `cooldown_horas`. Se fracassa sempre: aumente `bonus`, diminua
`antecedencia_horas`, mova a janela para quando a cidade está acordada e livre.

## 7. Diretor (`diretor` e `data/events/diretor.yaml`)

| Número | Efeito |
|---|---|
| `diretor.alvo` ({madrugada 15, manhã 25, tarde 35, noite 40}) | a tensão que ele persegue: mais alto = mundo mais agitado |
| `diretor.margem` (8) | quanto pode fugir do alvo antes de agir |
| `diretor.chance_de_agir` (0.25) | a cada checagem fora da margem |
| `diretor.pesos_eventos` | o que conta como tensão (briga 9, perseguição 6, prisão 5...) |
| `limites.max_eventos_diretor_por_hora/dia` (3/20) | teto |
| cada evento: `peso`, `cooldown_horas` | o que ele escolhe (e quanto repete) |

## 8. Criaturas, clima, olhar

- `criaturas` (`world.yaml`) e `data/events/creatures.yaml`: chance por noite, máximo ao mesmo tempo.
- `clima`: modo (real ou sorteado), tipos e efeitos (chuva tira gente da rua), `medo_de_chuva`.
- `limites.chance_olhar_por_hora` (0.02) e `cooldown_aparicao_dias` (7): o mistério com o Criador.

## 9. O que mudou na Fase 6 e por quê

Medido com `tools.report` (14 dias, seeds 7, 42 e 99, e o teste de 60 dias): veja a tabela completa em
`docs/relatorios/FASE_6.md`, seção "Balanceamento". Resumo: tédio ia para ≥ 95 em ~26% das amostras
(sono agora alivia tédio e a taxa da noite caiu); prisões (~13/semana na F2) caíram com
`pontos_para_prisao: 2.5` e barulho mais leve; rave, rodeio, casamento e mutirão quase sempre
fracassavam (janelas, antecedência e bônus ajustados; o mutirão também marcava conserto onde não dava
para consertar; a procissão e o casamento usavam a ação `missa`, que só vale onde o Padre está e não vale
para o próprio Padre — agora usam `rezar`); mortes em rajada (intervalo mínimo entre mortes naturais e
teto de 2 mortes por semana) e o Aprendiz morrendo de choque (chance 0.03 → 0.012).
