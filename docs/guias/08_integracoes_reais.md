# Guia 08 — Integrações com o mundo real

> Tudo que é do mundo real é **opcional**: sem MQTT, sem internet e sem Ollama o mundo continua vivendo
> igual (testado na Fase 6: broker caindo e voltando, Ollama fora do ar, servidor morto com `kill -9` e
> religado). Endereços e senhas **nunca** vão para o repositório (ele é público): ficam no `.env`.

## 0. O `.env`

```bash
cp .env.example .env      # e edite (o .env não vai para o git)
```
| Variável | Para quê |
|---|---|
| `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD` | o Mosquitto do homelab |
| `OLLAMA_URL`, `OLLAMA_MODEL`, `DW_OLLAMA_ATIVO` | o LLM local (`false` = nem tenta) |
| `DW_DB_PATH`, `DW_SERVER_HOST`, `DW_SERVER_PORT` | banco e porta |
| `DW_WEATHER_CACHE`, `DW_BORN_DIR`, `DW_SEED`, `DW_API_URL` | cache do clima, pasta dos nascidos, seed, endereço para a CLI |

O `world.yaml` lê essas variáveis com `${NOME:-padrão}`. Mudou o `.env`? Reinicie (`docker compose up -d`);
o `recarregar` não reabre conexões.

## 1. MQTT (o Mosquitto do homelab)

Configuração em `world.yaml > mqtt` (`ativo`, `client_id`, `estado_a_cada_minutos`, `reconectar_segundos`,
`topicos`). Biblioteca: paho-mqtt 2.x. O mundo publica `world/status = online` (retido) ao conectar e
deixa um "testamento" `offline` para quando cair.

**Publica:**

| Tópico | Quando | Conteúdo |
|---|---|---|
| `world/events` | todo acontecimento com importância ≥ 1 | o evento com o texto pronto (`text_rendered`) |
| `world/state` (retido) | a cada minuto do mundo (mín. 2 s reais) | hora, período, clima, tensão, população, quem está onde, névoa |
| `world/chat` | toda fala | `{"from", "from_name", "text", "ts", "meta"}` |
| `leds/tunnel` | início e fim de cada teletransporte | para a fita de LED (guia 07, seção 5) |
| `world/status` (retido) | ao ligar/desligar | `online` / `offline` |
| `world/commands/result` | resposta de cada comando | `{"id", "cmd", "arg", "result", "ts"}` |

**Escuta:**

| Tópico | Payload | Vira |
|---|---|---|
| `world/commands` | `chefe reconstruam a ferraria` ou `{"cmd": "chefe", "arg": "..."}` | qualquer comando (guia 10) |
| `sala/camera/pessoas` | `{"count": 2}` (ou `pessoas`/`people`), um número, `true/false` | `presenca n` (seção 2) |
| `homelab/servicos/<nome>` | `{"status": "down"}` / `up` / `degraded`, ou o texto | `homelab <nome> down` (seção 3) |
| `telas/<id>/status` | `online` / `offline` (ou `on/off`, `1/0`, `{"status": ...}`) | névoa na tela (guia 07) |

Testar sem nada ligado: `mosquitto_sub -h <broker> -t 'world/#' -v` e
`mosquitto_pub -h <broker> -t world/commands -m status`.

**Se o broker cair:** um aviso no log ("MQTT fora do ar ... a simulação continua e tenta de novo") e o mundo
segue; ele reconecta sozinho (a cada até `reconectar_segundos`) e volta a publicar. `GET /health` mostra
`mqtt.conectado`.

## 2. Câmera de presença (`sala/camera/pessoas`)

Qualquer coisa que conte pessoas no quarto (Frigate, Home Assistant, um sensor de presença) publica o
número. Com gente no quarto (`criador.yaml > presenca`):
- encarar a tela fica `multiplicador_olhar` (3×) mais provável, e o **olhar coletivo** (vários param e
  encaram) `multiplicador_olhar_coletivo` (4×);
- a cada **entrada** (0 → 1+), `chance_aparicao` (3%) de a **Aparição** acontecer (no máximo uma a cada
  `limites.cooldown_aparicao_dias`);
- a presença "expira" depois de `presenca_expira_minutos` sem mensagem nova: publique de tempos em tempos.

Teste: `tools.cli presenca 1` e `tools.cli aparicao`.

## 3. Status do homelab (`homelab/servicos/#`)

Quando um serviço real cai (`homelab/servicos/jellyfin` = `down`), aparece uma criatura `homelab: true` na
Sala do Servidor (o Gremlin do Rack, em `data/events/creatures.yaml`) e quem tem as `chama_profissoes`
(os Técnicos) ganha o objetivo de ir enfrentá-la. Ela só some quando o serviço volta (`up`). Funciona com
Uptime Kuma, Home Assistant, um script com `curl`... qualquer coisa que publique no tópico.

Teste: `tools.cli homelab jellyfin down` e `tools.cli homelab jellyfin up`.

(Hoje os Técnicos também trabalham na Sala do Servidor como profissão normal; fazer o trabalho depender só
de problema real é uma pendência.)

## 4. Clima real (Open-Meteo)

`world.yaml > clima`: `modo: auto` usa o clima **real** de Botucatu (`latitude`/`longitude`) quando o mundo
está no relógio real, e clima sorteado no tempo acelerado. Sem chave, sem cadastro. A resposta fica em
cache (`DW_WEATHER_CACHE`, padrão `var/clima.json`); sem internet, usa o cache e depois `clima_padrao`.
Outros modos: `real` (sempre Open-Meteo), `simulado`, `fixo`. Para outra cidade, mude `cidade`,
`latitude` e `longitude`. Os `tipos` mapeiam os códigos do tempo (WMO) para os climas do mundo.
No funeral **sempre** chove (`clima_do_funeral`), seja qual for o clima de verdade.

## 5. Ollama (LLM local, opcional)

`world.yaml > ollama`: `ativo`, `url`, `modelo`, `timeout_segundos` (4), `max_por_hora` (30),
`max_caracteres`, `situacoes` (que falas o LLM pode reescrever: mortes, funerais, ordens, Aparição...) e
`interpretar_ordens` (tenta entender ordens do Chefe sem palavra conhecida).

- Só é usado com o mundo no **relógio real** (velocidade ≤ 10): nunca no `--fast` nem nos testes.
- Se não responder no `timeout_segundos`, passar do limite por hora, ou devolver algo estranho (nome que não
  existe, texto longo), sai o **template** de sempre. A cada `checar_a_cada_segundos` ele verifica se o
  Ollama voltou.
- `GET /health` e `tools.cli status` mostram `llm.no_ar`, pedidos na última hora, falhas.
- Desligar de vez: `DW_OLLAMA_ATIVO=false` no `.env`, ou `python -m server --sem-llm`.

## 6. Coisas que ainda não existem (precisam de código)

- **A luz real do quarto** (a pegadinha do Palhaço, bible: opcional): o caminho natural é o servidor publicar
  um tópico novo (ex.: `quarto/luz/pegadinha`) quando o Palhaço faz `pregar_peca`, e a sua automação
  trocar a cor. Precisa de umas linhas em `server/mqtt_bridge.py` e um tópico no `world.yaml`.
- **O instrumento real do Músico** (`ligacao_real: instrumento_real`) e **sons**: idem.
- **Um script pronto para o WLED**: a receita está no guia 07; falta ajustar com a fita de verdade.
- **O Grilo** e outros "anjos" de fora das telas: projetos separados; podem ouvir `world/events` e
  `world/chat` e falar com o mundo por `world/commands`.

Todas estão em "Pendências" no `docs/relatorios/FASE_6.md`.
