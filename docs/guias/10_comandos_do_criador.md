# Guia 10 — Comandos do Criador

> Todos os comandos que existem, com exemplos. Eles chegam ao mundo por três caminhos, que dão o
> mesmo resultado (passam pela mesma fila e respondem `{"ok": true|false, ...}`):
>
> | Caminho | Exemplo |
> |---|---|
> | Terminal (CLI) | `.venv/bin/python -m tools.cli chefe "reconstruam a ferraria"` |
> | API HTTP | `curl -X POST http://<servidor>:8000/api/commands -H 'content-type: application/json' -d '{"cmd": "chefe", "arg": "reconstruam a ferraria"}'` |
> | MQTT | publicar em `world/commands` o texto `chefe reconstruam a ferraria` ou `{"cmd": "chefe", "arg": "..."}`; a resposta sai em `world/commands/result` |
>
> No Docker, a CLI roda dentro do container: `docker compose exec world python -m tools.cli status`.
> Fora do servidor, aponte com `--url http://<homelab>:8000` (ou a variável `DW_API_URL`).
> `--json` mostra a resposta crua. A documentação interativa da API fica em `http://<servidor>:8000/docs`.

## 1. Falar com o mundo (o "Criador")

Os personagens **não sabem** que você existe. Você fala por dois canais, e os dois podem entender
errado, atrasar ou resistir — de propósito.

### `chefe "<ordem>"` — ordens cívicas pelo Chefe
O Chefe recebe a ordem como uma "intuição", vai à Praça anunciar (se estiver de madrugada ou com muito
sono, adia) e cada morador **aceita, atrasa ou resiste** pela personalidade e pela afinidade com ele.
Nada acontece por mágica: a cidade cumpre (ou não) do jeito dela.

```bash
tools.cli chefe "reconstruam a ferraria"     # vira mutirão de conserto na Ferraria
tools.cli chefe "façam uma festa"            # o Chefe organiza a festa na Taverna
tools.cli chefe "proibido andar de skate"    # decreto por 3 dias: o Fiscal multa; o rebelde faz MAIS
tools.cli chefe "liberem o skate"            # o contrário
tools.cli chefe "reunião na praça"           # assembleia
tools.cli chefe "parem de brigar"            # paz (brigar fica menos atraente)
tools.cli chefe "todo mundo trabalhando"     # trabalho
tools.cli chefe "missa para todos"           # missa
```
- O que cada palavra vira está em `data/events/criador.yaml > chefe.interpretacoes` (dá para criar
  interpretações novas só no YAML). Ordem sem palavra conhecida: o Ollama tenta entender, se estiver no
  ar; senão o Chefe faz "como dá".
- Acompanhe com `tools.cli status` (linha "ordem #n ... aceitam X, atrasam Y, resistem Z").
- Sem Chefe vivo, a ordem espera até alguém assumir o papel.

### `medium "<mensagem>"` — a voz que a Médium ouve
```bash
tools.cli medium "a lua quer uma festa"
tools.cli medium "rezem pelo ferreiro"
```
A Médium ouve como VOZ (se estiver dormindo, em sonho), conta a visão e às vezes **entende tudo errado**
(`medium.chance_erro`, com `desastres` e `palavras_trocadas` em `criador.yaml`): "a lua pede **sapos** na
floresta".

### `reviver <id>` — o poder lendário
```bash
tools.cli reviver blacksmith
```
O morto volta mudado (mais estranho, com medo, esquecendo coisas), o Padre chama de milagre, a Médium
diz que foi ela, e a cidade comenta por dias. Vivo ou id inexistente: `ok: false`.

### `nascer [traços]`
```bash
tools.cli nascer                    # traços sorteados
tools.cli nascer alegre curioso     # com estes traços (ids de data/traits.yaml)
```
Nasce um personagem novo agora (arquivo em `data/characters/born/`). Renomeie pelo guia 01.

## 2. Consultar

| Comando | O que mostra |
|---|---|
| `tools.cli status` | hora, clima, tensão, população, mortos, névoa, criaturas, ordens e reações, decretos, assuntos do momento, presença, LLM |
| `tools.cli quem <id>` | a ficha viva: necessidades, humor, onde está e o que faz, traços, facção, memórias mais fortes, de quem gosta e não gosta, objetivos, a última decisão explicada |
| `tools.cli chat [--personagem id] [--lugar id] [--tipo categoria] [--limite 20]` | as últimas linhas do Chat do Mundo |

O Chat do Mundo também está em `http://<servidor>:8000/chat` (com filtros e linha do tempo; para uma
tela fixa: `/chat?personagem=clown&fonte=28&tema=escuro`).

## 3. Controlar o tempo e os dados

| Comando | Exemplo | Efeito |
|---|---|---|
| `pausar` / `continuar` | `tools.cli pausar` | o mundo para (as telas continuam abertas) |
| `velocidade <n>` | `tools.cli velocidade 60` | 1 = tempo real; 60 = uma hora do mundo por minuto |
| `recarregar` | `tools.cli recarregar` | aplica as mudanças de `data/` (nomes, falas, pesos, telas...) **sem perder o estado**; com erro no YAML não muda nada e avisa (guia 01) |

## 4. O mundo real (normalmente vêm sozinhos pelo MQTT)

| Comando | Exemplo | Vem do MQTT | Efeito |
|---|---|---|---|
| `presenca <n>` | `tools.cli presenca 1` | `sala/camera/pessoas` | gente no quarto: mais gente encara a tela; na entrada (0 → 1+), chance da Aparição |
| `homelab <serviço> <down\|up>` | `tools.cli homelab jellyfin down` | `homelab/servicos/<serviço>` | problema real: criatura na Sala do Servidor e trabalho para os Técnicos |
| `tela <id> <online\|offline>` | `tools.cli tela monitor_direita offline` | `telas/<id>/status` | os lugares da tela entram (ou saem) da névoa |

## 5. Testes e diversão

| Comando | Exemplo | Efeito |
|---|---|---|
| `clima <tipo> [minutos]` | `tools.cli clima tempestade 60` | força um clima (tipos em `world.yaml > clima.tipos`: limpo, nublado, neblina, garoa, chuva, tempestade) |
| `aparicao` | `tools.cli aparicao` | força a Aparição agora (a silhueta na tela, todos encaram) |
| `raio <lugar>` | `tools.cli raio forge` | um raio destrói as estruturas do lugar — bom para ver a cidade reconstruir |

## 6. Respostas e histórico

- Cada comando responde `ok: ...` ou `não: ...` no terminal (código de saída 0 ou 1, bom para scripts).
- `GET /api/commands` lista os últimos 50 comandos com o resultado; `GET /api/commands/<id>` um só.
- Os comandos aparecem no Chat do Mundo com a tag `criador`/`sistema`.
- Comando desconhecido: a resposta lista todos os que existem.
