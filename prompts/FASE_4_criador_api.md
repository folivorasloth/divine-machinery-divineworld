# Fase 4 — O Criador, a API e a integração

Leia `CLAUDE.md`, `docs/bible.md`, `docs/arquitetura.md` e os relatórios anteriores.

## Objetivo
O João consegue intervir no mundo, o mundo conversa com o ecossistema por MQTT, e existe uma API pronta para as telas. O Chat do Mundo ganha uma página web com filtros.

## Tarefas
1. **Comandos do Criador** (pela CLI, pela API HTTP e pelo tópico `world/commands`):
   - `chefe "<ordem>"`: vira um objetivo cívico que o Chefe repassa à cidade. Ordens comuns (reconstruir, festa, mudar regra, convocar reunião) são reconhecidas por palavras-chave; o resto, ele interpreta como dá. A cidade pode atrasar ou resistir, pela personalidade dos envolvidos.
   - `medium "<mensagem>"`: chega à Médium como uma "voz". Ela interpreta (às vezes errado, de propósito, com chance configurável) e age ou convence a seita.
   - `reviver <id>`: o poder do Criador. Evento lendário: o morto volta mudado (traço novo, memórias faltando ou medo de morrer), o Padre chama de milagre, a Médium reivindica, a cidade comenta por dias.
   - `nascer [traços opcionais]`, `pausar`, `continuar`, `velocidade <n>`, `status`, `quem <id>` (ficha viva: necessidades, humor, memórias, relações).
2. **LLM opcional para falas:** se o Ollama estiver disponível (endereço no `world.yaml`), falas importantes (eventos sociais, funerais, comandos do Criador) podem ser geradas com contexto real (quem, onde, humor, memórias, bordões). Timeout curto, limite por hora, e fallback automático para templates. Interpretação de ordens livres do Criador também pode usar o LLM, com fallback para palavras-chave.
3. **O olhar e a Aparição:**
   - "Encarar a tela" já existe como ação rara.
   - Ao receber `sala/camera/pessoas` com presença, aumenta um pouco a chance de alguém encarar.
   - Com uma chance bem baixa (cooldown longo), dispara a **Aparição**: os NPCs veem uma silhueta borrada, a seita enlouquece, o Padre fala em milagre, o Esquisito anota tudo. Isso entra na memória coletiva.
4. **Servidor (`server/`):** FastAPI com:
   - REST: estado, personagens, lugares, histórico do chat com filtros (personagem, lugar, tipo, período), comandos.
   - WebSocket `/ws?screen=<id>`: envia ao viewer o estado inicial dos lugares daquela tela e depois um fluxo de eventos (movimento, ação, fala, clima, hora, névoa, teletransporte).
   - Ponte MQTT conforme `CLAUDE.md`.
5. **Chat do Mundo web:** uma página simples (pode ficar em `viewer/chat.html`) com o fluxo ao vivo, filtros por personagem, lugar, tipo e período, e uma linha do tempo dos grandes acontecimentos. Pensada para ficar aberta numa tela dedicada.
6. **Docker:** `docker-compose.yml` com simulação e servidor, prontos para rodar no homelab (VM Ubuntu com Docker), volume para o SQLite e para `data/`.
7. **Testes** dos comandos, da API e da ponte MQTT (com broker de teste ou mock).

## Critérios de aceite
- Com `docker compose up`, o mundo vive, a API responde e o Chat do Mundo web mostra eventos ao vivo.
- `chefe "reconstruam a ferraria"` leva a cidade a reconstruir de fato, pelo comportamento dos NPCs, e não por mágica.
- `reviver` funciona e gera reações coerentes.
- Sem Ollama e sem MQTT, tudo continua funcionando.

## Ao terminar
Escreva `docs/relatorios/FASE_4.md`, atualize `docs/arquitetura.md` e faça commit.
