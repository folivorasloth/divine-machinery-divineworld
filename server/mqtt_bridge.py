"""Ponte MQTT (paho-mqtt 2.x) — seção 13.4 de docs/arquitetura.md.

Publica (tópicos em world.yaml > mqtt.topicos):
  world/events   eventos com importância >= 1 (JSON da seção 8)
  world/state    resumo, RETIDO, a cada `estado_a_cada_minutos` (minutos reais ÷ velocidade, mín. 2 s)
  world/chat     falas, no molde de npc/<id>/fala do ecossistema
  leds/tunnel    início e fim de cada teletransporte (para o WLED)
  world/status   online/offline, retido, com Last Will
  world/commands/result  resposta de cada comando recebido
Escuta:
  world/commands          {"cmd": "chefe", "arg": "..."} ou texto "chefe reconstruam a ferraria"
  sala/camera/pessoas     {"count": n} ou número  -> comando `presenca n`
  homelab/servicos/<nome> {"status": "down"|"up"|"degraded"} ou texto  -> `homelab <nome> <status>`
  telas/<id>/status       "online"/"offline" (ou {"status": ...})  -> `tela <id> online|offline`

Regra do ecossistema: o handler de mensagem NÃO faz nada pesado — só converte o
payload num `Command` e põe na fila do mundo. Broker fora do ar: um aviso por
queda no log e a simulação segue; o paho tenta reconectar sozinho.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import TYPE_CHECKING

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from sim.engine import Command

if TYPE_CHECKING:  # pragma: no cover
    from server.runtime import Runtime
    from sim.events import Event

log = logging.getLogger("server.mqtt")


def _text(payload: bytes) -> str:
    try:
        return payload.decode("utf-8").strip()
    except UnicodeDecodeError:
        return ""


def _json_or_text(payload: bytes):
    raw = _text(payload)
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def parse_message(topics, topic: str, payload: bytes) -> Command | None:
    """Payload de um tópico escutado -> Command (ou None se não der para entender).
    Separado do cliente para dar para testar sem broker."""
    value = _json_or_text(payload)
    if mqtt.topic_matches_sub(topics.commands, topic):
        if isinstance(value, dict) and value.get("cmd"):
            return Command(cmd=str(value["cmd"]).strip(), arg=str(value.get("arg", "")).strip(),
                           id=str(value.get("id", "") or ""))
        if isinstance(value, str) and value:
            cmd, _, arg = value.partition(" ")
            return Command(cmd=cmd.strip(), arg=arg.strip().strip('"'))
        return None
    if mqtt.topic_matches_sub(topics.presence, topic):
        count = value.get("count", value.get("pessoas", value.get("people"))) if isinstance(value, dict) else value
        try:
            n = int(float(count))
        except (TypeError, ValueError):
            if isinstance(count, bool):
                n = int(count)
            elif str(count).lower() in ("true", "on", "sim", "presente"):
                n = 1
            elif str(count).lower() in ("false", "off", "nao", "ausente"):
                n = 0
            else:
                return None
        return Command(cmd="presenca", arg=str(n))
    if mqtt.topic_matches_sub(topics.homelab, topic):
        service = topic.rstrip("/").split("/")[-1]
        status = value.get("status") if isinstance(value, dict) else value
        if isinstance(value, dict) and value.get("name"):
            service = str(value["name"])
        if not status:
            return None
        service = service.replace(" ", "_")
        return Command(cmd="homelab", arg=f"{service} {str(status).strip().lower()}")
    if mqtt.topic_matches_sub(topics.screen_status, topic):
        parts = topic.split("/")
        screen = parts[1] if len(parts) >= 3 else ""
        status = value.get("status") if isinstance(value, dict) else value
        status = str(status).strip().lower()
        status = {"on": "online", "off": "offline", "1": "online", "0": "offline",
                  "true": "online", "false": "offline"}.get(status, status)
        if screen and status in ("online", "offline"):
            return Command(cmd="tela", arg=f"{screen} {status}")
        return None
    return None


class MqttBridge:
    def __init__(self, runtime: "Runtime", client_factory=None):
        self.runtime = runtime
        self.cfg = runtime.data.world.mqtt
        self.topics = self.cfg.topics
        factory = client_factory or (lambda **kw: mqtt.Client(**kw))
        self.client = factory(callback_api_version=CallbackAPIVersion.VERSION2, client_id=self.cfg.client_id)
        if self.cfg.username:
            self.client.username_pw_set(self.cfg.username, self.cfg.password or None)
        self.client.will_set(self.topics.status, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        if hasattr(self.client, "on_connect_fail"):
            self.client.on_connect_fail = self._on_connect_fail
        self.client.reconnect_delay_set(min_delay=1, max_delay=max(1, int(self.cfg.reconnect_seconds)))
        self.connected = False
        self._warned = False
        self.received = 0
        self.published = 0
        self._stop = threading.Event()
        self._state_thread: threading.Thread | None = None

    # ----------------------------------------------------------- ciclo
    def start(self) -> None:
        try:
            self.client.connect_async(self.cfg.host, int(self.cfg.port), keepalive=60)
            self.client.loop_start()
        except Exception as exc:  # host inválido etc.: a simulação segue
            self._warn(f"MQTT não conectou ({exc}); a simulação continua sem MQTT.")
        self._state_thread = threading.Thread(target=self._state_loop, name="mqtt-estado", daemon=True)
        self._state_thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self.connected:
                self.client.publish(self.topics.status, "offline", qos=1, retain=True).wait_for_publish(2)
            self.client.disconnect()
            self.client.loop_stop()
        except Exception:  # pragma: no cover
            pass

    def summary(self) -> dict:
        return {"ativo": True, "conectado": self.connected, "host": self.cfg.host, "recebidas": self.received,
                "publicadas": self.published}

    def _warn(self, message: str) -> None:
        if not self._warned:
            log.warning(message)
            self._warned = True

    # ------------------------------------------------------- callbacks
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if getattr(reason_code, "is_failure", False):
            self._warn(f"MQTT recusou a conexão: {reason_code}")
            return
        self.connected = True
        self._warned = False
        log.info("MQTT conectado em %s:%s", self.cfg.host, self.cfg.port)
        for topic in (self.topics.commands, self.topics.presence, self.topics.homelab, self.topics.screen_status):
            client.subscribe(topic, qos=1)
        client.publish(self.topics.status, "online", qos=1, retain=True)
        self.publish_state()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        if self.connected:
            log.warning("MQTT desconectado (%s); tentando de novo a cada %ss.", reason_code,
                        self.cfg.reconnect_seconds)
        self.connected = False

    def _on_connect_fail(self, client, userdata):
        self._warn(f"MQTT fora do ar ({self.cfg.host}:{self.cfg.port}); a simulação continua e tenta de novo.")

    def _on_message(self, client, userdata, msg):
        """Só converte e enfileira (nada pesado no handler)."""
        self.received += 1
        try:
            cmd = parse_message(self.topics, msg.topic, msg.payload)
        except Exception:  # pragma: no cover - payload muito estranho
            log.exception("mensagem MQTT ilegível em %s", msg.topic)
            return
        if cmd is None:
            log.info("MQTT: ignorando %s %r", msg.topic, msg.payload[:80])
            return
        if mqtt.topic_matches_sub(self.topics.commands, msg.topic):
            cmd.reply = _Reply(self, cmd)
        self.runtime.world.submit(cmd)

    # ------------------------------------------------------- publicação
    def _publish(self, topic: str, payload, retain: bool = False) -> None:
        if not self.connected:
            return
        data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        self.client.publish(topic, data, qos=0, retain=retain)
        self.published += 1

    def on_event(self, ev: "Event") -> None:
        """Assinante do EventBus (thread da simulação): publish do paho não bloqueia."""
        if not self.connected or ev.type in ("decision", "tension"):
            return
        world = self.runtime.world
        names = world.names()
        if ev.type in ("teleport_started", "teleport_finished"):
            self._publish(self.topics.tunnel_leds, self.tunnel_payload(ev))
        if ev.importance >= 1:
            self._publish(self.topics.events, ev.to_dict(names))
        if ev.type == "speech" and ev.actors:
            d = ev.data
            self._publish(self.topics.chat, {
                "from": ev.actors[0], "from_name": names.get(ev.actors[0], ev.actors[0]),
                "text": ev.render(names), "ts": ev.real_ts,
                "meta": {"world_ts": ev.ts, "place": ev.place, "to": ev.actors[1] if len(ev.actors) > 1 else None,
                         "situation": d.get("situation"), "tags": ev.tags}})

    def tunnel_payload(self, ev: "Event") -> dict:
        world = self.runtime.world
        d = ev.data
        screens = {s.id: s for s in world.data.world.screens}

        def center(sid):
            s = screens.get(sid)
            if s is None:
                return None
            return {"x": s.position_cm.x + s.size_cm.width / 2, "y": s.position_cm.y + s.size_cm.height / 2}
        char = world.data.characters.get(ev.actors[0]) if ev.actors else None
        return {"phase": "start" if ev.type == "teleport_started" else "end", "char": ev.actors[0] if ev.actors else None,
                "from_screen": d.get("from_screen"), "to_screen": d.get("to_screen"),
                "from_cm": center(d.get("from_screen")), "to_cm": center(d.get("to_screen")),
                "duration_ms": int(float(d.get("duration_s") or 0) * 1000),
                "color": char.visual.color if char else "#ffffff"}

    def state_payload(self) -> dict:
        snap = self.runtime.snapshot()
        places: dict[str, list[str]] = {}
        for cid, c in (snap.get("characters") or {}).items():
            if c["alive"] and not c["away"]:
                places.setdefault(c["place"], []).append(cid)
        return {"ts": snap.get("ts"), "period": snap.get("period"), "is_night": snap.get("is_night"),
                "weather": snap.get("weather"), "tension": snap.get("tension"),
                "population": snap.get("population"), "alive": sorted(c for v in places.values() for c in v),
                "places": {k: sorted(v) for k, v in sorted(places.items())}, "fog": snap.get("fog", []),
                "paused": snap.get("paused"), "speed": snap.get("speed")}

    def publish_state(self) -> None:
        self._publish(self.topics.state, self.state_payload(), retain=True)

    def _state_loop(self) -> None:
        while not self._stop.is_set():
            speed = max(0.001, float(self.runtime.world.speed))
            every = max(2.0, self.cfg.state_every_minutes * 60 / speed)
            if self._stop.wait(every):
                return
            try:
                self.publish_state()
            except Exception:  # pragma: no cover
                log.exception("falha ao publicar world/state")

    def publish_result(self, cmd: Command, result: dict) -> None:
        self._publish(self.topics.command_results, {"id": cmd.id, "cmd": cmd.cmd, "arg": cmd.arg,
                                                    "result": result, "ts": time.time()})


class _Reply:
    """Faz o papel do Future: quando o mundo executa o comando, publica a resposta."""

    def __init__(self, bridge: MqttBridge, cmd: Command):
        self.bridge = bridge
        self.cmd = cmd
        self._done = False

    def done(self) -> bool:
        return self._done

    def set_result(self, result) -> None:
        self._done = True
        try:
            self.bridge.publish_result(self.cmd, result)
        except Exception:  # pragma: no cover
            log.exception("falha ao publicar a resposta do comando")
