"""Clima (Fase 3): real de Botucatu pelo Open-Meteo, com cache e plano B.

De onde vem o clima (`world.yaml > clima.modo`):

- `real`: pergunta ao Open-Meteo (grátis, sem chave) a cada `atualizar_minutos`.
  A pergunta roda numa thread separada (a simulação nunca espera a internet).
  A última resposta boa fica no `cache_arquivo`; sem internet, usa o cache;
  sem cache, o `clima_padrao`.
- `simulado`: sorteia o clima com o RNG do mundo (troca a cada
  `simulado.troca_a_cada_horas`, com os `pesos` de cada tipo). É o que vale
  com o tempo acelerado: não faz sentido pôr a chuva de agora num dia que o
  mundo simula em 5 segundos. Reproduzível com a seed.
- `auto` (padrão): `real` quando o mundo está no relógio real (velocidade 1 e
  hora do mundo perto da hora real); `simulado` no resto.
- `fixo`: sempre o `clima_padrao`.

Por cima disso, um clima pode ser FORÇADO por um tempo (o funeral: sempre
chove; eventos do diretor com `efeitos.clima`). O forçado ganha do resto.

O clima entra no mundo de três jeitos (tudo no YAML, `clima.efeitos`):
multiplica taxas de necessidades, multiplica notas de ações (e de qualquer
ação em lugar externo), e quem tem medo do clima (`medos.gatilho: chuva`)
ganha medo por hora. Também é filtro de falas (`climas: [chuva]`) e a
variável `{clima}`.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World

log = logging.getLogger("sim.weather")

REAL_TIME_TOLERANCE_MINUTES = 180  # "auto": o mundo está no relógio real se a diferença for menor


@dataclass
class WeatherNow:
    kind: str  # id em clima.tipos
    label: str  # nome em português ({clima})
    temp: float | None = None
    code: int | None = None
    source: str = "padrao"  # real | cache | simulado | padrao | forcado
    forced: str | None = None  # motivo do clima forçado (funeral, diretor)


def kind_for_code(world_cfg, code: int | None) -> str:
    for kid, kind in world_cfg.weather.kinds.items():
        if code is not None and code in kind.codes:
            return kid
    return world_cfg.weather.fallback


def fetch_open_meteo(cfg, client=None) -> dict:
    """Uma pergunta ao Open-Meteo. Devolve {"code", "temp", "fetched_at"}. Lança exceção se falhar.
    `client` permite trocar o httpx nos testes (nada de rede nos testes)."""
    params = {"latitude": cfg.latitude, "longitude": cfg.longitude,
              "current": "temperature_2m,weather_code", "timezone": "UTC"}
    if client is None:
        import httpx

        with httpx.Client(timeout=cfg.timeout_seconds) as c:
            resp = c.get(cfg.url, params=params)
    else:
        resp = client.get(cfg.url, params=params)
    resp.raise_for_status()
    cur = resp.json()["current"]
    return {"code": int(cur["weather_code"]), "temp": float(cur["temperature_2m"]),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


class Weather:
    """Estado do clima do mundo. `update()` é chamado a cada tick (barato)."""

    def __init__(self, world: "World", fetcher=None):
        self.world = world
        self.cfg = world.data.world.weather
        self.fetcher = fetcher or (lambda: fetch_open_meteo(self.cfg))
        fb = self.cfg.fallback
        self.base = WeatherNow(kind=fb, label=self._label(fb))
        self.forced: dict | None = None  # {"kind", "until", "reason"}
        self.next_change: float | None = None  # simulado: próxima troca (minuto absoluto)
        self.next_fetch: float = 0.0  # real: próxima pergunta (minuto absoluto)
        self._pending: dict | None = None  # resposta da thread, aplicada no próximo tick
        self._fetching = False
        self._lock = threading.Lock()
        self.last_announced: str | None = None
        self.failures = 0

    # ---------------------------------------------------------------- leitura
    def _label(self, kind: str) -> str:
        k = self.cfg.kinds.get(kind)
        return k.name if k else kind

    @property
    def now(self) -> WeatherNow:
        if self.forced is not None:
            kind = self.forced["kind"]
            return WeatherNow(kind=kind, label=self._label(kind), temp=self.base.temp, source="forcado",
                              forced=self.forced["reason"])
        return self.base

    @property
    def kind(self) -> str:
        return self.now.kind

    @property
    def label(self) -> str:
        return self.now.label

    def is_rain(self) -> bool:
        k = self.cfg.kinds.get(self.kind)
        return bool(k and k.rain)

    def effect_keys(self) -> list[str]:
        """Chaves de clima.efeitos que valem agora: o tipo e, se for o caso, frio/calor."""
        keys = [self.kind]
        temp = self.now.temp
        if temp is not None:
            if temp < self.cfg.cold_below:
                keys.append("frio")
            elif temp > self.cfg.hot_above:
                keys.append("calor")
        return keys

    # ------------------------------------------------------------ atualização
    def mode(self) -> str:
        mode = self.cfg.mode
        if mode != "auto":
            return mode
        w = self.world
        real_now = datetime.now(w.clock.tz)
        near = abs((real_now - w.clock.now).total_seconds()) / 60 < REAL_TIME_TOLERANCE_MINUTES
        # real só quando o mundo está rodando no relógio de verdade (run sem --fast,
        # velocidade 1, hora do mundo perto da hora real). Testes e --fast: sorteado.
        return "real" if (w.realtime and w.speed <= 1 and near) else "simulado"

    def force(self, kind: str, minutes: float, reason: str) -> None:
        until = self.world.now_minutes() + minutes
        if self.forced is not None and self.forced["until"] > until and self.forced["kind"] == kind:
            return  # já está forçado por mais tempo
        self.forced = {"kind": kind, "until": until, "reason": reason}
        self._announce()

    def update(self) -> None:
        now = self.world.now_minutes()
        if self.forced is not None and now >= self.forced["until"]:
            self.forced = None
            self._announce()
        mode = self.mode()
        if mode == "real":
            self._update_real(now)
        elif mode == "simulado":
            self._update_simulated(now)
        elif mode == "fixo" and self.base.kind != self.cfg.fallback:
            self.base = WeatherNow(kind=self.cfg.fallback, label=self._label(self.cfg.fallback))
            self._announce()

    def _update_simulated(self, now: float) -> None:
        if self.next_change is not None and now < self.next_change:
            return
        rng = self.world.rng
        sim = self.cfg.simulated
        kinds = sorted(k for k in sim.weights if sim.weights[k] > 0) or [self.cfg.fallback]
        weights = [sim.weights.get(k, 1.0) for k in kinds]
        # o clima tende a continuar como está (a chuva não liga e desliga a cada hora)
        if self.base.kind in kinds:
            weights[kinds.index(self.base.kind)] *= 2
        from sim.rng import weighted_choice

        kind = weighted_choice(rng, kinds, weights)
        low, high = sim.temp_night if self.world.clock.is_night() else sim.temp_day
        temp = round(rng.uniform(low, high), 1)
        self.next_change = now + rng.uniform(*sim.change_hours) * 60
        changed = kind != self.base.kind
        self.base = WeatherNow(kind=kind, label=self._label(kind), temp=temp, source="simulado")
        if changed:
            self._announce()

    def _update_real(self, now: float) -> None:
        with self._lock:
            pending, self._pending = self._pending, None
        if pending is not None:
            self._apply_real(pending, "real")
        if now >= self.next_fetch and not self._fetching:
            self.next_fetch = now + self.cfg.refresh_minutes
            if self.base.source == "padrao":
                cached = self.load_cache()
                if cached:
                    self._apply_real(cached, "cache")
            self._fetching = True
            threading.Thread(target=self._fetch_in_background, daemon=True, name="clima").start()

    def _fetch_in_background(self) -> None:
        try:
            result = self.fetcher()
        except Exception as exc:  # sem internet, timeout, resposta estranha: segue com o que tem
            self.failures += 1
            if self.failures == 1:
                log.warning("clima: Open-Meteo indisponível (%s); usando cache ou clima_padrao", exc)
            result = None
        else:
            self.failures = 0
            self.save_cache(result)
        with self._lock:
            if result is not None:
                self._pending = result
            self._fetching = False

    def fetch_now(self) -> bool:
        """Pergunta na hora, sem thread (testes e ferramentas). True se deu certo."""
        try:
            result = self.fetcher()
        except Exception:
            cached = self.load_cache()
            if cached:
                self._apply_real(cached, "cache")
            return False
        self.save_cache(result)
        self._apply_real(result, "real")
        return True

    def _apply_real(self, raw: dict, source: str) -> None:
        kind = kind_for_code(self.world.data.world, raw.get("code"))
        changed = kind != self.base.kind
        self.base = WeatherNow(kind=kind, label=self._label(kind), temp=raw.get("temp"), code=raw.get("code"),
                               source=source)
        if changed:
            self._announce()

    # ------------------------------------------------------------------ cache
    def cache_path(self) -> Path:
        path = Path(self.cfg.cache_file)
        return path

    def load_cache(self) -> dict | None:
        try:
            return json.loads(self.cache_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_cache(self, raw: dict) -> None:
        try:
            path = self.cache_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - disco cheio/sem permissão: não para o mundo
            log.warning("clima: não consegui gravar o cache (%s)", exc)

    # ------------------------------------------------------------------ chat
    def _announce(self) -> None:
        now = self.now
        key = f"{now.kind}:{now.forced}"
        if key == self.last_announced:
            return
        self.last_announced = key
        w = self.world
        situation = "clima_funeral" if now.forced == "funeral" else f"clima_{now.kind}"
        text = None
        if situation in w.data.lines or f"clima_{now.kind}" in w.data.lines:
            from sim import speech

            # o "narrador" do clima é o mundo: usa o primeiro vivo só para preencher variáveis
            narrator = next((c for c, st in sorted(w.states.items()) if st.alive), None)
            if narrator is not None:
                ctx = w._speech_ctx(narrator, w.data.world.central_place)
                for sit in (situation, f"clima_{now.kind}"):
                    text = speech.pick_line(w.data, sit, ctx, w.rng, None) if sit in w.data.lines else None
                    if text:
                        break
        if not text:
            text = f"O tempo muda: {now.label}."
        if w.storage is not None:
            w.storage.log_weather(w.clock.iso(), now.kind, now.label, now.temp, now.source, now.forced)
        w.emit("weather_changed", text, tags=["clima"], importance=1 if now.forced else 0,
               data={"kind": now.kind, "label": now.label, "temp": now.temp, "code": now.code,
                     "source": now.source, "forced": now.forced})

    # ----------------------------------------------------------- persistência
    def to_json(self) -> dict:
        return {"base": asdict(self.base), "forced": self.forced, "next_change": self.next_change,
                "last_announced": self.last_announced}

    def load(self, raw: dict) -> None:
        if not raw:
            return
        try:
            self.base = WeatherNow(**raw["base"])
        except (KeyError, TypeError):
            pass
        self.forced = raw.get("forced")
        self.next_change = raw.get("next_change")
        self.last_announced = raw.get("last_announced")
