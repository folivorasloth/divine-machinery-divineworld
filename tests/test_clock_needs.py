"""Relógio (períodos, dia/noite) e necessidades (taxas, traços, modos)."""

from __future__ import annotations

from datetime import datetime

import pytest

from sim import needs
from sim.clock import WorldClock
from sim.loader import load_data_or_raise
from tests.conftest import DATA


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


def make_clock(data, hhmm: str) -> WorldClock:
    start = WorldClock.parse_start(data.world.clock, hhmm, real_now=datetime(2026, 11, 9, 12, 0))
    return WorldClock(data.world.clock, start)


def test_periods_and_night(data):
    assert make_clock(data, "03:00").period() == "madrugada"
    assert make_clock(data, "06:00").period() == "manha"
    assert make_clock(data, "12:30").period() == "tarde"
    assert make_clock(data, "19:00").period() == "noite"
    assert make_clock(data, "05:59").is_night()
    assert not make_clock(data, "06:00").is_night()
    assert not make_clock(data, "18:29").is_night()
    assert make_clock(data, "18:30").is_night()


def test_clock_advances_and_crosses_midnight(data):
    clock = make_clock(data, "23:59")
    clock.advance()
    assert clock.hhmm() == "00:00"
    assert clock.now.day == 10
    assert clock.hour_float() == 0
    clock.advance(90)
    assert clock.hhmm() == "01:30" and clock.hour_float() == 1.5


def test_parse_start_iso_keeps_timezone(data):
    start = WorldClock.parse_start(data.world.clock, "2026-11-09T05:30")
    assert start.isoformat().startswith("2026-11-09T05:30:00-03:00")


def test_hunger_accumulates_faster_by_day(data):
    char = data.characters["florist"]  # sem multiplicador de fome
    day = {"fome": 10.0}
    night = {"fome": 10.0}
    for _ in range(60):
        needs.natural_change(data, char, day, is_night=False, dt_minutes=1)
        needs.natural_change(data, char, night, is_night=True, dt_minutes=1)
    rate = data.world.needs["fome"]
    assert day["fome"] == pytest.approx(10 + rate.rate_day)
    assert night["fome"] == pytest.approx(10 + rate.rate_night)


def test_traits_and_character_multiply_rates(data):
    # o Chefe: sono taxa 1.2 no arquivo × traço preguicoso 1.3
    chief = data.characters["chief"]
    assert needs.rate_multiplier(data, chief, "sono") == pytest.approx(1.2 * 1.3)
    # Mike: social 0.2 no arquivo × traço vazio 0.2
    assert needs.rate_multiplier(data, data.characters["mike"], "social") == pytest.approx(0.2 * 0.2)


def test_return_mode_goes_back_to_base_without_passing(data):
    char = data.characters["florist"]
    values = {"raiva": 80.0, "medo": 0.0}
    for _ in range(60 * 24):
        needs.natural_change(data, char, values, is_night=False, dt_minutes=1)
    assert values["raiva"] == pytest.approx(data.world.needs["raiva"].base)
    assert values["medo"] == pytest.approx(data.world.needs["medo"].base)


def test_sleeping_does_not_gain_sleep_and_values_are_clamped(data):
    char = data.characters["fool"]
    values = {"sono": 50.0, "fome": 99.0}
    needs.natural_change(data, char, values, is_night=True, dt_minutes=60, sleeping=True)
    assert values["sono"] == 50.0
    assert values["fome"] == 100.0  # não passa de 100
    needs.apply_effect(values, {"sono": -200}, 1.0)
    assert values["sono"] == 0.0


def test_mood_word_comes_from_highest_need(data):
    assert needs.mood(data, {"fome": 90, "sono": 70}) == data.world.needs["fome"].mood
    assert needs.mood(data, {"fome": 10}) == data.world.neutral_mood
