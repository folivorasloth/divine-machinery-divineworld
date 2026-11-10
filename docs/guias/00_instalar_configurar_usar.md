# Guia 00: instalar, configurar e usar

> Este guia é o caminho do zero até o mundo vivendo nas paredes, na ordem certa. Cada etapa
> aponta para o guia detalhado quando você quiser ir mais fundo.
>
> **Resumo:** o mundo é **um programa só**, que roda no homelab dentro do Docker. Cada tela da parede
> é só um **navegador em tela cheia** abrindo uma página desse programa. O MQTT e o Ollama são opcionais:
> sem eles, tudo funciona igual.

---

## Parte 1: instalar

### 1.1 O que você precisa

| Onde | O quê | Obrigatório? |
|---|---|---|
| Homelab (VM Ubuntu) | Docker com o plugin `docker compose`, e `git` | sim |
| Homelab | Mosquitto (o broker MQTT que você já tem) | não: só para integrar com o ecossistema |
| Notebook do LLM | Ollama com um modelo (ex.: `qwen2.5:7b`) | não: só enriquece as falas |
| Cada tela | qualquer aparelho com navegador (TV box, notebook ou celular velho, Raspberry Pi) | sim, uma por tela |
| Para testar no seu PC sem Docker | Python 3.11+ e Node.js 20+ | não |

### 1.2 Baixar e subir no homelab

```bash
git clone https://github.com/folivorasloth/divine-machinery-divineworld.git
cd divine-machinery-divineworld
cp .env.example .env
docker compose up -d --build
```

O primeiro build leva alguns minutos, porque também constrói o visual 3D. Depois disso:

```bash
docker compose ps                  # deve mostrar: dw-world ... Up (healthy)
docker compose logs -f world       # o Chat do Mundo passando no terminal (Ctrl+C só sai do log)
```

### 1.3 Conferir que está vivo

Abra no navegador de qualquer aparelho da rede (troque `<homelab>` pelo IP ou nome da VM):

| Endereço | O que é |
|---|---|
| `http://<homelab>:8000/health` | `"ok": true, "simulating": true`: o mundo está rodando |
| `http://<homelab>:8000/chat` | o **Chat do Mundo** ao vivo, com filtros e linha do tempo |
| `http://<homelab>:8000/viewer/` | a lista das telas, com um link para cada uma |
| `http://<homelab>:8000/viewer/layout.html` | o mapa da parede (telas e túneis) |
| `http://<homelab>:8000/docs` | a API documentada |

Se `/health` responder, a instalação acabou. O mundo já está vivendo no relógio real de Botucatu.

> **Dica:** a VM ficou sem acesso à internet no build? O `docker compose up --build` baixa a imagem
> base do Python e os pacotes do npm/pip. Ele precisa de internet **só na primeira vez** (e quando você
> atualizar o código).

---

## Parte 2: configurar

Tudo o que é configuração fica em dois lugares:
- **`.env`**: endereços e senhas do seu homelab. Ele **não vai para o git**, porque o repositório é público.
- **`data/world.yaml`**: o mundo em si (telas, ritmo, limites, clima...).

Depois de mudar o `.env`, rode `docker compose up -d` (recria o container). Depois de mudar qualquer
coisa em `data/`, rode `recarregar` (seção 3.3). Esse não precisa desligar nada.

### 2.1 O `.env` (endereços)

```bash
nano .env
```

| Variável | Para quê | Exemplo |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | onde está o Mosquitto | `192.168.0.10` / `1883` |
| `MQTT_USER` / `MQTT_PASSWORD` | se o broker tiver senha (o seu é anônimo: deixe vazio) | |
| `OLLAMA_URL` / `OLLAMA_MODEL` | o "Oráculo" | `http://192.168.0.20:11434` / `qwen2.5:7b` |
| `DW_OLLAMA_ATIVO` | `false` = nem tenta usar o Ollama (cala o aviso) | `true` |
| `DW_SERVER_PORT` | a porta no homelab | `8000` |
| `DW_SEED` | vazio = mundo imprevisível (o normal) | |

> **Atenção, Docker:** dentro do container, `localhost` é o **próprio container**, não o homelab.
> Se o Mosquitto roda na mesma VM, use o **IP da VM** em `MQTT_HOST`. Nomes `.local` (mDNS) às vezes
> não resolvem dentro do Docker; o IP sempre funciona.

Aplicar e conferir:
```bash
docker compose up -d
curl -s http://localhost:8000/health
#  "mqtt": {"conectado": true, ...}   e   "llm": {"no_ar": true, ...}  (se o Ollama estiver ligado)
```
`conectado: false` não quebra nada: o mundo segue e tenta de novo sozinho. Detalhes no **guia 08**.

### 2.2 As telas da parede (o mais importante)

O `world.yaml` vem com um **exemplo** de 4 telas. Ajuste ao seu quarto:

1. **Meça a parede.** O canto inferior esquerdo (no chão) é o ponto (0, 0); `x` cresce para a direita e
   `y` para cima, em **cm**. Para cada tela, anote o canto inferior esquerdo da **imagem** (não da
   moldura) e a largura × altura da imagem.
2. **Edite `data/world.yaml > telas`.** Cada tela é um bloco assim:

   ```yaml
   telas:
     - id: parede_centro              # vai na URL; minúsculas e _
       nome: TV grande do centro
       lugares: [town_square, cathedral, town_hall, market, tavern]   # cada lugar em UMA tela só
       posicao_cm: {x: 150, y: 120}
       tamanho_cm: {largura: 120, altura: 70}
       fps_max: 30
       qualidade: media                # baixa | media | alta
   ```
   - A cidade vai nas telas grandes do centro; os biomas, ao redor; os lugares sinistros (Cemitério,
     Sala do Servidor), nas telas laterais ou escondidas.
   - Aparelho fraco: `qualidade: baixa` e `fps_max: 20`.
   - Lugares vizinhos em telas diferentes precisam estar ligados por **túnel** (`tipo: tunel` em
     `data/places/<id>.yaml`). O validador avisa quando não estão.
3. **Valide e aplique** (seção 3.3):
   ```bash
   docker compose exec world python -m tools.validate
   docker compose exec world python -m tools.cli recarregar
   ```
4. **Confira** em `http://<homelab>:8000/viewer/layout.html` se o mapa bate com a parede.

Passo a passo completo, túneis e fita de LED: **guia 07**.

### 2.3 Ligar cada tela

Em cada aparelho, abra em **tela cheia**:
```
http://<homelab>:8000/viewer/?screen=<id da tela>
```
- **PC/notebook:** F11. Para abrir sozinho ao ligar, use o Chromium em modo quiosque:
  `chromium --kiosk "http://<homelab>:8000/viewer/?screen=parede_centro"` (coloque na inicialização).
- **Celular/tablet:** no menu do navegador, use "Adicionar à tela inicial" e abra pelo ícone (fica sem barra).
- **TV box:** qualquer navegador em tela cheia, ou um app de "kiosk browser".

Ajustes rápidos pela URL, sem editar nada: `&qualidade=baixa`, `&fps=15`, `&nomes=0` (esconde os
nomes), `&relogio=0` (esconde o relógio), `&foco=tavern` (enquadra um lugar só).

A tela que cair ou for desligada **reconecta sozinha** quando voltar. Para o mundo saber que ela
desligou (e os lugares dela entrarem na névoa), publique `telas/<id>/status = offline` pelo MQTT ou
pela automação da sua tomada inteligente (guias 07 e 08).

### 2.4 Integrações reais (opcional, quando quiser)

Tudo pelo MQTT, com os tópicos já prontos (detalhes no **guia 08**):

| Do mundo real | Publique em | O que acontece no mundo |
|---|---|---|
| Câmera de presença | `sala/camera/pessoas` → `{"count": 1}` | mais gente encara a tela; ao entrar alguém, chance rara da **Aparição** |
| Serviço do homelab caiu | `homelab/servicos/jellyfin` → `{"status": "down"}` | uma criatura surge na Sala do Servidor e os Técnicos vão enfrentar |
| Tela ligou/desligou | `telas/<id>/status` → `online`/`offline` | os lugares daquela tela saem/entram na névoa |
| Comando seu | `world/commands` → `chefe façam uma festa` | igual à CLI (Parte 3) |

O mundo publica `world/events`, `world/chat`, `world/state` (retido) e `leds/tunnel`. Esse último serve
para a fita de LED: a receita da automação WLED está no **guia 07, seção 5**.

Teste rápido, de qualquer máquina com o cliente do Mosquitto:
```bash
mosquitto_sub -h <broker> -t 'world/#' -v
```
```bash
mosquitto_pub -h <broker> -t world/commands -m status
```

### 2.5 Backup automático (faça no primeiro dia)

O arquivo `var/world.sqlite` **é** o mundo: memórias, relações, mortos, a história inteira. No
crontab do homelab (`crontab -e`):
```
17 4 * * * cd /caminho/do/divine-machinery-divineworld && docker compose exec -T world python -m tools.backup --manter 14
```
Os backups vão para `var/backups/`. Copie essa pasta para outro disco de vez em quando. Para
restaurar, veja o **guia 09, seção 4**.

---

## Parte 3: usar

### 3.1 Só olhar

O mundo vive sozinho: ninguém precisa fazer nada. Para acompanhar:
- **Nas telas:** o mundo em 3D, com balões de fala, dia e noite, chuva e o teletransporte entre telas.
- **No Chat do Mundo** (`/chat`): tudo o que acontece, com filtros por personagem, lugar, tipo e período,
  e a linha do tempo dos grandes acontecimentos. Para deixar numa tela dedicada:
  `/chat?fonte=28&tema=escuro` (ou `&personagem=clown` para seguir alguém).
- **No terminal:** `docker compose logs -f world`.

### 3.2 Intervir (você é o Criador)

Os comandos rodam pela CLI dentro do container (ou pela API, ou pelo MQTT; todos dão o mesmo resultado).
Para não digitar tudo sempre, crie um atalho no homelab:
```bash
alias mundo='docker compose -f /caminho/do/divine-machinery-divineworld/docker-compose.yml exec world python -m tools.cli'
```

| Quero... | Comando |
|---|---|
| ver como está o mundo | `mundo status` |
| a ficha viva de alguém (humor, memórias, de quem gosta) | `mundo quem clown` |
| as últimas falas | `mundo chat --limite 30` · `mundo chat --personagem priest` |
| dar uma ordem à cidade (pelo Chefe) | `mundo chefe "reconstruam a ferraria"` · `"façam uma festa"` · `"proibido andar de skate"` |
| sussurrar para a Médium (ela pode entender errado) | `mundo medium "a lua quer velas na floresta"` |
| reviver um morto (evento lendário) | `mundo reviver blacksmith` |
| fazer nascer alguém | `mundo nascer` · `mundo nascer alegre curioso` |
| pausar / continuar | `mundo pausar` · `mundo continuar` |
| acelerar para assistir | `mundo velocidade 60` (1 hora do mundo por minuto) · `mundo velocidade 1` volta ao normal |
| forçar clima / Aparição / um raio | `mundo clima tempestade 60` · `mundo aparicao` · `mundo raio forge` |

A cidade **não obedece por mágica**: o Chefe anuncia na Praça, cada um aceita, atrasa ou resiste pela
personalidade, e quem aceita vai fazer o trabalho do jeito dele. Acompanhe com `mundo status`. Todos os
comandos estão no **guia 10**.

### 3.3 Mudar o mundo sem programar

Tudo o que é criativo está em `data/`, em YAML. O fluxo é sempre o mesmo:

```bash
nano data/characters/clown.yaml                                # 1. edite
docker compose exec world python -m tools.validate             # 2. confira ("Tudo certo!")
docker compose exec world python -m tools.cli recarregar       # 3. aplique, sem desligar nada
```
Se houver erro no YAML, o `recarregar` **não muda nada**, avisa o que está errado (com sugestão) e o
mundo segue com a versão anterior.

| Quero... | Onde | Guia |
|---|---|---|
| renomear alguém, mudar aparência, traços, bordões | `data/characters/<id>.yaml` (mude o `nome:`, **nunca** o `id:`) | 01 |
| renomear um nascido | `data/characters/born/<id>.yaml` | 01 |
| criar um personagem novo | copie `data/characters/_MODELO.yaml` | 02 |
| escrever falas novas (o que mais dá vida) | `data/lines/*.yaml` | 03 |
| criar uma ação ou um evento novo | `data/actions/`, `data/events/` | 04 |
| mudar o ritmo (mortes, nascimentos, prisões, criaturas...) | `data/world.yaml` | 05 |
| trocar o boneco placeholder pelo seu modelo 3D | solte `viewer/public/models/characters/<id>.glb` e dê F5 na tela | 06 |
| mexer nas telas | `data/world.yaml > telas` | 07 |

Faça commit no git das suas mudanças em `data/`. Assim fica o histórico do que você mudou.

### 3.4 Manter

| Situação | O que fazer |
|---|---|
| parar / ligar | `docker compose stop` / `docker compose start` (salva e continua de onde parou) |
| falta de luz / reinício do homelab | nada: o container religa sozinho e o mundo recupera até 2 h do tempo perdido |
| atualizar o código | backup, depois `git pull` e `docker compose up -d --build` |
| algo estranho | `curl localhost:8000/health` e `docker compose logs --tail 100 world`; tabela de problemas no **guia 09, seção 6** |
| começar um mundo do zero | `docker compose stop`, **mova** (não apague) `var/world.sqlite*` para outra pasta, `docker compose start` |

---

## Parte 4: testar no seu PC (sem Docker, opcional)

Bom para experimentar mudanças antes de levar ao homelab, num mundo separado:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
(cd viewer && npm ci && npm run build)
.venv/bin/python -m server --novo --banco var/teste.sqlite --nascidos var/nascidos/teste \
    --speed 300 --seed 21 --sem-mqtt --sem-llm
```
Abra `http://localhost:8000/viewer/?screen=parede_centro` e `http://localhost:8000/chat`. Os comandos
funcionam igual, com `.venv/bin/python -m tools.cli <comando>`.
`--novo` **apaga** o banco indicado: nunca use com o banco de verdade.

Outras ferramentas úteis:
```bash
.venv/bin/python -m tools.run --fast --dias 7 --novo --banco var/x.sqlite --nascidos var/nascidos/x --resumo
.venv/bin/python -m tools.report --days 14 --seed 42
```
O primeiro simula uma semana em poucos minutos, só em texto, com a tabela de resumo no fim. O segundo é
o relatório de variedade: falas repetidas e alertas de balanceamento.

---

## Mapa dos guias

| Guia | Assunto |
|---|---|
| [01](01_renomear_e_editar_personagens.md) | renomear e editar personagens |
| [02](02_criar_personagem_novo.md) | criar personagem novo |
| [03](03_falas_e_humor.md) | falas e humor |
| [04](04_acoes_e_eventos.md) | ações e eventos |
| [05](05_balanceamento.md) | balanceamento (os números do `world.yaml`) |
| [06](06_modelos_3d_e_design.md) | modelos 3D no Blender |
| [07](07_telas_e_layout_fisico.md) | telas, layout físico e fita de LED |
| [08](08_integracoes_reais.md) | MQTT, câmera, homelab, clima, Ollama |
| [09](09_rodar_e_manter.md) | rodar, backup, logs, problemas |
| [10](10_comandos_do_criador.md) | todos os comandos do Criador |
