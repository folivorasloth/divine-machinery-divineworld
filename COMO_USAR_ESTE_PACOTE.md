# Como usar este pacote no Claude Code

Este pacote tem tudo que o Claude Code precisa para construir o Mundo Vivo do Divine Machinery em fases: o contexto (`CLAUDE.md`), a bible (`docs/bible.md`), um prompt por fase (`prompts/`) e o modelo de relatório. O guia para depois que o plano Max acabar está em `GUIA_POS_MAX.md`.

## Antes de começar (10 minutos)

1. Crie a pasta do projeto e coloque o conteúdo deste pacote dentro dela, mantendo a estrutura:
   ```
   divine-world/
     CLAUDE.md
     COMO_USAR_ESTE_PACOTE.md
     GUIA_POS_MAX.md
     docs/bible.md
     docs/relatorios/TEMPLATE.md
     prompts/FASE_0 ... FASE_6
   ```
2. Inicie o git: `git init && git add . && git commit -m "pacote inicial"`.
3. Tenha Python 3.11+, Node.js 20+ e Docker instalados na máquina onde o Claude Code vai rodar. O MQTT e o Ollama **não** são necessários para as fases rodarem; o código tem fallback.
4. Abra o Claude Code dentro da pasta `divine-world`. Ele lê o `CLAUDE.md` sozinho.

## Rodando as fases

Para cada fase, em ordem:

1. Comece uma conversa limpa (`/clear`), para a fase anterior não ocupar o contexto.
2. Cole: **"Execute a fase descrita em `prompts/FASE_<n>_<nome>.md`."**
3. Deixe trabalhar. Se ele perguntar algo, responda curto. Se travar num erro por muito tempo, peça para registrar no relatório como pendência e seguir.
4. Ao final, leia `docs/relatorios/FASE_<n>.md`. Rode os comandos da seção "Como testar".
5. Confirme o commit e vá para a próxima fase.

## Prioridade se o tempo apertar (2 dias de Max)

| Ordem | Fase | Por que importa | Tempo estimado |
|---|---|---|---|
| 1 | 0 · Preparação | Base de tudo, dados da bible em YAML | 30 min a 1 h |
| 2 | 1 · Núcleo | O mundo já vive, em texto | 2 a 4 h |
| 3 | 2 · Sociedade | É onde as histórias começam a emergir | 3 a 5 h |
| 4 | 3 · Vida, morte e Diretor | Ritmo, mortes, nascimentos, clima | 3 a 5 h |
| 5 | 4 · Criador e API | Você intervém; prepara o terreno pras telas | 2 a 4 h |
| 6 | 5 · Visual | O mundo aparece nas telas | 3 a 6 h |
| 7 | 6 · Polimento e guias | Balanceamento e documentação | 2 a 3 h |

As estimativas são grosseiras e dependem de quantos ajustes forem precisos. As fases 0 a 4 são o coração: se elas ficarem prontas, o resto você consegue tocar depois, com a ajuda dos guias.

**Se só der tempo para parte da Fase 5 ou 6,** peça antes de acabar o plano: *"Escreva agora os guias 01, 06 e 07 da Fase 6 com base no que já existe."* Eles são os que você mais vai precisar sozinho.

## Dicas para render mais

- **Uma fase por conversa.** Contexto limpo = menos erro e menos consumo.
- **Rode o mundo de verdade entre as fases,** nem que seja 5 minutos acelerado. Você vai notar coisas que nenhum teste pega.
- **Não peça mudanças criativas no meio de uma fase.** Anote numa lista e mande tudo junto ao final, ou depois.
- **Se o Claude Code disser que algo funciona,** confira pela seção "Como testar" do relatório.
- **Guarde os relatórios.** Eles são a memória do projeto quando você voltar daqui a semanas.
