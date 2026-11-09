# Divine Machinery — o Mundo Vivo

Um mundo 3D low-poly que vive nas paredes do quarto, distribuído por várias telas. Os NPCs vivem
sozinhos: trabalham, constroem, destroem, festejam, brigam, morrem e lembram. Nada é roteirizado.

- Fonte criativa: [`docs/bible.md`](docs/bible.md)
- Arquitetura (plano de todas as fases): [`docs/arquitetura.md`](docs/arquitetura.md)
- Relatórios de cada fase: [`docs/relatorios/`](docs/relatorios/)
- Regras do projeto para o Claude Code: [`CLAUDE.md`](CLAUDE.md)

## Estado atual

Fase 0 (preparação): estrutura, esquemas de dados, a bible convertida em YAML (`data/`) e o
validador. Ainda não há simulação rodando.

## Primeiros passos

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m tools.validate     # confere todos os YAML de data/
.venv/bin/python -m pytest             # roda os testes
```

## Onde mexer sem programar

Tudo em `data/`:

| Arquivo | O que muda |
|---|---|
| `data/characters/<id>.yaml` | nome, aparência, traços, rotina, bordões, relações de cada personagem |
| `data/characters/_MODELO.yaml` | modelo comentado para criar personagem novo |
| `data/places/<id>.yaml` | lugares, conexões, paleta, perigo, ações possíveis |
| `data/actions/*.yaml` | ações (verbos) e como cada uma é pontuada |
| `data/lines/*.yaml` | falas (templates) |
| `data/events/*.yaml` | eventos do diretor |
| `data/traits.yaml` | traços, profissões e o sorteio dos nascimentos |
| `data/world.yaml` | relógio, limites, telas, MQTT, Ollama, clima |

Depois de editar, rode `python -m tools.validate`.

Endereços (MQTT, Ollama) e senhas não ficam no repositório (ele é público): copie `.env.example`
para `.env` e ajuste. O `world.yaml` lê essas variáveis.
