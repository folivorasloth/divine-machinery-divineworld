# Fase 3 — Vida, morte e o Diretor

Leia `CLAUDE.md`, `docs/bible.md`, `docs/arquitetura.md` e os relatórios anteriores.

## Objetivo
O mundo ganha ciclo de vida e ritmo: nascimentos, mortes permanentes com funeral, fantasmas, criaturas noturnas, clima real e um Diretor que mantém o mundo interessante sem roteirizar.

## Tarefas
1. **Morte (permanente):** causas emergentes e configuráveis (briga, acidente, criatura, velhice, choque na Sala do Servidor, o Limbo). Probabilidades baixas e balanceadas em `world.yaml`.
2. **Funeral:** sempre chove na cidade durante o funeral. Procissão até o cemitério; cada personagem reage pela personalidade e pela afinidade com o morto (o Fool faz piada, a Florista canta, o Músico toca, a Dama só vai pra ser vista). A lápide fica no cemitério com nome, datas e causa.
3. **Luto:** necessidades e humor alterados nos próximos dias, proporcional à afinidade. Memória permanente.
4. **Fantasmas:** raros, à noite, perto de quem o morto mais amava ou odiava.
5. **Nascimentos:** de tempos em tempos (taxa configurável) ou por comando. Personalidade, aparência (cor, forma) e profissão sorteadas de `traits.yaml`; herança de um objeto ou mania de um morto recente. O novo personagem é salvo como YAML em `data/characters/born/`, para o João poder renomear e editar.
6. **Substituição de papéis:** se um personagem com papel importante morre (Chefe, Padre, Médium, Ferreiro...), alguém assume com o tempo (por eleição, sucessão ou vocação).
7. **Criaturas noturnas:** à noite cresce a chance de criaturas nos lugares perigosos. Crie um bestiário inicial em `data/events/creatures.yaml` (pode ser simples; o João vai redesenhar) e ligue os problemas reais do homelab (`homelab/servicos/#`) a criaturas na Sala do Servidor, que os Técnicos enfrentam.
8. **Clima real:** Open-Meteo para Botucatu, com cache. Chuva, frio e calor afetam necessidades e ações. Exceção: no funeral sempre chove.
9. **Telas offline:** ao receber `telas/<id>/status = offline`, os lugares daquela tela entram na névoa; quem estava lá fica preso, e ninguém consegue entrar.
10. **Diretor (storyteller):**
    - Mede a tensão do mundo (conflitos ativos, mortes recentes, tédio médio) e injeta eventos de `data/events/` para manter o ritmo: festa quando está calmo demais, trégua quando está caótico.
    - Respeita limites por hora e por dia.
    - Nunca escolhe o resultado de nada, só cria situações.
    - Eventos raros com cooldown longo (fantasma, ressurreição natural raríssima, aparição do personagem raro do João).
11. **Ferramenta de análise:** `python -m tools.report --days 7` simula N dias acelerados e gera um relatório de variedade: ações mais e menos usadas, falas repetidas, eventos por tipo, mortes e nascimentos, e alertas de repetição.
12. **Testes.**

## Critérios de aceite
- 30 dias simulados rodam sem erro, com nascimentos e mortes em quantidade plausível, sem extinguir nem lotar a cidade.
- O relatório de variedade não aponta nenhuma fala acima de um limite de repetição definido por você e justificado.
- O relatório da fase traz um funeral real contado a partir dos logs.

## Ao terminar
Escreva `docs/relatorios/FASE_3.md`, atualize `docs/arquitetura.md` e faça commit.
