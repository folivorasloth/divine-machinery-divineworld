// Personagens: placeholder montado com primitivas a partir do `visual` do YAML
// (cor, corpo, altura, chapéu, acessório, e palavras da aparência), com
// animação procedural. Se existir viewer/public/models/characters/<id>.glb, o
// modelo do João é usado no lugar, com as animações dele (por nome) e o
// movimento procedural só completando o que faltar.
import * as THREE from 'three';
import { box, cyl, cone, ball, mix } from './shapes.js';
import { mat, glow } from './ps1.js';
import {
  hatKind, accessoryKinds, outfitKind, appearanceExtras, gaitKind, hashString, pickClip, seededRandom,
} from './logic.js';

const SKINS = ['#f1c27d', '#e0ac69', '#c68642', '#8d5524', '#ffdbac', '#d4a373'];
const HAIRS = ['#2b1d0e', '#4a3020', '#7a5230', '#1b1b1b', '#9a8c7a', '#d9c7a0'];

/** Monta o boneco. Medidas em metros: altura 1.0 no YAML = 1,7 m. */
export function buildPlaceholder(id, visual) {
  const v = visual || { color: '#cccccc', secondary_color: '#666666', height: 1, body: 'normal' };
  const rnd = seededRandom(id);
  const skin = SKINS[hashString(id) % SKINS.length];
  const hat = hatKind(v.hat);
  const acc = accessoryKinds(v.accessory);
  const outfit = outfitKind(v.appearance, v.accessory);
  const ex = appearanceExtras(v.appearance);
  const main = v.color;
  const sec = v.secondary_color;
  const app = String(v.appearance || '').toLowerCase();
  const legsColor = app.includes('jeans') ? '#34558b' : mix(main, '#1b1b1b', 0.45);
  let hair = HAIRS[hashString(id + 'h') % HAIRS.length];
  if (app.includes('cabelo pintado')) hair = sec;
  if (app.includes('arrepiado')) hair = sec;

  const body = v.body || 'normal';
  const dims = {
    normal: { w: 0.44, d: 0.28, torso: 0.6, leg: 0.72, arm: 0.07 },
    magro: { w: 0.34, d: 0.22, torso: 0.62, leg: 0.8, arm: 0.055 },
    barrigudo: { w: 0.5, d: 0.34, torso: 0.58, leg: 0.66, arm: 0.075 },
    enorme: { w: 0.7, d: 0.42, torso: 0.72, leg: 0.72, arm: 0.11 },
    baixinho: { w: 0.48, d: 0.3, torso: 0.55, leg: 0.6, arm: 0.07 },
    corcunda: { w: 0.44, d: 0.32, torso: 0.55, leg: 0.62, arm: 0.07 },
  }[body] || { w: 0.44, d: 0.28, torso: 0.6, leg: 0.72, arm: 0.07 };
  const headS = 0.36;
  // escala para chegar à altura pedida (1.0 = 1,7 m)
  const natural = dims.leg + dims.torso + headS + 0.04;
  const scale = (1.7 * (v.height || 1)) / natural;

  const root = new THREE.Group(); // posição e direção no mundo
  const pose = new THREE.Group(); // deitar, ajoelhar, cair (gira em volta dos pés)
  const rig = new THREE.Group(); // escala do personagem
  rig.scale.setScalar(scale);
  root.add(pose);
  pose.add(rig);

  const hipY = dims.leg;
  const torso = new THREE.Group();
  torso.position.y = hipY;
  rig.add(torso);

  // pernas (pivô no quadril)
  const legs = [];
  for (const s of [-1, 1]) {
    const pivot = new THREE.Group();
    pivot.position.set(s * dims.w * 0.25, hipY, 0);
    const leg = box(pivot, dims.w * 0.36, dims.leg, dims.d * 0.75, legsColor);
    leg.position.y = -dims.leg;
    const shoeL = ex.bigShoes ? 0.42 : 0.24;
    box(pivot, dims.w * 0.4, 0.09, shoeL, ex.bigShoes ? '#e63946' : '#2b2118', 0, -dims.leg, shoeL * 0.2);
    rig.add(pivot);
    legs.push(pivot);
  }

  // tronco
  let torsoColor = main;
  if (outfit === 'suit') torsoColor = main;
  const chest = box(torso, dims.w, dims.torso, dims.d, torsoColor);
  if (body === 'barrigudo') ball(torso, dims.w * 0.52, torsoColor, 0, dims.torso * 0.35, dims.d * 0.35, 1).scale.set(1, 0.95, 0.85);
  if (body === 'corcunda') {
    torso.rotation.x = 0.45;
    ball(torso, dims.w * 0.42, torsoColor, 0, dims.torso * 0.75, -dims.d * 0.45, 0);
  }
  if (outfit === 'cassock' || outfit === 'robe' || outfit === 'dress') {
    // batina / manto / vestido: saia até o chão, esconde as pernas
    const len = hipY + dims.torso * 0.45;
    const skirt = cyl(rig, dims.w * 0.42, dims.w * (outfit === 'dress' ? 1.15 : 0.85), len, outfit === 'dress' ? main : main, 0, 0, 0, 7);
    skirt.userData.skirt = true;
    legs.forEach((l) => (l.visible = false));
    if (outfit === 'dress') {
      cyl(rig, dims.w * 1.05, dims.w * 1.18, 0.12, sec, 0, 0.02, 0, 7); // barra
    }
  }
  if (outfit === 'overalls') {
    legs.forEach((l) => l.children[0].material = mat(main));
    box(torso, dims.w * 0.15, dims.torso, 0.02, sec, -dims.w * 0.25, 0, dims.d / 2 + 0.005);
    box(torso, dims.w * 0.15, dims.torso, 0.02, sec, dims.w * 0.25, 0, dims.d / 2 + 0.005);
  }
  if (ex.dots) {
    for (let i = 0; i < 7; i++) {
      ball(torso, 0.035, '#f1faee', (rnd() - 0.5) * dims.w * 0.8, 0.08 + rnd() * dims.torso * 0.8, dims.d / 2 + 0.01, 0);
    }
  }
  if (outfit === 'poncho') {
    const p = cone(torso, dims.w * 0.95, dims.torso * 0.85, sec, 0, dims.torso * 0.12, 0, 4);
    p.rotation.y = Math.PI / 4;
    box(torso, dims.w * 1.2, 0.05, dims.d * 1.25, '#e63946', 0, dims.torso * 0.32, 0);
  }
  if (outfit === 'apron') box(torso, dims.w * 0.8, dims.torso * 0.95 + dims.leg * 0.45, 0.03, app.includes('couro') ? '#6b4226' : sec, 0, -dims.leg * 0.45, dims.d / 2 + 0.01);
  if (outfit === 'suit') {
    box(torso, dims.w * 0.12, dims.torso * 0.6, 0.02, sec, 0, dims.torso * 0.35, dims.d / 2 + 0.01); // gravata
  }
  if (outfit === 'coat') {
    box(torso, dims.w * 1.12, dims.torso + dims.leg * 0.55, dims.d * 1.12, main, 0, -dims.leg * 0.55, 0);
    for (let i = 0; i < 6; i++) box(torso, 0.1, 0.09, 0.03, sec, (i % 2 ? 1 : -1) * dims.w * 0.3, -dims.leg * 0.4 + Math.floor(i / 2) * 0.25, dims.d * 0.57);
  }

  // braços (pivô no ombro)
  const arms = [];
  const handColor = acc.includes('gloves') ? '#ffb703' : skin;
  for (const s of [-1, 1]) {
    const pivot = new THREE.Group();
    pivot.position.set(s * (dims.w / 2 + dims.arm * 0.6), dims.torso * 0.92, 0);
    const len = dims.torso * 0.9;
    const a = box(pivot, dims.arm * 1.6, len, dims.arm * 1.6, outfit === 'cassock' || outfit === 'robe' ? main : torsoColor);
    a.position.y = -len;
    const hand = box(pivot, dims.arm * 1.8, 0.09, dims.arm * 1.8, handColor, 0, -len - 0.09, 0);
    hand.name = 'hand';
    torso.add(pivot);
    pivot.userData.handY = -len - 0.05;
    arms.push(pivot);
  }

  // cabeça (pivô no pescoço)
  const head = new THREE.Group();
  head.position.y = dims.torso;
  torso.add(head);
  if (body === 'corcunda') head.rotation.x = -0.35;
  const face = ex.makeup ? '#f8f1e5' : skin;
  box(head, 0.12, 0.06, 0.12, skin, 0, 0, 0); // pescoço
  box(head, headS, headS, headS * 0.92, face, 0, 0.05, 0);
  const eyeY = 0.05 + headS * 0.58;
  const eyeZ = (headS * 0.92) / 2 + 0.005;
  const eyeR = ex.bigEyes ? 0.06 : 0.03;
  for (const s of [-1, 1]) {
    if (ex.bigEyes) box(head, eyeR * 1.6, eyeR * 1.6, 0.01, '#ffffff', s * 0.08, eyeY - eyeR * 0.6, eyeZ);
    box(head, eyeR, eyeR, 0.012, '#111111', s * 0.08, eyeY - eyeR * 0.3, eyeZ + 0.004);
  }
  if (ex.unibrow) box(head, 0.24, 0.035, 0.02, '#1b1b1b', 0, eyeY + 0.04, eyeZ);
  if (ex.mustache) box(head, 0.16, 0.03, 0.02, hair === sec ? '#2b1d0e' : hair, 0, 0.05 + headS * 0.28, eyeZ);
  if (ex.glasses) {
    for (const s of [-1, 1]) box(head, 0.09, 0.07, 0.01, '#cfe8ff', s * 0.08, eyeY - 0.04, eyeZ + 0.012, { opacity: 0.7 });
    box(head, 0.06, 0.015, 0.01, '#222222', 0, eyeY - 0.02, eyeZ + 0.012);
  }
  if (ex.thirdEye) box(head, 0.05, 0.05, 0.01, '#ffba08', 0, eyeY + 0.08, eyeZ + 0.004);
  if (ex.makeup) {
    for (const s of [-1, 1]) box(head, 0.05, 0.08, 0.01, '#4361ee', s * 0.08, eyeY - 0.1, eyeZ + 0.002);
    box(head, 0.14, 0.03, 0.01, '#e63946', 0, 0.05 + headS * 0.22, eyeZ + 0.002);
  }
  // cabelo (se o chapéu não cobre)
  if (!hat || ['straw', 'felt', 'cowboy', 'candles', 'spiky', 'cap', 'tophat'].includes(hat)) {
    if (ex.bald) {
      box(head, headS + 0.02, 0.08, headS * 0.6, hair, 0, 0.05 + headS * 0.45, -headS * 0.22);
    } else {
      box(head, headS + 0.03, 0.09, headS * 0.95, hair, 0, 0.05 + headS - 0.02, -0.005);
      box(head, headS + 0.03, headS * 0.5, 0.08, hair, 0, 0.05 + headS * 0.45, -headS * 0.45);
    }
  }
  const top = 0.05 + headS;
  const hatY = top - 0.02;
  const flames = [];
  switch (hat) {
    case 'straw':
      cyl(head, 0.38, 0.4, 0.04, '#e9c46a', 0, hatY, 0, 9);
      cyl(head, 0.17, 0.2, 0.14, '#e9c46a', 0, hatY + 0.04, 0, 8);
      cyl(head, 0.205, 0.205, 0.04, '#c1121f', 0, hatY + 0.05, 0, 8);
      break;
    case 'chef': {
      const g = new THREE.Group();
      cyl(g, 0.16, 0.15, 0.3, '#ffffff', 0, 0, 0, 7);
      ball(g, 0.2, '#ffffff', 0, 0.36, 0, 0);
      g.position.set(0.04, hatY, 0);
      g.rotation.z = -0.3; // torto
      head.add(g);
      break;
    }
    case 'jester':
      for (const s of [-1, 1]) {
        const c = cone(head, 0.1, 0.42, s < 0 ? '#e9c46a' : '#8d99ae', s * 0.12, hatY, 0, 5);
        c.rotation.z = -s * 0.9;
        ball(head, 0.05, '#ffd60a', s * 0.42, hatY + 0.26, 0, 0);
      }
      cyl(head, 0.2, 0.2, 0.07, '#8d99ae', 0, hatY - 0.02, 0, 8);
      break;
    case 'cowboy':
      cyl(head, 0.36, 0.36, 0.035, '#7a4e2d', 0, hatY, 0, 9).scale.set(1, 1, 0.85);
      cyl(head, 0.16, 0.19, 0.17, '#8b5a2b', 0, hatY + 0.03, 0, 7);
      break;
    case 'felt':
      cyl(head, 0.3, 0.3, 0.03, '#4a3728', 0, hatY, 0, 9);
      cyl(head, 0.16, 0.19, 0.16, '#5c4033', 0, hatY + 0.03, 0, 8);
      break;
    case 'candles':
      for (const [x, z] of [[-0.11, 0], [0.11, 0], [0, -0.1]]) {
        cyl(head, 0.025, 0.025, 0.14, '#f8f1e5', x, top, z, 5);
        const f = ball(head, 0.035, '#ffba08', x, top + 0.17, z, 0, { glow: true, unique: true });
        flames.push(f);
      }
      break;
    case 'helmet': {
      const h = new THREE.Mesh(new THREE.SphereGeometry(0.22, 7, 4, 0, Math.PI * 2, 0, Math.PI / 2), mat(sec === '#023047' ? '#ffb703' : '#ffb703'));
      h.position.y = top - 0.06;
      head.add(h);
      cyl(head, 0.05, 0.05, 0.06, '#fff8b0', 0, top - 0.01, 0.2, 6, { glow: true }).rotation.x = Math.PI / 2;
      break;
    }
    case 'spiky':
      for (let i = 0; i < 7; i++) {
        const c = cone(head, 0.06, 0.2, hair, (i % 4 - 1.5) * 0.08, top - 0.03, (Math.floor(i / 4) - 0.5) * 0.1, 4);
        c.rotation.set((rnd() - 0.5) * 0.8, 0, (rnd() - 0.5) * 0.9);
      }
      break;
    case 'hood':
      box(head, headS + 0.08, headS * 0.75, headS + 0.06, main, 0, 0.05 + headS * 0.4, -0.03);
      cone(head, 0.16, 0.22, main, 0, top - 0.02, -0.1, 4).rotation.x = -0.6;
      break;
    case 'crown':
      cyl(head, 0.19, 0.17, 0.12, '#ffd166', 0, hatY, 0, 6);
      break;
    case 'tophat':
      cyl(head, 0.3, 0.3, 0.03, '#111111', 0, hatY, 0, 9);
      cyl(head, 0.17, 0.17, 0.32, '#111111', 0, hatY, 0, 8);
      break;
    case 'cap':
      cyl(head, 0.2, 0.2, 0.08, sec, 0, hatY, 0, 8);
      box(head, 0.22, 0.02, 0.18, sec, 0, hatY, 0.2);
      break;
    case 'beanie':
      ball(head, 0.21, sec, 0, hatY, 0, 0).scale.y = 0.6;
      break;
    default:
      break;
  }

  // acessórios
  const [armL, armR] = arms;
  const inHand = (arm, obj) => {
    obj.position.y += arm.userData.handY;
    arm.add(obj);
  };
  const juggle = [];
  let cart = null;
  for (const a of acc) {
    switch (a) {
      case 'nose':
        ball(head, 0.085, '#ff1f1f', 0, eyeY - 0.12, eyeZ + 0.05, 0);
        break;
      case 'hammer': {
        const g = new THREE.Group();
        box(g, 0.05, 0.5, 0.05, '#7a4e2d', 0, -0.25, 0.08);
        box(g, 0.24, 0.12, 0.12, '#3b3b3b', 0, -0.3, 0.12);
        inHand(armR, g);
        break;
      }
      case 'clipboard': {
        const g = new THREE.Group();
        box(g, 0.24, 0.32, 0.03, '#8b5a2b', 0, -0.2, 0.1);
        box(g, 0.2, 0.25, 0.01, '#ffffff', 0, -0.17, 0.12);
        inHand(armL, g);
        break;
      }
      case 'spoon': {
        const g = new THREE.Group();
        box(g, 0.04, 0.4, 0.03, '#c68642', 0, -0.2, 0.06);
        ball(g, 0.06, '#c68642', 0, -0.42, 0.06, 0).scale.set(1, 1.3, 0.4);
        inHand(armR, g);
        break;
      }
      case 'towel':
        box(torso, 0.14, 0.32, dims.d + 0.04, '#f1faee', dims.w * 0.32, dims.torso * 0.62, 0);
        box(torso, 0.15, 0.04, dims.d + 0.05, '#e63946', dims.w * 0.32, dims.torso * 0.75, 0);
        break;
      case 'cigarette':
        cyl(head, 0.012, 0.012, 0.12, '#f8f1e5', 0.06, 0.05 + headS * 0.25, eyeZ + 0.05, 4).rotation.x = Math.PI / 2;
        ball(head, 0.016, '#ff7b00', 0.06, 0.05 + headS * 0.25, eyeZ + 0.11, 0, { glow: true });
        break;
      case 'basket': {
        const g = new THREE.Group();
        cyl(g, 0.16, 0.12, 0.16, '#a47148', 0, -0.2, 0.08, 7);
        for (let i = 0; i < 5; i++) ball(g, 0.05, ['#ff595e', '#ffca3a', '#8ac926', '#ff70a6', '#ffffff'][i], (i - 2) * 0.05, -0.02, 0.08 + (i % 2) * 0.04, 0);
        inHand(armL, g);
        break;
      }
      case 'juggling':
        for (let i = 0; i < 3; i++) {
          const b = ball(rig, 0.06, ['#e63946', '#4361ee', '#ffd60a'][i], 0, 0, 0, 0);
          b.userData.dynamic = true;
          juggle.push(b);
        }
        break;
      case 'pockets':
        for (let i = 0; i < 4; i++) box(torso, 0.1, 0.09, 0.03, sec, (i % 2 ? 1 : -1) * dims.w * 0.28, 0.12 + Math.floor(i / 2) * 0.22, dims.d / 2 + 0.02);
        break;
      case 'whistle': {
        box(torso, 0.04, 0.06, 0.03, '#c0c0c0', 0.03, dims.torso * 0.72, dims.d / 2 + 0.02);
        const g = new THREE.Group();
        box(g, 0.03, 0.42, 0.02, '#ffd60a', 0, -0.21, 0.06);
        inHand(armR, g);
        break;
      }
      case 'fan': {
        const g = new THREE.Group();
        const f = new THREE.Mesh(new THREE.CircleGeometry(0.2, 6, 0, Math.PI), mat(sec, { side: THREE.DoubleSide }));
        f.position.set(0, -0.05, 0.1);
        g.add(f);
        inHand(armR, g);
        break;
      }
      case 'bones':
        for (let i = 0; i < 7; i++) {
          const ang = (i / 6) * Math.PI - Math.PI;
          ball(torso, 0.03, '#f8f1e5', Math.cos(ang) * dims.w * 0.35, dims.torso * 0.9 + Math.sin(ang) * 0.08, dims.d / 2 + 0.02, 0);
        }
        break;
      case 'guitar': {
        const g = new THREE.Group();
        box(g, 0.3, 0.4, 0.08, '#a0522d', 0, 0, 0);
        box(g, 0.06, 0.45, 0.04, '#5c3317', 0, 0.4, 0);
        g.position.set(0, dims.torso * 0.1, -dims.d / 2 - 0.06);
        g.rotation.z = 0.5;
        torso.add(g);
        break;
      }
      case 'crucifix':
        box(torso, 0.05, 0.28, 0.03, '#e9c46a', 0, dims.torso * 0.3, dims.d / 2 + 0.03);
        box(torso, 0.17, 0.05, 0.03, '#e9c46a', 0, dims.torso * 0.47, dims.d / 2 + 0.03);
        break;
      case 'skate': {
        const g = new THREE.Group();
        box(g, 0.2, 0.62, 0.04, sec, 0, -0.3, -0.02);
        g.rotation.x = 0.2;
        inHand(armL, g);
        break;
      }
      case 'cart': {
        cart = new THREE.Group();
        box(cart, 0.55, 0.35, 0.45, '#7a6a5a', 0, 0.22, 0);
        for (let i = 0; i < 5; i++) ball(cart, 0.07, ['#ffd166', '#2a9d8f', '#e63946', '#adb5bd', '#8d5524'][i], (rnd() - 0.5) * 0.4, 0.6, (rnd() - 0.5) * 0.3, 0);
        for (const sx of [-0.25, 0.25]) cyl(cart, 0.08, 0.08, 0.04, '#222222', sx, 0.08, 0.15, 6).rotation.z = Math.PI / 2;
        cart.position.set(0, 0, 0.55 / scale + 0.2);
        cart.scale.setScalar(1 / scale * 1.4);
        rig.add(cart);
        break;
      }
      case 'headphones':
        box(head, headS + 0.08, 0.04, 0.06, '#222222', 0, top + 0.01, 0);
        break;
      case 'lantern':
        inHand(armL, box(new THREE.Group(), 0.1, 0.14, 0.1, '#ffd166', 0, -0.14, 0.05, { glow: true }));
        break;
      default:
        break;
    }
  }

  return {
    root, pose, rig, torso, head, legs, arms, flames, juggle, scale,
    height: 1.7 * (v.height || 1),
    gait: gaitKind(v.movement),
    body,
  };
}

/**
 * Um personagem na tela: guarda a parte visual (placeholder ou .glb) e
 * aplica a animação pedida. `anim` vem da ação; `override` é curto (tombo,
 * briga, o olhar) e ganha da ação até acabar.
 */
export class Actor {
  constructor(id, info, parts, glb = null) {
    this.id = id;
    this.info = info;
    this.parts = parts;
    this.root = parts.root;
    this.glb = glb; // {mixer, clips: {name: AnimationAction}, names: []}
    this.anim = 'idle';
    this.override = null;
    this.overrideUntil = 0;
    this.heading = (hashString(id) % 628) / 100;
    this.path = null; // {from, to, t0, dur}
    this.wanderAt = 0;
    this.place = info.place;
    this.phase = (hashString(id + 'p') % 1000) / 160;
    this.fade = null; // {kind: 'in'|'out'|'sink', t0, dur, done}
    this.faceTarget = null; // THREE.Vector3 (briga: um olha para o outro)
    this.currentClip = null;
  }

  setAnim(name) {
    this.anim = name;
  }

  play(name, seconds, now) {
    this.override = name;
    this.overrideUntil = now + seconds * 1000;
  }

  moveTo(x, z, seconds, now) {
    const from = this.root.position.clone();
    const to = new THREE.Vector3(x, 0, z);
    if (from.distanceTo(to) < 0.05) return;
    this.path = { from, to, t0: now, dur: Math.max(0.2, seconds) * 1000 };
  }

  get moving() {
    return this.path !== null;
  }

  headPosition(out = new THREE.Vector3()) {
    this.root.getWorldPosition(out);
    out.y += (this.parts.height || 1.7) * (this.anim === 'sleep' && !this.override ? 0.25 : 1.0) + 0.15;
    return out;
  }

  /** Chamado a cada quadro. `t` em segundos, `now` em ms, `camera` para o olhar. */
  update(dt, t, now, camera) {
    // caminho
    if (this.path) {
      const p = this.path;
      const k = Math.min(1, (now - p.t0) / p.dur);
      const pos = new THREE.Vector3().lerpVectors(p.from, p.to, k);
      if (this.parts.gait === 'zigzag') pos.x += Math.sin(k * 18) * 0.25 * (1 - k);
      this.root.position.copy(pos);
      const dx = p.to.x - p.from.x, dz = p.to.z - p.from.z;
      if (Math.abs(dx) + Math.abs(dz) > 0.01) this.heading = Math.atan2(dx, dz);
      if (k >= 1) this.path = null;
    }
    let anim = this.override && now < this.overrideUntil ? this.override : null;
    if (!anim) {
      this.override = null;
      anim = this.path ? 'walk' : this.anim;
    }
    // vira na direção certa (suave)
    let targetHeading = this.heading;
    if (anim === 'stare' && camera) {
      const wp = this.root.getWorldPosition(new THREE.Vector3());
      targetHeading = Math.atan2(camera.position.x - wp.x, camera.position.z - wp.z);
    } else if (anim === 'fight' && this.faceTarget) {
      const wp = this.root.getWorldPosition(new THREE.Vector3());
      targetHeading = Math.atan2(this.faceTarget.x - wp.x, this.faceTarget.z - wp.z);
    }
    let diff = targetHeading - this.root.rotation.y;
    diff = Math.atan2(Math.sin(diff), Math.cos(diff));
    this.root.rotation.y += diff * Math.min(1, dt * (anim === 'stare' ? 4 : 8));

    if (this.glb) this.updateGlb(anim, dt, t, now);
    else this.updatePlaceholder(anim, t, now);
    this.updateFade(now);
  }

  updateGlb(anim, dt, t, now) {
    const g = this.glb;
    const choice = pickClip(g.names, anim, g.fallback || {});
    if (choice.clip !== this.currentClip) {
      const next = choice.clip ? g.actions[choice.clip] : null;
      const prev = this.currentClip ? g.actions[this.currentClip] : null;
      if (next) {
        next.reset();
        next.setLoop(anim === 'fall' ? THREE.LoopOnce : THREE.LoopRepeat);
        next.clampWhenFinished = true;
        next.fadeIn(0.25).play();
      }
      if (prev && prev !== next) prev.fadeOut(0.25);
      this.currentClip = choice.clip;
    }
    g.mixer.update(dt);
    // o que o .glb não tem, o movimento procedural completa (no corpo inteiro)
    const pose = this.parts.pose;
    pose.position.set(0, 0, 0);
    pose.rotation.set(0, 0, 0);
    if (!choice.exact) proceduralRoot(pose, anim, t + this.phase, now, this.overrideUntil);
  }

  updatePlaceholder(anim, t0, now) {
    const P = this.parts;
    const t = t0 + this.phase;
    const [legL, legR] = P.legs;
    const [armL, armR] = P.arms;
    // volta para a pose neutra e aplica a da animação
    P.pose.position.set(0, 0, 0);
    P.pose.rotation.set(0, 0, 0);
    P.torso.position.y = P.legs[0].position.y;
    P.torso.rotation.set(P.body === 'corcunda' ? 0.45 : 0, 0, 0);
    P.head.rotation.set(P.body === 'corcunda' ? -0.35 : 0, 0, 0);
    legL.rotation.set(0, 0, 0);
    legR.rotation.set(0, 0, 0);
    armL.rotation.set(0, 0, 0.08);
    armR.rotation.set(0, 0, -0.08);
    const gait = P.gait;
    const speed = { slow: 0.6, heavy: 0.55, quick: 1.6, shuffle: 0.7, glide: 0.5, strut: 0.8, hop: 1.2 }[gait] || 1;
    switch (anim) {
      case 'idle': {
        P.torso.position.y += Math.sin(t * 2) * 0.008;
        P.head.rotation.y = Math.sin(t * 0.5) * 0.25;
        if (gait === 'slow') { armL.rotation.x = 0.5; armR.rotation.x = 0.5; armL.rotation.z = -0.3; armR.rotation.z = 0.3; } // mãos nas costas
        break;
      }
      case 'walk': {
        const f = t * 8 * speed;
        let swing = gait === 'shuffle' ? 0.15 : gait === 'glide' ? 0.05 : gait === 'stiff' ? 0.35 : 0.55;
        if (gait === 'skate') swing = 0;
        legL.rotation.x = Math.sin(f) * swing;
        legR.rotation.x = -Math.sin(f) * swing;
        armL.rotation.x = -Math.sin(f) * swing * 0.8;
        armR.rotation.x = Math.sin(f) * swing * 0.8;
        if (gait === 'stiff') { armL.rotation.x = 0; }
        let bob = Math.abs(Math.sin(f)) * 0.05;
        if (gait === 'hop') bob = Math.abs(Math.sin(f * 0.5)) * 0.3;
        if (gait === 'glide' || gait === 'skate') bob = 0;
        P.pose.position.y = bob;
        // balanço: o corpo inteiro gingando de um lado para o outro
        const sway = { swing: 0.14, strut: 0.1, heavy: 0.1, normal: 0.05 }[gait] ?? 0.04;
        P.pose.rotation.z = Math.sin(f) * sway;
        if (gait === 'sneak') { P.torso.rotation.x = 0.35; P.pose.position.y = -0.05; }
        if (gait === 'strut') P.head.rotation.x = -0.25; // nariz empinado
        if (gait === 'slow') { armL.rotation.x = 0.5; armR.rotation.x = 0.5; armL.rotation.z = -0.3; armR.rotation.z = 0.3; }
        if (gait === 'quick') P.torso.rotation.x = 0.12;
        break;
      }
      case 'talk':
        P.head.rotation.x = Math.sin(t * 7) * 0.12;
        armR.rotation.x = -0.9 + Math.sin(t * 4) * 0.5;
        armR.rotation.z = -0.3;
        P.torso.rotation.y = Math.sin(t * 2) * 0.1;
        break;
      case 'work': {
        const k = Math.sin(t * 6.5);
        armR.rotation.x = -1.6 + k * 0.9;
        armL.rotation.x = -0.6 + Math.sin(t * 6.5 + 1) * 0.2;
        P.torso.rotation.x = 0.15 + Math.max(0, k) * 0.12;
        break;
      }
      case 'sleep':
        P.pose.rotation.x = -Math.PI / 2;
        P.pose.position.set(0, 0.18, -0.2);
        P.torso.position.y += Math.sin(t * 1.2) * 0.02; // respiração
        armL.rotation.z = 0.2; armR.rotation.z = -0.2;
        break;
      case 'fall': {
        // tropeça, cai de costas, fica um pouco no chão e levanta
        const left = (this.overrideUntil - now) / 1000;
        const total = 2.6;
        const e = Math.min(1, Math.max(0, (total - left) / 0.35));
        const up = Math.min(1, Math.max(0, (0.6 - left) / 0.6));
        const k = e * (1 - up);
        P.pose.rotation.x = -k * (Math.PI / 2 - 0.1);
        P.pose.position.y = k * 0.12 + Math.sin(e * Math.PI) * 0.15;
        legL.rotation.x = -k * 0.9; legR.rotation.x = -k * 0.4;
        armL.rotation.z = 0.08 + k * 1.4; armR.rotation.z = -0.08 - k * 1.4;
        break;
      }
      case 'fight': {
        const f = t * 11;
        P.pose.position.z = Math.sin(f * 0.5) * 0.12;
        P.pose.position.y = Math.abs(Math.sin(f * 0.5)) * 0.06;
        armL.rotation.x = -1.5 + Math.sin(f) * 0.7;
        armR.rotation.x = -1.5 - Math.sin(f) * 0.7;
        P.torso.rotation.y = Math.sin(f) * 0.25;
        P.torso.rotation.x = 0.15;
        legL.rotation.x = 0.3; legR.rotation.x = -0.3;
        break;
      }
      case 'pray':
        // ajoelhado, mãos para cima, cabeça baixa
        P.pose.position.y = -P.legs[0].position.y * P.rig.scale.y * 0.42;
        legL.rotation.x = Math.PI / 2 - 0.1; legR.rotation.x = Math.PI / 2 - 0.1;
        armL.rotation.x = -2.6 + Math.sin(t * 1.5) * 0.08; armR.rotation.x = -2.6 + Math.sin(t * 1.5 + 0.4) * 0.08;
        armL.rotation.z = -0.15; armR.rotation.z = 0.15;
        P.head.rotation.x = 0.3;
        break;
      case 'dance': {
        const f = t * 6;
        P.pose.position.y = Math.abs(Math.sin(f)) * 0.22;
        P.pose.rotation.y = Math.sin(f * 0.25) * 1.2;
        armL.rotation.z = 2.4 + Math.sin(f) * 0.4;
        armR.rotation.z = -2.4 - Math.sin(f + 1) * 0.4;
        legL.rotation.x = Math.sin(f) * 0.4; legR.rotation.x = -Math.sin(f) * 0.4;
        P.pose.rotation.z = Math.sin(f) * 0.12;
        break;
      }
      case 'stare':
        // para tudo e encara a tela, cabeça levemente torta
        P.head.rotation.z = 0.18;
        P.head.rotation.x = -0.12;
        break;
      default:
        break;
    }
    // malabarismo: as bolinhas giram por cima das mãos (e caem quando ele cai)
    if (P.juggle.length) {
      const on = anim === 'work' || anim === 'idle' || anim === 'talk';
      P.juggle.forEach((b, i) => {
        const a = t * 5 + (i * Math.PI * 2) / 3;
        if (on) b.position.set(Math.cos(a) * 0.25, P.legs[0].position.y + 1.05 + Math.sin(a) * 0.3, 0.3);
        else b.position.set((i - 1) * 0.2, 0.05, 0.4);
      });
    }
    for (const f of P.flames) f.scale.setScalar(0.8 + Math.abs(Math.sin(t * 13 + f.position.x * 30)) * 0.5);
  }

  /** Aparecer/sumir (túnel, morte). */
  startFade(kind, seconds, now, done) {
    this.fade = { kind, t0: now, dur: seconds * 1000, done };
  }

  updateFade(now) {
    const f = this.fade;
    const r = this.parts.rig;
    const base = this.parts.scale || 1;
    if (!f) return;
    const k = Math.min(1, (now - f.t0) / f.dur);
    if (f.kind === 'out') {
      // sugado pelo túnel: estica para cima e afina até sumir
      r.scale.set(base * (1 - k), base * (1 + k * 2), base * (1 - k));
    } else if (f.kind === 'in') {
      const e = 1 - k;
      r.scale.set(base * k, base * (1 + e * 2), base * k);
    } else if (f.kind === 'sink') {
      this.root.position.y = -k * 1.8;
    }
    if (k >= 1) {
      if (f.kind === 'in') r.scale.setScalar(base);
      this.fade = null;
      if (f.done) f.done();
    }
  }
}

/** Movimento procedural no corpo inteiro (para .glb sem a animação pedida). */
function proceduralRoot(pose, anim, t, now, until) {
  switch (anim) {
    case 'walk':
      pose.position.y = Math.abs(Math.sin(t * 8)) * 0.05;
      pose.rotation.z = Math.sin(t * 8) * 0.05;
      break;
    case 'sleep':
      pose.rotation.x = -Math.PI / 2;
      pose.position.y = 0.2;
      break;
    case 'fall': {
      const left = (until - now) / 1000;
      const k = Math.min(1, Math.max(0, (2.6 - left) / 0.35)) * (1 - Math.min(1, Math.max(0, (0.6 - left) / 0.6)));
      pose.rotation.x = -k * (Math.PI / 2 - 0.1);
      break;
    }
    case 'fight':
      pose.position.z = Math.sin(t * 5.5) * 0.12;
      pose.rotation.z = Math.sin(t * 11) * 0.06;
      break;
    case 'dance':
      pose.position.y = Math.abs(Math.sin(t * 6)) * 0.22;
      pose.rotation.y = Math.sin(t * 1.5) * 1.2;
      break;
    case 'pray':
      pose.position.y = -0.3;
      pose.rotation.x = 0.25;
      break;
    case 'talk':
      pose.rotation.y = Math.sin(t * 2) * 0.1;
      break;
    case 'work':
      pose.rotation.x = 0.1 + Math.max(0, Math.sin(t * 6.5)) * 0.15;
      break;
    default:
      break;
  }
}

// ------------------------------------------------------------------ .glb
let loaderPromise = null;
const glbCache = new Map();

async function loader() {
  if (!loaderPromise) {
    loaderPromise = Promise.all([
      import('three/examples/jsm/loaders/GLTFLoader.js'),
      import('three/examples/jsm/utils/SkeletonUtils.js'),
    ]).then(([g, s]) => ({ loader: new g.GLTFLoader(), clone: s.clone }));
  }
  return loaderPromise;
}

/** Carrega (uma vez) e clona um .glb. Devolve null se der erro (fica o placeholder). */
export async function loadGlb(url) {
  const { loader: l, clone } = await loader();
  if (!glbCache.has(url)) {
    glbCache.set(url, new Promise((resolve) => l.load(url, resolve, undefined, (err) => {
      console.warn('[viewer] não consegui carregar', url, err);
      resolve(null);
    })));
  }
  const gltf = await glbCache.get(url);
  if (!gltf) return null;
  return { scene: clone(gltf.scene), animations: gltf.animations };
}

/**
 * Prepara um .glb de personagem: materiais com a cara de PS1 (texturas sem
 * suavizar e vértices tremendo), escala de segurança (se o modelo veio em
 * centímetros) e o mixer das animações.
 */
export function prepareCharacterGlb(model, visual, fallback) {
  const { scene, animations } = model;
  scene.traverse((o) => {
    if (!o.isMesh) return;
    const src = Array.isArray(o.material) ? o.material : [o.material];
    const out = src.map((m) => {
      const n = mat(m.color ? '#' + m.color.getHexString() : '#cccccc', { unique: true });
      n.flatShading = false;
      if (m.map) {
        m.map.magFilter = THREE.NearestFilter;
        m.map.minFilter = THREE.NearestFilter;
        n.map = m.map;
      }
      if (m.vertexColors) n.vertexColors = true;
      // Fase 6: material emissivo do Blender (Emission) continua aceso (olhos, lanterna, LED)
      if (m.emissive && m.emissive.getHex() !== 0) {
        n.emissive.copy(m.emissive);
        n.emissiveIntensity = m.emissiveIntensity ?? 1;
        if (m.emissiveMap) n.emissiveMap = m.emissiveMap;
      }
      if (m.transparent) { n.transparent = true; n.opacity = m.opacity; }
      n.needsUpdate = true;
      return n;
    });
    o.material = Array.isArray(o.material) ? out : out[0];
    o.frustumCulled = false; // modelos com esqueleto às vezes somem por causa da caixa
  });
  // escala: o modelo é usado do tamanho que veio (1 unidade = 1 metro). Se estiver
  // claramente errado (exportado em cm, ou minúsculo), ajusta para a altura do YAML.
  const bbox = new THREE.Box3().setFromObject(scene);
  const h = bbox.max.y - bbox.min.y;
  const want = 1.7 * ((visual && visual.height) || 1);
  let warn = null;
  if (h > 0 && (h < 0.3 || h > 6)) {
    scene.scale.multiplyScalar(want / h);
    warn = `altura ${h.toFixed(2)} fora do esperado (0,3 a 6 m); ajustei para ${want.toFixed(2)} m`;
  }
  const bbox2 = new THREE.Box3().setFromObject(scene);
  if (Math.abs(bbox2.min.y) > 0.25 * (bbox2.max.y - bbox2.min.y)) {
    scene.position.y -= bbox2.min.y;
    warn = (warn ? warn + '; ' : '') + 'a origem não estava nos pés; ajustei';
  }
  const mixer = new THREE.AnimationMixer(scene);
  const actions = {};
  for (const clip of animations || []) actions[clip.name] = mixer.clipAction(clip);
  return { scene, mixer, actions, names: Object.keys(actions), fallback, height: want, warn };
}
