"""Fase 5: o que o servidor entrega para o viewer 3D (hello com config visual, balões,
modelos .glb, páginas /viewer) e o esquema `visual` do world.yaml."""

from __future__ import annotations

import time

import pytest
import yaml
from fastapi.testclient import TestClient

from server.app import create_app
from server.runtime import Runtime
from server.ws import shorten_bubble
from sim.clock import WorldClock
from sim.loader import DataError, load_data_or_raise
from tests.conftest import DATA


@pytest.fixture
def runtime(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("viewer")
    data = load_data_or_raise(DATA, environ={})
    start = WorldClock.parse_start(data.world.clock, "10:00")
    rt = Runtime(data_dir=str(DATA), db_path=str(tmp / "w.sqlite"), speed=600, seed=5, start=start, new=True,
                 mqtt=False, llm=False, born_dir=str(tmp / "born"))
    return rt


def _client(runtime, monkeypatch, tmp_path, dist: bool):
    models = tmp_path / "models"
    (models / "characters").mkdir(parents=True)
    (models / "places").mkdir()
    (models / "characters" / "clown.glb").write_bytes(b"glTF-fake")
    monkeypatch.setenv("DW_MODELS_DIR", str(models))
    distdir = tmp_path / "dist"
    if dist:
        distdir.mkdir()
        (distdir / "index.html").write_text("<html>viewer</html>")
        (distdir / "layout.html").write_text("<html>layout</html>")
    monkeypatch.setenv("DW_VIEWER_DIST", str(distdir))
    return TestClient(create_app(runtime))


def test_hello_has_what_the_viewer_needs(runtime, monkeypatch, tmp_path):
    with _client(runtime, monkeypatch, tmp_path, dist=True) as c:
        deadline = time.time() + 10
        while time.time() < deadline and (c.get("/api/state").json().get("ticks") or 0) < 3:
            time.sleep(0.1)
        with c.websocket_connect("/ws?screen=parede_centro") as ws:
            hello = ws.receive_json()
    me = next(s for s in hello["screens"] if s["id"] == "parede_centro")
    assert me["max_fps"] == 30 and me["quality"] in ("baixa", "media", "alta") and me["offline"] is False
    homelab = next(s for s in hello["screens"] if s["id"] == "tela_homelab")
    assert homelab["quality"] == "baixa" and homelab["max_fps"] == 20
    vis = hello["config"]["visual"]
    assert vis["action_animation"]["brigar"] == "fight" and vis["event_animation"]["slapstick"] == "fall"
    assert vis["qualities"]["baixa"]["render_height"] < vis["qualities"]["alta"]["render_height"]
    assert hello["config"]["tunnel"]["led_speed_cm_per_s"] > 0
    # nomes de TODOS os lugares (o portal mostra para onde vai, mesmo fora da tela)
    assert hello["place_names"]["forest"] and hello["place_names"]["server_room"]
    assert "creatures" in hello and "dead" in hello
    priest = next((ch for ch in hello["characters"] if ch["id"] == "priest"), None)
    if priest:  # o placeholder lê a aparência ("batina") e o jeito de andar
        assert "atina" in priest["visual"]["appearance"] and priest["visual"]["movement"]


def test_bubble_is_short_and_lasts_by_length(runtime):
    assert shorten_bubble('A Cozinheira: "Come que esfria!"', "A Cozinheira", 90) == "Come que esfria!"
    long = shorten_bubble("palavra " * 30, None, 40)
    assert len(long) <= 40 and long.endswith("…")
    hub = runtime.hub
    short = hub.bubble_message("chef_wife", "community_kitchen", 'A Cozinheira: "Oi!"')
    big = hub.bubble_message("chef_wife", "community_kitchen", "A Cozinheira: " + "blá " * 15)
    cfg = runtime.data.world.visual.bubbles
    assert short["short"] == "Oi!" and short["duration_s"] == pytest.approx(cfg.min_seconds + 3 * cfg.seconds_per_char, abs=0.1)
    assert big["duration_s"] > short["duration_s"] and big["duration_s"] <= cfg.max_seconds
    assert big["text"].startswith("A Cozinheira")  # o texto inteiro continua indo


def test_models_and_viewer_pages(runtime, monkeypatch, tmp_path):
    with _client(runtime, monkeypatch, tmp_path, dist=True) as c:
        assert c.get("/api/models").json() == {"characters": ["clown"], "places": []}
        r = c.get("/viewer/models/characters/clown.glb")
        assert r.status_code == 200 and r.content == b"glTF-fake"
        assert "viewer" in c.get("/viewer/").text
        assert "layout" in c.get("/viewer/layout.html").text
        assert c.get("/chat").status_code == 200


def test_viewer_not_built_shows_how_to_build(runtime, monkeypatch, tmp_path):
    with _client(runtime, monkeypatch, tmp_path, dist=False) as c:
        r = c.get("/viewer/")
        assert r.status_code == 503 and "npm run build" in r.text
        assert c.get("/viewer/models/characters/clown.glb").status_code == 200  # modelos funcionam igual


def test_visual_config_is_validated(data_copy):
    world = data_copy / "world.yaml"
    raw = yaml.safe_load(world.read_text(encoding="utf-8"))
    raw["visual"]["animacao_por_acao"]["brigar"] = "voar"
    raw["visual"]["animacao_por_acao"]["acao_que_nao_existe"] = "walk"
    world.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(DataError) as err:
        load_data_or_raise(data_copy, environ={})
    text = str(err.value)
    assert "animacao_por_acao" in text
