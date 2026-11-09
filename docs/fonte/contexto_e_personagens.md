# Divine Machinery — Contexto e Personagens

Nov 9, 2026 · @joao

Este documento dá a uma sessão nova com o Claude, ou a qualquer pessoa,
o contexto para continuar o Divine Machinery sem reexplicar nada. O
passo a passo de instalação e uso está no [Guia
Completo](https://claude.ai/artifact/WJiK1a3QYJ9sMefX4AT7c3); o código,
em
[folivorasloth/divine-machinery](https://github.com/folivorasloth/divine-machinery).

## Como usar numa sessão nova

- **Claude Code com o repositório aberto:** nada a fazer. O arquivo
  CLAUDE.md na raiz traz este mesmo contexto e é lido automaticamente.

- **Claude no navegador ou no app:** compartilhe este documento ou cole
  o conteúdo no início da conversa, e diga o que quer fazer ("vamos
  criar o Hefesto", "quero ajustar o humor do Grilo").

- **Quando algo mudar** (personagem novo, convenção nova): atualize este
  documento e o CLAUDE.md. Os dois precisam contar a mesma história.

## O que é o Divine Machinery

O Divine Machinery é um projeto pessoal do João: um ecossistema de
personagens (NPCs) que vivem no ambiente dele, conversam entre si e
reagem ao que ele faz. Cada personagem tem personalidade, humor e
memória próprios. Todos falam a mesma língua técnica, mensagens MQTT, e
por isso um personagem novo entra sem mexer nos antigos.

| Máquina                                | Papel                                                                                       | Sempre ligada? |
|----------------------------------------|---------------------------------------------------------------------------------------------|----------------|
| Homelab (Proxmox → VM Ubuntu + Docker) | Broker Mosquitto (portas 1883 e 9001) e os personagens                                      | Sim            |
| Notebook pessoal                       | Onde o João trabalha: ActivityWatch, publicador de atividade, chat de terminal, voz (Piper) | Quando em uso  |
| Notebook do LLM                        | Ollama, o "Oráculo": modelo de conversa e embeddings (bge-m3)                               | Não            |

Princípios que valem para tudo:

- **Tudo local.** Nenhuma API de nuvem.

- **Funciona sem o Oráculo.** Sem o LLM, os personagens usam templates e
  citações curadas, e de vez em quando comentam que "o Oráculo saiu de
  casa".

- **Personalidade é dado, não código.** Cada personagem tem um
  persona/\<id\>.yaml que o João edita sem programar.

- **Simples e legível.** O João quer entender e manter o código sozinho.

## Como todo personagem funciona

O Grilo é o molde: os próximos personagens seguem as mesmas peças, e o
código compartilhado vai para common/ quando o segundo personagem
chegar.

**Protocolo MQTT.** Cada personagem usa três tópicos próprios e ouve os
dos outros:

| Tópico               | Conteúdo                                                                                    |
|----------------------|---------------------------------------------------------------------------------------------|
| npc/\<id\>/fala      | {"from", "text", "ts", "meta"}; o meta traz to (com quem fala), depth, lang, mode, citation |
| npc/\<id\>/humor     | Valores de humor e estado (retido)                                                          |
| npc/\<id\>/status    | online / offline, com Last Will (retido)                                                    |
| joao/fala            | O que o João digita                                                                         |
| pc/atividade, pc/afk | O que o João está fazendo no computador                                                     |

**Humor.** Três valores de 0 a 100 (irritacao, orgulho, energia) que
sobem e descem com eventos e voltam devagar para uma base. Deles saem
estados como normal, irritado, retruque e emburrado, e cada estado muda
o jeito de falar.

**Modos de resposta.** A cada fala, um modo é sorteado com pesos que
dependem do humor: debochado, direto (curto, sem piada) ou filosofico
(com trechos dos livros da biblioteca).

**Memória.**

- Curta: as últimas 20 mensagens, inclusive as falas dos outros
  personagens.

- De fontes: de onde veio cada citação recente. Com ela, "de quem é essa
  frase?" é respondido pelo registro, sem o modelo inventar.

- Ainda não há memória que sobreviva a um reinício (fase 2 do roteiro).

**Conversa entre personagens.** Todos ouvem npc/+/fala. Um personagem
responde sempre quando falam com ele e, nos outros casos, por sorteio
dependente do humor. Uma conversa entre NPCs para depois de 3 falas
encadeadas (depth), o que impede loops. Quem é quem fica em
persona/cast.yaml.

**Idioma.** Responde em português ou inglês, conforme o idioma em que
falaram com ele.

## Personagem pronto: Grilo Falante

O Grilo é um grilo britânico de alta classe, "educado em Oxford", preso
no computador do João e sussurrando comentários no ouvido dele. É chato
como um mordomo crítico, nunca como um vilão.

|                        |                                                                                                                                                                |
|------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Id nos tópicos         | grilo                                                                                                                                                          |
| Onde mora              | Homelab, container dm-grilo (código em grilo/, persona em persona/grilo.yaml)                                                                                  |
| Personalidade          | Esnobe, condescendente, impecavelmente educado; sarcástico com fundo filosófico. Zoa, mas acerta na crítica. Nada de ameaças nem de IA fria (não é uma GLaDOS) |
| Jeito de falar         | Português com pitadas de inglês ("my dear", "darling", "rather"); em inglês, britânico "posh". Normalmente 1 a 3 frases; até 5 no modo filosófico              |
| Modos (humor normal)   | Debochado 60, direto 25, filosófico 15. Irritado: debochado 70, filosófico 30 (retruca com filosofia)                                                          |
| Humor                  | Irritação acima de 80 com orgulho alto: retruca pesado. Com orgulho baixo: emburra por 10 minutos e só diz "hmpf"                                              |
| Interesses             | Filosofia (Nietzsche, Camus, Hume, os estoicos), chá, a Coroa, críquete (o trocadilho é inevitável)                                                            |
| Comenta sozinho quando | O João passa mais de 2h no mesmo app, volta de AFK, está ativo de madrugada ou abre uma distração (YouTube, Reddit…)                                           |
| Com outros personagens | Acha todos intelectualmente inferiores. Responde sempre que é citado; se mete em 30% das falas alheias (70% irritado, nunca emburrado)                         |
| Sem o Oráculo          | Templates nas duas línguas e citações curadas com autor e obra                                                                                                 |

Exemplos de tom (da persona):

- "Cinco horas no mesmo bug, my dear. Sísifo ao menos tinha uma pedra
  com certo pedigree."

- "Se o código funciona e você não sabe por quê, congratulations: você
  fundou uma religião."

- "One doesn't 'take a break', darling. One flees, with caffeine."

O tom ainda está sendo calibrado (fase 1 do roteiro): os exemplos atuais
foram escritos pelo Claude e devem ser substituídos por falas no humor
do João.

## Personagens planejados

Ainda não existem em código e não têm personalidade definida. Nada sobre
eles deve ser inventado sem o João.

| Personagem      | O que se sabe                                               | O que falta definir                                            |
|-----------------|-------------------------------------------------------------|----------------------------------------------------------------|
| Hefesto         | Nome citado pelo João; vai conversar (e brigar) com o Grilo | Quem é, como fala, que eventos o acionam, o que pensa do Grilo |
| Olho            | Citado no plano original do projeto                         | Tudo                                                           |
| NPCs do cenário | Personagens ambientes que assinam os mesmos tópicos         | Tudo                                                           |

Para definir um personagem, responda a estas perguntas antes de qualquer
código:

1.  Quem é e de onde vem? (Uma frase, como "grilo britânico preso no
    computador".)

2.  Como fala? Dê de 5 a 10 falas de exemplo.

3.  O que o aciona? (Fala do João, atividade do PC, outros sensores.)

4.  O que pensa dos outros personagens?

5.  Que humor tem e o que o irrita ou agrada?

## Regras para quem trabalhar no projeto

- **Plano antes de código.** Apresente estrutura, dependências e
  decisões, e espere a aprovação do João.

- **Simples e legível.** Nada de superdimensionar. Comente o que não for
  óbvio, em português.

- **Nomes no código em inglês**; comentários, logs, README e dados
  visíveis em português.

- **Nada de IPs no código.** Tudo vem do config.yaml, que não vai para o
  git porque o repositório é público.

- **Personalidade em YAML**, nunca no código.

- **Todo personagem funciona sem o LLM** e registra no log cada decisão
  com o motivo.

- **Nunca fazer trabalho pesado dentro de um handler do MQTT**: só
  enfileirar.

- **Testes** com python -m pytest antes de cada commit; teste rápido de
  personalidade com python -m grilo.main --offline.

- **Git:** commits em português, direto na main do
  [folivorasloth/divine-machinery](https://github.com/folivorasloth/divine-machinery).

- **Limites conhecidos:** modelos locais de 7B são limitados em humor e
  contexto longo; a memória se perde num reinício; o broker é anônimo e
  só serve à rede local.
