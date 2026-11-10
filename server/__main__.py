"""`python -m server`: a simulação + a API/WebSocket + a ponte MQTT, num processo.

    python -m server                          # tempo real (o mundo segue o relógio)
    python -m server --speed 60 --porta 8000  # 1 hora do mundo por minuto real
    python -m server --novo --seed 42 --inicio 07:00 --speed 120 --banco var/teste.sqlite
    python -m server --sem-mqtt --sem-llm     # sem nenhum serviço de fora

Depois: http://localhost:8000/chat (Chat do Mundo), /api/state, /docs (a API
toda, gerada pelo FastAPI). Comandos: python -m tools.cli chefe "..."
Ctrl+C (ou SIGTERM do Docker) salva o mundo e sai.
"""

from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from server.app import create_app
from server.runtime import Runtime
from sim.clock import WorldClock
from sim.loader import DataError, load_data_or_raise

LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "aviso": logging.WARNING, "erro": logging.ERROR}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sobe o Mundo Vivo com a API, o WebSocket e o MQTT.")
    p.add_argument("--dados", default="data", help="pasta de dados (padrão: data)")
    p.add_argument("--banco", default=None, help="SQLite (padrão: persistencia.banco do world.yaml)")
    p.add_argument("--speed", type=float, default=None, help="multiplicador do tempo (padrão: world.yaml)")
    p.add_argument("--fast", action="store_true", help="simula o mais rápido possível (só para testes)")
    p.add_argument("--novo", action="store_true", help="apaga o banco e começa um mundo novo")
    p.add_argument("--seed", type=int, default=None, help="semente (só para mundo novo)")
    p.add_argument("--inicio", default=None, help='hora do mundo novo: "07:00" ou "2026-11-10T07:00"')
    p.add_argument("--host", default=None, help="endereço (padrão: servidor.host do world.yaml)")
    p.add_argument("--porta", type=int, default=None, help="porta (padrão: servidor.porta do world.yaml)")
    p.add_argument("--sem-mqtt", action="store_true", help="não liga a ponte MQTT")
    p.add_argument("--sem-llm", action="store_true", help="não usa o Ollama")
    p.add_argument("--nascidos", default=None, help="pasta onde os nascidos viram YAML")
    p.add_argument("--sem-chat", action="store_true", help="não mostra o Chat do Mundo no terminal/log")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = load_data_or_raise(args.dados)
    except DataError as exc:
        print(exc, "\nRode: python -m tools.validate", file=sys.stderr)
        return 1
    logging.basicConfig(level=LOG_LEVELS[data.world.log_level], format="%(levelname)s %(name)s: %(message)s")
    start = WorldClock.parse_start(data.world.clock, args.inicio) if args.inicio else None

    def factory() -> Runtime:
        rt = Runtime(data_dir=args.dados, db_path=args.banco, speed=args.speed, seed=args.seed, fast=args.fast,
                     new=args.novo, start=start, mqtt=not args.sem_mqtt, llm=not args.sem_llm,
                     born_dir=args.nascidos)
        if not args.sem_chat:
            # o Chat do Mundo também no stdout (docker compose logs -f world), como no tools.run
            from rich.console import Console

            from tools.run import ChatPrinter

            rt.world.bus.subscribe(ChatPrinter(rt.world, [Console(highlight=False)], [], [], False, False))
        return rt

    app = create_app(runtime_factory=factory)
    host = args.host or data.world.server.host
    port = args.porta or data.world.server.port
    logging.getLogger("server").info("Mundo Vivo em http://%s:%s/chat", host, port)
    # sem o log de cada requisição (o /health do Docker a cada 30 s inundaria o Chat)
    uvicorn.run(app, host=host, port=port, log_level="info", ws_ping_interval=20, access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
