"""O processo do servidor: a simulação num thread + API/WebSocket + ponte MQTT.

Por que um processo só (seção 1.1 de docs/arquitetura.md): a simulação é a
dona do estado e a única que escreve no SQLite. A API só LÊ (o snapshot, sob
um lock curto, e o SQLite numa conexão de leitura, que o WAL permite) e
MANDA COMANDOS pela fila do mundo. Dois processos escrevendo no mesmo banco
ou trocando estado por arquivo seria mais complicado e mais frágil.

    Runtime(...).start()         # sobe o thread da simulação (+ LLM, + MQTT)
    runtime.command("chefe", "reconstruam a ferraria")   # -> Future com o resultado
    runtime.stop()               # para, salva e fecha
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
from pathlib import Path

from server.ws import Hub
from sim.engine import Command, World
from sim.llm import LLM
from sim.loader import DataError, load_data
from sim.reload import save_valid_copy, valid_copy_dir
from sim.persistence import Storage

log = logging.getLogger("server.runtime")


def load_with_valid_copy(data_dir: str | Path, db_path: str | None = None):
    """Carrega `data/`. Deu certo: guarda uma cópia em `var/data_valido/` (ao lado do banco).
    Deu erro e a cópia existe: liga com a cópia (devolve `(dados, True)`) e avisa no log;
    sem cópia, o erro sobe como antes (`DataError`, com a lista do validador)."""
    data, report = load_data(data_dir)
    if data is not None and report.ok:
        db = Path(db_path or data.world.storage.database)
        save_valid_copy(data, db.parent)
        return data, False
    db = Path(db_path) if db_path else None
    copy = valid_copy_dir(db.parent) if db else None
    if copy is None:  # sem --banco: descobre a pasta pelo world.yaml da cópia padrão
        copy = valid_copy_dir(Path(os.environ.get("DW_DB_PATH", "var/world.sqlite")).parent)
    if copy.is_dir():
        backup, breport = load_data(copy)
        if backup is not None and breport.ok:
            log.error("data/ com erro; ligando com a última versão válida (%s):\n%s", copy, report.format())
            return backup, True
    raise DataError(report)


class Runtime:
    def __init__(self, *, data_dir: str = "data", db_path: str | None = None, speed: float | None = None,
                 seed: int | None = None, fast: bool = False, new: bool = False, start=None,
                 mqtt: bool = True, llm: bool = True, born_dir: str | None = None, mqtt_client_factory=None,
                 llm_client=None):
        if born_dir:
            os.environ["DW_BORN_DIR"] = born_dir
        data, self.using_valid_copy = load_with_valid_copy(data_dir, db_path)
        self.db_path = Path(db_path or data.world.storage.database)
        if new:
            for suffix in ("", "-wal", "-shm"):
                Path(str(self.db_path) + suffix).unlink(missing_ok=True)
        self.storage = Storage(self.db_path)
        self.world = World(data, self.storage, seed=seed, speed=speed, start=start)
        self.world.data_dir = Path(data_dir)  # o `recarregar` lê sempre o data/ de verdade
        if self.using_valid_copy:
            self.world.emit("system", "ATENÇÃO: os arquivos de data/ estão com erro. O mundo ligou com a última "
                            "versão válida (var/data_valido). Corrija (python -m tools.validate) e rode "
                            "recarregar.", tags=["sistema"], importance=2, data={"valid_copy": True})
        self.fast = fast
        self.hub = Hub(self)
        self.world.bus.subscribe(self.hub.on_event)
        self.mqtt = None
        if mqtt and self.data.world.mqtt.enabled:
            from server.mqtt_bridge import MqttBridge

            self.mqtt = MqttBridge(self, client_factory=mqtt_client_factory)
            self.world.bus.subscribe(self.mqtt.on_event)
        if llm and self.data.world.ollama.enabled:
            self.world.llm = LLM(self.data.world.ollama, client=llm_client)
        self._thread: threading.Thread | None = None
        self.error: BaseException | None = None

    # ------------------------------------------------------------- ciclo
    def start(self) -> "Runtime":
        if self.world.llm is not None:
            self.world.llm.start()
        if self.mqtt is not None:
            self.mqtt.start()
        self._thread = threading.Thread(target=self._run, name="simulacao", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        w = self.world
        try:
            if w.resumed and w.speed == 1 and not self.fast:
                w.catch_up()
            w.run(fast=self.fast)
        except BaseException as exc:  # pragma: no cover - registrado e mostrado em /health
            self.error = exc
            log.exception("a simulação parou com erro")

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self.world.request_stop()
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self.mqtt is not None:
            self.mqtt.stop()
        if self.world.llm is not None:
            self.world.llm.stop()
        self.world.close()

    # ---------------------------------------------------------- comandos
    def command(self, cmd: str, arg: str = "", cmd_id: str = "") -> concurrent.futures.Future:
        """Põe um comando na fila do mundo. O Future recebe o resultado quando o
        thread da simulação executar (no próximo tick, ou logo, se pausado)."""
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self.world.submit(Command(cmd=cmd, arg=arg, id=cmd_id, reply=fut))
        return fut

    @property
    def data(self):
        """Os dados ATUAIS do mundo (mudam com o `recarregar`)."""
        return self.world.data

    # ----------------------------------------------------------- leitura
    def snapshot(self) -> dict:
        return self.world.snapshot()

    def names(self) -> dict[str, str]:
        return self.snapshot().get("names") or {}

    def reader(self) -> Storage:
        return Storage.reader(self.db_path)
