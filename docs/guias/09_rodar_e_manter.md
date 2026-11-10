# Guia 09 — Rodar e manter

> O mundo é **um processo só** (`python -m server`): a simulação + a API + o WebSocket das telas + a
> ponte MQTT. Ele salva sozinho no SQLite e, ao religar, continua de onde parou. No homelab ele roda no
> Docker. Este guia cobre subir, parar, atualizar, backup, logs e o que fazer quando algo quebra.

## 1. No homelab (Docker) — o jeito normal

Na VM Ubuntu com Docker, dentro da pasta do projeto:

```bash
cp .env.example .env              # uma vez: MQTT_HOST, OLLAMA_URL... (guia 08)
docker compose up -d --build      # sobe (o build também constrói o visual 3D)
docker compose ps                 # "dw-world ... Up (healthy)"
```
Depois, de qualquer aparelho da rede:
- `http://<homelab>:8000/chat` — o Chat do Mundo (com filtros e linha do tempo);
- `http://<homelab>:8000/viewer/` — as telas 3D (`?screen=<id>`) e `/viewer/layout.html` — o mapa da parede;
- `http://<homelab>:8000/health` — está vivo? (`simulating: true`, MQTT, LLM);
- `http://<homelab>:8000/docs` — a API.

O que fica fora do container (volumes, sobrevivem a rebuild):
- `./data` — os YAML (edite e rode `recarregar`);
- `./var` — o banco `world.sqlite` (a história inteira do mundo), o cache do clima, a cópia válida de
  `data/` (`var/data_valido/`) e os backups (`var/backups/`);
- `./viewer/public/models` — os seus `.glb`.

| Quero... | Comando |
|---|---|
| parar | `docker compose stop` (salva o mundo; `stop_grace_period: 20s` dá tempo) |
| ligar de novo | `docker compose start` (continua de onde parou) |
| reiniciar | `docker compose restart world` |
| ver o Chat/log ao vivo | `docker compose logs -f world` (`--tail 200` para as últimas linhas) |
| mandar um comando | `docker compose exec world python -m tools.cli status` (guia 10) |
| aplicar mudanças de `data/` | `docker compose exec world python -m tools.cli recarregar` |
| validar os YAML | `docker compose exec world python -m tools.validate` |
| desligar tudo | `docker compose down` (não apaga `data/` nem `var/`) |

**Reinício do homelab / falta de luz:** `restart: unless-stopped` religa o container sozinho. O mundo volta
do último salvamento (a cada `persistencia.salvar_a_cada_minutos` = 5 minutos do mundo; testado na Fase 6
com `kill -9`: perdeu 3 minutos do mundo) e, no relógio real, **recupera** até
`relogio.max_recuperacao_horas` (2 h) do tempo perdido simulando rápido; o resto é pulado com um aviso no
Chat. Se os YAML estiverem com erro nessa hora, ele liga com a última versão válida (guia 01, seção 1).

## 2. No computador (sem Docker, para testar)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # uma vez
(cd viewer && npm ci && npm run build)                        # uma vez (e depois de mudar viewer/src)
.venv/bin/python -m server                                     # tempo real, MQTT e Ollama do .env
.venv/bin/python -m server --speed 60 --sem-mqtt --sem-llm     # 1 hora do mundo por minuto, sem nada externo
```
Ctrl+C salva e sai. Mundo de teste separado (sem tocar no seu mundo de verdade):
```bash
.venv/bin/python -m server --novo --banco var/teste.sqlite --nascidos var/nascidos/teste --speed 300 --seed 21 --sem-mqtt --sem-llm
```
`--novo` **apaga** o banco indicado: nunca use com o banco de verdade. Só a simulação no terminal, sem
servidor: `python -m tools.run --speed 60` (ou `--fast --dias 1 --novo --banco var/x.sqlite --resumo`).

## 3. Atualizar o código

```bash
docker compose exec world python -m tools.backup     # antes de tudo: backup (seção 4)
git pull
docker compose up -d --build                         # reconstrói e religa; o mundo continua
docker compose logs --tail 50 world                  # "O mundo acorda de onde parou."
```
Sem Docker: `git pull`, `.venv/bin/pip install -e ".[dev]"`, `(cd viewer && npm ci && npm run build)` e
religue. Telas abertas reconectam sozinhas.

## 4. Backup do SQLite

O `var/world.sqlite` **é** o mundo (memórias, relações, mortos, a história do Chat). Faça backup:

```bash
docker compose exec world python -m tools.backup                  # -> var/backups/world-<data>.sqlite
.venv/bin/python -m tools.backup --destino /mnt/nas/divine --manter 30
```
É seguro com o mundo rodando (usa a cópia online do SQLite) e mantém os `--manter` mais novos (10).
Automático, no crontab do homelab (todo dia às 4h17):
```
17 4 * * * cd /caminho/do/projeto && docker compose exec -T world python -m tools.backup --manter 14
```
Copie a pasta `var/backups/` para outro disco/NAS de vez em quando. **Restaurar:** `docker compose stop`,
copie o backup por cima de `var/world.sqlite`, apague `var/world.sqlite-wal` e `var/world.sqlite-shm`,
`docker compose start`.

Os YAML (`data/`) ficam no git: faça commit das suas mudanças (personagens, falas, nascidos que você
renomeou) para ter histórico.

## 5. Logs

- `docker compose logs -f world`: o Chat do Mundo (cada linha com hora e lugar) + avisos do sistema
  (`WARNING sim.llm: Ollama fora do ar...`, `WARNING server.mqtt: MQTT fora do ar...`).
- `world.yaml > nivel_log` (`info`; `debug` mostra cada decisão explicada — muito volume).
- O Chat do Mundo inteiro fica no banco: `/chat` na web, `tools.cli chat`, `GET /api/chat?...`.

## 6. Quando algo quebra

| Sintoma | O que fazer |
|---|---|
| `/health` não responde | `docker compose ps` e `docker compose logs --tail 100 world`. Container reiniciando em laço = erro ao ligar: o log mostra a causa. |
| `"error": "..."` no `/health`, `simulating: false` | a simulação parou com erro (o servidor continua de pé). Copie o erro do log, `docker compose restart world`. Se repetir, restaure o último backup e anote o erro para corrigir no código. |
| "ATENÇÃO: os arquivos de data/ estão com erro" no Chat | algum YAML quebrou; o mundo está com a última versão válida. `tools.validate`, corrija, `recarregar`. |
| `recarregar` diz "NÃO recarregou" | idem: a lista mostra arquivo e problema. Nada mudou no mundo. |
| Erro de YAML e nunca houve versão válida (primeira vez) | o servidor não liga e mostra os erros; `python -m tools.validate` aponta tudo. |
| Tela 3D preta/parada | F5 na tela; o relógio do canto deve andar. `/viewer/` diz "não construído"? `npm run build` (ou rebuild do Docker). |
| Tela na névoa sem motivo | alguém publicou `telas/<id>/status = offline`; `tools.cli tela <id> online`. |
| MQTT não conecta | `/health` → `mqtt.conectado: false`; confira `MQTT_HOST/PORT/USER/PASSWORD` no `.env` e reinicie. O mundo segue sem ele. |
| Ollama "fora do ar" | normal se ele estiver desligado: falas por template. Confira `OLLAMA_URL`; `DW_OLLAMA_ATIVO=false` cala o aviso. |
| Mundo "estranho" depois de mexer em números | `tools.report --days 14 --seed 42` antes e depois (guia 05); volte o número pelo git (`git diff data/`). |
| Banco corrompido (raro: disco cheio, desligamento no meio) | pare, restaure o último backup (seção 4). |
| Quero começar um mundo do zero | `docker compose stop`, mova `var/world.sqlite*` para outra pasta (não apague: é história), `docker compose start`. |

## 7. Testes (para quem mexer no código)

```bash
.venv/bin/python -m tools.validate
.venv/bin/python -m pytest -q -o addopts=""     # ~200 testes, ~4 min
(cd viewer && npm test && npm run build)
.venv/bin/python -m tools.report --days 14 --seed 42
```
Peça ao Claude Code (ou faça você): *"Leia o CLAUDE.md e o docs/arquitetura.md, depois [tarefa]."*
