"""Telas online/offline → névoa nos lugares (Fase 3).

Quando uma tela física desliga (`telas/<id>/status = offline` no MQTT, ou o
comando `tela <id> offline`), todos os lugares dela entram na névoa:

- ninguém consegue entrar (o pathfinding trata a névoa como bloqueio, e quem
  estava a caminho desiste no próximo passo);
- quem já estava lá dentro fica preso: só decide coisas no próprio lugar;
- quem tem a imunidade `nevoa` (o Mike) entra e sai como se nada fosse.

Quando a tela volta (`online`), a névoa some (`fog_off`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sim.engine import World


class Screens:
    def __init__(self) -> None:
        self.offline: set[str] = set()  # ids de telas desligadas

    def fogged_places(self, world: "World") -> frozenset[str]:
        out: set[str] = set()
        for screen in world.data.world.screens:
            if screen.id in self.offline:
                out.update(screen.places)
        return frozenset(out)

    def set_status(self, world: "World", screen_id: str, online: bool) -> bool:
        """Liga/desliga uma tela. Devolve False se a tela não existe."""
        screen = next((s for s in world.data.world.screens if s.id == screen_id), None)
        if screen is None:
            world.emit("system", f"tela '{screen_id}' não existe no world.yaml", tags=["sistema"],
                       data={"screen": screen_id})
            return False
        was_offline = screen_id in self.offline
        if online and was_offline:
            self.offline.discard(screen_id)
            for pid in screen.places:
                world.emit("fog_off", f"A névoa se desfaz em {{@{pid}}}.", place=pid, tags=["misterio"],
                           importance=1, data={"screen": screen_id, "on": False})
        elif not online and not was_offline:
            self.offline.add(screen_id)
            for pid in screen.places:
                trapped = world.present_at(pid)
                text = f"Uma névoa espessa engole {{@{pid}}}."
                if trapped:
                    text += " Lá dentro ficaram " + world.list_names(trapped) + "."
                world.emit("fog_on", text, place=pid, tags=["misterio"], importance=1, actors=trapped,
                           data={"screen": screen_id, "on": True, "trapped": trapped})
        world.refresh_blocked()
        return True

    def to_json(self) -> dict:
        return {"offline": sorted(self.offline)}

    def load(self, raw: dict) -> None:
        self.offline = set(raw.get("offline", []))
