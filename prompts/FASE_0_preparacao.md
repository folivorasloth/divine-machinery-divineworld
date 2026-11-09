# Fase 0 — Preparação e esqueleto

Leia `CLAUDE.md` e `docs/bible.md` por completo antes de qualquer coisa.

## Objetivo
Deixar o repositório pronto para as próximas fases: estrutura de pastas, dependências, configuração e os dados iniciais do mundo convertidos da bible para YAML. Nenhuma lógica de simulação ainda.

## Tarefas
1. **Estrutura** de pastas conforme `CLAUDE.md`, com `pyproject.toml` (ou `requirements.txt`), `.gitignore`, `README.md` curto e `docker-compose.yml` inicial (só o serviço da simulação, ainda vazio).
2. **`docs/arquitetura.md`:** descreva a arquitetura que você vai implementar: camadas, módulos, fluxo de um "tick", formato dos eventos, esquema do SQLite, tópicos MQTT e contrato do WebSocket com o viewer. Este documento vai ser atualizado em cada fase.
3. **Esquemas de dados** (pydantic) para personagem, lugar, ação, evento, fala e traço. Valide os YAML ao carregar, com mensagens de erro claras em português (o João vai editar esses arquivos à mão).
4. **Converta a bible em dados:**
   - `data/characters/*.yaml`: um arquivo por personagem da bible. O casal e os grupos (Cowboys, Técnicos) viram personagens individuais com relações entre si.
     - Cada um tem `id` estável (ex.: `clown`, `fool`, `musician`, `priest`, `chef_wife`, `chef_husband`, `teen`, `cowboy_fat`, `cowboy_thin`, `cowboy_old`, `medium`, `weirdo`, `mike`, `lady`, `inspector`, `blacksmith`, `florist`, `greedy`, `tech_old`, `tech_apprentice`, `chief`).
     - `nome` provisório igual ao papel ("O Palhaço"), exceto `mike`, que se chama Mike.
     - Campos: aparência (texto), cor principal (hex, para o visual placeholder), traços, necessidades iniciais e taxas, profissão, local de trabalho, casa, rotina-base, bordões, medos, segredo, ligação com sistema real, relações iniciais e regras de herança.
     - Inclua um arquivo modelo comentado `data/characters/_MODELO.yaml` explicando cada campo, para o João criar personagens novos.
   - `data/places/*.yaml`: todos os lugares da bible, com conexões (grafo), paleta, nível de perigo, se é interno ou externo e quais ações fazem sentido ali. O teletransporte entre telas é uma conexão especial do tipo `tunnel`.
   - `data/world.yaml`: relógio (multiplicador), localização para o clima, endereços MQTT e Ollama, limites (máximo de figurantes, de eventos por hora, chance de morte, etc.), seed e mapeamento de telas para lugares (exemplo com 4 telas).
   - `data/traits.yaml`: traços sorteáveis para nascimentos (com efeitos nas necessidades e nos pesos das ações).
   - `data/lines/`: estrutura de templates de falas (pode começar com poucos exemplos por situação; a Fase 2 expande).
5. **Carregador e validador:** um comando `python -m tools.validate` que lê todo o `data/` e aponta erros (campo faltando, relação com id inexistente, lugar sem conexão).
6. **Testes** do carregador e dos esquemas.

## Critérios de aceite
- `python -m tools.validate` passa sem erros.
- Mudar o `nome` de um personagem no YAML não exige mudar nenhum outro arquivo.
- `docs/arquitetura.md` descreve o plano completo das fases 1 a 5.

## Ao terminar
Escreva `docs/relatorios/FASE_0.md` seguindo o template e faça commit.
