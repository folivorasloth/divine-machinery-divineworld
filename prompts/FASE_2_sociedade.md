# Fase 2 — Sociedade: relações, memória e conflito

Leia `CLAUDE.md`, `docs/bible.md`, `docs/arquitetura.md` e os relatórios anteriores.

## Objetivo
Os NPCs passam a ter vida social de verdade: gostam e odeiam, lembram, fofocam, brigam, fazem as pazes, organizam coisas juntos e quebram regras. É aqui que as histórias começam a emergir.

## Tarefas
1. **Relações:** afinidade de -100 a 100 entre cada par, iniciada pela bible e alterada por interações. A afinidade influencia a nota das ações sociais.
2. **Memória por NPC:** eventos marcantes com intensidade, sentimento e data. Memórias pequenas decaem; grandes (mortes, traições, casamentos) ficam. Memórias aparecem nas falas ("desde que você estragou meu casamento...").
3. **Fofoca:** NPCs repassam memórias de outros para terceiros, com chance de distorção. O Carteiro e o Padre (segredos de confissão) espalham mais.
4. **Conflito e reconciliação:** discussão, briga física (pastelão), perseguição, desculpas, abraço. Casal de cozinheiros com a briga das três da tarde e as pazes logo depois. Cowboys brigam entre si e terminam abraçados.
5. **Humor emergente:** ações de pastelão com chance de falha (tropeçar, cair do skate, pegadinha que dá errado no Palhaço, choque no Aprendiz), escolhidas pelos traços.
6. **Construções vivas:** prédios e objetos com estado (inteiro, danificado, destruído). Brigas, acidentes e criaturas danificam; NPCs reconstroem se quiserem (ou se o Chefe mandar). O Ferreiro lidera mutirões.
7. **Leis e punição:** o Fiscal registra infrações (pichar, roubar, barulho, brigar). Punição: prisão por um tempo; casos graves, o Limbo (o NPC some das telas e volta "estranho": traço novo sorteado).
8. **Facções:** Igreja (Padre) e Seita (Médium) disputam fiéis; missas de dia, rituais à noite na floresta e no subterrâneo. O Adolescente ronda a seita.
9. **Ganância:** o Ganancioso rouba e esconde coisas; os Cozinheiros percebem comida sumindo; acusações podem cair na pessoa errada.
10. **Eventos sociais organizados pelos NPCs:** festa na taverna, rave escondida, casamento, rodeio, procissão. Um NPC com vontade alta toma a iniciativa, convida os outros pela afinidade, e o evento acontece (ou fracassa) no lugar e na hora marcados.
11. **Falas:** expanda bastante os templates em `data/lines/`, por personagem e situação, com o tom da bible (sem limite de humor). Mínimo de 15 variações por situação comum.
12. **Testes** dos sistemas acima.

## Critérios de aceite
- Uma semana simulada (`--speed 3600`) gera brigas, pazes, fofocas, pelo menos uma festa organizada por NPCs, uma prisão e um ritual da seita, sem nenhum desses estar roteirizado.
- O relatório traz 3 "histórias" reais que emergiram, contadas a partir dos logs.

## Ao terminar
Escreva `docs/relatorios/FASE_2.md`, atualize `docs/arquitetura.md` e faça commit.
