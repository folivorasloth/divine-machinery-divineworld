# Fase 1 — Núcleo da simulação (headless)

Leia `CLAUDE.md`, `docs/bible.md`, `docs/arquitetura.md` e `docs/relatorios/FASE_0.md`.

## Objetivo
O mundo já vive sozinho, em texto. Os NPCs têm necessidades, escolhem ações por Utility AI, andam entre lugares, trabalham, comem, dormem e conversam. Tudo aparece no Chat do Mundo, no terminal.

## Tarefas
1. **Relógio e tick:** tempo do mundo seguindo o relógio real, com multiplicador (`--speed 60` = 1 hora por minuto). Dia e noite afetam necessidades e ações disponíveis.
2. **Necessidades:** variação contínua por taxa (fome sobe, sono sobe à noite...), modificadas pelos traços.
3. **Utility AI:**
   - Cada ação disponível no lugar e no horário recebe uma nota a partir de curvas configuráveis em YAML (necessidades, traços, hora, lugar, personagens presentes).
   - O NPC escolhe entre as melhores com aleatoriedade ponderada, para não ficar previsível.
   - Ações têm duração, custo e efeito.
   - **Log explicável:** cada decisão registra as 3 melhores opções e os motivos (nível debug).
4. **Ações básicas** (em `data/actions/`): andar até um lugar (com caminho pelo grafo), trabalhar (pela profissão), comer (na cozinha comunitária, sem dinheiro), dormir em casa, conversar, perambular (o comportamento do Mike), encarar a tela (raro, para o "olhar" da bible).
5. **Movimento entre lugares:** pelo grafo; ao atravessar uma conexão `tunnel`, gera evento de teletransporte com origem, destino e duração (será usado pelos LEDs e pelo visual).
6. **Conversa simples:** dois NPCs no mesmo lugar podem conversar; a fala sai de templates por situação, com variáveis (nome, lugar, hora, humor, clima). Falas usam os bordões de cada personagem.
7. **Chat do Mundo no terminal:** `python -m tools.run --speed 60` mostra o mundo vivendo, com cores por tipo de evento (`rich`). Opção de filtro por personagem ou lugar.
8. **Persistência:** estado e eventos em SQLite. Ao reiniciar, o mundo continua de onde parou.
9. **Testes:** necessidades, escolha de ação (com seed fixa), caminho no grafo, persistência.

## Critérios de aceite
- Rodar `--speed 600` por 5 minutos (um dia simulado inteiro) sem erros, com todos os NPCs cumprindo um dia plausível (acordam, trabalham, comem, socializam, dormem).
- O Mike perambula sem objetivo; o Padre toca o sino nos horários.
- O relatório traz um trecho real do Chat do Mundo de um dia simulado.

## Ao terminar
Escreva `docs/relatorios/FASE_1.md`, atualize `docs/arquitetura.md` e faça commit.
