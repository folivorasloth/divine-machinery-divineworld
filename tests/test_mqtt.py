"""Fase 4: a ponte MQTT. Sem broker: um cliente de mentira (o que o paho faria).
Com o `mosquitto` instalado na máquina, um teste de ponta a ponta num broker local
de verdade (pulado se não houver)."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import CallbackAPIVersion

from server.mqtt_bridge import MqttBridge, parse_message
from server.runtime import Runtime
from sim.clock import WorldClock
from sim.events import Event
from sim.loader import load_data_or_raise
from tests.conftest import DATA


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


def test_parse_every_listened_topic(data):
    t = data.world.mqtt.topics
    c = parse_message(t, "world/commands", b'{"cmd": "chefe", "arg": "reconstruam a ferraria", "id": "x1"}')
    assert (c.cmd, c.arg, c.id) == ("chefe", "reconstruam a ferraria", "x1")
    c = parse_message(t, "world/commands", 'medium "a lua quer festa"'.encode())
    assert (c.cmd, c.arg) == ("medium", "a lua quer festa")
    assert parse_message(t, "sala/camera/pessoas", b'{"count": 2}').arg == "2"
    assert parse_message(t, "sala/camera/pessoas", b"0").arg == "0"
    c = parse_message(t, "homelab/servicos/jellyfin", b'{"status": "down", "name": "jellyfin"}')
    assert (c.cmd, c.arg) == ("homelab", "jellyfin down")
    assert parse_message(t, "homelab/servicos/nextcloud", b"UP").arg == "nextcloud up"
    c = parse_message(t, "telas/monitor_esquerda/status", b"offline")
    assert (c.cmd, c.arg) == ("tela", "monitor_esquerda offline")
    assert parse_message(t, "telas/parede_centro/status", b'{"status": "online"}').arg == "parede_centro online"
    assert parse_message(t, "telas/x/status", b"talvez") is None
    assert parse_message(t, "outro/topico", b"oi") is None


class FakeClient:
    """Faz o papel do paho.mqtt.Client (sem rede)."""

    def __init__(self, **kw):
        self.kw = kw
        self.published: list[tuple[str, str, bool]] = []
        self.subscribed: list[str] = []
        self.will = None

    def username_pw_set(self, *a):
        pass

    def will_set(self, topic, payload, qos=0, retain=False):
        self.will = (topic, payload, retain)

    def reconnect_delay_set(self, **kw):
        pass

    def connect_async(self, host, port, keepalive=60):
        self.host = (host, port)

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))
        return SimpleNamespace(wait_for_publish=lambda *_: None)


@pytest.fixture
def bridge(tmp_path):
    data = load_data_or_raise(DATA, environ={})
    start = WorldClock.parse_start(data.world.clock, "10:00")
    rt = Runtime(data_dir=str(DATA), db_path=str(tmp_path / "w.sqlite"), seed=2, start=start, mqtt=True, llm=False,
                 mqtt_client_factory=FakeClient, born_dir=str(tmp_path / "born"))
    b = rt.mqtt
    b.start()
    b._on_connect(b.client, None, {}, SimpleNamespace(is_failure=False))
    yield rt, b
    b.stop()
    rt.world.close()


def test_bridge_connects_with_lwt_and_subscribes(bridge):
    rt, b = bridge
    c = b.client
    assert c.kw["callback_api_version"] == CallbackAPIVersion.VERSION2
    assert c.will == ("world/status", "offline", True)
    assert set(c.subscribed) == {"world/commands", "sala/camera/pessoas", "homelab/servicos/#", "telas/+/status"}
    assert ("world/status", "online", True) in c.published
    state = [p for p in c.published if p[0] == "world/state"]
    assert state and state[0][2] is True and "places" in json.loads(state[0][1])


def test_messages_become_commands_and_results_are_published(bridge):
    rt, b = bridge
    w = rt.world
    msg = SimpleNamespace(topic="world/commands", payload=b'{"cmd": "chefe", "arg": "reconstruam a ferraria", "id": "m1"}')
    b._on_message(b.client, None, msg)
    b._on_message(b.client, None, SimpleNamespace(topic="homelab/servicos/jellyfin", payload=b"down"))
    b._on_message(b.client, None, SimpleNamespace(topic="telas/monitor_esquerda/status", payload=b"offline"))
    b._on_message(b.client, None, SimpleNamespace(topic="sala/camera/pessoas", payload=b'{"count": 1}'))
    w.tick()  # o mundo drena a fila no começo do tick
    assert w.creator.orders and w.creator.orders[-1]["text"] == "reconstruam a ferraria"
    assert any(c.service == "jellyfin" for c in w.creatures.active)
    assert {"forest", "mountain"} <= set(w.blocked_places)
    assert w.creator.presence["count"] == 1
    res = [json.loads(p[1]) for p in b.client.published if p[0] == "world/commands/result"]
    assert res and res[0]["id"] == "m1" and res[0]["result"]["ok"]


def test_events_chat_and_tunnel_are_published(bridge):
    rt, b = bridge
    w = rt.world
    b.client.published.clear()
    w.emit("speech", "{@clown}: \"Bibi!\"", actors=["clown", "fool"], place="market", tags=["conversa"],
           importance=0, data={"situation": "conversa"})
    w.emit("death", "{@mike} morre.", actors=["mike"], place="forest", tags=["morte"], importance=3)
    w.emit("teleport_started", "x", actors=["clown"], place="town_square", importance=1,
           data={"from_place": "town_square", "to_place": "forest", "from_screen": "parede_centro",
                 "to_screen": "monitor_esquerda", "duration_s": 3.5})
    w.emit("decision", "debug", actors=["clown"])
    topics = [p[0] for p in b.client.published]
    chat = json.loads(next(p[1] for p in b.client.published if p[0] == "world/chat"))
    assert chat["from"] == "clown" and chat["meta"]["to"] == "fool" and "Bibi" in chat["text"]
    events = [json.loads(p[1]) for p in b.client.published if p[0] == "world/events"]
    assert [e["type"] for e in events] == ["death", "teleport_started"]  # rotina (importância 0) não vai
    led = json.loads(next(p[1] for p in b.client.published if p[0] == "leds/tunnel"))
    assert led["phase"] == "start" and led["duration_ms"] == 3500 and led["from_cm"] and led["color"].startswith("#")
    assert "decision" not in " ".join(topics)


def test_no_broker_the_world_goes_on(tmp_path, monkeypatch, caplog):
    def port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p
    monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("MQTT_PORT", str(port()))
    start = WorldClock.parse_start(load_data_or_raise(DATA).world.clock, "10:00")
    rt = Runtime(data_dir=str(DATA), db_path=str(tmp_path / "w.sqlite"), seed=2, start=start, fast=True, llm=False,
                 born_dir=str(tmp_path / "born"))
    rt.start()
    try:
        time.sleep(1.5)
        assert rt.alive and not rt.mqtt.connected
        assert rt.snapshot()["ticks"] > 10
    finally:
        rt.stop()


# ----------------------------------------------------- broker de verdade (opcional)
@pytest.mark.skipif(shutil.which("mosquitto") is None, reason="mosquitto não instalado")
def test_end_to_end_with_real_mosquitto(tmp_path, monkeypatch):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    conf = tmp_path / "m.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n")
    proc = subprocess.Popen(["mosquitto", "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
        monkeypatch.setenv("MQTT_PORT", str(port))
        got: dict[str, list] = {}
        sub = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id="teste")
        sub.on_message = lambda c, u, m: got.setdefault(m.topic, []).append(m.payload.decode())
        sub.connect("127.0.0.1", port)
        sub.subscribe("#")
        sub.loop_start()
        start = WorldClock.parse_start(load_data_or_raise(DATA).world.clock, "10:00")
        rt = Runtime(data_dir=str(DATA), db_path=str(tmp_path / "w.sqlite"), seed=2, start=start, speed=600,
                     llm=False, born_dir=str(tmp_path / "born"))
        rt.start()
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not rt.mqtt.connected:
                time.sleep(0.1)
            assert rt.mqtt.connected
            sub.publish("world/commands", json.dumps({"cmd": "nascer", "arg": "alegre", "id": "e2e"}))
            sub.publish("homelab/servicos/jellyfin", json.dumps({"status": "down"}))
            deadline = time.time() + 10
            while time.time() < deadline and not (got.get("world/commands/result") and got.get("world/state")):
                time.sleep(0.1)
            assert got["world/status"][-1] == "online"
            result = json.loads(got["world/commands/result"][0])
            assert result["id"] == "e2e" and result["result"]["ok"]
            assert "places" in json.loads(got["world/state"][-1])
            deadline = time.time() + 5
            while time.time() < deadline and not any(c.service == "jellyfin" for c in rt.world.creatures.active):
                time.sleep(0.1)
            assert any(c.service == "jellyfin" for c in rt.world.creatures.active)
            assert any(json.loads(e)["type"] == "birth" for e in got.get("world/events", []))
        finally:
            rt.stop()
        time.sleep(0.3)
        assert got["world/status"][-1] == "offline"
        sub.loop_stop()
        sub.disconnect()
    finally:
        proc.terminate()
        proc.wait(timeout=5)
