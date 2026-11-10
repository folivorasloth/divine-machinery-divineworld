# Guia — modelos 3D e design das telas

> Escrito na Fase 5 com a convenção dos modelos; a Fase 6 completa este guia (Blender passo a passo,
> paletas, sons). Tudo aqui foi testado com o viewer de verdade (`docs/relatorios/FASE_5.md`).

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
