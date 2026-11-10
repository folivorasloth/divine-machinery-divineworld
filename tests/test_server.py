"""Fase 4: a API HTTP e o WebSocket (FastAPI TestClient; sem MQTT e sem Ollama)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.runtime import Runtime
from sim.clock import WorldClock
from sim.loader import load_data_or_raise
from tests.conftest import DATA


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("server")
    data = load_data_or_raise(DATA, environ={})
    start = WorldClock.parse_start(data.world.clock, "07:00")
    rt = Runtime(data_dir=str(DATA), db_path=str(tmp / "w.sqlite"), speed=600, seed=11, start=start, new=True,
                 mqtt=False, llm=False, born_dir=str(tmp / "born"))
    app = create_app(rt)
    with TestClient(app) as c:
        deadline = time.time() + 10
        while time.time() < deadline and (c.get("/api/state").json().get("ticks") or 0) < 5:
            time.sleep(0.1)
        yield c


def test_health_and_state(client):
    h = client.get("/health").json()
    assert h["ok"] and h["simulating"] and h["mqtt"] == {"ativo": False}
    s = client.get("/api/state").json()
    for key in ("ts", "period", "weather", "tension", "population", "paused", "speed"):
        assert key in s
    assert s["population"] >= 21 and s["speed"] == 600


def test_characters_places_screens_meta(client):
    chars = client.get("/api/characters").json()
    ids = {c["id"] for c in chars}
    assert {"clown", "chief", "mike"} <= ids
    clown = next(c for c in chars if c["id"] == "clown")
    assert clown["name"] and clown["place"] and "action" in clown
    sheet = client.get("/api/characters/clown").json()
    assert sheet["id"] == "clown" and "necessidades" in sheet and "memorias" in sheet
    assert client.get("/api/characters/ninguem").status_code == 404
    places = client.get("/api/places").json()
    forge = next(p for p in places if p["id"] == "forge")
    assert forge["screen"] == "parede_centro" and forge["structures"]
    screens = client.get("/api/screens").json()
    assert {s["id"] for s in screens} >= {"parede_centro", "tela_homelab"}
    meta = client.get("/api/meta").json()
    assert meta["categories"] and meta["characters"] and "chefe" in meta["commands"]


def test_commands_and_chat_filters(client):
    r = client.post("/api/commands", json={"cmd": "chefe", "arg": "reconstruam a ferraria"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "feito" and body["result"]["ok"] and body["result"]["kind"] == "reconstruir"
    assert client.get(f"/api/commands/{body['id']}").json()["cmd"] == "chefe"
    assert client.post("/api/commands", json={"cmd": "voar"}).status_code == 400
    st = client.post("/api/commands", json={"cmd": "status"}).json()["result"]["status"]
    assert st["ordens"][-1]["texto"] == "reconstruam a ferraria"
    time.sleep(0.3)
    chat = client.get("/api/chat", params={"type": "creator_command"}).json()["events"]
    assert chat and "reconstruam a ferraria" in chat[0]["text_rendered"]
    by_tag = client.get("/api/chat", params={"tag": "criador", "limit": 50}).json()["events"]
    assert by_tag and all("criador" in e["tags"] for e in by_tag)
    by_char = client.get("/api/chat", params={"character": "chief", "limit": 30}).json()["events"]
    assert by_char and all("chief" in e["actors"] for e in by_char)
    by_place = client.get("/api/chat", params={"place": "town_square", "limit": 30}).json()["events"]
    assert all(e["place"] == "town_square" for e in by_place)
    every = client.get("/api/chat", params={"limit": 500}).json()["events"]
    mid = every[len(every) // 2]["ts"]
    later = client.get("/api/chat", params={"since": mid, "limit": 500}).json()["events"]
    assert later and all(e["ts"] >= mid for e in later)
    earlier = client.get("/api/chat", params={"until": mid, "limit": 500}).json()["events"]
    assert earlier and all(e["ts"] <= mid for e in earlier)
    assert all(e["type"] not in ("move_started", "move_arrived") for e in every)
    tl = client.get("/api/timeline", params={"min_importance": 1}).json()["events"]
    assert tl and all(e["importance"] >= 1 for e in tl)


def test_pause_and_continue(client):
    assert client.post("/api/commands", json={"cmd": "pausar"}).json()["result"]["paused"] is True
    t1 = client.get("/api/state").json()["ticks"]
    time.sleep(0.4)
    assert client.get("/api/state").json()["ticks"] == t1
    assert client.post("/api/commands", json={"cmd": "continuar"}).json()["result"]["paused"] is False


def test_chat_page_is_served(client):
    r = client.get("/chat")
    assert r.status_code == 200 and "Chat do Mundo" in r.text and "/ws/chat" in r.text
    assert client.get("/viewer/chat.html").status_code == 200


def test_ws_chat_streams_live_events(client):
    with client.websocket_connect("/ws/chat") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["places"]
        client.post("/api/commands", json={"cmd": "nascer", "arg": "alegre"})
        got = []
        deadline = time.time() + 10
        while time.time() < deadline:
            msg = ws.receive_json()
            if msg["type"] == "event":
                got.append(msg["event"])
                if any(e["type"] == "birth" for e in got):
                    break
        assert any(e["type"] == "birth" for e in got)
        assert all("text_rendered" in e for e in got)


def test_ws_screen_hello_and_filtered_stream(client):
    with client.websocket_connect("/ws?screen=monitor_esquerda") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["screen"] == "monitor_esquerda"
        assert {p["id"] for p in hello["places"]} == {"forest", "mountain"}
        assert all(c["place"] in ("forest", "mountain") for c in hello["characters"])
        ws.send_json({"type": "ping"})
        client.post("/api/commands", json={"cmd": "tela", "arg": "monitor_esquerda offline"})
        kinds = set()
        deadline = time.time() + 10
        while time.time() < deadline and "fog" not in kinds:
            msg = ws.receive_json()
            kinds.add(msg["type"])
            if msg["type"] == "event":
                ev = msg["event"]
                d = ev["data"]
                assert ev["place"] is None or {ev["place"], d.get("from"), d.get("to"), d.get("from_place"),
                                               d.get("to_place")} & {"forest", "mountain"} or ev["type"] == "apparition"
        assert "pong" in kinds and "fog" in kinds
        client.post("/api/commands", json={"cmd": "tela", "arg": "monitor_esquerda online"})
    with client.websocket_connect("/ws?screen=nao_existe") as ws:
        assert ws.receive_json()["type"] == "error"
