# Guia 07 — Telas e layout físico da parede

> O mundo é um só; cada tela é uma **janela** para alguns lugares dele. Este guia mostra como
> adicionar uma tela, escolher os lugares dela, medir a posição na parede, ligar os túneis de LED
> (WLED) e conferir tudo na página de layout. Tudo é configurado em `data/world.yaml > telas`.

## 1. Como as telas funcionam

- O servidor (`python -m server`, ou o Docker) roda a simulação. Cada tela física é só um **navegador
  em tela cheia** abrindo `http://<servidor>:8000/viewer/?screen=<id da tela>`. Serve qualquer coisa
  com navegador: TV box, notebook velho, celular, tablet, Raspberry Pi.
- `http://<servidor>:8000/viewer/` (sem `?screen=`) lista as telas configuradas, com um link para cada.
- Cada lugar aparece em **no máximo uma** tela. Lugares fora de todas as telas continuam existindo
  (o mundo vive mesmo sem ninguém olhando) — hoje o Limbo e o Mundo de Fora estão assim.
- Personagens que vão de um lugar de uma tela para um lugar de outra tela passam por um **túnel de
  teletransporte**: somem no portal roxo de uma tela, uma luz corre pela parede (a fita de LED) e eles
  saem do portal da outra tela quando a luz chega.
- Se uma tela **desliga**, os lugares dela entram na **névoa**: ninguém entra nem sai até ela voltar
  (seção 6).

## 2. Medir a parede

1. Escolha um canto de referência: o **canto inferior esquerdo** da parede (no chão) é o ponto (0, 0).
2. `x` cresce para a **direita**, `y` cresce para **cima**, tudo em **centímetros**.
3. Para cada tela, meça a posição do **canto inferior esquerdo da área de imagem** (não da moldura) e o
   tamanho da imagem (largura × altura).
4. Anote num papel: id que você vai dar, posição e tamanho. Exemplo do `world.yaml` que vem no projeto:

| id | o que é | posição (x, y) | tamanho (l × a) |
|---|---|---|---|
| `parede_centro` | TV grande do centro | 150, 120 | 120 × 70 |
| `monitor_esquerda` | monitor da esquerda | 40, 140 | 55 × 32 |
| `monitor_direita` | monitor da direita | 320, 140 | 55 × 32 |
| `tela_homelab` | tela transparente perto do homelab | 420, 60 | 30 × 20 |

A posição serve para duas coisas: desenhar o mapa (`/viewer/layout.html`) e calcular **quanto tempo a
luz do LED leva** de uma tela à outra (distância entre os **centros** das telas ÷ velocidade da luz).

## 3. Adicionar uma tela

Abra `data/world.yaml`, procure `telas:` e acrescente um bloco (copie um existente):

```yaml
telas:
  # ... as que já existem ...
  - id: tablet_porta              # id fixo: minúsculas, números e _ (é o que vai na URL)
    nome: Tablet perto da porta   # nome livre (aparece no layout e na lista)
    lugares: [cemetery, prison]   # ids de data/places/ — e TIRE esses lugares da tela onde estavam
    posicao_cm: {x: 10, y: 100}   # canto inferior esquerdo da imagem, em cm
    tamanho_cm: {largura: 22, altura: 14}
    fps_max: 20                   # limite de quadros por segundo (aparelho fraco: 15–20)
    qualidade: baixa              # baixa | media | alta (world.yaml > visual.qualidades)
```

Regras (o `tools.validate` confere todas e explica o erro):
- `id` único; cada lugar em **uma** tela só (se você colocar o Cemitério na tela nova, tire-o da
  `parede_centro`); os lugares têm que existir (`data/places/<id>.yaml`).
- A **ordem** em `lugares` é a ordem dos dioramas na grade da tela (da esquerda para a direita, de cima
  para baixo). A grade se ajusta sozinha ao formato da tela.
- Lugares de **telas diferentes** que são vizinhos devem estar ligados por **túnel**, não por caminho a
  pé (aviso: "caminho a pé ... atravessa telas"). Veja a seção 4.
- Lugares numa tela pequena: 2 ou 3. A TV do centro aguenta 11, mas cada um fica pequeno.

Depois:
```bash
.venv/bin/python -m tools.validate          # "Tudo certo!"
.venv/bin/python -m tools.cli recarregar    # aplica sem desligar o mundo
```
O `recarregar` aplica telas novas, lugares trocados de tela, posições e qualidade: as telas abertas
redesenham sozinhas (a do centro perde o Cemitério, por exemplo). Agora, no aparelho novo, abra
`http://<servidor>:8000/viewer/?screen=tablet_porta` em tela cheia (F11 no navegador; no celular,
"adicionar à tela inicial" deixa sem barra).

> Dicas da bible: a cidade nas telas centrais e maiores; os biomas ao redor; os lugares sinistros
> (Sala do Servidor, Cemitério) nas telas laterais ou mais escondidas; o Limbo, se quiser, numa tela
> pequena e isolada (hoje ele não está em nenhuma).

## 4. Os túneis (no mundo)

As conexões ficam em cada lugar, `data/places/<id>.yaml > conexoes`:

```yaml
conexoes:
  - {para: town_hall, tipo: tunel, minutos: 5}     # teletransporte (LED entre telas)
  - {para: underground, tipo: caminho, minutos: 15} # a pé, dentro da mesma tela
```

- `tipo: tunel` = teletransporte; `minutos` = quanto tempo do **mundo** a viagem leva (para a
  simulação). A luz do LED na parede tem a duração dela (seção 5); a tela de destino só mostra o
  personagem saindo do portal quando as duas coisas terminaram.
- Basta declarar de um lado (o grafo é de mão dupla). Cada túnel vira um **portal roxo** no diorama, com
  o nome do destino.
- Todo lugar normal precisa ter caminho até a Praça (`lugar_central`); o validador avisa lugar isolado.

## 5. A fita de LED (WLED)

A simulação **não** fala com o WLED direto: ela publica no MQTT e você liga isso no WLED do jeito que
preferir (Node-RED, Home Assistant, um script). Isso deixa o mundo funcionando mesmo com a fita
desligada.

**O que é publicado** no tópico `leds/tunnel` (nome em `world.yaml > mqtt.topicos.tunel_leds`), duas
mensagens por viagem:

```json
{"phase": "start", "char": "tech_apprentice", "from_screen": "tela_homelab", "to_screen": "parede_centro",
 "from_cm": {"x": 435.0, "y": 70.0}, "to_cm": {"x": 210.0, "y": 155.0}, "duration_ms": 4010, "color": "#219ebc"}
{"phase": "end", "char": "tech_apprentice", ...}
```

- `from_cm`/`to_cm` são os **centros** das telas; `duration_ms` = distância ÷
  `tunel.velocidade_led_cm_por_s` (no mínimo `tunel.duracao_minima_s`); `color` é o `visual.cor` do
  personagem (cada um corre na parede com a sua cor).
- A tela de destino espera esse tempo antes de mostrar o personagem saindo. Então **ajuste a
  velocidade para bater com a sua fita**: se a fita faz curva e é mais comprida que a linha reta entre
  as telas, diminua `velocidade_led_cm_por_s` (ou meça e use `comprimento da fita ÷ tempo desejado`).

**Receita para o WLED** (qualquer automação que assine `leds/tunnel`):
1. Monte uma tabela com, para cada par de telas, o **primeiro e o último LED** do trecho de fita entre
   elas (ex.: `tela_homelab → parede_centro = LEDs 0 a 140`). Se a fita é uma só, trechos de pares
   diferentes podem se sobrepor.
2. Ao receber `phase: start`, anime um "pontinho" do primeiro ao último LED em `duration_ms`
   milissegundos, na cor `color`. No sentido inverso (`to_screen → from_screen`), do último ao primeiro.
   Com a API JSON do WLED, cada passo é um `POST http://<wled>/json/state` com
   `{"seg": [{"id": 0, "i": [<led>, "<cor sem #>"]}]}` (apagando o LED anterior); ou use um efeito
   pronto de "corrida" do WLED com a velocidade calculada a partir de `duration_ms`.
3. `phase: end` pode apagar o trecho (é quando o personagem saiu do túnel na simulação).
4. Endereço do WLED e do MQTT ficam na sua automação, nunca no repositório (ele é público).

Para ver as mensagens sem fita nenhuma: `mosquitto_sub -h <broker> -t leds/tunnel -v`.
(Um script pronto de WLED não faz parte do projeto ainda: é uma pendência registrada no relatório da
Fase 6, porque precisa da fita de verdade para ajustar.)

## 6. Tela desligada = névoa

- A simulação não "vê" se o navegador fechou; quem avisa é o **MQTT** `telas/<id>/status` com
  `online` ou `offline` (também aceita `on/off`, `1/0` ou `{"status": "offline"}`). Ex.: uma automação do
  Home Assistant que publica `offline` quando a TV desliga.
- À mão: `.venv/bin/python -m tools.cli tela tablet_porta offline` (e `online` para voltar).
- Na névoa: os lugares da tela ficam cobertos de nuvens nas telas, ninguém entra nem sai a pé ou por
  túnel, e quem estava dentro fica preso até a tela voltar (quem tem imunidade `nevoa` atravessa).
- Se o **navegador** cair (Wi-Fi, servidor reiniciando), a página tenta reconectar sozinha e redesenha
  tudo quando volta; o mundo não para por causa disso.

## 7. A página de layout

`http://<servidor>:8000/viewer/layout.html` desenha a parede vista de frente:
- cada tela no lugar e no tamanho medidos, com o nome e os lugares dela;
- uma linha para cada túnel entre telas, com a **distância em cm** e a **duração da luz** em segundos;
- ao vivo: cada teletransporte acende a linha correspondente; telas na névoa ficam cinzas;
- embaixo, um cartão por tela (posição, qualidade, FPS, link para abrir) e os lugares fora de qualquer
  tela.

Use para conferir se o desenho bate com a parede **antes** de furar alguma coisa. Ela também
redesenha sozinha depois de um `recarregar`.

## 8. Qualidade e desempenho por tela

- `fps_max` e `qualidade` em cada tela; os níveis ficam em `world.yaml > visual.qualidades`
  (`altura_render`, `gotas_de_chuva`, `tremer_vertices`, `luzes_extras`, `detalhe`).
- Para testar sem editar nada, na URL: `?qualidade=baixa`, `?fps=15`, `?altura=180`, `?nomes=0`,
  `?relogio=0`, `?foco=<lugar>` (enquadra um lugar só).
- Celular ou notebook velho: `qualidade: baixa` e `fps_max: 20`. Tela transparente: fundo escuro funciona
  melhor (a imagem preta fica "invisível").

## 9. Checklist de uma tela nova

- [ ] Bloco novo em `world.yaml > telas` com `id`, `nome`, `lugares`, `posicao_cm`, `tamanho_cm`.
- [ ] Os lugares saíram da tela antiga; vizinhos em telas diferentes ligados por `tipo: tunel`.
- [ ] `tools.validate` sem erro; `tools.cli recarregar`.
- [ ] `/viewer/layout.html` bate com a parede.
- [ ] O aparelho abre `/viewer/?screen=<id>` em tela cheia (e liga sozinho nessa página, se der).
- [ ] (Opcional) automação publicando `telas/<id>/status` e o trecho de LED na receita do WLED.
