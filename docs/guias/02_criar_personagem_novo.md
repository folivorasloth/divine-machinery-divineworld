# Guia 02 — Criar um personagem novo

> Um personagem novo é **um arquivo YAML** em `data/characters/`. Não precisa programar e não precisa
> desligar o mundo: `tools.validate` + `tools.cli recarregar` e ele chega em casa, como um morador novo.
> Exemplo usado neste guia: o Coveiro (`gravedigger`).

## 1. Copiar o modelo

```bash
cp data/characters/_MODELO.yaml data/characters/gravedigger.yaml
```
O `_MODELO.yaml` é comentado campo a campo (arquivos que começam com `_` são ignorados pelo mundo).
Abra o arquivo novo e apague os comentários que não quiser.

## 2. Os campos obrigatórios

```yaml
id: gravedigger                 # PERMANENTE. minúsculas, números e _. Igual ao nome do arquivo.
nome: O Coveiro                 # livre (com artigo: "O Coveiro" contrai certo: "do Coveiro")
pronome: ele                    # ele | ela (concordância nas falas)
aparencia: Alto e curvado, chapéu de abas largas, pá no ombro, botas sempre sujas de terra.
visual:
  cor: "#4a4e69"
  cor_secundaria: "#9a8c98"
  altura: 1.15
  corpo: corcunda               # magro | normal | barrigudo | enorme | baixinho | corcunda
  chapeu: chapéu de feltro
  acessorio: lanterna
tracos: [melancolico, honesto, solitario]   # ids de data/traits.yaml
profissao: coveiro              # id de data/traits.yaml > profissoes (veja a seção 4)
casa: houses                    # onde dorme (id de lugar)
```

- `tracos`: normalmente 3. Eles mudam a velocidade das necessidades (o `preguicoso` cansa mais rápido) e a
  vontade de cada ação (o `briguento` briga mais). A lista com o que cada um faz está em
  `data/traits.yaml > tracos` (ids: alegre, bravo, briguento, carente, curioso, debochado, devoto,
  estranho, fofoqueiro, ganancioso, melancolico, misterioso, preguicoso, rebelde, solitario...).
- `visual` + `aparencia` + `movimento` montam o boneco placeholder das telas (palavras reconhecidas no
  guia 06, seção 4). Depois você pode fazer o `.glb` dele (`viewer/public/models/characters/gravedigger.glb`).

## 3. O que faz um personagem ser bom de simulação

A bible resume: **uma vontade forte, um medo, um defeito que gera comédia e alguém que ele detesta.**
No YAML isso vira:

```yaml
quer: Que alguém, um dia, visite um túmulo que ele cavou.
medos:
  - {descricao: Que a terra mexa sozinha., gatilho: cemiterio}
defeito: Mede todo mundo com os olhos, "para o caso de precisar".
bordoes:
  - "Sete palmos. Nem mais, nem menos."
  - "Terra boa, essa."
segredo: Conversa com os mortos e eles respondem. Às vezes discordam.
movimento: Devagar, arrastando a pá, parando para olhar o céu.
```

E, principalmente, **rotina, necessidades e relações** (seções 4–6): é isso que faz ele agir sozinho.

## 4. Profissão, trabalho e rotina

Primeiro, a profissão. Se nenhuma das que existem serve, crie uma em `data/traits.yaml > profissoes`
(uma linha, copiando as outras):

```yaml
profissoes:
  # ...
  - {id: coveiro, nome: Coveiro, atividade: cava covas e conversa com as lápides, local_trabalho: cemetery}
```
(`atividade` vira a variável `{trabalho}`: "O Coveiro cava covas e conversa com as lápides no Cemitério".
Com `profissao: nenhuma` a narração do trabalho é "não faz nada em especial" — engraçado para o Mike,
estranho para os outros. `papel_importante: true` faz alguém assumir o papel se ele morrer;
`sorteavel: false` impede que nascidos sorteiem a profissão.)

```yaml
profissao: coveiro
local_trabalho: cemetery        # onde a ação "trabalhar" acontece
rotina:
  - {das: "07:00", ate: "08:00", acao: comer, lugar: community_kitchen}
  - {das: "08:00", ate: "12:00", acao: trabalhar, lugar: cemetery}
  - {das: "18:00", ate: "19:00", acao: visitar_tumulo, peso: 3}
  - {das: "22:30", ate: "06:30", acao: dormir, lugar: houses, peso: 2.5}
necessidades:
  social: {inicial: 10, taxa: 0.6}   # solitário: sente pouca falta de gente
  medo: {taxa: 0.5}
```

- A **rotina não é roteiro**: cada bloco multiplica a vontade de fazer aquela ação naquele horário (`peso`,
  padrão 2). Com fome ou sono demais, ele faz outra coisa. Horários podem atravessar a meia-noite.
- `acao` é um id de `data/actions/*.yaml` (comer, dormir, trabalhar, conversar, perambular, rezar,
  festejar, visitar_tumulo, cochilar...). O `tools.validate` reclama de id que não existe.
- **Profissões que já existem** (`data/traits.yaml > profissoes`): `bobo`, `colecionador`, `cozinheiro`, `ferreiro`,
  `fiscal`, `florista`, `lider`, `medium`, `musico`, `nenhuma`, `padre`, `palhaco`, `tecnico`, `vaqueiro`.
- `necessidades.<id>.taxa` multiplica a taxa do `world.yaml` só para ele (1.5 = 50% mais rápido);
  `inicial` é o valor com que ele chega.

## 5. Relações (para ele entrar nas fofocas e nos conflitos)

```yaml
afinidade_padrao: 0            # com quem não está na lista (-100 a 100)
relacoes:
  - {com: priest, afinidade: 40, tipo: colega, nota: Os dois trabalham em todo funeral.}
  - {com: fool, afinidade: 60, tipo: amigo, nota: O Fool conta para ele as piadas que fez nos enterros.}
  - {com: medium, afinidade: -50, tipo: rival, nota: Ela acorda os mortos que ele acabou de pôr para dormir.}
```

- **Pelo menos 2 ou 3 relações**, com pelo menos uma negativa: é a afinidade que gera conversa, fofoca,
  discussão, briga, paz, convite para festa, voto na eleição, luto.
- A afinidade é **deste** personagem com o outro. Para o outro sentir algo por ele, acrescente a linha
  no arquivo do outro (ex.: em `medium.yaml`, `{com: gravedigger, afinidade: -30, tipo: rival}`).
- `tipo` é livre, mas alguns têm efeito: `casal` (já são casados), `irmao`, `pai`, `mae`, `filho`,
  `aprendiz`, `mentor` (nunca casam entre si; aprendiz/filho têm preferência na sucessão).
- Sempre o **id** do outro (`priest`), nunca o nome.
- Opcional: `faccao: igreja` ou `seita` (muda sozinha com o tempo pela afinidade com o Padre e a Médium).

## 6. Falas próprias

Em qualquer arquivo de `data/lines/` (ou num novo, ex.: `data/lines/coveiro.yaml` com `situacoes:`):

```yaml
situacoes:
  trabalhar:
    - texto: "{eu} cava uma cova nova. Ninguém morreu. \"É bom ter uma pronta.\""
      personagens: [gravedigger]
      peso: 2
  conversar:
    - texto: "{eu} pergunta a {outro} a altura exata dele. Por nada."
      personagens: [gravedigger]
  funeral_personalidade:
    - texto: "{eu} bate a terra com a pá três vezes, tira o chapéu e diz: \"{bordao}\""
      personagens: [gravedigger]
      peso: 3
```
Detalhes (variáveis, filtros, humor, repetição): guia [03](03_falas_e_humor.md).

## 7. Morte, herança e o que muda quando ele morre

```yaml
heranca:
  objetos: [a pá velha, a lanterna]
  manias: [medir as pessoas com os olhos]
  herdeiros: [fool]
se_morrer: Ninguém sabe cavar direito; os enterros atrasam.
```
- `se_morrer` aqui é só texto. Para a morte dele **mudar o mundo**, crie um bloco em
  `data/world.yaml > se_morrer` (copie o do `fool` ou do `clown`): chuva, ações que ficam mais/menos
  prováveis para quem, por quantos dias, luto mais forte de alguém e o texto do Chat.
- Falas de morte e funeral por personagem: `data/lines/vida.yaml` com `mortos: [gravedigger]`
  (o que os outros dizem quando ele morre) e `epitafio` com `mortos: [gravedigger]` (a lápide).

## 8. Ligação com sistemas reais

O campo `ligacao_real` é **informativo** (documenta a intenção); quem liga de verdade é a **profissão**:

| Quero que ele... | Como |
|---|---|
| receba as ordens do Criador (`chefe "..."`) | `profissao: lider` (só um líder recebe; com dois, o primeiro vivo) — `data/events/criador.yaml > chefe.profissao` |
| ouça a voz (`medium "..."`) | `profissao: medium` — `criador.yaml > medium.profissao` |
| enfrente as criaturas do homelab real (`homelab/servicos/#`) | `profissao: tecnico`, ou acrescente a profissão dele em `data/events/creatures.yaml > chama_profissoes` |
| reaja à presença no quarto / Aparição | todos reagem; falas próprias nas situações `aparicao_*` e `encarar_tela` |

Coisas novas do mundo real (ex.: o instrumento real do Músico, a luz do quarto) precisam de código: veja
o guia 08 e as pendências no relatório da Fase 6.

## 9. Colocar no mundo

```bash
.venv/bin/python -m tools.validate        # corrija até "Tudo certo!"
.venv/bin/python -m tools.cli recarregar  # "novos no mundo: gravedigger"
.venv/bin/python -m tools.cli quem gravedigger
```
Ele aparece em casa, com as necessidades iniciais, e o Chat do Mundo diz *"Os dados do mundo foram
recarregados. chegou: O Coveiro."* Se o servidor estiver desligado, ele entra quando ligar.

Para ver como ele se comporta antes de soltar no mundo de verdade, simule dias acelerados numa cópia:
```bash
.venv/bin/python -m tools.run --fast --dias 3 --novo --banco var/teste.sqlite --personagem gravedigger --resumo
.venv/bin/python -m tools.report --days 7      # ele aparece na tabela "Personagens: variedade"
```
Se ele fizer sempre a mesma coisa ("fez só 3 ações diferentes"), dê mais blocos de rotina, relações ou
traços que puxem para outras ações.

## 10. Tirar um personagem

Apague (ou renomeie para começar com `_`) o arquivo **com o servidor parado** e tire as referências a ele
dos outros arquivos (o `tools.validate` lista todas). Ao ligar, ele fica "congelado" no banco — nada é
apagado; se o arquivo voltar, ele volta de onde estava.
