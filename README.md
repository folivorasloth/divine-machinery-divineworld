# Divine Machinery — o Mundo Vivo

Um mundo 3D low-poly que vive nas paredes do quarto, distribuído por várias telas. Os NPCs vivem
sozinhos: trabalham, constroem, destroem, festejam, brigam, morrem e lembram. Nada é roteirizado.

- Fonte criativa: [`docs/bible.md`](docs/bible.md)
- Arquitetura (plano de todas as fases): [`docs/arquitetura.md`](docs/arquitetura.md)
- Relatórios de cada fase: [`docs/relatorios/`](docs/relatorios/)
- Regras do projeto para o Claude Code: [`CLAUDE.md`](CLAUDE.md)

## Estado atual

Fase 1 (núcleo): o mundo já vive sozinho, em texto. Os NPCs têm necessidades, escolhem ações por
Utility AI, andam pelo grafo de lugares (com túneis), trabalham, comem, dormem e conversam; o
Padre toca o sino; tudo aparece no Chat do Mundo no terminal e fica salvo em SQLite.

Fase 2 (sociedade): afinidades vivas, memórias (que aparecem nas falas), fofoca com distorção,
discussões, brigas de pastelão, pazes, pegadinhas e tombos, construções que quebram e são
consertadas, o Fiscal com advertências, prisão e Limbo, Igreja × Seita, o Ganancioso roubando
(e a cidade acusando, às vezes a pessoa errada) e festas, raves, rodeios, procissões, casamentos
e mutirões organizados pelos próprios NPCs. `--resumo` mostra tudo que aconteceu.

Fase 3 (vida, morte e diretor): mortes permanentes com causas configuráveis, funeral com chuva,
cortejo, reações por personalidade e lápide; luto, herança, fantasmas e ressurreição rara;
nascimentos sorteados (viram YAML em `data/characters/born/`), sucessão de papéis (eleição do
Chefe), criaturas noturnas e do homelab, clima de Botucatu (Open-Meteo, com cache), névoa nas
telas desligadas e um Diretor que mede a tensão e injeta eventos. `tools.report` mede a variedade.

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
| `data/traits.yaml` | traços, profissões e o sorteio dos nascimentos |
| `data/world.yaml` | relógio, limites, telas, MQTT, Ollama, clima; memórias, fofoca, leis, facções, roubos |

Depois de editar, rode `python -m tools.validate`.

Endereços (MQTT, Ollama) e senhas não ficam no repositório (ele é público): copie `.env.example`
para `.env` e ajuste. O `world.yaml` lê essas variáveis.
