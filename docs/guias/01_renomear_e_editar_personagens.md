# Guia 01 — Renomear e editar personagens

> Para quem não lembra de nada do código. Você só vai editar **um arquivo de texto (YAML)** e rodar
> **dois comandos**. O mundo **não** precisa ser desligado: ninguém perde memória, relação ou lugar.
> Testado na Fase 6 com o servidor rodando (ver `docs/relatorios/FASE_6.md`).

## 0. O que você precisa saber antes

- Cada personagem mora num arquivo: `data/characters/<id>.yaml`. O Palhaço é `data/characters/clown.yaml`,
  o Chefe é `chief.yaml`, a Cozinheira é `chef_wife.yaml`... (a lista de ids está na seção 6).
- No topo de cada arquivo tem duas linhas:
  ```yaml
  id: clown          # NUNCA mude. É por ele que o mundo acha o personagem (banco, memórias, relações).
  nome: O Palhaço    # Mude à vontade. É o que aparece no Chat do Mundo, nos balões e nas telas.
  ```
- Para falar de **outro** personagem dentro de um arquivo (relações, herdeiros, falas), use sempre o
  **id** dele (`fool`), nunca o nome ("O Fool"). Assim, renomear nunca quebra nada.

## 1. Renomear um personagem (o caso mais comum)

1. Abra o arquivo do personagem num editor de texto. Exemplo: `data/characters/clown.yaml`.
2. Troque só a linha `nome:`:
   ```yaml
   nome: O Bozó
   ```
   - **Dica de português:** comece o nome com o artigo (`O Bozó`, `A Dona Cida`). O mundo faz as
     contrações sozinho: "na casa **do** Bozó", "fala **com o** Bozó", "**pro** Bozó". Sem artigo
     (`Bozó`) também funciona, só fica "de Bozó", "pra Bozó".
   - Se o nome tiver `:` ou começar com `*`, `[`, `{` ou `"`, ponha entre aspas: `nome: "Zé: o Grande"`.
3. Salve o arquivo.
4. Confira se não quebrou nada (na pasta do projeto):
   ```bash
   .venv/bin/python -m tools.validate
   ```
   O final deve ser `Tudo certo! 0 erros, ...`. Se aparecer `[ERRO]`, ele diz o arquivo, a linha do
   problema e, muitas vezes, a correção ("Você quis dizer...?"). Corrija e rode de novo.
   No Docker: `docker compose exec world python -m tools.validate`.
5. Aplique **sem desligar o mundo**:
   ```bash
   .venv/bin/python -m tools.cli recarregar
   ```
   Resposta esperada:
   ```
   Recarregado: 21 personagens, 20 lugares, 47 ações, 1564 falas.
     clown: O Palhaço -> O Bozó
   ```
   (os números mudam com o seu mundo.) No Docker: `docker compose exec world python -m tools.cli recarregar`.
   Outras formas do mesmo comando: pela API (`curl -X POST localhost:8000/api/commands -H
   'content-type: application/json' -d '{"cmd":"recarregar"}'`) ou publicando `recarregar` no tópico
   MQTT `world/commands`.
6. Veja o resultado:
   - **Chat do Mundo** (`http://<servidor>:8000/chat`): aparece a linha *"Os dados do mundo foram
     recarregados. O Palhaço agora se chama "O Bozó"."* e daí em diante tudo sai com o nome novo. O
     **histórico antigo também** passa a mostrar o nome novo (o Chat guarda o id, não o nome) — basta
     recarregar a página do chat (F5).
   - **Telas 3D** (`/viewer/?screen=...`): redesenham sozinhas em ~1 segundo, com o nome novo
     embaixo dos pés e nos balões. Não precisa apertar F5.
   - `.venv/bin/python -m tools.cli quem clown` mostra a ficha com o nome novo.

**Se o YAML estiver com erro**, o `recarregar` **não muda nada**: o mundo continua com a última versão
que estava funcionando, e responde:
```
NÃO recarregou: os YAML têm erro. O mundo continua com a versão anterior.
  - [ERRO] data/characters/clown.yaml: ...
```
O mesmo aviso aparece no Chat do Mundo. Corrija, rode `tools.validate` e `recarregar` de novo.

> E se o homelab reiniciar com um YAML quebrado? O servidor liga com a **última versão válida**
> (uma cópia que ele guarda em `var/data_valido/` toda vez que liga sem erro) e escreve um aviso
> "ATENÇÃO: os arquivos de data/ estão com erro..." no Chat do Mundo. Corrija e rode `recarregar`.

## 2. Mudar a aparência

No mesmo arquivo:

```yaml
aparencia: Magro, macacão de bolinhas desbotado, nariz vermelho rachado, sapatos enormes...
movimento: Saltitando e dando estrelinhas.
visual:
  cor: "#e63946"            # cor da roupa (#RRGGBB, entre aspas)
  cor_secundaria: "#f1faee" # detalhes
  altura: 1.05              # 1.0 = 1,7 m (de 0.2 a 3)
  corpo: magro              # magro | normal | barrigudo | enorme | baixinho | corcunda
  chapeu: nenhum            # texto: palha, chef, guizos, cowboy, cartola, coroa, capuz... ou "nenhum"
  acessorio: nariz vermelho # texto: martelo, prancheta, viola, cruz, skate, lanterna...
```

- O boneco placeholder das telas é montado a partir desses textos: palavras como **batina**, **vestido**,
  **macacão**, **bolinhas**, **óculos**, **bigode** na `aparencia` e **saltitando**, **skate**,
  **arrastando**, **furtivo** no `movimento` viram peças e jeitos de andar. A lista completa das palavras
  reconhecidas está no guia [06 — modelos 3D](06_modelos_3d_e_design.md), seção 4.
- `recarregar` aplica: as telas redesenham o boneco com as cores e peças novas.
- Se existir um modelo seu (`viewer/public/models/characters/<id>.glb`), ele vale no lugar do
  placeholder (guia 06). O nome do arquivo é o **id**, então renomear não exige renomear o `.glb`.

## 3. Mudar traços, bordões, medos, segredo

```yaml
tracos: [debochado, imprevisivel, carente]   # ids de data/traits.yaml (normalmente 3)
bordoes:
  - "*FOM FOM* (buzina de borracha)"
  - "*FOOOM*"
medos:
  - {descricao: Silêncio. Ninguém rindo., gatilho: silencio}
segredo: É irmão do Fool e chora escondido quando o irmão está triste.
quer: Plateia. Qualquer plateia.
defeito: Toda pegadinha dele dá errado nele mesmo.
```

- **Traços** mudam o comportamento de verdade: quanto cada necessidade sobe e quanto ele gosta de cada
  ação. Veja os disponíveis (e o que cada um faz) em `data/traits.yaml > tracos`. Um traço que não existe
  vira erro no `tools.validate`, com sugestão.
- **Bordões** entram nas falas pela variável `{bordao}` (sorteado). Escreva vários.
- `pronome: ele` ou `ela` acerta a concordância ("cansad**o**/cansad**a**").
- Mudou traços? Depois do `recarregar` o efeito é imediato no próximo minuto do mundo; as memórias e
  relações ficam como estavam (traços ganhos em vida, como os de quem volta do Limbo, também ficam).
- Rotina (`rotina:`), casa (`casa:`), trabalho (`profissao:`, `local_trabalho:`) e necessidades
  (`necessidades:`) também recarregam. A rotina **puxa**, não obriga: veja o guia 05.
- Relações (`relacoes:`) são as afinidades **iniciais**. Num mundo que já está rodando, a afinidade viva
  (que mudou com brigas e pazes) fica no banco: mudar o número no YAML só vale para um mundo novo e
  para a "volta devagar" (as afinidades voltam aos poucos para o valor do YAML com o tempo).

## 4. Falas próprias de um personagem

As falas ficam em `data/lines/*.yaml`, por **situação** (comer, conversar, brigar, funeral...). Para
uma fala ser só de um personagem, use o filtro `personagens` com o **id**:

```yaml
situacoes:
  conversar:
    - texto: "{eu} buzina duas vezes para {outro}. {bordao}"
      personagens: [clown]
```

- `{eu}` é quem fala, `{outro}` é com quem; para citar um personagem específico, use `{@id}`:
  `"{eu} jura que viu {@fool} chorando."` — **nunca** escreva "O Fool" por extenso (o `tools.validate`
  avisa, porque não acompanharia uma renomeação).
- `recarregar` aplica falas novas e pesos novos na hora.
- Tudo sobre falas (variáveis, filtros, como evitar repetição): guia [03 — falas e humor](03_falas_e_humor.md).

## 5. Renomear quem nasceu sozinho

Nascidos viram arquivos novos, com nome provisório "O Recém-chegado nº 3" / "A Recém-chegada nº 3":

- No uso normal: `data/characters/born/born_<n>.yaml` (no Docker, a mesma pasta, que é um volume).
- Se o servidor foi ligado com `--nascidos PASTA` ou com a variável `DW_BORN_DIR`, ficam nessa pasta.
- Descubra quem é quem: `.venv/bin/python -m tools.cli quem born_3` (ou procure "nasce" no Chat do Mundo).

Edite igual a qualquer personagem (passos 1 a 6): troque `nome:`, e se quiser `aparencia`, `visual`,
`tracos`, `bordoes`. **Não mude o `id`** nem o nome do arquivo. Depois `tools.validate` e `recarregar`.
O nome provisório dos próximos nascidos fica em `data/traits.yaml > nascimento > nome_padrao` e
`nome_padrao_ela` (`{n}` é o número).

## 6. Renomear um lugar

Mesma coisa em `data/places/<id>.yaml` (linha `nome:`); estruturas dentro do lugar (`estruturas:`, ex.:
`{id: forge_anvil, nome: a bigorna}`) também têm `nome`. Para nomes de lugar use o artigo maiúsculo
("A Taverna") e para estruturas minúsculo ("a bigorna"): os dois contraem certo ("na Taverna",
"na bigorna"). `recarregar` aplica, e os nomes nas telas e nos portais mudam junto.

## 7. Ids dos personagens da bible

| id | quem | id | quem |
|---|---|---|---|
| `chief` | o Chefe | `priest` | o Padre |
| `clown` | o Palhaço | `medium` | a Médium |
| `fool` | o Fool | `weirdo` | o Esquisito |
| `musician` | o Músico | `teen` | o Adolescente |
| `chef_wife` | a Cozinheira | `lady` | a Dama |
| `chef_husband` | o Cozinheiro | `greedy` | o Ganancioso |
| `blacksmith` | o Ferreiro | `inspector` | o Fiscal |
| `florist` | a Florista | `mike` | Mike |
| `cowboy_fat`, `cowboy_thin`, `cowboy_old` | os três Cowboys | `tech_old`, `tech_apprentice` | o Técnico e o Aprendiz |

## 8. O que NÃO recarrega (precisa reiniciar o servidor)

`world.yaml > mqtt`, `servidor`, `persistencia`, `ollama` (endereço/modelo) e o fuso/passo do `relogio`.
O `recarregar` avisa ("só vale depois de reiniciar: mqtt") quando você mudou algum deles. Reiniciar
também não perde nada: `docker compose restart world` (ou Ctrl+C e `python -m server` de novo) continua
o mundo de onde parou.

Remover um personagem (apagar o arquivo) com o mundo ligado não tira ele do mundo: o `recarregar`
avisa "sem arquivo (continuam com a versão antiga)". Para tirar de vez, apague o arquivo e reinicie: ele
fica "congelado" no banco (nada é apagado; se o arquivo voltar, ele volta). Lembre de tirar as
referências a ele nos outros arquivos — o `tools.validate` lista todas.

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `Não consegui falar com o servidor` | o servidor não está rodando, ou é outra porta/máquina | `python -m server` (ou `docker compose up -d`); `tools.cli --url http://<homelab>:8000 recarregar` |
| `[ERRO] ... campo desconhecido 'nomee'` | erro de digitação numa chave | use a chave sugerida |
| `[ERRO] ... personagem 'Palhaço' não existe` | usou o nome no lugar do id | troque pelo id (`clown`) |
| `[AVISO] ... nome por extenso` | escreveu "O Palhaço" dentro de uma fala | troque por `{@clown}` |
| A tela 3D não mudou | a aba está desconectada (o relógio do canto parado?) | F5 na aba; confira `http://<servidor>:8000/health` |
| Nome novo no Chat ao vivo, antigo nas linhas velhas | a página do chat foi aberta antes | F5 na página do chat |
