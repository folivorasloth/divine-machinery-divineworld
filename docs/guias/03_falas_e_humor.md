# Guia 03 — Falas e humor

> Ninguém no mundo tem voz: tudo que eles "dizem" são **templates de texto** em `data/lines/*.yaml`, que
> viram balões nas telas e linhas no Chat do Mundo. Este guia mostra como escrever, que variáveis
> existem, os filtros e como não deixar o mundo repetitivo. Depois de mexer: `tools.validate` e
> `tools.cli recarregar` (vale na hora, sem reiniciar).

## 1. Onde ficam e como se ligam

- `data/lines/*.yaml`, por tema: `rotina` (comer, dormir, trabalhar...), `social` (conversar, responder),
  `conflito` (discutir, brigar, fazer as pazes), `pastelao` (tombos, pegadinhas), `fofoca`, `ganancia`
  (roubo, sumiço), `lei` (Fiscal, prisão, Limbo), `fe` (missa, ritual, sino), `vida` (morte, funeral,
  luto, nascimento, fantasmas, criaturas, clima), `criador` (ordens do Chefe, voz da Médium, Aparição).
- Cada arquivo tem `situacoes:`, e cada **situação** é uma lista de falas. Situações com o mesmo nome em
  arquivos diferentes **se somam**.
- Quem escolhe a situação é a **ação** (em `data/actions/*.yaml`): `fala: comer` + `chance_fala: 0.3`
  quer dizer "quando alguém começa a comer, 30% de chance de sair um balão da situação `comer`". Ações
  sociais têm também `fala_alvo` (o que o outro responde). Eventos (morte, funeral, sucessão...) usam
  situações fixas (`morte_briga`, `funeral_anuncio`, `epitafio`...): veja os nomes nos arquivos.
- Quando não sai fala, aparece a **narração** da ação (`narracao:` no YAML da ação), no Chat.

## 2. Escrevendo uma fala

```yaml
situacoes:
  comer:
    - "{eu} come um prato fundo de sopa em {lugar}."          # forma curta: só o texto
    - texto: "{eu} reclama do sal. Depois repete o prato."      # forma longa: texto + filtros
      tracos: [ranzinza]
      peso: 2
```

- Use aspas duplas em volta do texto. Aspas **dentro** do texto: `\"` (`"{eu} grita: \"Fogo!\""`).
- Uma linha por fala; o balão mostra até `world.yaml > visual.baloes.max_letras` letras (o resto vira "…"):
  frases curtas funcionam melhor na parede.
- **Nunca** escreva o nome de um personagem por extenso ("O Palhaço"). Use `{eu}`/`{outro}` ou `{@clown}`.
  Assim a fala acompanha qualquer renomeação (o `tools.validate` avisa se você esquecer).

## 3. Variáveis

| Variável | Vira |
|---|---|
| `{eu}` | quem fala/age |
| `{outro}` | o alvo (com quem conversa, briga...) |
| `{terceiro}` | de quem se fala numa fofoca |
| `{lugar}` | o lugar da cena |
| `{hora}` / `{periodo}` / `{clima}` | "15:30" / "Tarde" / "chuva fraca" |
| `{bordao}` / `{bordao_outro}` | um bordão sorteado de quem fala / do alvo (`bordoes:` na ficha) |
| `{trabalho}` | o que a profissão faz ("forja ferramentas") |
| `{humor}` | a necessidade mais alta acima de 60 ("faminto", "entediado"); senão `humor_neutro` |
| `{morto}` | o morto da situação (funeral, luto, fantasma) |
| `{objeto}` | um objeto (roubo, herança, achado) |
| `{lembranca}` | uma memória de quem fala (só com o filtro `memoria`) |
| `{fato}` | o que a fofoca conta |
| `{evento}` / `{convidados}` | nome do evento social / lista de nomes |
| `{infracao}` / `{faccao}` / `{traco}` | nomes de infração, facção (a Igreja, a Seita), traço |
| `{@id}` | o nome atual de um personagem ou lugar específico: `{@fool}`, `{@cathedral}` |

Nem toda variável existe em toda situação: `{outro}` só em ações com alvo; `{morto}` só em morte/luto;
`{fato}` só em fofoca. Na dúvida, copie uma fala que já existe na mesma situação. Variável sem valor fica
escrita como está (o texto sai estranho, mas nada quebra). Variável que não existe é erro no
`tools.validate` (com a lista das que existem). A lista oficial está em `sim/text.py > TEMPLATE_VARS`.

**Concordância de gênero:** `{o|a}` usa o pronome de quem fala (`pronome: ele|ela` na ficha):
`"{eu} acorda cansad{o|a}."` → "A Dama acorda cansada." Para o alvo: `{outro:o|a}`; para o terceiro:
`{terceiro:o|a}`.

**Artigos:** os nomes começam com artigo ("O Padre", "A Praça", "a bigorna") e o mundo contrai sozinho:
`"de {outro}"` → "do Padre", `"em {lugar}"` → "na Praça", `"pra {outro}"` → "pro Padre", `"a {lugar}"` →
"à Praça". Escreva sempre a forma sem contração (`de`, `em`, `por`, `a`, `pra`) antes da variável.

## 4. Filtros (quem pode usar a fala)

| Campo | Exemplo | Significa |
|---|---|---|
| `personagens` | `[clown, fool]` | só estes ids |
| `tracos` | `[bravo, ranzinza]` | só quem tem um destes traços |
| `profissoes` | `[padre]` | só quem tem a profissão (vale para quem assumir o papel de um morto) |
| `lugares` | `[tavern]` | só nestes lugares |
| `periodos` | `[noite, madrugada]` | só nestes períodos |
| `climas` | `[chuva, tempestade]` | só com este clima |
| `necessidades_min` | `{raiva: 60}` | só se a necessidade de quem fala estiver acima |
| `memoria` | `[briga, roubo]` | só se quem fala lembra de algo assim (com o alvo, se houver); a lembrança vira `{lembranca}` |
| `mortos` | `[fool]` | (morte, funeral, luto) só quando o morto é este |
| `peso` | `2` | chance relativa (padrão 1); `0.3` = rara |

Uma fala com filtro concorre com as gerais: dê `peso: 2` ou `3` para as falas próprias de um personagem
saírem mais que as genéricas.

## 5. Humor: o que funciona no mundo

Do pilar da bible: "a cada olhada na parede, algo diferente". O humor vai do tombo ao humor negro.

- **Específico vence genérico.** "O Fiscal mede a distância entre as barracas com a régua" é melhor que
  "O Fiscal trabalha". Use a profissão, o defeito e o bordão do personagem.
- **O defeito da ficha é a piada.** O Palhaço: toda pegadinha dá errado nele. O Chefe: aprova dois pedidos
  contraditórios. O Fool: a piada certa no momento errado (funerais: `funeral_personalidade` com
  `personagens: [fool]`).
- **Reação > ação.** Situações de resposta (`resposta`, `fala_alvo`) são onde o outro personagem brilha.
- **Memória dá continuidade.** Falas com `memoria: [briga]` fazem o Ferreiro lembrar *daquela* briga com
  o Palhaço dias depois — é o que faz parecer vivo.
- **Clima e hora mudam o tom.** `climas: [chuva]`, `periodos: [madrugada]` para o lado estranho do mundo.
- **O "olhar" e o mistério** (`encarar_tela`, `assunto_aparicao`): curtas, sem explicar.

## 6. Evitando repetição

1. **Escreva muitas.** Situações comuns (`comer`, `conversar`, `trabalhar`, `resposta`, `dormir`) devem ter
   15 ou mais falas gerais, mais as próprias de cada personagem.
2. O mundo já evita repetir: cada personagem não repete nenhuma das suas **8 últimas** falas, se houver
   outra opção (`sim/speech.py > RECENT_LIMIT`). Com poucas falas numa situação, isso não segura.
3. **Meça**: o relatório de variedade simula dias acelerados e lista as falas que mais se repetiram:
   ```bash
   .venv/bin/python -m tools.report --days 7 --seed 42
   .venv/bin/python -m tools.report --days 30 --saida var/variedade.txt   # mais completo (~6 min)
   ```
   A tabela "Falas mais repetidas" mostra o texto exato, quantas vezes e a situação; acima do limite
   (`max(3, dias × 0,5)`: 3 numa semana, 15 num mês) vira ALERTA. Para cada alerta: acrescente 3–5
   variações na mesma situação (com o mesmo filtro) ou baixe o `peso` daquela fala.
4. "Narrações mais repetidas" é só informação (cada ação tem uma narração-padrão); se uma incomodar,
   aumente o `chance_fala` da ação (mais balões, menos narração) ou escreva mais falas para ela.

## 7. LLM (opcional)

Com o Ollama ligado (guia 08) e o mundo no relógio real, as falas das situações listadas em
`world.yaml > ollama.situacoes` (mortes, funerais, ordens, Aparição...) podem ser **reescritas** pelo
LLM, a partir do template. Sem Ollama, sai o template — por isso o template sempre tem que ser bom
sozinho.

## 8. Checklist

- [ ] Texto entre aspas, nomes como variáveis (`{eu}`, `{@id}`), nunca por extenso.
- [ ] `{o|a}` onde há adjetivo de gênero.
- [ ] Preposição sem contração antes de variável (`de {lugar}`, não `da {lugar}`).
- [ ] `tools.validate` → "Tudo certo!"; `tools.cli recarregar`.
- [ ] De vez em quando, `tools.report --days 7` para ver o que está repetindo.
