# CLAUDE.md — Divine Machinery: o Mundo Vivo

Este arquivo é lido em toda sessão. Ele define o projeto, a arquitetura, as convenções e a forma de trabalhar. A fonte criativa (personagens, lugares, regras do mundo) é `docs/bible.md`: leia antes de qualquer fase.

## O projeto

Um mundo 3D low-poly que vive nas paredes do quarto do João Pedro, distribuído por várias telas (monitores, TVs, telas transparentes). Os NPCs vivem de forma **100% autônoma**: trabalham, constroem, destroem, festejam, brigam, morrem e lembram. O João (o "Criador") pode intervir, mas o mundo **nunca é roteirizado**: as histórias emergem de regras, necessidades, relações, memória e de um diretor que controla o ritmo.

Faz parte de um ecossistema maior (Divine Machinery) que já usa um broker **MQTT (Mosquitto)** no homelab e tem outros personagens fora das telas, como o Grilo Falante.

## Princípios inegociáveis

1. **Emergência, não roteiro.** Nunca escreva sequências fixas de história. Escreva necessidades, ações pequenas, regras e eventos que se combinam.
2. **Dados fora do código.** Personagens, lugares, ações, eventos, falas e balanceamento ficam em arquivos YAML em `data/`. O João precisa conseguir mudar nomes, traços e falas **sem programar**.
3. **`id` estável, `nome` editável.** Todo personagem e lugar tem um `id` fixo em inglês ou snake_case (ex.: `clown`, `chef_wife`), usado pelo código, e um `nome` de exibição editável. Renomear nunca pode quebrar save, memória ou relação.
4. **A simulação é a fonte da verdade; as telas só desenham.** A simulação roda sozinha no homelab (headless). As telas são clientes que recebem estado e eventos e renderizam. Se nenhuma tela estiver ligada, o mundo continua vivendo.
5. **Funciona sem LLM.** O LLM local (Ollama, nem sempre disponível) é opcional, só pra enriquecer falas. Tudo funciona com templates.
6. **Testável e observável.** Toda decisão de um NPC pode ser explicada nos logs ("escolheu `brigar` porque raiva=82 e afinidade com Palhaço=-60"). Existe um modo de tempo acelerado para simular dias em minutos.
7. **Simples e legível.** O João é desenvolvedor e vai manter isso sozinho depois. Prefira código claro, comentado nas partes não óbvias, a abstrações espertas.

## Arquitetura

```
divine-world/
  CLAUDE.md
  docs/
    bible.md                # fonte criativa
    arquitetura.md          # escrita/atualizada por você ao longo das fases
    guias/                  # guias para o João (fase 6)
    relatorios/             # um relatório por fase (obrigatório)
  data/                     # tudo editável pelo João
    world.yaml              # config geral, ritmo, tempo, clima, limites
    places/*.yaml           # lugares, conexões, paleta, perigos
    characters/*.yaml       # um arquivo por personagem (id, nome, traços, rotina...)
    actions/*.yaml          # biblioteca de ações (verbos) e pesos
    events/*.yaml           # eventos do diretor e eventos raros
    lines/*.yaml            # templates de falas por situação e por personagem
    traits.yaml             # traços para nascimentos aleatórios
  sim/                      # simulação (Python, headless)
  server/                   # API HTTP + WebSocket + ponte MQTT
  viewer/                   # visual 3D low-poly (Three.js), uma página por tela
  tools/                    # CLI, relatórios, análise de repetição
  tests/
  docker-compose.yml        # roda tudo no homelab
```

### Stack
- **Simulação e servidor:** Python 3.11+, `pydantic`, `pyyaml`, `fastapi` + `uvicorn` (HTTP e WebSocket), `paho-mqtt` 2.x (atenção à `CallbackAPIVersion`), `httpx`, `sqlite3` (persistência), `rich` (terminal), `pytest`.
- **Visual:** Three.js com Vite, JavaScript puro ou TypeScript simples. Cada tela abre `viewer/?screen=<id>` e desenha os lugares atribuídos a ela.
- **Clima real:** Open-Meteo (grátis, sem chave), para Botucatu-SP (lat -22.886, lon -48.445), com cache e fallback se estiver sem internet.
- **LLM opcional:** Ollama na rede local, endereço no config, timeout curto e fallback para templates.

### Modelo da simulação (camadas)
1. **Relógio:** o tempo do mundo segue o relógio real (dia e noite reais), com multiplicador para testes.
2. **Necessidades e humor por NPC:** valores de 0 a 100 (fome, sono, social, fé, raiva, tédio, medo...) que variam com o tempo e com eventos.
3. **Utility AI:** a cada decisão, o NPC dá nota para cada ação disponível com base nas necessidades, nos traços, nas relações, no lugar, na hora e nos objetivos ativos, e escolhe uma das melhores (com aleatoriedade controlada).
4. **Ações:** verbos pequenos e combináveis definidos em YAML (andar, conversar, trabalhar, comer, dormir, construir, quebrar, rezar, ritual, festejar, roubar, consolar, brigar, fofocar, viajar, encarar a tela...).
5. **Relações e memória:** afinidade entre pares, e uma memória por NPC com eventos marcantes (que decaem, mas os grandes ficam).
6. **Diretor (storyteller):** mede a tensão do mundo e injeta eventos para manter o ritmo, sem decidir a história.
7. **Falas:** templates com variáveis; LLM opcional por cima.
8. **Chat do Mundo:** todo acontecimento vira um registro com tags (personagem, lugar, tipo), persistido e consultável.

### Integração com o ecossistema (MQTT)
- Publica em `world/events` (eventos), `world/state` (resumo periódico, retido), `world/chat` (falas), `leds/tunnel` (início e fim de teletransporte entre telas, para o WLED).
- Escuta em `world/commands` (comandos do Criador), `sala/camera/pessoas` (presença no quarto, para a Aparição e o "olhar"), `homelab/servicos/#` (problemas reais viram trabalho dos Técnicos e criaturas na Sala do Servidor) e `telas/<id>/status` (tela offline = lugar na névoa).
- Tópicos e endereços ficam no `world.yaml`. Se o MQTT estiver fora, a simulação continua e registra o aviso.

## Convenções
- Código e identificadores em inglês; textos do mundo, falas, YAML de conteúdo e documentação em **português brasileiro**.
- Nada de IP, senha ou caminho fixo no código: tudo em config ou variável de ambiente.
- Testes com `pytest`. Seed aleatória configurável para reproduzir situações.
- Commits pequenos e descritivos ao fim de cada etapa relevante.

## Forma de trabalhar (obrigatória)
1. No início de cada fase, leia este arquivo, `docs/bible.md`, `docs/arquitetura.md` e os relatórios anteriores em `docs/relatorios/`.
2. Apresente um plano curto da fase e siga em frente. O João tem pouco tempo; não espere aprovação, a não ser que algo seja realmente ambíguo e caro de desfazer.
3. Implemente, teste e rode a simulação para conferir o comportamento de verdade, não só os testes unitários.
4. **Ao final de cada fase, escreva `docs/relatorios/FASE_<n>.md`** seguindo `docs/relatorios/TEMPLATE.md`, atualize `docs/arquitetura.md` e faça commit.
5. Se algo da fase ficar de fora, registre no relatório em "Pendências", com o motivo. Nunca diga que algo funciona sem ter rodado.
