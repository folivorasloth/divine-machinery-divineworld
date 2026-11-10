# Guia 04 — Ações e eventos novos (só com YAML)

> O mundo é feito de **verbos pequenos** (ações), **eventos** que o diretor injeta para dar ritmo,
> **eventos sociais** que os próprios NPCs organizam e **criaturas**. Quase tudo isso se cria copiando um
> bloco de YAML. Depois de mexer: `tools.validate`, `tools.cli recarregar` (vale na hora) e, para ver o
> efeito, `tools.report --days 7`.

## 1. Como uma ação é escolhida (o mínimo para entender os números)

A cada decisão, cada personagem dá uma **nota** para cada ação possível ali e escolhe uma das melhores
(com um pouco de sorte):

```
nota = peso × (fator de cada consideração) × traços × rotina × objetivos × viagem × repetição
```
- **peso**: a vontade base (0.05 = rara, 1 = comum).
- **considerações**: cada uma lê uma **entrada** (a fome, a hora, a afinidade com o alvo...) e passa por
  uma **curva** que devolve um fator de 0 a 1.
- **traços** (`data/traits.yaml > tracos.<id>.efeitos.acoes`) multiplicam: o `briguento` tem `brigar: 2`.
- **rotina** (bloco da ficha naquele horário) e **objetivos** (convites, ordens do Chefe, diretor) multiplicam.
- **viagem**: lugar longe vale menos (`world.yaml > decisao.meia_vida_viagem_minutos`).
- **repetição**: acabou de fazer, vale menos (`decisao.penalidade_repeticao`).

Para ver as notas de verdade: `tools.run --fast --horas 3 --novo --debug --personagem clown` mostra cada
decisão com o top 3 e os motivos; com o servidor, `tools.cli quem clown` mostra a última decisão explicada.

## 2. Criar uma ação nova

Exemplo: **contar causo** (alguém junta gente e conta uma história). Em `data/actions/sociais.yaml` (ou
num arquivo novo `data/actions/<tema>.yaml` com `acoes:` no topo):

```yaml
  - id: contar_causo
    nome: Contar causo
    descricao: Junta quem estiver por perto e conta uma história que ninguém pediu.
    tipo: individual             # individual | social (com alvo)
    peso: 0.4
    duracao_minutos: [15, 40]    # sorteia entre os dois
    condicoes:
      periodos: [tarde, noite]
    consideracoes:
      - entrada: necessidade.social
        curva: {tipo: pontos, pontos: [[0, 0.1], [50, 0.5], [90, 1]]}
      - entrada: presentes        # quantas pessoas no lugar
        curva: {tipo: pontos, pontos: [[0, 0], [2, 0.5], [6, 1]]}
    efeitos:
      necessidades: {social: -30, tedio: -20}
    narracao: "{eu} junta gente em {lugar} e começa: \"Isso foi no tempo que...\""
    fala: contar_causo           # situação de falas (crie em data/lines/)
    chance_fala: 0.6
    cooldown_minutos: 180
    tags: [conversa]
```

Depois, **três passos que fazem a ação existir no mundo**:
1. **Onde dá para fazer:** acrescente `contar_causo` em `acoes:` dos lugares (`data/places/tavern.yaml`,
   `town_square.yaml`...) — ou `em_qualquer_lugar: true` na ação.
2. **Quem gosta mais:** em `data/traits.yaml`, no traço `contador_de_causo`, `efeitos.acoes:
   {contar_causo: 2.5}`. Ou um bloco de rotina na ficha de alguém.
3. **Falas:** em `data/lines/social.yaml`, uma situação `contar_causo:` com várias falas (guia 03).

Campos mais usados (a explicação completa está no topo de `data/actions/basicas.yaml` e `sociais.yaml`):

| Campo | Para quê |
|---|---|
| `condicoes.periodos`, `horarios`, `lugar_proprio` (`casa`/`trabalho`), `profissoes`, `personagens`, `alvo` | quando/quem/onde pode |
| `consideracoes[].entrada` | `necessidade.<id>`, `alvo_necessidade.<id>`, `afinidade`, `hora`, `presentes`, `perigo`, `tensao`, `dano`, `memoria.<tipo>`, `faccao.<id>`, `presenca.<id>`... |
| `curva` | `pontos` (a mais fácil: liga os pontos), `linear`, `potencia`, `logistica`, `degrau`; `inverter`, `minimo` |
| `efeitos.necessidades` / `alvo_necessidades` | variação total ao longo da ação (negativo satisfaz) |
| `efeitos.afinidade`, `afinidade_do_alvo`, `por_traco`, `dano_estrutura` | relação, efeito por traço, estragar algo |
| `fala`, `chance_fala`, `fala_alvo`, `chance_fala_alvo`, `narracao`, `narracao_fim` | texto |
| `memoria`, `infracao`, `falha`, `reconcilia`, `ir_atras`, `chance_perseguicao` | sociedade (Fase 2) |
| `dormindo: true`, `vagar: true`, `cooldown_minutos`, `importancia`, `tags` | detalhes |
| `ativa: false` | a ação existe mas o mundo não usa |

E o visual: diga que animação ela usa em `world.yaml > visual.animacao_por_acao` (ex.: `contar_causo:
talk`). Sem isso, o boneco fica em `idle`.

## 3. Criar um evento do diretor

O diretor mede a tensão (brigas, medo, raiva...) e injeta **situações** para puxar o ritmo — nunca decide o
resultado. Copie um bloco em `data/events/diretor.yaml`:

```yaml
  - id: quermesse
    nome: quermesse improvisada
    tipo: social                 # ritmo | social | clima | criatura | raro | lendario
    tensao: acalma               # acalma | agita | neutro
    peso: 0.8
    cooldown_horas: 48
    lugares: [town_square]
    condicoes:
      periodos: [tarde]
    efeitos:
      necessidades: {tedio: -10}
      objetivo: {acao: festejar, lugar: town_square, bonus: 3, duracao_horas: 3, para: todos}
    texto: "Alguém pendura bandeirinhas na {lugar}. Ninguém sabe quem. Cheiro de pipoca às {hora}."
    importancia: 1
```
- Se um evento sair demais (o `tools.report` mostra "Diretor: eventos injetados"), aumente o
  `cooldown_horas` ou baixe o `peso`. Ele avisa quando um evento passa de 30% de tudo que o diretor fez.
- `world.yaml > diretor` controla quando ele age (alvo de tensão por período, margem, chance) e
  `limites.max_eventos_diretor_por_hora/dia`.

## 4. Criar um evento social (organizado pelos NPCs)

Em `data/events/sociais.yaml` (o topo explica cada campo). Ninguém manda acontecer: de hora em hora,
quem bate com `organizadores` e tem a `vontade` tem `chance_por_hora` de ter a ideia, marca hora e lugar e
convida quem mais gosta. Exemplo, a **noite do causo**:

```yaml
  - id: noite_do_causo
    nome: noite do causo
    acao: contar_causo
    lugar: tavern
    organizadores:
      tracos: [contador_de_causo]
    vontade: {social: 50}
    chance_por_hora: 0.05
    comeca_entre: {das: "19:30", ate: "21:30"}
    antecedencia_horas: [1, 3]
    duracao_horas: [1, 2]
    convite_afinidade_min: 20
    max_convidados: 8
    quorum: 4
    bonus: 8
    cooldown_horas: 48
    memoria: festa
    memoria_fracasso: festa_fracassada
    importancia: 2
    textos:
      planejado: ["{eu} avisa: {evento} hoje às {hora} em {lugar}. Chama {convidados}."]
      comeca: ["Começa a {evento} de {eu}. Ouvindo: {convidados}."]
      fracassa: ["{eu} contou o causo inteiro para as cadeiras vazias de {lugar}."]
      termina: ["Fim da {evento}. {convidados} saem jurando que é tudo verdade."]
```
**Lições do balanceamento da Fase 6** (`docs/relatorios/FASE_6.md`): um evento fracassa quando o
`bonus` não vence o que os convidados fariam naquela hora (trabalho de tarde, cama de madrugada), quando a
`antecedencia_horas` é grande (eles esquecem) ou quando a janela `comeca_entre` cai num horário em que a
cidade dorme — ou quando a `acao` não vale para quem vai (a procissão usava `missa`, que só vale onde o Padre está e não vale para o próprio Padre: ele nunca ia, e ninguém ia sem ele). Confira a taxa de sucesso na tabela "Eventos sociais" do `tools.report`.

## 5. Criar uma criatura

`data/events/creatures.yaml` (o topo explica): nome, lugares, `quando` (noite, chuva...), chance, perigo,
medo que causa, quanto tempo fica, textos de aparecer/sumir/vencida; `homelab: true` = só aparece
quando um serviço real cai (guia 08); `chama_profissoes` = quem ganha o objetivo de enfrentar. O viewer
desenha uma criatura genérica com olhos acesos (modelo próprio: ainda não suportado; pendência).

## 6. Necessidades, traços, infrações, memórias

Também só YAML:
- **Necessidade nova:** `world.yaml > necessidades` (modo `acumula` ou `retorna`, taxas, `humor`); depois
  use em considerações (`necessidade.<id>`) e efeitos. Personagens existentes recebem o valor inicial.
- **Traço novo:** `data/traits.yaml > tracos` (`efeitos.necessidades`, `efeitos.acoes`, `opostos`,
  `sorteavel` para nascidos).
- **Infração nova:** `world.yaml > leis.infracoes` + `infracao: <id>` na ação.
- **Tipo de memória:** `world.yaml > memoria.tipos` (força, sentimento, duração, frases de fofoca e
  lembrança) + `memoria: <tipo>` na ação.

## 7. Quando precisa de código

| Quero... | Precisa de código? |
|---|---|
| ação nova com necessidades, curvas, falas, alvo, infração, memória, falha | **não** |
| evento do diretor que muda necessidades, cria objetivo, força clima, chama criatura | **não** |
| evento social novo (festa, causo, torneio...) | **não** |
| entrada nova de consideração (algo que o mundo ainda não mede, ex.: "dinheiro") | sim — `sim/utility.py` (`read_input`) |
| regra especial (o que o `especial:` faz: roubar, prender, fofoca, confissão, recrutar...) | sim — `sim/engine.py` (`_special_before`/`_special_after`) |
| efeito no mundo real (luz do quarto, instrumento, som) | sim — `server/mqtt_bridge.py` publica um tópico novo |
| animação nova no viewer (além das 10 da convenção) | sim — `viewer/src/characters.js` |

Os `especial:` que já existem (e podem ser reaproveitados em ações novas): `fofoca`, `confissao`,
`denuncia`, `prender`, `roubar`, `recrutar`, `ordem_reconstruir`, `funeral`, `tumulo`, `criatura`,
`assembleia`, `anuncio_criador`, `reuniao_criador`. Leia `docs/arquitetura.md` (seções 7, 11 e 12) antes
de mexer no código.
