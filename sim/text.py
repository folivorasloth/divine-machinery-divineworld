"""Templates de texto (falas e Chat do Mundo).

Duas etapas, para que renomear um personagem nunca quebre nada:

1. `fill(template, ctx)`: troca as variáveis de situação ({eu}, {outro},
   {lugar}...) por TOKENS DE ID (`{@clown}`, `{@tavern}`) ou por texto
   (hora, clima, bordão). É isso que vai para o banco e para os eventos.
2. `render(texto, nomes)`: na hora de mostrar, troca cada `{@id}` pelo
   `nome` atual do YAML. Se o João renomear o Palhaço, até o histórico
   antigo do chat passa a mostrar o nome novo.

Nos YAML de falas também dá para citar alguém direto pelo id: `{@fool}`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

# Variáveis aceitas nos templates (o validador reclama de qualquer outra).
# Valor: descrição em português (aparece no _MODELO e nos guias).
TEMPLATE_VARS: dict[str, str] = {
    "eu": "nome de quem fala/age",
    "outro": "nome do alvo (com quem fala/briga/conversa)",
    "lugar": "nome do lugar onde a cena acontece",
    "hora": "hora do mundo, ex.: 15:30",
    "periodo": "período do dia (Madrugada, Manhã, Tarde, Noite)",
    "clima": "clima atual, ex.: chuva fraca",
    "bordao": "um bordão sorteado de quem fala",
    "bordao_outro": "um bordão sorteado do alvo",
    "trabalho": "a atividade da profissão de quem fala, ex.: forja ferramentas",
    "morto": "nome de um morto (funeral, lembrança) — Fase 3",
    "objeto": "um objeto (roubo, herança, objeto sagrado) — Fase 2",
    "humor": "humor de quem fala, vindo da necessidade mais alta (ex.: faminto)",
}

# Variáveis que viram token de id (personagem ou lugar), não texto.
ID_VARS = {"eu", "outro", "lugar", "morto"}

_FIELD = re.compile(r"\{([^{}]*)\}")


def fields(template: str) -> list[str]:
    """Lista os campos entre chaves: 'Oi {eu}, {@fool}' -> ['eu', '@fool']."""
    return _FIELD.findall(template)


def check_template(template: str, known_ids: set[str]) -> list[str]:
    """Devolve a lista de problemas do template (vazia = ok), em português."""
    problems = []
    if template.count("{") != template.count("}"):
        problems.append("chaves { } desbalanceadas")
    for field in fields(template):
        if field.startswith("@"):
            if field[1:] not in known_ids:
                problems.append(f"{{{field}}}: não existe personagem nem lugar com id '{field[1:]}'")
        elif field not in TEMPLATE_VARS:
            options = ", ".join("{" + v + "}" for v in TEMPLATE_VARS)
            problems.append(f"variável desconhecida {{{field}}}. Use uma destas: {options}")
    return problems


def fill(template: str, ctx: Mapping[str, str]) -> str:
    """Etapa 1: preenche variáveis. Para variáveis de id, `ctx` traz o id
    (ex.: {'eu': 'clown'}) e o resultado vira `{@clown}`. Variável sem valor
    fica como está (melhor um texto estranho do que um crash)."""

    def replace(match: re.Match) -> str:
        field = match.group(1)
        if field.startswith("@") or field not in ctx:
            return match.group(0)
        value = ctx[field]
        return "{@" + value + "}" if field in ID_VARS else str(value)

    return _FIELD.sub(replace, template)


# Contrações do português quando o nome começa com artigo ("A Catedral"):
# "em A Catedral" -> "na Catedral", "de O Padre" -> "do Padre".
_CONTRACTIONS = {
    ("em", "O"): "no", ("em", "A"): "na", ("em", "Os"): "nos", ("em", "As"): "nas",
    ("de", "O"): "do", ("de", "A"): "da", ("de", "Os"): "dos", ("de", "As"): "das",
    ("por", "O"): "pelo", ("por", "A"): "pela", ("por", "Os"): "pelos", ("por", "As"): "pelas",
    ("a", "O"): "ao", ("a", "A"): "à", ("a", "Os"): "aos", ("a", "As"): "às",
    ("pra", "O"): "pro", ("pra", "A"): "pra", ("pra", "Os"): "pros", ("pra", "As"): "pras",
}
_CONTRACT = re.compile(r"\b(em|de|por|a|pra) (Os|As|O|A) (?=\w)")
# artigo maiúsculo de um nome no MEIO da frase vira minúsculo ("com O Músico" -> "com o Músico")
_MID_ARTICLE = re.compile(r"(?<=[a-zà-ú,] )(Os|As|O|A)(?= \w)")


def contract(text: str) -> str:
    """'em A Praça' -> 'na Praça', 'rumo a A Praça' -> 'rumo à Praça',
    'conversa com O Músico' -> 'conversa com o Músico'.
    Só mexe em artigo MAIÚSCULO (o começo de um nome como "O Padre")."""
    text = _CONTRACT.sub(lambda m: _CONTRACTIONS[(m.group(1), m.group(2))] + " ", text)
    return _MID_ARTICLE.sub(lambda m: m.group(1).lower(), text)


def render(text: str, names: Mapping[str, str]) -> str:
    """Etapa 2: troca `{@id}` pelo nome atual. Id desconhecido vira o próprio id.
    Depois aplica as contrações ("em A Praça" -> "na Praça")."""

    def replace(match: re.Match) -> str:
        field = match.group(1)
        if field.startswith("@"):
            return names.get(field[1:], field[1:])
        return match.group(0)

    return contract(_FIELD.sub(replace, text))
