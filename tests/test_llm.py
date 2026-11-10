"""Fase 4: o LLM opcional (Ollama). Um Ollama de mentira (http.server local)
responde; e quando ele não existe, tudo sai dos templates."""

from __future__ import annotations

import json
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sim.clock import WorldClock
from sim.engine import Command, World
from sim.llm import LLM
from sim.loader import load_data_or_raise
from tests.conftest import DATA


@pytest.fixture(scope="module")
def data():
    return load_data_or_raise(DATA, environ={})


class FakeOllama:
    """Ollama falso: /api/tags e /api/generate. `answer` é o que ele responde."""

    def __init__(self, answer: str = "{@chief} sente um frio na espinha. Vamo vê isso aí."):
        self.answer = answer
        self.prompts: list[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silêncio
                pass

            def _send(self, body: dict):
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                self._send({"models": [{"name": "fake"}]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                fake.prompts.append(body["prompt"])
                self._send({"response": fake.answer})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def realtime_world(data, url: str, **cfg) -> World:
    ocfg = data.world.ollama.model_copy(update={"url": url, "enabled": True, "timeout_seconds": 2, **cfg})
    start = WorldClock.parse_start(data.world.clock, "10:00", real_now=datetime(2026, 11, 10, 12, 0))
    w = World(data, None, seed=1, start=start, speed=1)
    w.data.world = w.data.world.model_copy(update={"ollama": ocfg})
    w.realtime = True  # o LLM só entra com o mundo no relógio real
    w.llm = LLM(ocfg).start()
    for _ in range(50):
        if w.llm.available:
            break
        time.sleep(0.05)
    return w


def wait_drain(w: World, events: list, cond, seconds: float = 5.0) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        w._drain_commands()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_llm_rewrites_important_lines_with_context(data):
    fake = FakeOllama()
    w = realtime_world(data, fake.url)
    try:
        events = []
        w.bus.subscribe(events.append)
        assert w.llm_usable()
        ev = w.say("chief", "ordem_intuicao", extra={"fato": "reconstruam a ferraria", "evento": "x"},
                   event_type="creator_order", importance=2, tags=["criador"])
        assert ev is None  # saiu para o LLM; a simulação não esperou
        assert wait_drain(w, events, lambda: any(e.type == "creator_order" for e in events))
        out = [e for e in events if e.type == "creator_order"][0]
        assert out.data["llm"] is True and out.text == fake.answer
        prompt = fake.prompts[0]
        assert "{@chief}" in prompt and "Vamo vê isso aí." in prompt and "reconstruam a ferraria" in prompt
    finally:
        w.llm.stop()
        fake.close()


def test_invalid_llm_answer_falls_back_to_template(data):
    fake = FakeOllama(answer="{@ninguem_existe} {variavel} blá")
    w = realtime_world(data, fake.url)
    try:
        events = []
        w.bus.subscribe(events.append)
        assert w.say("chief", "ordem_intuicao", extra={"fato": "x", "evento": "y"}, event_type="creator_order",
                     importance=2) is None
        assert wait_drain(w, events, lambda: any(e.type == "creator_order" for e in events))
        out = [e for e in events if e.type == "creator_order"][0]
        assert out.data["llm"] is False and "{variavel}" not in out.text and "{@chief}" in out.text
    finally:
        w.llm.stop()
        fake.close()


def test_routine_lines_and_fast_mode_never_use_llm(data):
    fake = FakeOllama()
    w = realtime_world(data, fake.url)
    try:
        assert w.say("chief", "conversa", target="chef_wife", importance=0) is not None  # rotina: na hora
        w.realtime = False  # tempo acelerado
        assert w.say("chief", "ordem_intuicao", extra={"fato": "x", "evento": "y"}, importance=2) is not None
        assert fake.prompts == []
    finally:
        w.llm.stop()
        fake.close()


def test_rate_limit_per_hour(data):
    fake = FakeOllama()
    w = realtime_world(data, fake.url, max_per_hour=1)
    try:
        assert w.say("chief", "ordem_intuicao", extra={"fato": "a", "evento": "b"}, importance=2) is None
        assert w.say("chief", "ordem_intuicao", extra={"fato": "a", "evento": "b"}, importance=2) is not None
    finally:
        w.llm.stop()
        fake.close()


def test_ollama_offline_means_templates_right_away(data):
    w = realtime_world(data, f"http://127.0.0.1:{free_port()}")
    try:
        assert not w.llm.available and not w.llm_usable()
        assert w.say("chief", "ordem_intuicao", extra={"fato": "a", "evento": "b"}, importance=2) is not None
    finally:
        w.llm.stop()


def test_llm_interprets_free_orders(data):
    fake = FakeOllama(answer="festa")
    w = realtime_world(data, fake.url)
    try:
        res = w.handle_command(Command("chefe", "quero ver o povo feliz hoje à noite"))
        assert res["ok"] and "interpretando" in res["message"]
        order = w.creator.orders[-1]
        assert wait_drain(w, [], lambda: order["status"] != "interpretando")
        assert order["kind"] == "festa" and order["how"] == "llm" and order["receiver"] == "chief"
    finally:
        w.llm.stop()
        fake.close()
