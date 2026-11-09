# Fase 6 — Polimento, balanceamento e guias para o João

Leia `CLAUDE.md`, `docs/bible.md`, `docs/arquitetura.md` e todos os relatórios.

## Objetivo
Deixar o projeto estável, balanceado e documentado para o João manter e evoluir **sozinho**, sem depender de IA para as tarefas do dia a dia.

## Tarefas
1. **Teste longo:** simule 60 dias acelerados. Use `tools.report` para encontrar repetição, personagens "parados", necessidades que explodem, cidade que esvazia ou lota, eventos que nunca acontecem. Ajuste o balanceamento no YAML (não no código) e documente o que mudou e por quê.
2. **Robustez:** a simulação sobrevive a: MQTT caindo, Ollama sumindo, YAML com erro (avisa e mantém a última versão válida), tela desconectando, reinício do homelab.
3. **Recarregar sem reiniciar:** mudanças em `data/` (nomes, falas, pesos) são aplicadas com um comando `recarregar`, sem perder o estado do mundo.
4. **Guias em `docs/guias/`**, em português, passo a passo, para quem não lembra de nada do código:
   - `01_renomear_e_editar_personagens.md`: mudar nome, aparência, traços, bordões e falas de um personagem, e renomear nascidos.
   - `02_criar_personagem_novo.md`: a partir do `_MODELO.yaml`, incluindo relações e ligação com sistemas reais.
   - `03_falas_e_humor.md`: como escrever templates, variáveis disponíveis e como evitar repetição.
   - `04_acoes_e_eventos.md`: criar uma ação ou um evento novo só com YAML, e quando precisa de código.
   - `05_balanceamento.md`: os principais números do `world.yaml` e o que cada um muda no comportamento do mundo.
   - `06_modelos_3d_e_design.md`: fluxo no Blender para personagens e cenários low-poly estilo PS1 (contagem de polígonos, texturas pequenas, paleta), escala, eixo, origem, nomes de animação, exportar `.glb`, onde colocar o arquivo e como testar.
   - `07_telas_e_layout_fisico.md`: adicionar uma tela, atribuir lugares, medir posições na parede, configurar os túneis de LED (WLED) e a página de layout.
   - `08_integracoes_reais.md`: MQTT do homelab, câmera de presença, status do homelab, clima, Ollama.
   - `09_rodar_e_manter.md`: subir, parar, atualizar, backup do SQLite, logs, e o que fazer quando algo quebra.
   - `10_comandos_do_criador.md`: todos os comandos, com exemplos.
5. **README** com a visão geral e links para os guias.
6. **Relatório final** `docs/relatorios/FASE_6.md` com:
   - o estado de cada fase;
   - o que ficou pendente, priorizado;
   - uma lista de "próximos passos que o João consegue fazer sozinho".

## Critérios de aceite
- 60 dias simulados sem erros, com o relatório de variedade dentro dos limites.
- Seguindo só o guia 01, alguém renomeia um personagem e vê o nome novo no Chat do Mundo e no visual, sem reiniciar.

## Ao terminar
Escreva `docs/relatorios/FASE_6.md`, atualize `docs/arquitetura.md` e o README, e faça o commit final.
