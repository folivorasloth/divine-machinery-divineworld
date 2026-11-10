"""Relógio do mundo.

O mundo anda em passos fixos (`relogio.passo_minutos`, padrão 1 minuto do
mundo por tick). Quem decide QUANDO dar o próximo passo é o laço do
`sim.engine.World.run` (tempo real × multiplicador, ou o mais rápido possível
no modo `--fast`). Este módulo só sabe dizer que horas são, em que período
estamos e se é noite.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sim.schemas import ClockConfig, time_to_minutes


class WorldClock:
    def __init__(self, config: ClockConfig, now: datetime):
        self.config = config
        self.tz = ZoneInfo(config.timezone)
        self.now = now.astimezone(self.tz)
        # períodos em minutos do dia, em ordem (o validador garante a ordem)
        self._periods = [(time_to_minutes(p.start), p.id, p.name) for p in config.periods]
        self._day_start = time_to_minutes(config.day_start)
        self._night_start = time_to_minutes(config.night_start)

    @classmethod
    def parse_start(cls, config: ClockConfig, value: str | None, real_now: datetime | None = None) -> datetime:
        """Hora inicial de um mundo NOVO. Aceita None (agora), "05:30" (hoje
        nesse horário) ou um ISO completo ("2026-11-09T05:30")."""
        tz = ZoneInfo(config.timezone)
        base = (real_now or datetime.now(tz)).astimezone(tz)
        if not value:
            return base.replace(second=0, microsecond=0)
        if len(value) <= 5 and ":" in value:
            minutes = time_to_minutes(value if len(value) == 5 else "0" + value)
            midnight = base.replace(hour=0, minute=0, second=0, microsecond=0)
            return midnight + timedelta(minutes=minutes)
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.astimezone(tz)

    # ------------------------------------------------------------------ passos
    @property
    def step_minutes(self) -> float:
        return self.config.step_minutes

    def advance(self, minutes: float | None = None) -> None:
        self.now = self.now + timedelta(minutes=self.step_minutes if minutes is None else minutes)

    # ------------------------------------------------------------- consultas
    def minute_of_day(self) -> int:
        return self.now.hour * 60 + self.now.minute

    def hour_float(self) -> float:
        """15:30 -> 15.5 (entrada `hora` das curvas)."""
        return self.now.hour + self.now.minute / 60 + self.now.second / 3600

    def period(self) -> str:
        minute = self.minute_of_day()
        current = self._periods[0][1]
        for start, pid, _name in self._periods:
            if start <= minute:
                current = pid
        return current

    def period_name(self, pid: str | None = None) -> str:
        pid = pid or self.period()
        for _start, p, name in self._periods:
            if p == pid:
                return name
        return pid

    def is_night(self) -> bool:
        minute = self.minute_of_day()
        return minute >= self._night_start or minute < self._day_start

    def hhmm(self) -> str:
        return self.now.strftime("%H:%M")

    def iso(self) -> str:
        return self.now.isoformat(timespec="seconds")
