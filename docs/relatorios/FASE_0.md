# Relatório — Fase 0: Preparação e esqueleto

**Data:** 2026-11-09  ·  **Status:** concluída

## Resumo em 3 linhas
O repositório está pronto para as próximas fases: estrutura de pastas, dependências, Docker e um
plano de arquitetura detalhado. Toda a bible virou YAML em `data/` (21 personagens, 20 lugares, ações,
traços, falas e eventos de exemplo), e o comando `python -m tools.validate` confere tudo e explica os erros em português.
Ainda não existe simulação rodando (isso é a Fase 1).

## O que foi feito
- Estrutura conforme o `CLAUDE.md`: `data/`, `sim/`, `server/`, `viewer/`, `tools/`, `tests/`,
  `docs/guias/`, `var/` (fora do git), mais `pyproject.toml`, `.gitignore`, `.env.example`,
  `README.md`, `Dockerfile` e `docker-compose.yml` (serviço `sim`, por enquanto só valida os dados).
- `docs/arquitetura.md`: módulos de cada fase, threads, fluxo do tick, necessidades, Utility AI
  (fórmula da nota, curvas, escolha, formato do log explicável), planos e movimento, formato dos
  eventos, falas, esquema SQLite (F1 a F3), comandos do Criador, REST, contrato do WebSocket,
  tópicos/payloads MQTT, Docker e o viewer.
- Esquemas pydantic (`sim/schemas.py`) para mundo, lugar, personagem, ação (com curvas), evento,
  fala, traço, profissão e regras de nascimento. Chaves do YAML em português; atributos em inglês.
- Carregador/validador (`sim/loader.py`) que junta todos os problemas, com arquivo, campo,
  sugestão ("Você quis dizer 'tracos'?") e detecção de nome usado no lugar de id. Checa
  referências cruzadas, grafo (lugar sem conexão, lugar isolado, conexões conflitantes), telas,
  variáveis das falas e nomes escritos por extenso.
- `sim/curves.py` (curvas `pontos`, `linear`, `potencia`, `logistica`, `degrau`) e `sim/text.py`
  (templates com tokens `{@id}` que viram o nome atual só na hora de mostrar).
- Dados convertidos da bible:
  - `data/characters/`: os 21 personagens pedidos (casal, Cowboys e Técnicos como indivíduos com
    relações entre si), com aparência, `visual` (cor, corpo, chapéu, acessório), traços,
    necessidades, profissão, local de trabalho, casa, rotina-base, bordões, medos, segredo,
    ligação com o mundo real, relações e herança. `_MODELO.yaml` comentado campo a campo.
  - `data/places/`: os 14 lugares da tabela da bible (a Cidade dividida em Praça, Prefeitura,
    Cozinha, Taverna, Ferraria, Feira e Casas) + o Campo. Conexões `caminho` e `tunel`.
  - `data/world.yaml`: relógio, necessidades, Utility AI, limites, clima de Botucatu, MQTT,
    Ollama, servidor, SQLite e 4 telas de exemplo.
  - `data/traits.yaml`: 54 traços (das três palavras de cada ficha) com efeitos, 14 profissões,
    sorteio de aparências e regras de nascimento.
  - `data/actions/`: 19 ações com curvas (7 já marcadas para a Fase 2 com `ativa: false`).
  - `data/lines/`: 18 situações, 50 falas de exemplo (a Fase 2 expande).
  - `data/events/diretor.yaml`: 3 eventos de exemplo do diretor.
- 50 testes (`pytest`).

## Como testar (passo a passo)
```bash
cd divine-world
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 1) validar os dados
.venv/bin/python -m tools.validate
#    deve terminar com "Tudo certo! 0 erros, 0 aviso(s)." e código de saída 0

# 2) rodar os testes
.venv/bin/python -m pytest
#    deve mostrar "50 passed"

# 3) ver o validador pegando um erro (num rascunho, sem estragar o data/ de verdade)
cp -r data /tmp/dados-teste
sed -i 's/^tracos:/tracoss:/' /tmp/dados-teste/characters/fool.yaml
.venv/bin/python -m tools.validate --dados /tmp/dados-teste
#    deve apontar "campo desconhecido 'tracoss'. Você quis dizer 'tracos'?" e sair com código 1

# 4) renomear um personagem sem mexer em mais nada
cp -r data /tmp/dados-renomear
sed -i 's/^nome: O Palhaço$/nome: Bozó das Couves/' /tmp/dados-renomear/characters/clown.yaml
.venv/bin/python -m tools.validate --dados /tmp/dados-renomear      # 0 erros

# (opcional) Docker: só valida os dados por enquanto
docker compose up --build
```
(Se preferir, ative o ambiente com `source .venv/bin/activate` e use só `python -m ...`.)

## Amostra real
Saída real de `python -m tools.validate` nos dados desta fase:
```
Divine Machinery — o Mundo Vivo: 21 personagens, 20 lugares, 19 ações, 54 traços, 14 profissões, 50 falas em 18
situações, 3 eventos, 4 telas.

Tudo certo! 0 erros, 0 aviso(s).
```
Saída real com erros propositais numa cópia dos dados (`tracos` digitado errado no Fool, cor
inválida na Florista, variável inexistente e nome por extenso numa fala):
```
ERRO  data/characters/florist.yaml: visual.cor: valor 'amarelo' inválido — cor no formato #RRGGBB (ex.: "#ff8800", com aspas)
ERRO  data/characters/fool.yaml: tracos: campo obrigatório faltando
ERRO  data/characters/fool.yaml: tracoss: campo desconhecido 'tracoss'. Você quis dizer 'tracos'? Campos válidos aqui: afinidade_padrao, aparencia, ...
ERRO  data/lines/fe.yaml: situação 'encarar_tela', fala "{eu} come o pão do Mike {sobremesa}": variável desconhecida {sobremesa}. Use uma destas: {eu}, {outro}, {lugar}, ...
AVISO data/lines/fe.yaml: situação 'encarar_tela', fala "{eu} come o pão do Mike {sobremesa}": o nome 'Mike' está escrito por extenso. Use {@mike} para o texto acompanhar se o nome mudar.

4 erro(s), 1 aviso(s).
```
Renomeação real (Palhaço → "Bozó das Couves", só a linha `nome:` alterada): o validador passou
sem erros, e uma fala guardada como `'{@clown} buzina pra {@fool}. *FOM FOM*'` foi exibida como
`Bozó das Couves buzina pra O Fool. *FOM FOM*`; a afinidade `fool → clown` continuou 65.

## Decisões tomadas e por quê
- **Chaves do YAML em português sem acento, atributos Python em inglês (alias do pydantic)** — o
  João edita os YAML (`nome`, `tracos`, `rotina`), e o código segue a regra de identificadores em
  inglês. Sem acento nas chaves para evitar erro de digitação.
- **Ids de personagem e lugar em inglês; ids de vocabulário em português** (`brigar`, `fome`,
  `preguicoso`, `noite`) — o prompt da fase fixou os ids em inglês dos personagens, e o
  `CLAUDE.md` usa `brigar` como exemplo de ação. Personagens e lugares compartilham o espaço de ids.
- **Textos guardados com tokens `{@id}` e nomes trocados só na exibição** — assim renomear muda
  até o histórico do Chat do Mundo, e o banco nunca guarda nomes.
- **A Cidade virou vários lugares** (Praça, Prefeitura, Cozinha Comunitária, Taverna, Ferraria,
  Feira, Casas, Catedral, Prisão, Cemitério), agrupados pela região `city` — a bible lista o que a
  Cidade tem, e as fases 1 e 2 precisam de lugares para comer, trabalhar e dormir.
- **Lugar novo "O Campo" (`fields`)** — não está na tabela, mas a bible diz que os Cowboys
  "trabalham no campo de manhã". É fácil de remover se o João não quiser.
- **"As Casas" é um lugar só**, e todos moram lá (o Padre mora na Catedral) — casas individuais
  podem vir depois sem quebrar nada (só muda `casa:`).
- **Biomas ligados à Cidade por túneis** (Praça↔Floresta, Feira↔Mar, Prefeitura↔Sala do Servidor,
  Cemitério↔Subterrâneo, Montanha↔Céu); dentro da mesma tela, caminhos a pé. O validador avisa se
  um caminho a pé atravessar telas.
- **Acesso dos lugares**: `normal`, `especial` (Céu e Limbo: só por regra) e `nunca` (Mundo de
  Fora) — a bible diz que ninguém sabe se dá pra chegar ao Céu e que o Mundo de Fora nunca é visitado.
- **Rotina-base é multiplicador de nota, não ordem** — mantém o princípio "emergência, não
  roteiro": a fome ou o sono podem vencer a rotina.
- **`tocar_sino` com janelas de horário e peso alto** — garante o sino nos horários (critério da
  Fase 1) sem código especial.
- **Fórmula da nota multiplicativa** (produto de fatores 0..1) — uma ação que não faz sentido agora
  (fome zero → comer) cai sozinha, e o log explica fator por fator.
- **Curva `pontos` como forma principal** — ligar pontos sobre o valor cru (fome 0..100, hora
  0..24) é o mais fácil de entender sem matemática.
- **Ações das fases seguintes já descritas com `ativa: false`** — traços e lugares precisam
  citá-las (o validador confere), e a Fase 2 só liga e ajusta.
- **Nome provisório do bobo da corte: "O Fool"** — a bible chama a ficha de "The Fool", mas no
  texto sempre diz "o Fool"; segue o padrão "O/A + papel" dos outros.
- **Nomes do casal e dos grupos**: "A Cozinheira", "O Cozinheiro", "O Cowboy Barrigudo/Magrelo/
  Velho", "O Técnico", "O Aprendiz" — direto da descrição da bible.
- **Lacunas da bible ficaram vazias, não inventadas**: o Aprendiz não tem bordão nem segredo; a
  Dama não tem chapéu. Onde precisei de um número (taxas, afinidades, perigos), usei valores
  iniciais razoáveis, marcados como ponto de partida.
- **`seed` e endereços via variáveis de ambiente** (`${DW_SEED:-}`, `${MQTT_HOST:-mqtt.local}`,
  `${OLLAMA_URL:-http://oraculo.local:11434}`) — o repositório é público.
- **Um processo só para simulação e servidor (Fase 4)** — evita dois escritores no SQLite; MQTT e
  API só enfileiram comandos.
- **Os NPCs do mundo não publicam em `npc/<id>/fala`** por padrão — evita o Grilo responder a cada
  fala do mundo; dá para ligar depois.
- **`pyproject.toml` em vez de `requirements.txt`** — um lugar só para dependências e config do
  pytest; `pip install -e ".[dev]"` instala tudo.

## Arquivos principais criados ou alterados
- `docs/arquitetura.md` — plano de arquitetura das fases 1 a 5 (será atualizado a cada fase).
- `sim/schemas.py` — esquemas de todos os dados.
- `sim/loader.py` — carregador, validador e grafo dos lugares.
- `sim/curves.py` — curvas da Utility AI.
- `sim/text.py` — templates de falas e tokens `{@id}`.
- `tools/validate.py` — `python -m tools.validate [--dados pasta] [--estrito]`.
- `data/world.yaml`, `data/traits.yaml`, `data/places/*.yaml`, `data/characters/*.yaml`,
  `data/characters/_MODELO.yaml`, `data/actions/*.yaml`, `data/lines/*.yaml`, `data/events/diretor.yaml`.
- `tests/` — `test_data.py`, `test_rename.py`, `test_validation_errors.py`, `test_curves_text.py`.
- `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `Dockerfile`, `docker-compose.yml`.

## Testes
- 50 testes, 50 passando (`.venv/bin/python -m pytest`, Python 3.13).
- Cobrem: os dados reais sem erros nem avisos, presença de todos os personagens e lugares,
  simetria do grafo e túneis, relações iniciais, telas, variáveis de ambiente, o `_MODELO.yaml`
  válido e ignorado; renomear um personagem (e todos os personagens e lugares) sem mexer em
  outro arquivo; 22 tipos de erro de edição (campo faltando, erro de digitação, id inexistente,
  nome no lugar de id, afinidade fora da faixa, cor inválida, lugar sem conexão, lugar isolado,
  conexão conflitante, YAML quebrado com número da linha, id repetido, variável de fala inválida,
  nome por extenso, lugar em duas telas, entrada/curva inválida, horário mal escrito...); curvas,
  janelas de horário que atravessam a meia-noite, templates e a troca de `${VAR:-padrão}` por variáveis de ambiente.

## Limitações e problemas conhecidos
- Não há simulação ainda: os números (taxas, pesos, curvas) nunca rodaram de verdade. A Fase 1 vai
  ajustá-los vendo o mundo rodar.
- Se um arquivo de personagem tiver erro de formato, ele é descartado inteiro naquela validação; os
  erros de referência *dentro* dele só aparecem depois que o formato for corrigido.
- O `docker compose build` foi testado nesta máquina só com um ajuste temporário de certificado
  (o ambiente de desenvolvimento usa um proxy próprio); o `Dockerfile` do repositório é o mesmo
  sem esse ajuste, e a imagem rodou o validador com sucesso.

## Pendências (o que ficou para depois)
- Personagem raro (o desenho do Criador) — a bible deixa a ficha em branco até o desenho existir.
- Criaturas (`data/events/creatures.yaml`) e eventos sociais — Fases 2 e 3, como previsto.
- Falas: só exemplos (≤ 9 por situação) — a Fase 2 expande para ≥ 15 por situação comum.
- Guias em `docs/guias/` — Fase 6.
- Pendências criativas da bible continuam abertas (nomes, criaturas, se o Palhaço mexe nas luzes
  reais — no YAML está `opcional: true`, regras de nascimento).

## Onde o João pode mexer sem programar
- `data/characters/<id>.yaml` — `nome` (renomear não quebra nada), aparência, `visual`, traços,
  rotina, bordões, medos, relações. Para criar um novo, copie `data/characters/_MODELO.yaml`.
- `data/places/<id>.yaml` — nome, descrição, paleta, perigo, conexões (`caminho` ou `tunel`) e as
  ações possíveis ali.
- `data/world.yaml` — telas e quais lugares cada uma mostra, limites e chances, ritmo do relógio,
  parâmetros da escolha de ações, tópicos MQTT. Endereços e senhas vão no `.env`.
- `data/traits.yaml` — o que cada traço faz, profissões, sorteio dos nascimentos.
- `data/actions/*.yaml`, `data/lines/*.yaml`, `data/events/*.yaml` — ações, falas e eventos.
- Depois de qualquer edição: `python -m tools.validate`.

## Revisão do orquestrador
Revisão feita em 2026-11-09, rodando os comandos de novo.

| Critério de aceite | Resultado | Evidência |
|---|---|---|
| `python -m tools.validate` passa sem erros | ✅ passou | Saída: "21 personagens, 20 lugares, 19 ações, 54 traços, 14 profissões, 50 falas em 18 situações, 3 eventos, 4 telas. Tudo certo! 0 erros, 0 aviso(s)." |
| Mudar o `nome` de um personagem não exige mudar outro arquivo | ✅ passou | Troquei só `nome:` em `data/characters/clown.yaml` para "Bozó Teste" → validação seguiu com 0 erros (depois revertido). `tests/test_rename.py` cobre o mesmo. |
| `docs/arquitetura.md` descreve o plano das fases 1 a 5 | ✅ passou | Seções 4–14 cobrem relógio/tick, Utility AI, eventos, falas, SQLite (F1), sociedade (F2), vida/morte/diretor (F3), Criador/API/MQTT/WebSocket (F4) e visual (F5). |

Testes: `pytest` → 50 passed. Conferido que não há IP fixo em `data/` nem em `sim/` (só `0.0.0.0` como bind padrão do servidor, com variável de ambiente).
Observação: o `Dockerfile` commitado não foi construído dentro do sandbox (proxy com certificado próprio); fica para a Fase 4 validar com `docker compose up`.
