# Divine Machinery — o Mundo Vivo

Um mundo 3D low-poly que vive nas paredes do quarto, distribuído por várias telas. Os NPCs vivem
sozinhos: trabalham, constroem, destroem, festejam, brigam, morrem e lembram. Nada é roteirizado.

- Fonte criativa: [`docs/bible.md`](docs/bible.md)
- Arquitetura (plano de todas as fases): [`docs/arquitetura.md`](docs/arquitetura.md)
- Relatórios de cada fase: [`docs/relatorios/`](docs/relatorios/)
- Regras do projeto para o Claude Code: [`CLAUDE.md`](CLAUDE.md)

## Guias (para o João, passo a passo)

| Guia | Para quando você quer... |
|---|---|
| [01 — Renomear e editar personagens](docs/guias/01_renomear_e_editar_personagens.md) | mudar nome, aparência, traços, bordões e falas (e renomear nascidos), sem desligar o mundo |
| [02 — Criar personagem novo](docs/guias/02_criar_personagem_novo.md) | um morador novo a partir do `_MODELO.yaml`, com relações e ligação com o mundo real |
| [03 — Falas e humor](docs/guias/03_falas_e_humor.md) | escrever templates, variáveis, filtros, e não deixar o mundo repetitivo |
| [04 — Ações e eventos](docs/guias/04_acoes_e_eventos.md) | criar uma ação, um evento do diretor, um evento social ou uma criatura só com YAML (e quando precisa de código) |
| [05 — Balanceamento](docs/guias/05_balanceamento.md) | os números do `world.yaml` e o que cada um muda; como medir com `tools.report` |
| [06 — Modelos 3D e design](docs/guias/06_modelos_3d_e_design.md) | fazer personagens e cenários no Blender (estilo PS1) e trocar os placeholders |
| [07 — Telas e layout físico](docs/guias/07_telas_e_layout_fisico.md) | adicionar uma tela, medir a parede, túneis de LED (WLED), página de layout |
| [08 — Integrações reais](docs/guias/08_integracoes_reais.md) | MQTT do homelab, câmera de presença, status do homelab, clima, Ollama |
| [09 — Rodar e manter](docs/guias/09_rodar_e_manter.md) | subir, parar, atualizar, backup, logs e o que fazer quando algo quebra |
| [10 — Comandos do Criador](docs/guias/10_comandos_do_criador.md) | todos os comandos, com exemplos |

## O que existe (fases 0 a 6)

- **O mundo vive sozinho** (F1–F3): 21 moradores da bible com necessidades, traços, rotina e Utility AI;
  andam pelo grafo de 20 lugares (com túneis de teletransporte entre telas), trabalham, comem, dormem,
  conversam, fofocam, discutem, brigam, fazem as pazes, roubam, vão presos ou para o Limbo, rezam, fazem
  rituais, festejam e organizam festas, raves, rodeios, procissões, casamentos e mutirões. Morrem (de
  verdade), têm funeral com chuva, luto, herança, fantasmas; nascem moradores novos; papéis vagos são
  assumidos (eleição do Chefe). Criaturas à noite, clima real de Botucatu e um Diretor que controla o
  ritmo. Tudo explicável no log e salvo em SQLite; nada roteirizado.
- **O Criador** (F4): `chefe "..."`, `medium "..."`, `reviver`, `nascer`, a presença no quarto e a Aparição;
  API HTTP, WebSocket, ponte MQTT, Chat do Mundo na web (`/chat`), Docker. Ollama opcional.
- **O visual** (F5): cada tela abre `/viewer/?screen=<id>` e mostra, em 3D low-poly estilo PS1, os
  lugares dela ao vivo; `.glb` próprios trocam os placeholders sem código; `/viewer/layout.html` é o mapa
  da parede.
- **Polimento** (F6): `recarregar` aplica mudanças de `data/` sem reiniciar e sem perder o estado (YAML
  com erro mantém a última versão válida, também ao religar); `tools.report` mede a saúde do mundo
  (prisões, eventos, mortes, necessidades, lugares); balanceamento de 60 dias; `tools.backup`; os guias.

Relatórios de cada fase, com o que foi testado e o que ficou pendente: [`docs/relatorios/`](docs/relatorios/)
(o resumo geral e os próximos passos estão em [`FASE_6.md`](docs/relatorios/FASE_6.md)).

## Primeiros passos

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m tools.validate     # confere todos os YAML de data/
.venv/bin/python -m pytest             # roda os testes

# o mundo vivendo no terminal (Ctrl+C salva e sai; ao religar, continua de onde parou)
.venv/bin/python -m tools.run --speed 60                       # 1 hora do mundo por minuto
.venv/bin/python -m tools.run --fast --dias 1 --novo --resumo  # um dia inteiro em segundos
.venv/bin/python -m tools.run --help                           # filtros e outras opções
.venv/bin/python -m tools.report --days 7                      # relatório de variedade (pasta temporária)
```
O mundo com a API e o Chat do Mundo na web (Fase 4):

```bash
.venv/bin/python -m server                     # tempo real; abra http://localhost:8000/chat
.venv/bin/python -m server --speed 60 --sem-mqtt --sem-llm
.venv/bin/python -m tools.cli chefe "reconstruam a ferraria"    # noutro terminal
.venv/bin/python -m tools.cli status
.venv/bin/python -m tools.cli quem clown
.venv/bin/python -m tools.cli recarregar                        # aplica mudanças de data/ sem reiniciar
.venv/bin/python -m tools.backup                                # backup do mundo (seguro com ele rodando)

# as telas 3D (Fase 5): uma vez, constrói o viewer (Node 18+); o servidor serve em /viewer
(cd viewer && npm ci && npm run build)
#   http://localhost:8000/viewer/?screen=parede_centro   (lista das telas em /viewer/)
#   desenvolvimento do viewer, com o servidor rodando: (cd viewer && npm run dev) -> http://localhost:5173/viewer/

# no homelab (o Docker já constrói o viewer)
cp .env.example .env && docker compose up -d --build           # http://<homelab>:8000/chat
docker compose exec world python -m tools.cli status
```

Simulações de teste (`--fast` ou `--banco`) gravam os nascidos em `var/nascidos/<banco>/`, não em
`data/characters/born/` (ou use `--nascidos PASTA`, ou a variável `DW_BORN_DIR`).

## Onde mexer sem programar

Tudo em `data/`:

| Arquivo | O que muda |
|---|---|
| `data/characters/<id>.yaml` | nome, aparência, traços, rotina, bordões, relações de cada personagem |
| `data/characters/_MODELO.yaml` | modelo comentado para criar personagem novo |
| `data/places/<id>.yaml` | lugares, conexões, paleta, perigo, ações possíveis |
| `data/actions/*.yaml` | ações (verbos) e como cada uma é pontuada |
| `data/lines/*.yaml` | falas (templates) |
| `data/events/*.yaml` | eventos do diretor e eventos sociais organizados pelos NPCs (`sociais.yaml`) |
| `data/events/criador.yaml` | o que as ordens do Chefe e as vozes da Médium viram, quem obedece, o olhar e a Aparição |
| `data/traits.yaml` | traços, profissões e o sorteio dos nascimentos |
| `data/world.yaml` | relógio, limites, telas, MQTT, Ollama, clima; memórias, fofoca, leis, facções, roubos |

Depois de editar, rode `python -m tools.validate` e, com o servidor ligado, `python -m tools.cli recarregar`
(guia 01).

Endereços (MQTT, Ollama) e senhas não ficam no repositório (ele é público): copie `.env.example`
para `.env` e ajuste. O `world.yaml` lê essas variáveis.
