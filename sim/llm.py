"""LLM local opcional (Ollama) — Fase 4. Sem ele, tudo funciona com templates.

Regras (seção 9 de docs/arquitetura.md):
- só é usado com o mundo no relógio real (`World.realtime` e velocidade 1);
- nunca no thread da simulação: os pedidos vão para uma fila e um thread
  próprio fala com o Ollama (`httpx`, timeout curto `ollama.timeout_segundos`);
- `max_por_hora` pedidos por hora; acima disso, template;
- de `checar_a_cada_segundos` em `checar_a_cada_segundos` pergunta se o Ollama
  está no ar (GET /api/tags). Fora do ar = nem tenta (a fala sai na hora, do template);
- a resposta volta para a simulação como um comando interno na fila
  (`World.submit_internal`), e o engine valida: só pode citar pessoas por
  `{@id}` existentes, sem outras variáveis, até `max_caracteres`. Senão, template.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable

import httpx

log = logging.getLogger("sim.llm")


class LLM:
    def __init__(self, cfg, client: httpx.Client | None = None):
        self.cfg = cfg
        self.client = client
        self.available = False
        self.last_check = 0.0
        self.calls: deque[float] = deque()  # instantes (monotonic) dos pedidos da última hora
        self.jobs: queue.Queue = queue.Queue()
        self.ok = 0
        self.failed = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._warned = False

    # ------------------------------------------------------------ ciclo
    def start(self) -> "LLM":
        if not self.cfg.enabled or self._thread is not None:
            return self
        if self.client is None:
            self.client = httpx.Client(timeout=self.cfg.timeout_seconds)
        self._thread = threading.Thread(target=self._run, name="llm", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def summary(self) -> dict:
        self._trim()
        return {"ativo": bool(self.cfg.enabled), "no_ar": self.available, "pedidos_na_ultima_hora": len(self.calls),
                "max_por_hora": self.cfg.max_per_hour, "respostas_ok": self.ok, "falhas": self.failed,
                "modelo": self.cfg.model}

    # ------------------------------------------------------------ uso
    def _trim(self) -> None:
        now = time.monotonic()
        while self.calls and now - self.calls[0] > 3600:
            self.calls.popleft()

    def usable(self) -> bool:
        if not self.cfg.enabled or self._thread is None or not self.available:
            return False
        self._trim()
        return len(self.calls) < self.cfg.max_per_hour

    def _submit(self, kind: str, prompt: str, callback: Callable[[str | None], None]) -> bool:
        if not self.usable():
            return False
        self.calls.append(time.monotonic())
        self.jobs.put((kind, prompt, callback))
        return True

    def rewrite(self, prompt: str, callback: Callable[[str | None], None]) -> bool:
        return self._submit("fala", prompt, callback)

    def interpret(self, text: str, options: list[str], callback: Callable[[str | None], None]) -> bool:
        prompt = (
            "Você interpreta ordens para uma cidade de bonecos. Classifique a ordem abaixo em UMA destas "
            f"categorias: {', '.join(options)}.\nResponda só com a categoria, sem mais nada.\n\n"
            f"Ordem: \"{text}\"\nCategoria:"
        )

        def done(answer: str | None) -> None:
            kind = None
            if answer:
                low = answer.strip().lower()
                kind = next((o for o in options if o in low), None)
            callback(kind)

        return self._submit("interpretar", prompt, done)

    # ------------------------------------------------------------ thread
    def check(self) -> bool:
        """O Ollama está no ar? (GET /api/tags, timeout curto)."""
        self.last_check = time.monotonic()
        try:
            r = self.client.get(self.cfg.url.rstrip("/") + "/api/tags", timeout=self.cfg.timeout_seconds)
            self.available = r.status_code == 200
        except httpx.HTTPError as exc:
            if not self._warned:
                log.warning("Ollama fora do ar (%s): falas pelos templates.", exc.__class__.__name__)
                self._warned = True
            self.available = False
        if self.available:
            self._warned = False
        return self.available

    def generate(self, prompt: str) -> str | None:
        try:
            r = self.client.post(
                self.cfg.url.rstrip("/") + "/api/generate",
                json={"model": self.cfg.model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.8, "num_predict": 120}},
                timeout=self.cfg.timeout_seconds,
            )
            r.raise_for_status()
            text = (r.json().get("response") or "").strip()
            return text or None
        except (httpx.HTTPError, ValueError) as exc:
            log.info("LLM falhou (%s): fica o template.", exc.__class__.__name__)
            return None

    def _run(self) -> None:
        self.check()
        while not self._stop.is_set():
            if time.monotonic() - self.last_check > self.cfg.check_every_seconds:
                self.check()
            try:
                _kind, prompt, callback = self.jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            text = self.generate(prompt)
            if text is None:
                self.failed += 1
            else:
                self.ok += 1
            try:
                callback(text)
            except Exception:  # pragma: no cover - nunca derruba o thread
                log.exception("callback do LLM falhou")


def build_prompt(world, speaker: str, situation: str, line: str, place: str, target: str | None) -> str:
    """Contexto real para o LLM: quem, onde, humor, memórias recentes, bordões e a fala do template."""
    from sim import needs as needs_mod

    names = world.names()
    char = world.data.characters[speaker]
    st = world.states[speaker]
    mems = sorted(world.memories.of(speaker), key=lambda m: -m.intensity)[:3]
    memories = "; ".join(world.memories.phrase(m, "lembranca") for m in mems if world.memories.phrase(m, "lembranca"))
    ids = ", ".join(f"{{@{i}}} = {names[i]}" for i in dict.fromkeys([speaker] + ([target] if target else []))
                    if i in names)
    return (
        "Você escreve falas curtas para o Chat do Mundo, uma cidade low-poly de bonecos que não sabem que "
        "são observados. Português do Brasil, humor do tombo ao humor negro.\n"
        f"Personagem: {{@{speaker}}} ({char.role or char.profession}); traços: {', '.join(world.traits_of(speaker))}; "
        f"bordões: {' / '.join(char.catchphrases) or 'nenhum'}; humor agora: {needs_mod.mood(world.data, st.needs)}.\n"
        f"Lugar: {names.get(place, place)}. Clima: {world.weather.label}. Hora: {world.clock.hhmm()}.\n"
        f"Memórias fortes: {memories or 'nenhuma'}.\n"
        f"Situação: {situation}.\n"
        f"Frase original: {line}\n\n"
        "Reescreva a frase original com o mesmo sentido, no jeito desse personagem, em no máximo "
        f"{world.data.world.ollama.max_chars} caracteres. Cite pessoas e lugares SÓ com os marcadores entre chaves "
        f"exatamente como estão ({ids}); não invente outros marcadores. Responda só com a frase."
    )
