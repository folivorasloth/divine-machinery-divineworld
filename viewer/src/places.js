// Cenários placeholder, um por lugar, feitos só com primitivas.
// Cada lugar é um "diorama" quadrado de PLOT × PLOT metros, centrado na origem,
// com o chão em y = 0. Lugares internos (taverna, ferraria...) são mostrados em
// corte, como casa de boneca: chão, parede do fundo e parede lateral baixa.
// Um .glb em viewer/public/models/places/<id>.glb substitui tudo isto.
import * as THREE from 'three';
import { box, cyl, cone, ball, roof, flat, disc, bake, mix } from './shapes.js';
import { mat, glow } from './ps1.js';
import { seededRandom } from './logic.js';

export const PLOT = 10;
const H = PLOT / 2;

/**
 * Monta o cenário de um lugar. Devolve:
 *   root        THREE.Group
 *   update(t, env)  animação (água, fumaça, LEDs); env = {night, rain}
 *   spots       pontos (x, z) onde os personagens ficam
 *   lamps       luzes {x, y, z, color} (viram PointLight na qualidade alta)
 *   tunnelSpot  (x, z) onde fica o portal do túnel
 */
export function buildPlace(place, detail = 1) {
  const root = new THREE.Group();
  root.name = `place:${place.id}`;
  const P = place.palette;
  const R = seededRandom(place.id);
  const ctx = { root, P, R, detail, dyn: [], lamps: [], spots: null, night: [], place };
  const builder = BUILDERS[place.id] || (place.environment === 'interno' ? genericInterior : genericExterior);
  builder(ctx);
  bake(root);
  for (const d of ctx.dyn) if (d.object && !d.object.parent) root.add(d.object);
  return {
    root,
    spots: ctx.spots || ringSpots(R, place.environment === 'interno'),
    lamps: ctx.lamps,
    tunnelSpot: ctx.tunnelSpot || { x: H - 1.2, z: H - 1.2 },
    update(t, env) {
      for (const d of ctx.dyn) d.update(t, env);
      for (const n of ctx.night) n(env.night);
    },
  };
}

/** Pontos onde os personagens ficam: um anel em volta do meio (o meio tem o enfeite principal). */
function ringSpots(R, interior) {
  const out = [];
  for (let i = 0; i < 24; i++) {
    const a = (i / 24) * Math.PI * 2 + R() * 0.2;
    const r = 2.2 + R() * 1.9;
    let x = Math.cos(a) * r;
    let z = Math.sin(a) * r;
    if (interior) z = Math.abs(z) * 0.9 - 0.3; // dentro de casa: na frente das coisas do fundo
    out.push({ x, z });
  }
  return out;
}

// ---------------------------------------------------------------- pedaços comuns
function ground(c, color, opts = {}) {
  const g = box(c.root, PLOT, 0.5, PLOT, color, 0, -0.5, 0, { unique: true });
  // borda mais escura, para separar um lugar do outro
  box(c.root, PLOT + 0.2, 0.3, PLOT + 0.2, mix(color, '#000000', 0.45), 0, -0.75, 0);
  if (c.P.night && !opts.noNight) {
    const day = new THREE.Color(color);
    const night = new THREE.Color(mix(color, c.P.night, 0.65));
    const m = g.material;
    c.night.push((n) => m.color.copy(day).lerp(night, n));
  }
  return g;
}

function walls(c, color, h = 3.2, side = true) {
  box(c.root, PLOT, h, 0.4, color, 0, 0, -H + 0.2);
  if (side) box(c.root, 0.4, h * 0.55, PLOT - 0.4, mix(color, '#000000', 0.15), -H + 0.2, 0, 0.2);
  // rodapé
  box(c.root, PLOT, 0.25, 0.5, mix(color, '#000000', 0.35), 0, 0, -H + 0.25);
}

function tree(c, x, z, s = 1, leaf = '#2d936c', trunk = '#6b4226') {
  cyl(c.root, 0.12 * s, 0.18 * s, 0.9 * s, trunk, x, 0, z, 5);
  ball(c.root, 0.75 * s, leaf, x, 1.35 * s, z);
}

function pine(c, x, z, s = 1, leaf = '#1b4332') {
  cyl(c.root, 0.1 * s, 0.14 * s, 0.6 * s, '#4a3020', x, 0, z, 5);
  cone(c.root, 0.9 * s, 1.4 * s, leaf, x, 0.5 * s, z, 6);
  cone(c.root, 0.65 * s, 1.1 * s, mix(leaf, '#ffffff', 0.08), x, 1.2 * s, z, 6);
}

function lamp(c, x, z, color = '#ffe8a3', h = 2.2) {
  cyl(c.root, 0.05, 0.07, h, '#2b2b2b', x, 0, z, 5);
  const head = box(c.root, 0.3, 0.3, 0.3, color, x, h, z, { glow: true });
  head.userData.dynamic = true;
  c.lamps.push({ x, y: h + 0.15, z, color });
  return head;
}

/** Fumaça subindo (bolinhas que sobem e somem). */
function smoke(c, x, y, z, color = '#bbbbbb', n = 4) {
  const group = new THREE.Group();
  group.userData.dynamic = true;
  const puffs = [];
  for (let i = 0; i < n; i++) {
    const p = ball(group, 0.25, color, 0, 0, 0, 0, { opacity: 0.6, unique: true });
    puffs.push(p);
  }
  group.position.set(x, y, z);
  c.root.add(group);
  c.dyn.push({
    update(t) {
      puffs.forEach((p, i) => {
        const k = (t * 0.35 + i / n) % 1;
        p.position.set(Math.sin(k * 6 + i) * 0.25, k * 2.2, 0);
        p.scale.setScalar(0.6 + k * 1.4);
        p.material.opacity = 0.55 * (1 - k);
      });
    },
  });
}

/** Janela que acende de noite. */
function windowLight(c, w, h, x, y, z, color = '#ffd166', rotY = 0) {
  const m = glow(color, { unique: true });
  const g = new THREE.PlaneGeometry(w, h);
  const mesh = new THREE.Mesh(g, m);
  mesh.position.set(x, y, z);
  mesh.rotation.y = rotY;
  mesh.userData.dynamic = true;
  c.root.add(mesh);
  const day = new THREE.Color('#3a4a5a');
  const lit = new THREE.Color(color);
  c.night.push((n) => m.color.copy(day).lerp(lit, Math.min(1, n * 1.3)));
  return mesh;
}

function house(c, x, z, w, d, h, wall, roofColor, rot = 0) {
  const g = new THREE.Group();
  g.position.set(x, 0, z);
  g.rotation.y = rot;
  c.root.add(g);
  box(g, w, h, d, wall);
  roof(g, w, h * 0.55, d, roofColor, 0, h, 0);
  box(g, 0.5, 0.9, 0.05, mix(wall, '#000000', 0.5), 0, 0, d / 2 + 0.01);
  // janelas (dinâmicas, ficam fora do bake)
  const sub = { root: g, night: c.night };
  windowLight(sub, 0.4, 0.4, -w / 4 - 0.05, h * 0.6, d / 2 + 0.02);
  windowLight(sub, 0.4, 0.4, w / 4 + 0.05, h * 0.6, d / 2 + 0.02);
  return g;
}

function portalSpot(c, x, z) {
  c.tunnelSpot = { x, z };
}

// ----------------------------------------------------------------- os lugares
const BUILDERS = {
  town_square(c) {
    const { P } = c;
    ground(c, mix(P.main, '#c9b38a', 0.55));
    disc(c.root, 4.3, mix(P.main, '#e8d9b5', 0.5), 0, 0.02, 0, 8);
    // chafariz
    cyl(c.root, 1.3, 1.4, 0.45, '#d9d4c7', 0, 0, 0, 8);
    const water = disc(c.root, 1.15, '#4cc9f0', 0, 0.46, 0, 8, { glow: true });
    water.userData.dynamic = true;
    cyl(c.root, 0.15, 0.2, 1.1, '#d9d4c7', 0, 0.45, 0, 6);
    cyl(c.root, 0.5, 0.25, 0.2, '#d9d4c7', 0, 1.5, 0, 6);
    const spout = ball(c.root, 0.18, '#a8e6ff', 0, 1.8, 0, 0, { glow: true, opacity: 0.8, unique: true });
    spout.userData.dynamic = true;
    c.dyn.push({ update: (t) => spout.position.setY(1.75 + Math.sin(t * 5) * 0.08) });
    // coreto
    const gx = -3.2, gz = -3.0;
    cyl(c.root, 1.4, 1.5, 0.3, '#f1faee', gx, 0, gz, 8);
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      cyl(c.root, 0.06, 0.06, 1.6, '#f1faee', gx + Math.cos(a) * 1.2, 0.3, gz + Math.sin(a) * 1.2, 4);
    }
    cone(c.root, 1.7, 1.1, P.secondary, gx, 1.9, gz, 8);
    // pedestal vazio da futura estátua da Dama
    box(c.root, 1.0, 0.9, 1.0, '#cfc8b8', 3.3, 0, -3.3);
    box(c.root, 1.2, 0.15, 1.2, '#b8b0a0', 3.3, 0.9, -3.3);
    // bancos
    for (const [x, z, r] of [[-3.6, 1.8, 0.4], [3.6, 1.6, -0.4], [0, 3.9, 0]]) {
      const b = box(c.root, 1.4, 0.35, 0.45, '#8b5a2b', x, 0.2, z);
      b.rotation.y = r;
      box(c.root, 0.1, 0.25, 0.4, '#3b3b3b', x - 0.5, 0, z);
      box(c.root, 0.1, 0.25, 0.4, '#3b3b3b', x + 0.5, 0, z);
    }
    lamp(c, -4.3, 4.3);
    lamp(c, 4.3, 4.3);
    tree(c, 4.2, -0.8, 0.9, '#57a773');
    tree(c, -4.4, -0.3, 0.8, '#57a773');
    portalSpot(c, 4.0, 2.8);
  },

  cathedral(c) {
    const { P } = c;
    const stone = P.main;
    ground(c, mix(stone, '#a39e90', 0.5));
    // fachada no fundo, com a torre central e a agulha (inspirada na Catedral de Botucatu)
    box(c.root, 7, 4.2, 1.6, stone, 0, 0, -3.9);
    box(c.root, 2.2, 4.2, 2.0, mix(stone, '#ffffff', 0.15), 0, 4.2, -3.9);
    cone(c.root, 1.45, 3.6, mix(stone, '#8d8778', 0.5), 0, 8.4, -3.9, 4);
    cyl(c.root, 0.04, 0.04, 0.7, '#e9c46a', 0, 12.0, -3.9, 4);
    box(c.root, 0.5, 0.08, 0.08, '#e9c46a', 0, 12.4, -3.9);
    // torrezinhas laterais
    for (const x of [-3.1, 3.1]) {
      box(c.root, 0.9, 5.2, 0.9, stone, x, 0, -3.5);
      cone(c.root, 0.65, 1.6, mix(stone, '#8d8778', 0.5), x, 5.2, -3.5, 4);
    }
    // porta em arco e rosácea
    box(c.root, 1.3, 2.2, 0.05, '#4a3b2a', 0, 0, -3.08);
    cone(c.root, 0.65, 0.6, '#4a3b2a', 0, 2.2, -3.1, 3).rotation.y = Math.PI / 2;
    const rose = disc(c.root, 0.75, '#ffd166', 0, 0, 0, 8, { glow: true });
    rose.rotation.x = 0; rose.position.set(0, 5.2, -2.88); rose.lookAt(0, 5.2, 10);
    // vitrais coloridos nas laterais
    const colors = ['#e63946', '#4361ee', '#ffd166', '#2a9d8f', '#b5179e'];
    for (let i = 0; i < 4; i++) {
      for (const s of [-1, 1]) {
        const w = flat(c.root, 0.5, 1.3, colors[(i + (s > 0 ? 2 : 0)) % colors.length], 0, 0, 0, { glow: true });
        w.rotation.set(0, 0, 0);
        w.position.set(s * 3.52, 2.4, -3.4 + i * 0.0);
        w.lookAt(s * 10, 2.4, -3.4);
        w.position.z = -3.9;
      }
    }
    // naves laterais baixas (corte) com vitrais
    for (const s of [-1, 1]) {
      box(c.root, 0.4, 2.0, 5.5, mix(stone, '#000000', 0.08), s * 4.6, 0, -0.4);
      for (let i = 0; i < 3; i++) {
        const v = flat(c.root, 0.9, 0.5, colors[(i + (s > 0 ? 1 : 3)) % colors.length], 0, 0, 0, { glow: true });
        v.position.set(s * 4.38, 1.2, -1.8 + i * 1.6);
        v.rotation.set(0, (-s * Math.PI) / 2, Math.PI / 2);
      }
    }
    // escadaria
    for (let i = 0; i < 3; i++) box(c.root, 3.2 - i * 0.3, 0.18, 0.5, '#d6d0bf', 0, i * 0.18, -2.7 - i * 0.0 + (2 - i) * 0.45);
    // bancos (a missa)
    for (let r = 0; r < 3; r++) {
      for (const s of [-1, 1]) box(c.root, 2.2, 0.45, 0.4, '#7a4e2d', s * 1.8, 0, 0.4 + r * 1.2);
    }
    // sino na torre
    const bell = cone(c.root, 0.4, 0.55, '#d4af37', 0, 5.0, -3.0, 6);
    bell.userData.dynamic = true;
    c.dyn.push({ update: (t) => (bell.rotation.z = Math.sin(t * 2) * 0.05) });
    c.spots = [];
    for (let i = 0; i < 18; i++) c.spots.push({ x: (i % 6 - 2.5) * 1.3, z: 0.0 + Math.floor(i / 6) * 1.25 + (i % 2) * 0.2 });
    portalSpot(c, 4.0, 3.8);
  },

  town_hall(c) {
    const { P } = c;
    ground(c, mix(P.main, '#bfae8e', 0.5));
    box(c.root, 7.5, 3.6, 2.6, P.main, 0, 0, -3.4);
    box(c.root, 8.0, 0.4, 3.0, P.secondary, 0, 3.6, -3.4);
    roof(c.root, 7.8, 1.1, 2.8, P.secondary, 0, 4.0, -3.4);
    for (let i = 0; i < 5; i++) cyl(c.root, 0.18, 0.2, 3.4, '#f1e3c4', -3 + i * 1.5, 0.1, -1.9, 6);
    box(c.root, 8.0, 0.15, 1.2, '#e9dcc0', 0, 0, -1.6);
    // relógio na fachada
    const clock = disc(c.root, 0.45, '#fff2cc', 0, 0, 0, 10, { glow: true });
    clock.position.set(0, 4.45, -2.0); clock.lookAt(0, 4.45, 10);
    // mastro com bandeira
    cyl(c.root, 0.05, 0.05, 4.2, '#555555', 4.2, 0, -1.2, 4);
    const flag = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 0.6, 4, 1), mat('#e63946', { side: THREE.DoubleSide, unique: true }));
    flag.position.set(4.75, 3.8, -1.2);
    flag.userData.dynamic = true;
    c.root.add(flag);
    const fp = flag.geometry.attributes.position;
    const base = fp.array.slice();
    c.dyn.push({ update(t) {
      for (let i = 0; i < fp.count; i++) {
        const x = base[i * 3];
        fp.array[i * 3 + 2] = Math.sin(t * 4 + x * 4) * 0.12 * (x + 0.55);
      }
      fp.needsUpdate = true;
    } });
    // a mesa do Chefe e a fila de reclamações
    box(c.root, 1.8, 0.8, 0.8, '#7a4e2d', -1.5, 0, 0.6);
    box(c.root, 0.4, 0.05, 0.3, '#ffffff', -1.6, 0.8, 0.6);
    box(c.root, 0.3, 0.12, 0.2, '#c1121f', -1.0, 0.8, 0.6);
    lamp(c, -4.2, 3.8, '#fff2cc');
    tree(c, 4.0, 3.2, 0.8, '#6a994e');
    portalSpot(c, 3.8, 1.8);
  },

  market(c) {
    const { P, R } = c;
    ground(c, mix(P.main, '#c2b280', 0.6));
    const stripes = [P.secondary, '#f94144', '#577590', '#f8961e'];
    const stalls = [[-3, -3], [0.2, -3.4], [3.3, -2.8], [-3.4, 0.8]];
    stalls.forEach(([x, z], i) => {
      box(c.root, 2.2, 0.9, 1.0, '#8b5a2b', x, 0, z);
      for (const dx of [-1.0, 1.0]) for (const dz of [-0.45, 0.45]) cyl(c.root, 0.05, 0.05, 2.1, '#5c3d2e', x + dx, 0, z + dz, 4);
      for (let s = 0; s < 4; s++) {
        const aw = box(c.root, 0.6, 0.12, 1.4, s % 2 ? '#ffffff' : stripes[i % stripes.length], x - 0.9 + s * 0.6, 2.05, z + 0.15);
        aw.rotation.x = 0.25;
      }
      for (let f = 0; f < 5; f++) ball(c.root, 0.16, ['#e63946', '#ffd166', '#90be6d', '#f8961e'][(f + i) % 4], x - 0.8 + f * 0.4, 1.0, z + 0.1);
    });
    for (let i = 0; i < 6 * c.detail; i++) box(c.root, 0.5, 0.45, 0.5, '#a47148', 2 + R() * 2.5, 0, 1 + R() * 3);
    lamp(c, 4.3, -0.5, '#fff3b0');
    portalSpot(c, 4.0, 4.0);
  },

  community_kitchen(c) {
    const { P } = c;
    ground(c, '#9c6b4e');
    walls(c, mix(P.main, '#ffffff', 0.25), 3.0);
    // fogão a lenha com fogo e chaminé
    box(c.root, 2.4, 1.0, 1.1, '#2b2b2b', 2.5, 0, -4.0);
    const fire = box(c.root, 1.6, 0.35, 0.05, '#ff7b00', 2.5, 0.25, -3.44, { glow: true, unique: true });
    fire.userData.dynamic = true;
    c.dyn.push({ update: (t) => fire.material.color.setHSL(0.07 + Math.sin(t * 13) * 0.02, 1, 0.5 + Math.sin(t * 9) * 0.08) });
    box(c.root, 0.5, 4.2, 0.5, '#3b3b3b', 3.4, 0, -4.4);
    smoke(c, 3.4, 4.3, -4.4, '#cccccc');
    cyl(c.root, 0.35, 0.3, 0.45, '#6c757d', 2.0, 1.0, -4.0, 8);
    cyl(c.root, 0.3, 0.3, 0.35, '#495057', 3.0, 1.0, -4.0, 8);
    // despensa
    box(c.root, 1.6, 2.4, 0.6, '#8b5a2b', -3.2, 0, -4.4);
    for (let i = 0; i < 3; i++) box(c.root, 1.5, 0.06, 0.55, '#5c3317', -3.2, 0.6 + i * 0.7, -4.1);
    // mesas compridas
    for (const z of [-0.8, 1.9]) {
      box(c.root, 5.5, 0.12, 1.0, '#a47148', 0.3, 0.75, z);
      for (const x of [-2.2, 2.8]) box(c.root, 0.15, 0.75, 0.8, '#5c3317', x, 0, z);
      for (const s of [-0.85, 0.85]) box(c.root, 5.3, 0.4, 0.3, '#7a4e2d', 0.3, 0, z + s);
      for (let k = 0; k < 4; k++) cyl(c.root, 0.18, 0.14, 0.1, '#f1faee', -1.6 + k * 1.3, 0.87, z, 6);
    }
    windowLight(c, 1.0, 0.8, -1.0, 1.9, -4.78, '#ffd8a8');
    c.lamps.push({ x: 2.5, y: 1, z: -3.2, color: '#ff7b00' });
    c.spots = [];
    for (let i = 0; i < 16; i++) c.spots.push({ x: -2.5 + (i % 8) * 0.8, z: i < 8 ? -1.9 : 0.6 });
    portalSpot(c, 4.0, 3.8);
  },

  tavern(c) {
    const { P } = c;
    ground(c, '#6b4423');
    walls(c, P.secondary, 3.2);
    // balcão
    box(c.root, 4.5, 1.1, 0.8, P.main, -1.5, 0, -3.3);
    box(c.root, 4.7, 0.12, 1.0, '#3b2414', -1.5, 1.1, -3.3);
    for (let i = 0; i < 6; i++) cyl(c.root, 0.12, 0.12, 0.35, ['#ffbf69', '#90be6d', '#e63946'][i % 3], -3.3 + i * 0.7, 1.22, -3.3, 5);
    // prateleira de garrafas
    for (let i = 0; i < 8; i++) cyl(c.root, 0.08, 0.08, 0.4, ['#2a9d8f', '#e9c46a', '#8c2f1b'][i % 3], -3.6 + i * 0.6, 2.0, -4.6, 5);
    box(c.root, 5.0, 0.08, 0.35, '#3b2414', -1.5, 1.95, -4.6);
    // barris
    for (const [x, z] of [[3.6, -4.0], [4.2, -3.2], [3.7, -2.4]]) cyl(c.root, 0.45, 0.45, 0.9, '#8b5a2b', x, 0, z, 8);
    // mesa de sinuca
    box(c.root, 2.4, 0.8, 1.3, '#3b2414', 1.8, 0, 1.6);
    box(c.root, 2.2, 0.05, 1.1, '#2d6a4f', 1.8, 0.8, 1.6);
    // palco improvisado
    box(c.root, 2.4, 0.3, 1.8, '#a47148', -3.4, 0, 1.6);
    // lampiões
    for (const x of [-3.5, 0, 3.5]) {
      const l = box(c.root, 0.3, 0.4, 0.3, '#ffbf69', x, 2.6, -4.5, { glow: true });
      l.userData.dynamic = true;
      c.lamps.push({ x, y: 2.6, z: -4.2, color: '#ffbf69' });
    }
    c.spots = [];
    for (let i = 0; i < 18; i++) c.spots.push({ x: -3.5 + (i % 6) * 1.35, z: -2.2 + Math.floor(i / 6) * 1.2 + (i % 2) * 0.3 });
    portalSpot(c, 4.0, 4.0);
  },

  forge(c) {
    const { P } = c;
    ground(c, '#3b3b3b');
    walls(c, mix(P.secondary, '#555555', 0.3), 3.0);
    // forja com boca acesa
    box(c.root, 2.4, 1.8, 1.6, '#5a5a5a', -2.6, 0, -3.8);
    const mouth = box(c.root, 1.2, 0.6, 0.05, P.light, -2.6, 0.6, -2.98, { glow: true, unique: true });
    mouth.userData.dynamic = true;
    c.dyn.push({ update: (t) => mouth.material.color.setHSL(0.07, 1, 0.45 + Math.abs(Math.sin(t * 7)) * 0.15) });
    box(c.root, 0.7, 2.6, 0.7, '#4a4a4a', -2.6, 1.8, -4.2);
    smoke(c, -2.6, 4.4, -4.2, '#999999');
    c.lamps.push({ x: -2.6, y: 1, z: -2.6, color: P.light });
    // bigorna
    box(c.root, 0.5, 0.6, 0.5, '#5c3d2e', 0.5, 0, -0.5);
    box(c.root, 1.1, 0.35, 0.45, '#2b2d42', 0.5, 0.6, -0.5);
    cone(c.root, 0.22, 0.45, '#2b2d42', 1.25, 0.65, -0.5, 4).rotation.z = -Math.PI / 2;
    // ferramentas penduradas
    for (let i = 0; i < 5; i++) {
      box(c.root, 0.08, 0.9, 0.08, '#8b5a2b', 0.8 + i * 0.6, 1.4, -4.7);
      box(c.root, 0.3, 0.18, 0.12, '#6c757d', 0.8 + i * 0.6, 2.25, -4.7);
    }
    // balde e fole
    cyl(c.root, 0.3, 0.25, 0.5, '#6c757d', 2.8, 0, 0.8, 7);
    box(c.root, 1.0, 0.4, 0.6, '#5c3317', -1.0, 0, -3.4);
    portalSpot(c, 4.0, 4.0);
  },

  houses(c) {
    const { P } = c;
    ground(c, mix('#7fb069', P.secondary, 0.2));
    flat(c.root, 1.4, PLOT, '#c9b38a', 0, 0.02, 0);
    const walls_ = [P.main, P.light, P.secondary, '#118ab2', '#f78c6b', '#ffd166'];
    const roofs = ['#8c2f1b', '#5c3317', '#3a4a7a', '#7a4e2d'];
    const spots = [[-3, -3, 0], [3, -3.2, 0], [-3.2, 1.2, Math.PI / 2], [3.1, 1.0, -Math.PI / 2], [-3.0, 4.0, 0], [3.2, 4.0, 0]];
    const n = Math.max(3, Math.round(spots.length * Math.min(1, c.detail + 0.3)));
    spots.slice(0, n).forEach(([x, z, r], i) => house(c, x, z, 2.2, 2.0, 1.7 + (i % 3) * 0.25, walls_[i % walls_.length], roofs[i % roofs.length], r));
    lamp(c, -1.1, 0.5);
    lamp(c, 1.1, -2.5);
    c.spots = [];
    for (let i = 0; i < 16; i++) c.spots.push({ x: (i % 2 ? 0.5 : -0.5) + (c.R() - 0.5) * 0.4, z: -4 + i * 0.55 });
    portalSpot(c, 0.0, 4.4);
  },

  prison(c) {
    const { P } = c;
    ground(c, mix(P.main, '#666666', 0.5));
    box(c.root, 8, 3.2, 3, P.secondary, 0, 0, -3.3);
    // celas com grades
    for (let cell = 0; cell < 3; cell++) {
      const x = -2.6 + cell * 2.6;
      box(c.root, 2.0, 2.2, 0.05, '#1f1f1f', x, 0, -1.78);
      for (let b = 0; b < 7; b++) cyl(c.root, 0.04, 0.04, 2.2, '#9aa0a6', x - 0.9 + b * 0.3, 0, -1.7, 4);
      box(c.root, 2.1, 0.1, 0.1, '#9aa0a6', x, 2.2, -1.7);
    }
    box(c.root, 8.2, 0.4, 3.2, '#3a3a3a', 0, 3.2, -3.3);
    // lista de infrações
    box(c.root, 0.8, 1.1, 0.05, '#f1faee', 3.8, 1.0, -1.7);
    // pátio cercado
    for (let i = 0; i < 9; i++) cyl(c.root, 0.05, 0.05, 1.2, '#7a7a7a', -4.4 + i * 1.1, 0, 4.4, 4);
    box(c.root, 9, 0.06, 0.06, '#7a7a7a', 0, 1.1, 4.4);
    lamp(c, 4.3, 0.5, P.light);
    c.spots = [];
    for (let i = 0; i < 12; i++) c.spots.push({ x: -3.5 + (i % 6) * 1.4, z: i < 6 ? -2.6 : 1.2 + c.R() });
    portalSpot(c, -4.0, 3.6);
  },

  fields(c) {
    const { P, R } = c;
    ground(c, mix(P.main, '#6a994e', 0.3));
    // plantação
    for (let r = 0; r < 6; r++) {
      box(c.root, 6.5, 0.18, 0.45, '#7f5539', -0.5, 0, -4 + r * 0.9);
      const n = Math.round(9 * c.detail);
      for (let k = 0; k < n; k++) cone(c.root, 0.16, 0.5, r % 2 ? '#a7c957' : '#f2e8cf', -3.5 + k * (6.5 / n), 0.18, -4 + r * 0.9, 4);
    }
    // espantalho
    cyl(c.root, 0.05, 0.05, 2.0, '#5c3d2e', 3.6, 0, -2.4, 4);
    box(c.root, 1.3, 0.08, 0.08, '#5c3d2e', 3.6, 1.5, -2.4);
    box(c.root, 0.6, 0.7, 0.3, P.secondary, 3.6, 1.0, -2.4);
    ball(c.root, 0.22, '#f2e8cf', 3.6, 1.9, -2.4);
    cyl(c.root, 0.4, 0.4, 0.06, '#e9c46a', 3.6, 2.07, -2.4, 8);
    cone(c.root, 0.18, 0.25, '#e9c46a', 3.6, 2.1, -2.4, 6);
    // feno e cerca
    cyl(c.root, 0.6, 0.6, 0.9, '#e9c46a', -3.8, 0, 3.4, 8).rotation.z = Math.PI / 2;
    for (let i = 0; i < 9; i++) box(c.root, 0.1, 0.8, 0.1, '#8b5a2b', -4.5 + i * 1.12, 0, 4.6);
    box(c.root, 9, 0.08, 0.08, '#8b5a2b', 0, 0.6, 4.6);
    for (let i = 0; i < 3 * c.detail; i++) tree(c, -4.2 + R() * 1.0, -4.2 + R() * 1.5, 0.7 + R() * 0.3, '#6a994e');
    c.spots = [];
    for (let i = 0; i < 14; i++) c.spots.push({ x: -3.4 + (i % 7) * 1.0, z: i < 7 ? 1.4 : 2.6 });
    portalSpot(c, 4.2, 4.0);
  },

  cemetery(c) {
    const { P, R } = c;
    ground(c, mix(P.main, '#3e4a59', 0.4));
    c.graveRows = [];
    // lápides (mais uma a cada enterro, ver addGrave)
    for (let i = 0; i < 10; i++) {
      const x = -3.6 + (i % 5) * 1.5;
      const z = -3.4 + Math.floor(i / 5) * 1.6;
      gravestone(c.root, x, z, R);
    }
    // cripta
    box(c.root, 2.2, 2.0, 1.8, '#5c677d', 3.2, 0, -3.6);
    roof(c.root, 2.2, 0.8, 1.8, '#3e4a59', 3.2, 2.0, -3.6);
    box(c.root, 0.8, 1.3, 0.05, '#111111', 3.2, 0, -2.69);
    // cerca de ferro
    for (let i = 0; i < 12; i++) cyl(c.root, 0.03, 0.03, 1.1, '#1b1b1b', -4.6 + i * 0.84, 0, 4.6, 4);
    box(c.root, 9.4, 0.05, 0.05, '#1b1b1b', 0, 1.0, 4.6);
    // árvore morta
    cyl(c.root, 0.12, 0.2, 2.6, '#3b3b3b', -4.0, 0, 1.6, 5);
    for (const [a, l] of [[0.7, 1.2], [-0.8, 1.0], [0.3, 0.9]]) {
      const b = cyl(c.root, 0.04, 0.07, l, '#3b3b3b', -4.0, 1.6 + l * 0.2, 1.6, 4);
      b.rotation.z = a;
    }
    mist(c, P.light);
    lamp(c, 1.0, 4.0, '#a9bcd0', 1.8);
    c.spots = [];
    for (let i = 0; i < 16; i++) c.spots.push({ x: -3.5 + (i % 8) * 1.0, z: i < 8 ? 0.6 : 2.4 });
    portalSpot(c, 4.0, 2.0);
  },

  forest(c) {
    const { P, R } = c;
    ground(c, mix(P.main, P.secondary, 0.5));
    const n = Math.round(22 * c.detail);
    for (let i = 0; i < n; i++) {
      const a = R() * Math.PI * 2;
      const r = 2.8 + R() * 1.9;
      pine(c, Math.cos(a) * r, Math.sin(a) * r * 0.95, 0.8 + R() * 0.7, R() < 0.5 ? P.main : P.secondary);
    }
    // círculo de pedras do ritual, com velas
    for (let i = 0; i < 7; i++) {
      const a = (i / 7) * Math.PI * 2;
      box(c.root, 0.35, 0.5 + R() * 0.3, 0.3, '#6c757d', Math.cos(a) * 1.5, 0, Math.sin(a) * 1.5);
      const candle = cyl(c.root, 0.04, 0.04, 0.14, '#ffba08', Math.cos(a) * 1.15, 0, Math.sin(a) * 1.15, 4, { glow: true });
      candle.userData.dynamic = true;
    }
    disc(c.root, 0.6, '#3a2a1a', 0, 0.02, 0, 7);
    // cogumelos
    for (let i = 0; i < 6 * c.detail; i++) {
      const x = (R() - 0.5) * 7, z = (R() - 0.5) * 7;
      cyl(c.root, 0.04, 0.05, 0.15, '#f1faee', x, 0, z, 4);
      cone(c.root, 0.14, 0.1, '#e63946', x, 0.15, z, 6);
    }
    mist(c, P.light, 0.12);
    c.spots = [];
    for (let i = 0; i < 16; i++) {
      const a = (i / 16) * Math.PI * 2;
      c.spots.push({ x: Math.cos(a) * 2.1, z: Math.sin(a) * 2.1 });
    }
    portalSpot(c, 0, 4.3);
  },

  mountain(c) {
    const { P, R } = c;
    ground(c, mix(P.main, '#6c757d', 0.3));
    for (const [x, z, r, h] of [[-2.6, -2.8, 2.6, 6.5], [1.6, -3.4, 2.9, 8.0], [4.0, -1.5, 1.8, 4.5]]) {
      cone(c.root, r, h, mix(P.main, '#5a5f66', 0.4), x, 0, z, 5);
      cone(c.root, r * 0.38, h * 0.38, '#f8f9fa', x, h * 0.62, z, 5);
    }
    for (let i = 0; i < 8 * c.detail; i++) ball(c.root, 0.25 + R() * 0.35, '#8d99ae', (R() - 0.5) * 8, 0.1, 1 + R() * 3.5);
    // pilhas de pedra dos peregrinos
    for (const [x, z] of [[-2.0, 2.0], [2.6, 2.8]]) {
      for (let k = 0; k < 3; k++) ball(c.root, 0.25 - k * 0.06, '#adb5bd', x, 0.15 + k * 0.32, z);
    }
    pine(c, -4.0, 1.0, 0.9, '#40916c');
    pine(c, 4.2, 2.0, 0.8, '#40916c');
    portalSpot(c, -4.0, 4.0);
  },

  sea(c) {
    const { P } = c;
    // areia na frente, água no resto
    box(c.root, PLOT, 0.5, 3.2, '#f2d7a6', 0, -0.5, H - 1.6);
    box(c.root, PLOT + 0.2, 0.3, PLOT + 0.2, '#03045e', 0, -0.75, 0);
    const geo = new THREE.PlaneGeometry(PLOT, PLOT - 3.2, 14, 10);
    geo.rotateX(-Math.PI / 2);
    const water = new THREE.Mesh(geo, mat(P.main, { unique: true }));
    water.position.set(0, -0.15, -1.6);
    water.userData.dynamic = true;
    c.root.add(water);
    const pos = geo.attributes.position;
    const base = pos.array.slice();
    const day = new THREE.Color(P.main);
    const night = new THREE.Color(P.night || P.secondary);
    c.dyn.push({ update(t, env) {
      for (let i = 0; i < pos.count; i++) {
        const x = base[i * 3], z = base[i * 3 + 2];
        pos.array[i * 3 + 1] = Math.sin(t * 1.4 + x * 0.9 + z * 0.6) * 0.12 + Math.sin(t * 0.8 + z) * 0.08;
      }
      pos.needsUpdate = true;
      geo.computeVertexNormals();
      water.material.color.copy(day).lerp(night, env.night * 0.8);
    } });
    // barquinho
    const boat = new THREE.Group();
    box(boat, 1.6, 0.4, 0.7, '#8b5a2b');
    cyl(boat, 0.04, 0.04, 1.6, '#5c3d2e', 0, 0.3, 0, 4);
    const sail = cone(boat, 0.5, 1.1, '#f1faee', 0.35, 0.6, 0, 3);
    sail.rotation.y = Math.PI / 2;
    boat.position.set(-1.6, 0, -2.6);
    boat.userData.dynamic = true;
    c.root.add(boat);
    c.dyn.push({ update(t) { boat.position.y = Math.sin(t * 1.2) * 0.1 - 0.1; boat.rotation.z = Math.sin(t * 0.9) * 0.08; } });
    // píer
    box(c.root, 1.0, 0.15, 4.0, '#a47148', 3.2, 0.05, 1.0);
    for (let i = 0; i < 4; i++) cyl(c.root, 0.08, 0.08, 0.8, '#5c3d2e', 2.8 + (i % 2) * 0.8, -0.6, 0 + Math.floor(i / 2) * 1.8, 4);
    // coisas que a maré traz
    box(c.root, 0.5, 0.35, 0.4, '#5c3d2e', -3.6, 0, 3.6).rotation.y = 0.5;
    ball(c.root, 0.2, '#2a9d8f', -2.6, 0.05, 4.2);
    c.spots = [];
    for (let i = 0; i < 14; i++) c.spots.push({ x: -4 + (i % 7) * 1.1, z: i < 7 ? 2.5 : 3.8 });
    portalSpot(c, -4.2, 4.3);
  },

  desert(c) {
    const { P, R } = c;
    ground(c, P.main);
    for (let i = 0; i < 5; i++) {
      const d = ball(c.root, 1.6 + R() * 1.2, mix(P.main, P.secondary, 0.25 + R() * 0.3), (R() - 0.5) * 7, -0.4, -3.2 + R() * 2.5, 1);
      d.scale.set(1.4, 0.35, 1);
    }
    // ruínas
    for (const [x, h] of [[-2.8, 1.8], [-1.8, 0.9], [-0.8, 2.2]]) cyl(c.root, 0.28, 0.32, h, '#e9d8a6', x, 0, 1.2, 6);
    box(c.root, 2.6, 0.35, 0.6, '#e9d8a6', -1.8, 2.2, 1.2).rotation.z = -0.12;
    // cactos
    for (const [x, z] of [[3.0, 0.5], [3.8, 3.0], [-3.8, 3.5]]) {
      cyl(c.root, 0.2, 0.22, 1.4, '#588157', x, 0, z, 6);
      cyl(c.root, 0.12, 0.12, 0.6, '#588157', x + 0.3, 0.6, z, 5).rotation.z = -0.9;
    }
    // objeto "sagrado" meio enterrado, brilhando
    const relic = box(c.root, 0.35, 0.35, 0.35, '#ffd166', 1.4, 0.0, 3.6, { glow: true });
    relic.rotation.set(0.5, 0.6, 0.3);
    c.spots = null;
    portalSpot(c, 4.0, 4.0);
  },

  sky(c) {
    const { P, R } = c;
    // sem chão: nuvens fazem o piso
    for (let i = 0; i < 26 * Math.max(0.6, c.detail); i++) {
      const b = ball(c.root, 1.0 + R() * 0.9, i % 3 ? '#fff1e6' : P.main, (R() - 0.5) * 8.5, -0.6 + R() * 0.3, (R() - 0.5) * 8.5, 0);
      b.scale.y = 0.45;
    }
    // portão dourado
    for (const x of [-1.3, 1.3]) cyl(c.root, 0.18, 0.2, 2.8, P.secondary, x, 0, -3.5, 6);
    box(c.root, 3.2, 0.3, 0.4, P.secondary, 0, 2.8, -3.5);
    const halo = new THREE.Mesh(new THREE.TorusGeometry(0.7, 0.08, 4, 10), glow('#ffd166'));
    halo.position.set(0, 3.6, -3.5);
    halo.userData.dynamic = true;
    c.root.add(halo);
    c.dyn.push({ update: (t) => (halo.rotation.y = t * 0.8) });
    // nuvenzinhas passando
    const drift = new THREE.Group();
    drift.userData.dynamic = true;
    for (let i = 0; i < 4; i++) ball(drift, 0.6, '#ffffff', i * 2.5 - 4, 3 + (i % 2), -1 + i, 0, { opacity: 0.85 });
    c.root.add(drift);
    c.dyn.push({ update: (t) => (drift.position.x = Math.sin(t * 0.15) * 1.5) });
    portalSpot(c, -3.8, 3.8);
  },

  server_room(c) {
    const { P, R } = c;
    ground(c, P.secondary, { noNight: true });
    walls(c, '#050a18', 3.4);
    const leds = [];
    for (let row = 0; row < 2; row++) {
      for (let k = 0; k < 5; k++) {
        const x = -3.6 + k * 1.5;
        const z = -3.8 + row * 2.4;
        box(c.root, 0.9, 2.6, 0.8, '#111827', x, 0, z);
        for (let l = 0; l < 6; l++) {
          const led = box(c.root, 0.08, 0.06, 0.02, R() < 0.5 ? P.main : '#ff3355', x - 0.3 + (l % 3) * 0.12, 0.6 + Math.floor(l / 3) * 1.1 + R() * 0.3, z + 0.41, { glow: true, unique: true });
          led.userData.dynamic = true;
          leds.push([led, R() * 10, 1 + R() * 4]);
        }
      }
    }
    c.dyn.push({ update(t) { for (const [led, ph, sp] of leds) led.visible = Math.sin(t * sp + ph) > -0.3; } });
    // cabos soltos
    for (let i = 0; i < 7; i++) box(c.root, 0.06, 0.04, 3 + R() * 2, ['#00f5ff', '#ffb703', '#ff3355'][i % 3], -4 + i * 1.2, 0.01, 1.8).rotation.y = (R() - 0.5) * 0.8;
    // o fundo que ninguém olha: uma porta preta com dois olhos
    box(c.root, 1.6, 2.6, 0.05, '#000000', 3.6, 0, -4.76);
    const eyes = new THREE.Group();
    eyes.userData.dynamic = true;
    ball(eyes, 0.06, '#ff0033', -0.15, 0, 0, 0, { glow: true });
    ball(eyes, 0.06, '#ff0033', 0.15, 0, 0, 0, { glow: true });
    eyes.position.set(3.6, 1.8, -4.7);
    c.root.add(eyes);
    c.dyn.push({ update: (t) => (eyes.visible = Math.sin(t * 0.37) > 0.6) });
    // faíscas
    const sparks = new THREE.Group();
    sparks.userData.dynamic = true;
    const sp = [];
    for (let i = 0; i < 5; i++) sp.push(ball(sparks, 0.07, '#7df9ff', 0, 0, 0, 0, { glow: true }));
    c.root.add(sparks);
    c.dyn.push({ update(t) {
      const burst = Math.floor(t * 0.7) % 3 === 0;
      sp.forEach((s, i) => {
        s.visible = burst && Math.sin(t * 40 + i) > 0;
        s.position.set(-2.1 + Math.sin(i * 7) * 0.4, 2.2 + Math.cos(t * 30 + i) * 0.3, -1.0);
      });
    } });
    c.lamps.push({ x: 0, y: 2.5, z: -1, color: P.main });
    c.spots = [];
    for (let i = 0; i < 12; i++) c.spots.push({ x: -3.5 + (i % 6) * 1.4, z: i < 6 ? -2.3 : 0.6 + R() * 2 });
    portalSpot(c, 4.0, 3.8);
  },

  underground(c) {
    const { P, R } = c;
    ground(c, mix(P.night || '#10002b', P.main, 0.3), { noNight: true });
    walls(c, '#1a0b3b', 3.6);
    for (let i = 0; i < 10 * c.detail; i++) {
      const x = (R() - 0.5) * 9, z = -4.5 + R() * 1.2;
      cone(c.root, 0.3 + R() * 0.3, 1 + R() * 1.6, '#2c1a5a', x, 0, z, 5);
    }
    // cristais
    for (let i = 0; i < 9 * c.detail; i++) {
      const cr = cone(c.root, 0.18, 0.7 + R() * 0.6, i % 2 ? P.secondary : P.light, (R() - 0.5) * 8.5, 0, (R() - 0.5) * 8.5, 4, { glow: true });
      cr.rotation.set((R() - 0.5) * 0.6, R() * 3, (R() - 0.5) * 0.6);
    }
    // caixas de som da rave
    for (const x of [-3.8, 3.8]) {
      box(c.root, 1.0, 1.8, 0.9, '#0d0d0d', x, 0, -3.2);
      disc(c.root, 0.32, '#333333', x, 1.2, -2.74, 8).rotation.x = 0;
    }
    // luzes da rave (giram)
    const rave = new THREE.Group();
    rave.userData.dynamic = true;
    const beams = [];
    for (let i = 0; i < 4; i++) {
      const b = cone(rave, 0.6, 3.2, ['#f72585', '#4cc9f0', '#b5179e', '#7209b7'][i], 0, 0, 0, 6, { glow: true, opacity: 0.22, additive: true });
      b.rotation.x = Math.PI;
      b.position.y = 3.2;
      beams.push(b);
    }
    rave.position.set(0, 0, -0.5);
    c.root.add(rave);
    c.dyn.push({ update(t, env) {
      beams.forEach((b, i) => {
        const a = t * 0.9 + (i * Math.PI) / 2;
        b.position.set(Math.cos(a) * 1.6, 3.2, Math.sin(a) * 1.6);
        b.visible = env.night > 0.5 || i < 2;
      });
    } });
    c.lamps.push({ x: 0, y: 2, z: 0, color: P.light });
    portalSpot(c, 4.0, 4.0);
  },
};

function gravestone(parent, x, z, R) {
  const h = 0.6 + R() * 0.35;
  box(parent, 0.55, h, 0.18, '#8d99ae', x, 0, z).rotation.z = (R() - 0.5) * 0.15;
  cyl(parent, 0.275, 0.275, 0.18, '#8d99ae', x, h, z, 6).rotation.x = Math.PI / 2;
  flat(parent, 0.5, 0.9, '#2f3e46', x, 0.02, z + 0.6);
}

/** Uma lápide nova no Cemitério (evento `grave`). */
export function addGrave(placeRoot, index) {
  const R = seededRandom('grave' + index);
  const g = new THREE.Group();
  g.userData.dynamic = true;
  const x = -3.6 + (index % 8) * 1.0;
  const z = 3.4 - Math.floor(index / 8) * 0.9;
  gravestone(g, x, z, R);
  disc(g, 0.25, '#ffffff', x + 0.2, 0.03, z + 0.4, 5); // flores
  placeRoot.add(g);
}

/** Névoa rasteira (lugares sinistros). */
function mist(c, color, opacity = 0.18) {
  const group = new THREE.Group();
  group.userData.dynamic = true;
  const layers = [];
  for (let i = 0; i < 3; i++) {
    const m = flat(group, PLOT * 0.95, PLOT * 0.95, color, 0, 0.25 + i * 0.3, 0, { glow: true, opacity, unique: true });
    m.material.depthWrite = false;
    layers.push(m);
  }
  c.root.add(group);
  c.dyn.push({ update(t) { layers.forEach((l, i) => { l.position.x = Math.sin(t * 0.2 + i) * 0.3; l.position.z = Math.cos(t * 0.17 + i * 2) * 0.3; }); } });
}

function genericExterior(c) {
  const { P, R } = c;
  ground(c, P.main);
  for (let i = 0; i < 6 * c.detail; i++) tree(c, (R() - 0.5) * 8, (R() - 0.5) * 8, 0.6 + R() * 0.6, P.secondary);
  for (let i = 0; i < 4; i++) box(c.root, 0.6, 0.4 + R() * 0.8, 0.6, P.light, (R() - 0.5) * 7, 0, (R() - 0.5) * 7);
}

function genericInterior(c) {
  const { P, R } = c;
  ground(c, mix(P.secondary, '#000000', 0.2));
  walls(c, P.main, 3.0);
  for (let i = 0; i < 4; i++) box(c.root, 1.2, 0.8, 0.8, P.secondary, -3 + i * 2, 0, -4 + R());
  const l = box(c.root, 0.3, 0.3, 0.3, P.light, 0, 2.6, -4.5, { glow: true });
  l.userData.dynamic = true;
  c.lamps.push({ x: 0, y: 2.6, z: -4, color: P.light });
}

/** Restos de construção (estruturas danificadas/destruídas, vindas da F2). */
export function buildRubble(count, seed) {
  const g = new THREE.Group();
  const R = seededRandom(seed);
  for (let i = 0; i < count * 5; i++) {
    const b = box(g, 0.25 + R() * 0.35, 0.2 + R() * 0.3, 0.25 + R() * 0.35, R() < 0.5 ? '#7a6a5a' : '#4a4a4a', (R() - 0.5) * 1.6, 0, (R() - 0.5) * 1.2);
    b.rotation.set(R(), R() * 3, R());
  }
  // fita de "obra"
  box(g, 1.8, 0.05, 0.05, '#ffd60a', 0, 0.6, 0.8);
  cyl(g, 0.04, 0.04, 0.7, '#ff7b00', -0.9, 0, 0.8, 4);
  cyl(g, 0.04, 0.04, 0.7, '#ff7b00', 0.9, 0, 0.8, 4);
  return g;
}
