"""Curvas da Utility AI, janelas de horário e templates de texto."""

from __future__ import annotations

import pytest

from sim import curves, text
from sim.schemas import Curve, TimeWindow


def c(**kw) -> Curve:
    return Curve.model_validate(kw)


def test_linear_and_invert():
    assert curves.evaluate(c(tipo="linear"), 50) == pytest.approx(0.5)
    assert curves.evaluate(c(tipo="linear", inverter=True), 80) == pytest.approx(0.2)


def test_linear_uses_input_range():
    # afinidade vai de -100 a 100: 0 fica no meio
    assert curves.evaluate(c(tipo="linear"), 0, curves.input_range("afinidade")) == pytest.approx(0.5)


def test_power_curve():
    assert curves.evaluate(c(tipo="potencia", expoente=2), 50) == pytest.approx(0.25)


def test_logistic_curve_midpoint():
    assert curves.evaluate(c(tipo="logistica", meio=70), 70) == pytest.approx(0.5)
    assert curves.evaluate(c(tipo="logistica", meio=70), 100) > 0.9


def test_step_curve():
    curve = c(tipo="degrau", limite=50)
    assert curves.evaluate(curve, 49) == 0 and curves.evaluate(curve, 50) == 1


def test_points_curve_interpolates_and_clamps():
    curve = c(tipo="pontos", pontos=[[0, 0], [60, 0.6], [80, 1]])
    assert curves.evaluate(curve, 30) == pytest.approx(0.3)
    assert curves.evaluate(curve, 70) == pytest.approx(0.8)
    assert curves.evaluate(curve, 200) == 1
    assert curves.evaluate(curve, -5) == 0


def test_points_on_hour_scale():
    curve = c(tipo="pontos", pontos=[[0, 1], [6, 1], [8, 0.3], [24, 0.3]])
    assert curves.evaluate(curve, 7, curves.input_range("hora")) == pytest.approx(0.65)


def test_floor():
    assert curves.evaluate(c(tipo="linear", minimo=0.2), 0) == pytest.approx(0.2)


def test_unsorted_points_rejected():
    with pytest.raises(ValueError):
        c(tipo="pontos", pontos=[[50, 0], [10, 1]])


def test_time_window_across_midnight():
    window = TimeWindow.model_validate({"das": "22:00", "ate": "06:00"})
    assert window.contains(23 * 60) and window.contains(3 * 60)
    assert not window.contains(12 * 60)


def test_template_fill_and_render():
    stored = text.fill("{eu} toca o sino da {lugar} às {hora}. {bordao}", {
        "eu": "priest", "lugar": "cathedral", "hora": "06:00", "bordao": "Deus me livre e guarde!",
    })
    assert stored == "{@priest} toca o sino da {@cathedral} às 06:00. Deus me livre e guarde!"
    names = {"priest": "O Padre", "cathedral": "A Catedral"}
    assert text.render(stored, names) == "O Padre toca o sino da Catedral às 06:00. Deus me livre e guarde!"


def test_template_check():
    known = {"fool", "tavern"}
    assert text.check_template("{eu} e {@fool} em {lugar}", known) == []
    assert text.check_template("{eu} {xpto}", known)
    assert text.check_template("{@zzz}", known)
    assert text.check_template("{eu", known)


def test_render_contracts_articles_of_names():
    names = {"chief": "O Chefe", "square": "A Praça", "smith": "O Ferreiro", "mike": "Mike"}
    assert text.render("{@chief} chega em {@square}.", names) == "O Chefe chega na Praça."
    assert text.render("{@chief} vai rumo a {@square}.", names) == "O Chefe vai rumo à Praça."
    assert text.render("{@chief} e {@smith} conversam.", names) == "O Chefe e o Ferreiro conversam."
    assert text.render("{@smith} buzina pra {@mike}.", names) == "O Ferreiro buzina pra Mike."
