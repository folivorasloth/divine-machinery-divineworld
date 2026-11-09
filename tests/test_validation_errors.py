"""O validador encontra erros comuns de edição e explica em português."""

from __future__ import annotations

from sim.loader import expand_env, load_data
from tests.conftest import edit_yaml, messages


def _errors(data_copy) -> str:
    _, report = load_data(data_copy, environ={})
    assert not report.ok, "esperava erros"
    return "\n".join(str(i) for i in report.errors)


def test_missing_required_field(data_copy):
    edit_yaml(data_copy / "characters" / "fool.yaml", lambda c: c.pop("casa"))
    out = _errors(data_copy)
    assert "fool.yaml" in out and "casa: campo obrigatório faltando" in out


def test_typo_in_field_name_suggests_fix(data_copy):
    def change(c):
        c["tracoss"] = c.pop("tracos")
    edit_yaml(data_copy / "characters" / "fool.yaml", change)
    out = _errors(data_copy)
    assert "campo desconhecido 'tracoss'" in out and "Você quis dizer 'tracos'?" in out


def test_relation_with_unknown_id(data_copy):
    edit_yaml(data_copy / "characters" / "fool.yaml", lambda c: c["relacoes"].append({"com": "ghost", "afinidade": 10}))
    assert "personagem 'ghost' não existe" in _errors(data_copy)


def test_relation_using_name_instead_of_id_gets_hint(data_copy):
    edit_yaml(data_copy / "characters" / "clown.yaml", lambda c: c.update(nome="bozo"))
    edit_yaml(data_copy / "characters" / "teen.yaml", lambda c: c["relacoes"].append({"com": "bozo", "afinidade": 1}))
    assert "Isso parece um NOME; use o id 'clown'" in _errors(data_copy)


def test_place_name_used_as_id_gets_hint(data_copy):
    edit_yaml(data_copy / "characters" / "fool.yaml", lambda c: c.update(casa="mike"))
    out = _errors(data_copy)
    assert "lugar 'mike' não existe" in out


def test_affinity_out_of_range(data_copy):
    edit_yaml(data_copy / "characters" / "fool.yaml", lambda c: c["relacoes"][0].update(afinidade=150))
    assert "deve ser ≤ 100" in _errors(data_copy)


def test_invalid_color(data_copy):
    edit_yaml(data_copy / "characters" / "fool.yaml", lambda c: c["visual"].update(cor="amarelo"))
    assert "#RRGGBB" in _errors(data_copy)


def test_unknown_trait(data_copy):
    edit_yaml(data_copy / "characters" / "fool.yaml", lambda c: c["tracos"].append("corajozo"))
    assert "traço (definido em traits.yaml) 'corajozo' não existe" in _errors(data_copy)


def test_place_without_connection(data_copy):
    edit_yaml(data_copy / "places" / "desert.yaml", lambda c: c.update(conexoes=[]))
    edit_yaml(data_copy / "places" / "sea.yaml", lambda c: c.update(conexoes=[x for x in c["conexoes"] if x["para"] != "desert"]))
    assert "lugar sem conexão" in _errors(data_copy)


def test_isolated_island_of_places(data_copy):
    # mar <-> deserto continuam ligados entre si, mas sem túnel para a feira
    edit_yaml(data_copy / "places" / "sea.yaml", lambda c: c.update(conexoes=[x for x in c["conexoes"] if x["para"] != "market"]))
    edit_yaml(data_copy / "places" / "market.yaml", lambda c: c.update(conexoes=[x for x in c["conexoes"] if x["para"] != "sea"]))
    assert "lugar isolado" in _errors(data_copy)


def test_conflicting_connection(data_copy):
    edit_yaml(data_copy / "places" / "town_hall.yaml", lambda c: c["conexoes"][0].update(minutos=99))
    assert "declarada diferente" in _errors(data_copy)


def test_connection_to_unknown_place(data_copy):
    edit_yaml(data_copy / "places" / "forge.yaml", lambda c: c["conexoes"].append({"para": "moon", "minutos": 3}))
    assert "lugar 'moon' não existe" in _errors(data_copy)


def test_yaml_syntax_error_has_line_number(data_copy):
    path = data_copy / "characters" / "fool.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\nrelacoes: [ {com: clown\n", encoding="utf-8")
    out = _errors(data_copy)
    assert "erro de sintaxe YAML na linha" in out


def test_duplicate_id(data_copy):
    (data_copy / "characters" / "fool2.yaml").write_text(
        (data_copy / "characters" / "fool.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert "id 'fool' repetido" in _errors(data_copy)


def test_unknown_template_variable(data_copy):
    edit_yaml(data_copy / "lines" / "rotina.yaml", lambda c: c["situacoes"]["comer"].append("{eu} come {comida}"))
    assert "variável desconhecida {comida}" in _errors(data_copy)


def test_unknown_id_token_in_line(data_copy):
    edit_yaml(data_copy / "lines" / "rotina.yaml", lambda c: c["situacoes"]["comer"].append("{eu} olha {@ninguem}"))
    assert "não existe personagem nem lugar com id 'ninguem'" in _errors(data_copy)


def test_literal_name_in_line_is_a_warning(data_copy):
    edit_yaml(data_copy / "lines" / "rotina.yaml", lambda c: c["situacoes"]["comer"].append("{eu} rouba o prato do Mike."))
    _, report = load_data(data_copy, environ={})
    assert report.ok
    assert "{@mike}" in messages(report)


def test_place_in_two_screens(data_copy):
    edit_yaml(data_copy / "world.yaml", lambda c: c["telas"][1]["lugares"].append("tavern"))
    assert "está em duas telas" in _errors(data_copy)


def test_bad_consideration_input(data_copy):
    def change(c):
        c["acoes"][2]["consideracoes"][0]["entrada"] = "necessidade.fomee"
    edit_yaml(data_copy / "actions" / "basicas.yaml", change)
    assert "necessidade 'fomee' não existe" in _errors(data_copy)


def test_curve_missing_parameter(data_copy):
    def change(c):
        c["acoes"][2]["consideracoes"][0]["curva"] = {"tipo": "logistica"}
    edit_yaml(data_copy / "actions" / "basicas.yaml", change)
    assert "precisa de 'meio'" in _errors(data_copy)


def test_bad_time_format(data_copy):
    edit_yaml(data_copy / "characters" / "fool.yaml", lambda c: c["rotina"][0].update(das="7h"))
    assert "HH:MM" in _errors(data_copy)


def test_one_bad_action_does_not_hide_the_others(data_copy):
    edit_yaml(data_copy / "actions" / "basicas.yaml", lambda c: c["acoes"][3].update(tipo="esquisito"))
    data, report = load_data(data_copy, environ={})
    assert not report.ok
    assert "comer" in data.actions  # as outras ações do arquivo continuam carregadas


def test_env_expansion():
    raw = {"host": "${MQTT_HOST:-mqtt.local}", "lista": ["${X}", "a${Y:-b}c"], "n": 3}
    assert expand_env(raw, {}) == {"host": "mqtt.local", "lista": ["", "abc"], "n": 3}
    assert expand_env(raw, {"MQTT_HOST": "broker", "X": "1", "Y": "z"}) == {
        "host": "broker", "lista": ["1", "azc"], "n": 3,
    }


def test_env_overrides_world(data_copy):
    data, report = load_data(data_copy, environ={"MQTT_HOST": "broker.casa", "MQTT_PORT": "1999", "DW_SEED": "7"})
    assert report.ok, messages(report)
    assert data.world.mqtt.host == "broker.casa"
    assert data.world.mqtt.port == 1999
    assert data.world.seed == 7
