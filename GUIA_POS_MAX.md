# Guia pós-Max: tocando o Mundo Vivo sozinho

> **A Fase 6 rodou:** os guias completos e testados estão em [`docs/guias/`](docs/guias/) (índice no
> `README.md`). O comando de recarregar existe: `python -m tools.cli recarregar`. Este arquivo fica como
> resumo.

Este guia é o seguro caso a Fase 6 não termine a tempo. Ele explica, sem depender do código exato, como fazer as coisas que você mais vai querer depois: renomear e criar personagens, desenhar os modelos 3D, montar o layout físico das telas e integrar com o mundo real. Os detalhes finais (nomes exatos de comandos e campos) estarão nos relatórios das fases e em `docs/guias/`, se a Fase 6 rodar.

## 1. Renomear e editar personagens

Tudo que é criativo mora em `data/`, em YAML.

1. Abra `data/characters/<id>.yaml` (ex.: `clown.yaml` para o Palhaço).
2. Mude o campo `nome`. **Nunca mude o `id`:** é ele que liga o personagem às relações, às memórias e ao save.
3. No mesmo arquivo dá pra mudar aparência, cor, traços, bordões, medos e segredo.
4. Rode a validação (`python -m tools.validate`) para conferir se não quebrou nada.
5. Aplique: com o comando de recarregar (Fase 6) ou reiniciando a simulação. O mundo continua de onde parou.

Personagens que nasceram sozinhos ficam em `data/characters/born/`. Renomeie do mesmo jeito.

## 2. Criar um personagem novo

1. Copie `data/characters/_MODELO.yaml` com um `id` novo e único, em snake_case (ex.: `gravedigger.yaml`).
2. Preencha os campos. Os mais importantes para o comportamento são **traços**, **necessidades iniciais**, **profissão**, **casa** e **local de trabalho**.
3. Coloque pelo menos duas ou três **relações** iniciais com personagens existentes, para ele entrar nas fofocas e nos conflitos.
4. Escreva falas próprias em `data/lines/` (veja a seção 3).
5. Valide e recarregue. Ele aparece com um modelo placeholder, até você fazer o 3D dele.

Dica de design: um personagem bom de simulação tem **uma vontade forte, um medo, um defeito que gera comédia e alguém que ele detesta.** É isso que faz ele agir sozinho, sem roteiro.

## 3. Falas e humor

- As falas são templates com variáveis, tipo `{nome}`, `{lugar}`, `{alvo}`, `{hora}` e `{clima}`. A lista exata de variáveis fica no relatório da Fase 1 ou 2.
- Escreva **várias versões** de cada situação: repetição é o que mais mata a sensação de mundo vivo.
- Se uma fala começar a cansar, o relatório de variedade (`tools.report`) mostra quais estão se repetindo demais.

## 4. Modelos 3D e design dos personagens (Blender, estilo PS1)

O visual da Fase 5 usa placeholders. Para trocar pelos seus:

1. **Modele em low-poly:** algo entre 300 e 1.500 triângulos por personagem é o suficiente pro estilo PS1/PS2. Silhueta forte vale mais que detalhe: o chapéu, o nariz e a postura devem ser reconhecíveis de longe numa tela pequena.
2. **Textura pequena:** 64×64 a 256×256 pixels, sem filtro (pixelada), ou só cor por face. Paleta vibrante; personagens de lugares sinistros com tons frios.
3. **Escala e orientação:** 1 unidade = 1 metro, personagem de frente para o eixo +Z, **origem nos pés**. Confira a convenção exata no guia da Fase 5, se ele existir.
4. **Animações com os nomes da convenção:** `idle`, `walk`, `talk`, `work`, `sleep`, `fall`, `fight`, `pray`, `dance` e `stare`. Pode começar com `idle` e `walk`; o resto usa o movimento procedural de reserva.
5. **Exporte em `.glb`** (glTF binário) e salve como `viewer/public/models/characters/<id>.glb`. O `<id>` é o mesmo do YAML. Recarregue a tela e ele aparece no lugar do placeholder.
6. **Cenários:** mesmo processo, em `viewer/public/models/places/<id>.glb`. A Catedral (réplica da de Botucatu) é a peça icônica: vale caprichar.

Para ganhar tempo: monte primeiro uma "família" de bonecos com o mesmo corpo base e mude só cabeça, chapéu e acessórios. É assim que jogos de PS1 faziam muitos NPCs com pouco trabalho.

## 5. Layout físico das telas e "um mundo mesmo"

O mundo é um só; cada tela é uma janela para alguns lugares dele.

1. **Planeje a parede:** desenhe num papel a parede do quarto, onde vai cada tela, e meça a posição em centímetros a partir de um canto.
2. **Distribua os lugares:** a cidade nas telas centrais e maiores; os biomas ao redor; os lugares sinistros (Sala do Servidor, cemitério) nas telas laterais ou mais escondidas; o Limbo, se quiser, numa tela pequena e isolada.
3. **Configure no `world.yaml`:** cada tela com um `id`, os lugares que ela mostra e a posição física.
4. **Abra a página de layout** (`viewer/layout.html`, da Fase 5) e confira se o mapa bate com a parede.
5. **Em cada tela,** abra o navegador em tela cheia em `viewer/?screen=<id>`. Celular velho, tablet, notebook ou TV box servem.
6. **Túneis de LED:** fita endereçável com WLED passando entre as telas. A simulação publica o teletransporte em `leds/tunnel`; um pequeno script ou automação traduz origem e destino em um pontinho correndo na fita, na duração certa. As posições em centímetros do `world.yaml` servem para calcular quais LEDs acender.

## 6. Integrações com o mundo real

Tudo passa pelo MQTT do homelab. Os tópicos estão no `CLAUDE.md`.

- **Câmera de presença** (`sala/camera/pessoas`): alimenta o "olhar" e a Aparição.
- **Status do homelab** (`homelab/servicos/#`): problemas reais viram trabalho para os Técnicos e criaturas na Sala do Servidor.
- **Telas** (`telas/<id>/status`): tela offline vira névoa no mundo.
- **Clima:** já vem da internet, sem configurar nada.
- **Ollama:** opcional, só para enriquecer falas. Coloque o endereço no `world.yaml`.

## 7. Rodando no homelab

Na VM Ubuntu com Docker, dentro da pasta do projeto, rode `docker compose up -d`. Para parar, `docker compose down`. O banco de dados (SQLite) fica num volume; faça backup dele de vez em quando, porque ele é a história inteira do seu mundo.

## 8. Continuando sem o plano Max

- O projeto foi pensado para você mexer em quase tudo **só editando YAML**.
- Para código, os relatórios das fases explicam o que cada parte faz e onde está. Leia o `docs/arquitetura.md` antes de mexer.
- Com um plano menor, o Claude Code ainda ajuda em tarefas pontuais. Mande sempre o contexto: *"Leia o CLAUDE.md e o docs/arquitetura.md, depois [tarefa]."*
- Faça uma coisa de cada vez e rode o mundo acelerado depois de cada mudança.
