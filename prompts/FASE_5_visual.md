# Fase 5 — Visual 3D low-poly (placeholders prontos para trocar)

Leia `CLAUDE.md`, `docs/bible.md`, `docs/arquitetura.md` e os relatórios anteriores.

## Objetivo
Cada tela abre uma página e mostra, ao vivo, a sua parte do mundo em 3D low-poly estilo PS1/PS2: lugares, personagens andando, balões de fala, dia e noite, clima, névoa e o teletransporte entre telas. Os modelos agora são placeholders, feitos para o João substituir depois pelos dele sem mexer no código.

## Tarefas
1. **Viewer (Three.js + Vite)** em `viewer/`: `?screen=<id>` conecta no WebSocket e desenha os lugares atribuídos àquela tela no `world.yaml`.
2. **Estética PS1/PS2** (referências: My Summer Car, HORSES):
   - renderização em baixa resolução com upscale sem suavização (pixelado);
   - *vertex snapping* (tremidinha de vértice);
   - sombreamento flat;
   - névoa de distância;
   - paleta vibrante, e lugares sinistros com azuis frios e cara de terror (paleta vem do YAML do lugar).
3. **Placeholders gerados por código:**
   - personagens montados com primitivas (corpo, cabeça, chapéu, acessório), com a cor e a silhueta do YAML, para cada um já ser reconhecível (o chapéu do Chefe, o nariz do Palhaço, a batina do Padre);
   - cenários com primitivas e geometria simples (casas, Catedral estilizada, árvores, água, dunas).
4. **Sistema de assets substituíveis:**
   - se existir `viewer/public/models/characters/<id>.glb` ou `viewer/public/models/places/<id>.glb`, ele é usado no lugar do placeholder;
   - convenção de animações por nome: `idle`, `walk`, `talk`, `work`, `sleep`, `fall`, `fight`, `pray`, `dance`, `stare`; se faltar alguma, usa a mais próxima ou um movimento procedural;
   - documente a convenção (escala, eixo, origem nos pés, nomes de animação) em `docs/guias/`.
5. **Animação procedural** para os placeholders: andar com balanço, tropeçar e cair, brigar, dançar, rezar, dormir, e encarar a câmera (o "olhar").
6. **Balões de fala** sobre os personagens, legíveis de longe, com duração proporcional ao texto.
7. **Ambiente:** ciclo de dia e noite pelo relógio do mundo, chuva e clima real, chuva forte no funeral, névoa cobrindo o lugar de uma tela offline.
8. **Teletransporte:** o personagem entra no túnel e some; publica em `leds/tunnel` (origem, destino, duração) para o WLED; aparece na tela de destino quando o tempo acaba.
9. **Layout das telas:** `world.yaml` define as telas (id, lugares que mostra, posição física na parede em cm, para calcular a duração e o caminho do LED). Inclua uma página `viewer/layout.html` que desenha o mapa físico das telas e das conexões, para o João conferir.
10. **Desempenho:** precisa rodar liso num notebook ou celular velho num navegador. Limite de FPS e de qualidade configurável por tela.
11. **A Aparição** no visual: uma silhueta borrada passando rapidamente, e todos os NPCs da tela olhando.

## Critérios de aceite
- Com o servidor rodando, duas abas com telas diferentes mostram lugares diferentes do mesmo mundo, e um personagem atravessa de uma para a outra pelo túnel.
- Um `.glb` qualquer colocado na pasta substitui o placeholder de um personagem sem mudar código.
- Prints das telas no relatório (salve em `docs/relatorios/img/`).

## Ao terminar
Escreva `docs/relatorios/FASE_5.md`, atualize `docs/arquitetura.md` e faça commit.
