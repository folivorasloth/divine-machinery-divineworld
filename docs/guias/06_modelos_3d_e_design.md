# Guia — modelos 3D e design das telas

> Seções 1–5: a convenção dos modelos (Fase 5, testada com o viewer de verdade, `docs/relatorios/FASE_5.md`).
> Seções 6–10 (Fase 6): o passo a passo no Blender para personagens e cenários estilo PS1, paletas,
> checklist antes de exportar e como testar. Feito para o Blender 4.x (no 3.6 os menus são os mesmos).

## 1. Como a troca funciona (sem programar)

Hoje cada personagem e cada lugar é desenhado por código, com primitivas (caixas, cones, esferas),
a partir do YAML. Para trocar pelo seu modelo:

| Para trocar | Coloque o arquivo em | Exemplo |
|---|---|---|
| um personagem | `viewer/public/models/characters/<id>.glb` | `characters/clown.glb` |
| um lugar inteiro (o diorama) | `viewer/public/models/places/<id>.glb` | `places/tavern.glb` |

- O `<id>` é o do YAML (`data/characters/clown.yaml` → `clown`), **nunca o nome** ("O Palhaço").
  Renomear o personagem no YAML não exige renomear o arquivo.
- Recarregue a página da tela (F5). Não precisa `npm run build` nem reiniciar o servidor: o servidor
  serve essa pasta direto (`/viewer/models/...`) e conta o que existe em `GET /api/models`.
- No Docker, a pasta `viewer/public/models` é um volume (`docker-compose.yml`): copie o arquivo para lá
  no homelab e recarregue as telas.
- Se o arquivo estiver quebrado, a tela continua com o placeholder e escreve o erro no console do
  navegador (F12).
- Para testar o caminho todo antes de modelar: `python -m tools.exemplo_glb clown` cria um "totem" de
  caixas (verde e amarelo, com nariz vermelho apontando para a frente) com as animações `idle` e `walk`.
  Apague o arquivo depois.

## 2. Convenção do arquivo

| Item | Regra |
|---|---|
| Formato | **glTF binário (`.glb`)**, um arquivo só (texturas embutidas). No Blender: *File → Export → glTF 2.0*, formato *glTF Binary*. |
| Escala | **1 unidade = 1 metro.** Uma pessoa comum tem ~1,7 m. A altura do YAML (`visual.altura`) **não** é aplicada ao `.glb`: modele o Chefe barrigudo e o Ferreiro enorme no tamanho que eles têm. O viewer só aumenta todos por igual com `visual.escala_personagens` (world.yaml, hoje 1,3, para ler de longe). |
| Eixos | **+Y para cima**, o personagem **olha para +Z** (a frente). O exportador glTF do Blender converte sozinho (Z-up → Y-up) com *+Y Up* marcado; no Blender o personagem olha para **−Y** (a "Front view", tecla 1 do numpad, mostra o rosto). |
| Origem | **Nos pés**, no meio entre os dois pés (y = 0 é o chão). Lugares: origem no **centro do chão** do diorama. |
| Tamanho de um lugar | O diorama é um quadrado de **10 × 10 m** (de −5 a +5 em X e Z), chão em y = 0. Pode passar um pouco para cima (torres), mas não para os lados, senão invade o vizinho. O fundo (−Z) é o lado mais longe da câmera: paredes altas vão ali. |
| Polígonos | Pense em PS1: personagem de 300 a 1.500 triângulos, lugar até ~10.000. A tela do homelab roda em qualidade "baixa". |
| Texturas | Pequenas (64×64 a 256×256). O viewer desliga a suavização (pixel grande de propósito). Cores chapadas por material também funcionam. |
| Materiais | Use a cor base (*Base Color*) e, se quiser, uma textura. O viewer troca o material por um "PS1" (luz simples + vértices que tremem) mantendo cor, textura, transparência e cores de vértice. Brilho metálico/rugosidade são ignorados. |
| Sombreamento | O viewer respeita as normais do modelo. Para o visual "flat" das outras peças, use *Shade Flat* no Blender antes de exportar. |
| Esqueleto | Opcional. Com armature, exporte com *Skinning* ligado. Sem esqueleto também funciona (animação de objetos, como o totem de exemplo). |

**Rede de segurança:** se o modelo vier com altura absurda (menos de 0,3 m ou mais de 6 m — típico de
quem exportou em centímetros), o viewer ajusta para a altura do YAML; se a origem não estiver nos pés,
ele desce o modelo até o chão. Os dois casos aparecem como aviso no console. Corrija no arquivo quando der.

## 3. Animações (por nome)

Dê às *Actions* do Blender (ou aos clipes do glTF) **estes nomes**:

| Nome | Quando toca | Ações do mundo (padrão do `world.yaml`) |
|---|---|---|
| `idle` | parado (padrão de tudo) | qualquer ação sem animação própria |
| `walk` | andando de um lugar para outro, perambulando | andar, viajar, perambular, fugir, perseguir, patrulhar, skate |
| `talk` | conversando, discursando | conversar, fofocar, discutir, consolar, pregar, anunciar ordem, assembleia... |
| `work` | trabalhando com as mãos | trabalhar, comer, construir, tocar o sino, pichar, roubar, malabarismo |
| `sleep` | dormindo deitado | dormir, cochilar |
| `fall` | tombo (curto, toca uma vez) | evento `slapstick` (pastelão) e o começo da morte |
| `fight` | briga | brigar, quebrar, prender, enfrentar; evento `fight` |
| `pray` | rezando, em ritual | rezar, missa, ritual, velar, visitar túmulo, revelar visão |
| `dance` | festa | festejar |
| `stare` | parado encarando a tela (o "olhar") | encarar a tela, espiar; evento `stare`; a Aparição |

- O nome é comparado sem diferenciar maiúsculas e ignorando o prefixo do Blender: `Walk`,
  `walk_01` e `Armature|Walk` valem como `walk`.
- **Se faltar uma**, o viewer tenta as substitutas de `world.yaml > visual.animacao_substituta`
  (ex.: falta `fight` → usa `work`, senão `idle`) e **completa com movimento procedural** no corpo
  inteiro (deitar para `sleep`, tombar para `fall`, pular e girar para `dance`, ajoelhar para `pray`,
  virar para a câmera em `stare`). Só `idle` já dá um personagem aceitável.
- `stare` é especial: o viewer sempre vira o personagem para a câmera; a animação só precisa da pose
  (de preferência imóvel, cabeça levemente torta: é para dar arrepio).
- `fall` deve terminar deitado (o viewer segura o último quadro) e ter ~1 a 2 s.
- As animações devem ficar **no lugar** (sem andar para frente): quem move o personagem pelo mapa é o viewer.
- Que ação usa que animação é configurável sem programar: `world.yaml > visual.animacao_por_acao` e
  `visual.animacao_por_evento`.

## 4. Os placeholders (o que já existe e como influenciar)

Cada boneco é montado do YAML do personagem; mudar o YAML muda o boneco:

- `visual.cor` (roupa), `visual.cor_secundaria` (detalhes), `visual.altura` (1,0 = 1,7 m), `visual.corpo`
  (`magro`, `normal`, `barrigudo`, `enorme`, `baixinho`, `corcunda`).
- `visual.chapeu` — palavras reconhecidas: palha, chef, guizos, couro/cowboy, feltro, velas, capacete/lanterna,
  arrepiado, capuz, coroa, cartola, boné, gorro (outro texto = chapéu de feltro; "nenhum" = sem chapéu).
- `visual.acessorio` — nariz, martelo, prancheta, colher, pano, cigarro, cesta/flor, malabares/bolinhas,
  bolsos, apito/régua, leque, colar/ossos, viola/violão, crucifixo/cruz, luvas, skate, carrinho, fone,
  lanterna (pode ter mais de um: "apito e régua").
- `aparencia` (o texto da bible) — batina, manto e vestido viram saia até o chão; macacão, poncho,
  avental, terno, casaco, moletom; e detalhes: bolinhas, óculos, bigode, olhos grandes, monocelha,
  sapatos enormes, maquiagem, olho pintado na testa, careca, jeans, cabelo pintado.
- `movimento` — o jeito de andar: saltitando/pulando (pula), skate (desliza sem passo), arrastando,
  desliza/flutua, zigue-zague, passinhos/apressado, reto, desfila (nariz empinado), gingado (balança),
  passos pesados, furtivo (curvado), devagar (mãos nas costas).

Os lugares têm um cenário feito à mão por `id` (Praça com chafariz e coreto, Catedral com torre e
vitrais, Taverna com balcão e sinuca, Sala do Servidor com racks piscando e dois olhos no fundo...).
Um lugar novo sem cenário próprio ganha um genérico com as cores da `paleta` do YAML. As cores de cada
lugar (`paleta.principal`, `secundaria`, `luz`, `noite`) tingem o chão, e à noite o chão puxa para
`paleta.noite`; lugares com `sinistro: true` puxam o céu da tela para o azul de terror.

## 5. Telas, qualidade e desempenho

- Cada tela abre `http://<servidor>:8000/viewer/?screen=<id>` (lista em `/viewer/`; mapa em
  `/viewer/layout.html`).
- `world.yaml > telas[]`: `fps_max` (limite de quadros por segundo) e `qualidade` (`baixa`, `media`,
  `alta`). Os níveis estão em `world.yaml > visual.qualidades`: `altura_render` (pixels de altura da
  imagem interna — quanto menor, mais "PS1" e mais leve), `gotas_de_chuva`, `tremer_vertices`,
  `luzes_extras` (luzes de verdade em lampiões e forja) e `detalhe` (quantidade de árvores e enfeites).
- Para testar sem editar: `?qualidade=baixa`, `?fps=15`, `?altura=180`, `?nomes=0` (sem nomes),
  `?relogio=0` (sem relógio), `?foco=<lugar>` (a câmera mostra só aquele lugar).
- Celular ou notebook velho: `qualidade: baixa` e `fps_max: 20`.


## 6. Blender passo a passo: um personagem

O objetivo é um boneco de **300 a 1.500 triângulos**, com **silhueta forte** (o chapéu, o nariz, a
barriga e a postura têm que ser reconhecíveis numa tela pequena do outro lado do quarto), textura
pequena e pixelada (ou só cor por face) e as animações com os nomes da seção 3.

### 6.1 Preparar a cena (uma vez)
1. *File → New → General*. Apague o cubo, a câmera e a luz (`A`, `X`).
2. *Scene Properties → Units*: **Unit System = Metric, Unit Scale = 1.0, Length = Meters**. (É isso que
   garante 1 unidade = 1 metro; o erro mais comum é exportar em centímetros e o boneco sair gigante.)
3. Salve como `.blend` numa pasta sua (fora do projeto, ou numa pasta `arte/` que você não vai
   publicar): o projeto só recebe o `.glb` exportado.
4. Opcional, para ver o "PS1" já no Blender: *Viewport Shading → Solid → Lighting: Flat, Color:
   Attribute/Material*; e nas imagens, *Image Texture → Interpolation: Closest*.

### 6.2 Modelar (low-poly de verdade)
1. Comece de um **cubo** ou de um cilindro de **6 a 8 lados** (`Shift+A → Mesh`). Nada de subdivisão.
2. **Corpo base reaproveitável:** faça um tronco, pernas e braços com poucos loops (`Ctrl+R`), use o
   modificador *Mirror* (eixo X) para modelar só metade, e aplique o Mirror antes de exportar.
3. **Posição e eixo:** o boneco de pé **com os pés em z = 0**, centralizado em x = 0, y = 0, olhando para
   **−Y** (a vista *Front*, tecla `1` do numpad, mostra o rosto). Altura de uma pessoa: ~1,7 m (o Chefe é
   mais baixo e largo, o Ferreiro enorme: modele no tamanho real de cada um).
4. **Origem nos pés:** com o objeto selecionado, coloque o cursor 3D em (0, 0, 0) (`Shift+C`) e
   *Object → Set Origin → Origin to 3D Cursor*.
5. **Aplique as transformações:** `Ctrl+A → All Transforms` (escala 1, rotação 0). Sem isso, o boneco
   pode sair deitado ou de tamanho errado.
6. **Contagem:** ligue *Overlays → Statistics* e confira **Triangles** (o viewer roda em celular velho;
   300–1.500 por personagem é o alvo). Use *Decimate* (modo *Collapse*) se passou muito.
7. **Sombreamento flat:** selecione tudo e *Object → Shade Flat* (o visual facetado das outras peças).
8. **Família de bonecos:** salve o corpo base num `.blend` e, para cada personagem, duplique e troque
   só cabeça, chapéu e acessórios. É assim que jogo de PS1 fazia muito NPC com pouco trabalho.

### 6.3 Cor e textura (pequena, pixelada)
- **Mais simples (recomendado para começar):** um material por cor (*Principled BSDF → Base Color*),
  atribuído às faces (*Edit Mode → selecione faces → Material → Assign*). O viewer ignora metálico e
  rugosidade; só a cor base (e a transparência) contam.
- **Com textura:** *UV → Smart UV Project*, crie uma imagem de **64×64, 128×128 ou no máximo 256×256**,
  pinte no *Texture Paint* (ou num editor de pixel art) e ligue no *Base Color*. Interpolação *Closest*.
  O viewer já desliga a suavização (pixel grande de propósito).
- **Cores de vértice** (*Vertex Paint*) também funcionam: o viewer mantém.
- **Paleta:** use as cores do próprio personagem (`visual.cor` e `visual.cor_secundaria` no YAML) para
  ele continuar reconhecível; veja a seção 8 para a paleta dos lugares.

### 6.4 Esqueleto (opcional) e animações
1. Sem esqueleto também dá: anime o objeto inteiro (é o que o totem de exemplo faz). Para braços e
   pernas, crie uma *Armature* simples (quadril, coluna, cabeça, 2 braços, 2 pernas: ~10 ossos),
   `Ctrl+P → With Automatic Weights`.
2. Abra o *Dope Sheet → Action Editor* e crie **uma Action por animação** com os nomes da seção 3:
   `idle`, `walk`, `talk`, `work`, `sleep`, `fall`, `fight`, `pray`, `dance`, `stare`. Ligue o *Fake User*
   (o escudo ao lado do nome) em cada uma, senão o Blender descarta as que não estão em uso.
3. **No lugar:** as animações não andam para frente (o viewer move o boneco). `walk` em ciclo de ~1 s,
   `idle` respirando 2–3 s, `fall` de 1–2 s terminando deitado, `stare` quase imóvel.
4. Comece só com `idle` e `walk`: o resto o viewer completa com movimento procedural (seção 3).
5. Para o ar de PS1, use poucas *keyframes* e interpolação *Constant* ou *Linear*
   (*Key → Interpolation Mode*): o movimento "travadinho" faz parte do estilo.

### 6.5 Exportar o `.glb`
*File → Export → glTF 2.0 (.glb/.gltf)*:

| Opção | Valor |
|---|---|
| Format | **glTF Binary (.glb)** |
| Include | *Selected Objects* (selecione o boneco e a armature) |
| Transform | **+Y Up** marcado |
| Mesh | *Apply Modifiers* marcado; *UVs*, *Normals* marcados; *Vertex Colors* se usou |
| Material | *Export* (as imagens vão embutidas no `.glb`) |
| Animation | marcado; *Group by NLA Track* desmarcado; **Export all Actions** (ou *Actions* em "Mode") |
| Skinning | marcado se tiver armature |

Salve como `viewer/public/models/characters/<id>.glb` — o **id do YAML** (`clown.glb`), nunca o nome.

## 7. Blender passo a passo: um cenário (o diorama de um lugar)

1. Mesma cena (metros). O lugar é um quadrado de **10 × 10 m** com o chão em z = 0, centrado na origem
   (de −5 a +5 em X e em Y do Blender). O fundo do diorama (o lado longe da câmera) é o **+Y do Blender**
   (que vira −Z no viewer): paredes altas, montanhas e a torre da Catedral vão ali; a frente (−Y) fica
   aberta para a câmera ver quem está dentro.
2. **Lugar interno** (Taverna, Sala do Servidor, Catedral): faça em **corte** — chão + parede do fundo
   + uma lateral — como uma casa de bonecas. Senão ninguém lá dentro aparece.
3. Até ~**10.000 triângulos** por lugar; peças repetidas (árvores, lápides, bancos) podem ser cópias
   ligadas (`Alt+D`).
4. Deixe **espaço livre no meio** para os personagens (o viewer espalha os bonecos pelo chão do diorama)
   e não ponha nada acima de ~6 m (senão cobre o vizinho na grade da tela).
5. Origem no centro do chão, `Ctrl+A → All Transforms`, *Shade Flat*, exporte igual à seção 6.5 como
   `viewer/public/models/places/<id>.glb` (`places/cathedral.glb`). No cenário o material vem **como
   você exportou** (luz do viewer, sem a tremidinha dos personagens). Animações de cenário (vitral
   piscando, rack com luz) **ainda não tocam** — pendência da Fase 6; use material emissivo para luzes.
6. **Os portais de túnel e o entulho de obra** continuam sendo desenhados pelo viewer por cima do seu
   cenário (o portal roxo nas bordas, a fita de obra quando uma estrutura está danificada).
7. **A Catedral** é a réplica da Catedral de Botucatu (bible): fotos de frente e de lado como imagem de
   referência (*Shift+A → Image → Reference*) ajudam a acertar a torre central e as proporções.

## 8. Paleta e clima de cada lugar

- As cores do chão e da luz vêm de `data/places/<id>.yaml > paleta` (`principal`, `secundaria`, `luz`,
  `noite`). Use as mesmas cores no seu cenário para combinar com o céu e a névoa do viewer.
- Bible: cidade **vibrante e quente**; lugares sinistros (Sala do Servidor, Cemitério, Subterrâneo,
  Limbo) em **azuis frios** e com `sinistro: true` no YAML (o céu da tela puxa para o azul de terror).
- À noite o viewer escurece o cenário e acende janelas e lampiões dos placeholders; num `.glb` seu, um
  material **emissivo** (*Principled BSDF → Emission Color/Strength*) fica aceso o tempo todo (de dia e
  de noite) — use para janelas, lampiões, os olhos do que mora na Sala do Servidor, a lanterna do
  capacete. Vale para personagens e cenários.

## 9. Checklist antes de exportar

- [ ] Unidades em metros, escala 1, `Ctrl+A → All Transforms` aplicado.
- [ ] Pés (ou o chão do cenário) em z = 0; origem nos pés / no centro do chão.
- [ ] Personagem olhando para −Y no Blender (a vista Front mostra o rosto).
- [ ] Triângulos dentro do alvo (personagem ≤ 1.500, lugar ≤ 10.000).
- [ ] Texturas ≤ 256×256, embutidas.
- [ ] Actions com os nomes certos e *Fake User*; animações no lugar.
- [ ] Nome do arquivo = id do YAML (`clown.glb`), na pasta certa (`characters/` ou `places/`).

## 10. Testar

1. Com o servidor rodando, confira que ele vê o arquivo:
   ```bash
   curl -s localhost:8000/api/models        # {"characters": ["clown"], "places": []}
   ```
2. Abra (ou dê F5 em) `http://<servidor>:8000/viewer/?screen=parede_centro&foco=<lugar onde ele está>`.
   `?foco=` enquadra só um lugar, bom para olhar de perto. O personagem tem que estar numa das telas:
   `.venv/bin/python -m tools.cli quem clown` diz onde ele está.
3. Abra o console do navegador (F12): avisos de **escala** ("altura fora de 0,3–6 m") ou de **origem**
   ("descendo até o chão") querem dizer que a seção 6.2 ficou para trás; erro de carregamento = o
   arquivo está quebrado (a tela continua com o placeholder).
4. Para ver as animações: no tempo acelerado tudo passa rápido; `.venv/bin/python -m tools.cli
   velocidade 1` deixa o mundo no ritmo real. `window.__dw.live()` no console mostra o estado da tela.
5. Teste automático do caminho todo (precisa do Playwright e de um servidor na porta 8000):
   `python -m tools.exemplo_glb chief` + `node viewer/e2e/aceite_glb.cjs` (veja o relatório da Fase 5).
   Apague os `.glb` de teste depois.
6. No Docker, a pasta `viewer/public/models` é um volume: copie o `.glb` para lá no homelab e dê F5 nas
   telas. Não precisa rebuild nem reiniciar.

**Sons:** ainda não existem (a bible deixa para o João criar). Quando existirem, a convenção natural é
a mesma: `viewer/public/sounds/places/<id>.ogg` por lugar — isso precisa de código no viewer (pendência
registrada no relatório da Fase 6).
