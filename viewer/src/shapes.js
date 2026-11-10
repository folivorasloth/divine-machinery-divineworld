// Primitivas low-poly para montar cenários e personagens placeholder.
// Todas recebem cor (#rrggbb) e posição; devolvem um Mesh já posicionado.
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { mat, glow } from './ps1.js';

const place = (mesh, x = 0, y = 0, z = 0, parent) => {
  mesh.position.set(x, y, z);
  if (parent) parent.add(mesh);
  return mesh;
};

/** Caixa com a BASE em y (não o centro): fica mais fácil empilhar. */
export function box(parent, w, h, d, color, x = 0, y = 0, z = 0, opts) {
  const g = new THREE.BoxGeometry(w, h, d);
  g.translate(0, h / 2, 0);
  return place(new THREE.Mesh(g, opts?.glow ? glow(color, opts) : mat(color, opts)), x, y, z, parent);
}

export function cyl(parent, rTop, rBottom, h, color, x = 0, y = 0, z = 0, seg = 6, opts) {
  const g = new THREE.CylinderGeometry(rTop, rBottom, h, seg);
  g.translate(0, h / 2, 0);
  return place(new THREE.Mesh(g, opts?.glow ? glow(color, opts) : mat(color, opts)), x, y, z, parent);
}

export function cone(parent, r, h, color, x = 0, y = 0, z = 0, seg = 5, opts) {
  const g = new THREE.ConeGeometry(r, h, seg);
  g.translate(0, h / 2, 0);
  return place(new THREE.Mesh(g, opts?.glow ? glow(color, opts) : mat(color, opts)), x, y, z, parent);
}

/** Esfera low-poly (icosaedro): `detail` 0 = 20 faces, 1 = 80. */
export function ball(parent, r, color, x = 0, y = 0, z = 0, detail = 0, opts) {
  const g = new THREE.IcosahedronGeometry(r, detail);
  return place(new THREE.Mesh(g, opts?.glow ? glow(color, opts) : mat(color, opts)), x, y, z, parent);
}

/** Telhado de duas águas (prisma triangular) sobre uma caixa w × d, com altura h. */
export function roof(parent, w, h, d, color, x = 0, y = 0, z = 0) {
  const shape = new THREE.Shape();
  shape.moveTo(-w / 2 - 0.15, 0);
  shape.lineTo(w / 2 + 0.15, 0);
  shape.lineTo(0, h);
  shape.closePath();
  const g = new THREE.ExtrudeGeometry(shape, { depth: d + 0.3, bevelEnabled: false });
  g.translate(0, 0, -(d + 0.3) / 2);
  return place(new THREE.Mesh(g, mat(color)), x, y, z, parent);
}

/** Plano deitado no chão (y = altura). */
export function flat(parent, w, d, color, x = 0, y = 0.01, z = 0, opts) {
  const g = new THREE.PlaneGeometry(w, d);
  g.rotateX(-Math.PI / 2);
  return place(new THREE.Mesh(g, opts?.glow ? glow(color, opts) : mat(color, opts)), x, y, z, parent);
}

/** Disco/polígono deitado no chão. */
export function disc(parent, r, color, x = 0, y = 0.01, z = 0, seg = 8, opts) {
  const g = new THREE.CircleGeometry(r, seg);
  g.rotateX(-Math.PI / 2);
  return place(new THREE.Mesh(g, opts?.glow ? glow(color, opts) : mat(color, opts)), x, y, z, parent);
}

/**
 * Junta todas as malhas paradas de um grupo numa malha por material (bem menos
 * "draw calls": importante para notebook e celular velho). Malhas com
 * `userData.dynamic` (água, fumaça, LEDs piscando) ficam de fora.
 */
export function bake(group) {
  group.updateMatrixWorld(true);
  const inv = new THREE.Matrix4().copy(group.matrixWorld).invert();
  const buckets = new Map();
  const remove = [];
  group.traverse((o) => {
    if (!o.isMesh || o.userData.dynamic || hasDynamicParent(o, group)) return;
    const m = Array.isArray(o.material) ? null : o.material;
    if (!m) return;
    let g = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone();
    for (const name of Object.keys(g.attributes)) if (name !== 'position' && name !== 'normal') g.deleteAttribute(name);
    if (!g.attributes.normal) g.computeVertexNormals();
    g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld));
    if (!buckets.has(m)) buckets.set(m, []);
    buckets.get(m).push(g);
    remove.push(o);
  });
  for (const o of remove) o.parent.remove(o);
  for (const [m, geos] of buckets) {
    const merged = mergeGeometries(geos, false);
    if (merged) group.add(new THREE.Mesh(merged, m));
    geos.forEach((g) => g.dispose());
  }
  return group;
}

function hasDynamicParent(o, root) {
  let p = o.parent;
  while (p && p !== root) {
    if (p.userData.dynamic) return true;
    p = p.parent;
  }
  return false;
}

/** Cor hex -> THREE.Color, misturada com outra (t = 0..1). */
export function mix(a, b, t) {
  return '#' + new THREE.Color(a).lerp(new THREE.Color(b), t).getHexString();
}
