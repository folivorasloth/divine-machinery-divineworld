"""Gera um .glb de exemplo (um "boneco-totem" de caixas) para testar a troca de placeholder.

    python -m tools.exemplo_glb clown          # cria viewer/public/models/characters/clown.glb
    python -m tools.exemplo_glb clown --saida /tmp/x.glb

O modelo segue a convenção de docs/guias/06_modelos_3d_e_design.md: 1 unidade = 1 metro,
+Y para cima, olhando para +Z, origem nos pés, 1,7 m de altura, e duas animações com os
nomes que o viewer entende: `idle` (a cabeça vira) e `walk` (o corpo balança). As outras
(talk, work, ...) faltam de propósito: o viewer usa a substituta e completa com movimento
procedural. Só biblioteca padrão (struct/json): serve de referência do formato.
Depois de testar, apague o arquivo (ou deixe, se quiser ver o totem na tela).
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def _box(w: float, h: float, d: float, y0: float) -> tuple[list[float], list[float], list[int]]:
    """Caixa com a base em y0: posições, normais (flat) e índices."""
    x, z = w / 2, d / 2
    y1 = y0 + h
    faces = [  # (normal, 4 cantos)
        ((0, 0, 1), [(-x, y0, z), (x, y0, z), (x, y1, z), (-x, y1, z)]),
        ((0, 0, -1), [(x, y0, -z), (-x, y0, -z), (-x, y1, -z), (x, y1, -z)]),
        ((1, 0, 0), [(x, y0, z), (x, y0, -z), (x, y1, -z), (x, y1, z)]),
        ((-1, 0, 0), [(-x, y0, -z), (-x, y0, z), (-x, y1, z), (-x, y1, -z)]),
        ((0, 1, 0), [(-x, y1, z), (x, y1, z), (x, y1, -z), (-x, y1, -z)]),
        ((0, -1, 0), [(-x, y0, -z), (x, y0, -z), (x, y0, z), (-x, y0, z)]),
    ]
    pos, nor, idx = [], [], []
    for n, corners in faces:
        base = len(pos) // 3
        for c in corners:
            pos += c
            nor += n
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return pos, nor, idx


def build(parts: list[tuple[str, tuple, tuple]]) -> bytes:
    """parts: (nome, (w, h, d, y0, dz), cor rgb 0..1). Cada parte vira um nó filho de "Root"."""
    blob = bytearray()
    accessors, views, meshes, nodes, materials = [], [], [], [], []

    def add_view(data: bytes, target: int | None) -> int:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), **({"target": target} if target else {})})
        blob.extend(data)
        return len(views) - 1

    def add_acc(values, comp, count, typ, target=None, minmax=False):
        fmt = "f" if comp == 5126 else "H"
        v = add_view(struct.pack(f"<{len(values)}{fmt}", *values), target)
        acc = {"bufferView": v, "componentType": comp, "count": count, "type": typ}
        if minmax:
            n = {"VEC3": 3, "SCALAR": 1}[typ]
            acc["min"] = [min(values[i::n]) for i in range(n)]
            acc["max"] = [max(values[i::n]) for i in range(n)]
        accessors.append(acc)
        return len(accessors) - 1

    for i, (name, (w, h, d, y0, dz), color) in enumerate(parts):
        pos, nor, idx = _box(w, h, d, y0)
        pos = [p + (dz if k % 3 == 2 else 0) for k, p in enumerate(pos)]
        a_pos = add_acc(pos, 5126, len(pos) // 3, "VEC3", 34962, minmax=True)
        a_nor = add_acc(nor, 5126, len(nor) // 3, "VEC3", 34962)
        a_idx = add_acc(idx, 5123, len(idx), "SCALAR", 34963)
        materials.append({"name": name, "pbrMetallicRoughness": {"baseColorFactor": [*color, 1], "metallicFactor": 0}})
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nor},
                                                     "indices": a_idx, "material": i}]})
        nodes.append({"name": name, "mesh": i})
    nodes.append({"name": "Root", "children": list(range(len(parts)))})
    root = len(nodes) - 1
    head = next(i for i, p in enumerate(parts) if p[0] == "head")
    body = next(i for i, p in enumerate(parts) if p[0] == "body")

    # animações: idle = a cabeça vira de um lado para o outro; walk = o corpo sobe e desce
    times = [0.0, 0.5, 1.0, 1.5, 2.0]
    t_acc = add_acc(times, 5126, len(times), "SCALAR", minmax=True)
    import math

    rots = []
    for t in times:
        a = math.sin(t * math.pi) * 0.5
        rots += [0, math.sin(a / 2), 0, math.cos(a / 2)]
    r_acc = add_acc(rots, 5126, len(times), "VEC4")
    steps = []
    for t in times:
        steps += [0, abs(math.sin(t * math.pi * 2)) * 0.08, 0]
    s_acc = add_acc(steps, 5126, len(times), "VEC3")
    animations = [
        {"name": "idle", "samplers": [{"input": t_acc, "output": r_acc, "interpolation": "LINEAR"}],
         "channels": [{"sampler": 0, "target": {"node": head, "path": "rotation"}}]},
        {"name": "walk", "samplers": [{"input": t_acc, "output": s_acc, "interpolation": "LINEAR"}],
         "channels": [{"sampler": 0, "target": {"node": body, "path": "translation"}}]},
    ]
    gltf = {
        "asset": {"version": "2.0", "generator": "divine-world tools.exemplo_glb"},
        "scene": 0, "scenes": [{"nodes": [root]}], "nodes": nodes, "meshes": meshes, "materials": materials,
        "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": 0}], "animations": animations,
    }
    while len(blob) % 4:
        blob.append(0)
    gltf["buffers"][0]["byteLength"] = len(blob)
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    return out


TOTEM = [
    ("legs", (0.4, 0.8, 0.25, 0.0, 0.0), (0.1, 0.1, 0.12)),
    ("body", (0.6, 0.6, 0.35, 0.8, 0.0), (0.15, 0.85, 0.35)),
    ("head", (0.45, 0.3, 0.4, 1.4, 0.0), (0.98, 0.85, 0.2)),
    ("nose", (0.12, 0.08, 0.15, 1.5, 0.25), (0.9, 0.1, 0.1)),  # o nariz aponta para +Z (a frente)
]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("id", help="id do personagem (data/characters/<id>.yaml)")
    ap.add_argument("--saida", help="arquivo de saída (padrão: viewer/public/models/characters/<id>.glb)")
    a = ap.parse_args(argv)
    out = Path(a.saida or f"viewer/public/models/characters/{a.id}.glb")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build(TOTEM))
    print(f"ok: {out} ({out.stat().st_size} bytes). Recarregue a página da tela.")


if __name__ == "__main__":
    main()
