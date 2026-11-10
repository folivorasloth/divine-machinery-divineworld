// O viewer de uma tela: /viewer/?screen=<id>
// Conecta no WebSocket do mundo (/ws?screen=<id>), desenha os lugares daquela
// tela e anima o que chega. A simulação é a fonte da verdade: se a conexão
// cai, a página tenta de novo sozinha e redesenha tudo com o `hello`.
import * as THREE from 'three';
import './style.css';
import { setupRenderer, glow } from './ps1.js';
import { buildPlace, addGrave, buildRubble, PLOT } from './places.js';
import { buildPlaceholder, Actor, loadGlb, prepareCharacterGlb } from './characters.js';
import { Environment, buildFogBank } from './environment.js';
import { Overlay } from './overlay.js';
import {
  DEFAULT_VISUAL, animForAction, gridLayout, gridPositions, worldHours, shortenBubble, bubbleDuration,
  teleportAppearAt, hashString, seededRandom,
} from './logic.js';

const GAP = 2.2;
const params = new URLSearchParams(location.search);
const screenId = params.get('screen');
const app = document.getElementById('app');

// estado exposto para depuração e para os testes (Playwright): window.__dw
const dbg = { screen: screenId, connected: false, hellos: 0, messages: {}, log: [], actors: {}, places: [], fps: 0 };
window.__dw = dbg;
const note = (kind, data) => {
  dbg.messages[kind] = (dbg.messages[kind] || 0) + 1;
  if (kind === 'teleport' || kind === 'apparition' || kind === 'fog') {
    dbg.log.push({ at: Date.now(), kind, ...data });
    if (dbg.log.length > 200) dbg.log.shift();
  }
};

if (!screenId) {
  showPicker();
} else {
  start();
}

// ------------------------------------------------------------ sem ?screen=
async function showPicker() {
  document.body.classList.add('picker');
  app.innerHTML = '<h1>Divine Machinery — o Mundo Vivo</h1><p>Escolha a tela (abra cada uma no seu monitor):</p><ul id="list"></ul>' +
    '<p><a href="layout.html">Mapa das telas na parede</a> · <a href="/chat">Chat do Mundo</a></p>';
  try {
    const screens = await (await fetch('/api/screens')).json();
    const ul = document.getElementById('list');
    for (const s of screens) {
      const li = document.createElement('li');
      li.innerHTML = `<a href="?screen=${encodeURIComponent(s.id)}"></a> <small></small>`;
      li.querySelector('a').textContent = s.nome || s.name || s.id;
      li.querySelector('small').textContent = `(${s.id}) ${(s.lugares || s.places || []).join(', ')}`;
      ul.appendChild(li);
    }
  } catch (e) {
    app.insertAdjacentHTML('beforeend', '<p>Não consegui falar com o servidor do mundo.</p>');
  }
}

// ------------------------------------------------------------------ a tela
function start() {
  const canvas = document.createElement('canvas');
  canvas.id = 'world';
  app.appendChild(canvas);
  const layer = document.createElement('div');
  layer.className = 'overlay';
  app.appendChild(layer);
  const ghostLayer = document.createElement('div');
  ghostLayer.className = 'apparition-fx';
  app.appendChild(ghostLayer);

  let view = null; // tudo que depende do hello
  let renderer = null;
  let resizeFn = null;
  let models = { characters: [], places: [] };
  let quality = null;
  let maxFps = 30;

  const overlay = new Overlay(layer, { showNames: true, showClock: true });
  overlay.setStatus('conectando ao mundo…');

  // ------------------------------------------------------------ conexão
  let ws = null;
  let retry = 1000;
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws?screen=${encodeURIComponent(screenId)}`);
    ws.onopen = () => { retry = 1000; dbg.connected = true; };
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      note(msg.type, msg.type === 'teleport' ? msg : msg.type === 'fog' ? msg : {});
      if (msg.type === 'hello') onHello(msg);
      else if (msg.type === 'error') overlay.setStatus(`tela '${screenId}' não existe. Telas: ${(msg.screens || []).join(', ')}`);
      else if (view) handle(msg);
    };
    ws.onclose = () => {
      dbg.connected = false;
      overlay.setStatus('sem conexão com o mundo — tentando de novo…');
      setTimeout(connect, retry);
      retry = Math.min(15000, retry * 1.7);
    };
  }
  setInterval(() => { if (ws && ws.readyState === 1) ws.send('{"type":"ping"}'); }, 25000);

  async function onHello(hello) {
    dbg.hellos++;
    try { models = await (await fetch('/api/models')).json(); } catch { /* sem lista: só placeholders */ }
    const me = hello.screens.find((s) => s.id === screenId) || { places: hello.places.map((p) => p.id), max_fps: 30, quality: 'media', name: screenId };
    const visual = { ...DEFAULT_VISUAL, ...((hello.config && hello.config.visual) || {}) };
    const qName = params.get('qualidade') || params.get('quality') || me.quality || 'media';
    quality = { ...(visual.qualities[qName] || visual.qualities.media) };
    if (params.get('altura')) quality.render_height = Number(params.get('altura'));
    maxFps = Number(params.get('fps')) || me.max_fps || 30;
    overlay.opts.showNames = params.get('nomes') === '0' ? false : visual.show_names;
    overlay.opts.showClock = params.get('relogio') === '0' ? false : visual.show_clock;
    overlay.hud.hidden = !overlay.opts.showClock;
    if (view) disposeView();
    if (!renderer) {
      const r = setupRenderer(canvas, quality);
      renderer = r.renderer;
      resizeFn = r.resize;
    } else {
      const r = setupRenderer(canvas, quality); // qualidade pode ter mudado
      renderer.dispose();
      renderer = r.renderer;
      resizeFn = r.resize;
    }
    view = buildView(hello, me, visual);
    overlay.setStatus('');
    dbg.places = view.order;
    dbg.quality = qName;
    dbg.maxFps = maxFps;
  }

  function disposeView() {
    overlay.clear();
    view.scene.traverse((o) => { if (o.geometry) o.geometry.dispose(); });
    view = null;
  }

  // ------------------------------------------------------------- montar
  function buildView(hello, me, visual) {
    const scene = new THREE.Scene();
    const order = me.places.filter((id) => hello.places.some((p) => p.id === id));
    const places = Object.fromEntries(hello.places.map((p) => [p.id, p]));
    const { cols } = gridLayout(order.length, (window.innerWidth || 16) / (window.innerHeight || 9));
    const pos = gridPositions(order, cols, PLOT, GAP);
    const plots = {};
    let sinister = 0;
    const lamps = [];
    for (const id of order) {
      const p = places[id];
      if (p.sinister) sinister++;
      const group = new THREE.Group();
      group.position.set(pos[id].x, 0, pos[id].z);
      scene.add(group);
      const built = buildPlace(p, quality.detail);
      group.add(built.root);
      const plot = { id, place: p, group, built, center: new THREE.Vector3(pos[id].x, 0, pos[id].z), used: new Map(),
        portals: {}, rubble: null, fog: null, graves: 0 };
      plots[id] = plot;
      for (const l of built.lamps) lamps.push({ ...l, x: l.x + pos[id].x, z: l.z + pos[id].z });
      if (models.places.includes(id)) replacePlaceWithGlb(plot);
      // portais dos túneis (um por conexão de túnel)
      const tunnels = (p.connections || []).filter((c) => c.kind === 'tunel');
      tunnels.forEach((c, i) => {
        const s = built.tunnelSpot;
        const portal = buildPortal(id + c.to);
        portal.position.set(s.x - i * 1.6, 0, s.z);
        group.add(portal);
        plot.portals[c.to] = portal;
        const target = hello.places.find((q) => q.id === c.to);
        const lab = overlay.addLabel('⇄ ' + (target ? target.name : nameOfPlace(hello, c.to)),
          new THREE.Vector3(pos[id].x + s.x - i * 1.6, 2.5, pos[id].z + s.z), 'portal-label');
        portal.userData.label = lab;
      });
      // nome do lugar na frente do diorama
      plot.label = overlay.addLabel(p.name, new THREE.Vector3(pos[id].x, 0, pos[id].z + PLOT / 2 + 0.3));
      setStructures(plot, p.structures || []);
      if (p.fog) setFog(plot, true);
      if (id === 'cemetery') for (let i = 0; i < Math.min(24, hello.dead || 0); i++) addGrave(built.root, plot.graves++);
    }
    // luzes de verdade (só na qualidade alta): os primeiros lampiões
    const pointLights = [];
    for (const l of lamps.slice(0, quality.extra_lights || 0)) {
      const pl = new THREE.PointLight(l.color, 0, 7, 1.6);
      pl.position.set(l.x, l.y, l.z);
      scene.add(pl);
      pointLights.push(pl);
    }
    // limites da grade e câmera
    const xs = order.map((id) => pos[id].x), zs = order.map((id) => pos[id].z);
    const bounds = {
      minX: Math.min(...xs) - PLOT / 2, maxX: Math.max(...xs) + PLOT / 2,
      minZ: Math.min(...zs) - PLOT / 2, maxZ: Math.max(...zs) + PLOT / 2,
    };
    bounds.w = bounds.maxX - bounds.minX;
    bounds.d = bounds.maxZ - bounds.minZ;
    bounds.cx = (bounds.minX + bounds.maxX) / 2;
    bounds.cz = (bounds.minZ + bounds.maxZ) / 2;
    const camera = new THREE.PerspectiveCamera(34, 16 / 9, 0.5, 400);
    const env = new Environment(scene, bounds, quality, visual, order.length ? sinister / order.length : 0);
    env.setWeather(hello.world.weather || { kind: 'nublado' });
    const v = {
      scene, camera, env, plots, order, places, visual, bounds, pointLights, me,
      actors: new Map(), pending: new Map(), creatures: new Map(), apparition: null,
      hours: worldHours(hello.world.ts), speed: hello.world.speed || 1, paused: !!hello.world.paused,
      weatherLabel: hello.world.weather ? hello.world.weather.label : '', temp: hello.world.weather ? hello.world.weather.temp : null,
      screens: hello.screens, hello,
    };
    view = v;
    fit(v);
    for (const c of hello.characters) upsert(c, true);
    for (const c of hello.creatures || []) setCreature(c, true);
    return v;
  }

  function nameOfPlace(hello, id) {
    return (hello.place_names && hello.place_names[id]) || id;
  }

  function fit(v) {
    const sz = resizeFn();
    const { camera, bounds } = v;
    camera.aspect = sz.aspect;
    camera.updateProjectionMatrix();
    const target = new THREE.Vector3(bounds.cx, 0, bounds.cz + 0.6);
    const dir = new THREE.Vector3(0, Math.sin(0.92), Math.cos(0.92)); // ~53° de cima
    const corners = [];
    for (const x of [bounds.minX, bounds.maxX]) for (const z of [bounds.minZ, bounds.maxZ]) for (const y of [0, 3.5]) corners.push(new THREE.Vector3(x, y, z));
    // a fileira do fundo tem coisa alta (torre da Catedral, montanhas): um pouco de céu em cima
    for (const x of [bounds.minX, bounds.maxX]) corners.push(new THREE.Vector3(x, 7, bounds.minZ + 2));
    corners.push(new THREE.Vector3(bounds.cx, 0, bounds.maxZ + 1.4)); // nomes dos lugares
    let lo = 2, hi = 400;
    for (let i = 0; i < 30; i++) {
      const mid = (lo + hi) / 2;
      camera.position.copy(target).addScaledVector(dir, mid);
      camera.lookAt(target);
      camera.updateMatrixWorld();
      const ok = corners.every((c) => {
        const p = c.clone().project(camera);
        return Math.abs(p.x) < 0.97 && p.y > -0.95 && p.y < 0.93;
      });
      if (ok) hi = mid; else lo = mid;
    }
    camera.position.copy(target).addScaledVector(dir, hi);
    camera.lookAt(target);
    v.env.camDist = hi;
  }

  window.addEventListener('resize', () => { if (view) fit(view); });

  function buildPortal(seed) {
    const g = new THREE.Group();
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.75, 0.12, 4, 10), glow('#b388ff', { unique: true }));
    ring.position.y = 0.95;
    const inner = new THREE.Mesh(new THREE.CircleGeometry(0.65, 10), glow('#3c096c', { opacity: 0.85, unique: true }));
    inner.position.y = 0.95;
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.75, 0.15, 8), glow('#240046'));
    g.add(ring, inner, base);
    g.userData = { ring, inner, activeUntil: 0, phase: (hashString(seed) % 100) / 10 };
    return g;
  }

  function replacePlaceWithGlb(plot) {
    loadGlb(`models/places/${plot.id}.glb`).then((m) => {
      if (!m || !view || view.plots[plot.id] !== plot) return;
      plot.group.remove(plot.built.root);
      m.scene.name = `glb:${plot.id}`;
      plot.group.add(m.scene);
      dbg.placeModels = [...(dbg.placeModels || []), plot.id];
    });
  }

  // ------------------------------------------------------------ estado
  function setStructures(plot, list) {
    const broken = list.filter((s) => s.state && s.state !== 'inteiro').length;
    if (plot.rubble) { plot.group.remove(plot.rubble); plot.rubble = null; }
    if (broken > 0) {
      plot.rubble = buildRubble(broken, plot.id + broken);
      plot.rubble.position.set(1.8, 0, 1.4);
      plot.group.add(plot.rubble);
    }
  }

  function setFog(plot, on) {
    if (on && !plot.fog) {
      plot.fog = buildFogBank(plot.id);
      plot.group.add(plot.fog);
      plot.built.root.visible = false;
      plot.label.el.classList.add('fogged');
      plot.label.el.textContent = `${plot.place.name} — na névoa`;
    } else if (!on && plot.fog) {
      plot.group.remove(plot.fog);
      plot.fog = null;
      plot.built.root.visible = true;
      plot.label.el.classList.remove('fogged');
      plot.label.el.textContent = plot.place.name;
    }
    for (const a of view.actors.values()) if (a.place === plot.id) a.root.visible = !on;
  }

  function hiddenPlaces() {
    const s = new Set();
    for (const p of Object.values(view.plots)) if (p.fog) s.add(p.id);
    return s;
  }

  /** Um lugar para o personagem ficar dentro do diorama (fixo por id + ação, sem dois no mesmo ponto). */
  function spotFor(plot, id, action) {
    const spots = plot.built.spots;
    for (const [k, owner] of plot.used) if (owner === id) plot.used.delete(k);
    let i = hashString(id + (action || '')) % spots.length;
    for (let tries = 0; tries < spots.length && plot.used.has(i); tries++) i = (i + 1) % spots.length;
    plot.used.set(i, id);
    const s = spots[i];
    return new THREE.Vector3(plot.center.x + s.x, 0, plot.center.z + s.z);
  }

  function releaseSpot(id) {
    for (const p of Object.values(view.plots)) for (const [k, owner] of p.used) if (owner === id) p.used.delete(k);
  }

  function makeActor(info) {
    const parts = buildPlaceholder(info.id, info.visual);
    const cs = view.visual.character_scale || 1;
    parts.height *= cs;
    const actor = new Actor(info.id, info, parts);
    actor.root.scale.setScalar(cs);
    actor.root.name = `actor:${info.id}`;
    view.scene.add(actor.root);
    if (models.characters.includes(info.id)) {
      loadGlb(`models/characters/${info.id}.glb`).then((m) => {
        if (!m || !view || view.actors.get(info.id) !== actor) return;
        const glb = prepareCharacterGlb(m, info.visual, view.visual.animation_fallback || {});
        if (glb.warn) console.warn(`[viewer] ${info.id}.glb: ${glb.warn}`);
        // troca o boneco de primitivas pelo modelo do João (mesma posição e pose)
        actor.parts.pose.remove(actor.parts.rig);
        const holder = new THREE.Group();
        holder.add(glb.scene);
        actor.parts.pose.add(holder);
        actor.parts.rig = holder;
        actor.parts.scale = 1;
        actor.parts.height = glb.height * (view.visual.character_scale || 1);
        actor.glb = glb;
        actor.currentClip = null;
        dbg.characterModels = [...(dbg.characterModels || []), info.id];
        dbg.clips = { ...(dbg.clips || {}), [info.id]: glb.names };
      });
    }
    view.actors.set(info.id, actor);
    return actor;
  }

  function removeActor(id) {
    const a = view.actors.get(id);
    if (!a) return;
    view.scene.remove(a.root);
    view.actors.delete(id);
    overlay.removeActor(id);
    releaseSpot(id);
  }

  /** Mensagem `character` (ou personagem do hello): cria, move ou atualiza. */
  function upsert(info, initial = false) {
    const now = performance.now();
    const id = info.id;
    const pend = view.pending.get(id);
    if (pend) { pend.info = info; return; } // ainda dentro do túnel: aparece quando a luz chegar
    let a = view.actors.get(id);
    if (info.alive === false) {
      if (a && !a.dying) {
        a.dying = true;
        a.play('fall', 2.6, now);
        setTimeout(() => a.startFade('sink', 2.5, performance.now(), () => removeActor(id)), 2600);
      }
      return;
    }
    const plot = view.plots[info.place];
    if (!plot) {
      // saiu da tela (Limbo, prisão de outra tela, um caminho para fora...)
      if (a && !a.leaving) {
        a.leaving = true;
        a.startFade('out', 0.6, now, () => removeActor(id));
      }
      return;
    }
    if (!a) {
      a = makeActor(info);
      const s = spotFor(plot, id, info.action);
      a.root.position.copy(s);
      if (!initial) a.startFade('in', 0.5, now);
    } else if (a.place !== info.place && !a.path) {
      a.moveTo(...xz(spotFor(plot, id, info.action)), 1.5, now);
    } else if (a.info.action !== info.action && !a.path && info.action) {
      const s = spotFor(plot, id, info.action);
      a.moveTo(s.x, s.z, Math.min(3, a.root.position.distanceTo(s) / 1.4), now);
    }
    a.info = info;
    a.place = info.place;
    a.leaving = false;
    a.setAnim(animForAction(info.action, false, view.visual));
    a.root.visible = !plot.fog;
    overlay.name(a, info.name);
  }

  const xz = (v3) => [v3.x, v3.z];

  function setCreature(c, on) {
    const key = c.uid ?? `${c.kind}@${c.place}`;
    const old = view.creatures.get(key);
    if (old) { view.scene.remove(old); view.creatures.delete(key); }
    if (!on) return;
    const plot = view.plots[c.place];
    if (!plot) return;
    const g = buildCreature(c.kind);
    const R = seededRandom(String(key));
    g.position.set(plot.center.x + (R() - 0.5) * 5, 0, plot.center.z - 1.5 - R() * 2);
    view.scene.add(g);
    view.creatures.set(key, g);
  }

  function buildCreature(kind) {
    const g = new THREE.Group();
    const R = seededRandom(kind);
    const color = new THREE.Color().setHSL(0.6 + R() * 0.3, 0.5, 0.12);
    const body = new THREE.Mesh(new THREE.IcosahedronGeometry(0.7, 0), new THREE.MeshLambertMaterial({ color, flatShading: true }));
    body.position.y = 0.9;
    body.scale.set(1, 1.4, 0.8);
    g.add(body);
    for (let i = 0; i < 6; i++) {
      const spike = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.6, 4), body.material);
      const a = (i / 6) * Math.PI * 2;
      spike.position.set(Math.cos(a) * 0.55, 1.2 + R() * 0.4, Math.sin(a) * 0.4);
      spike.rotation.z = -Math.cos(a) * 0.9;
      g.add(spike);
    }
    for (const s of [-1, 1]) {
      const eye = new THREE.Mesh(new THREE.IcosahedronGeometry(0.09, 0), glow(R() < 0.5 ? '#ff0033' : '#ccff00'));
      eye.position.set(s * 0.22, 1.25, 0.55);
      g.add(eye);
    }
    g.userData.creature = kind;
    return g;
  }

  // -------------------------------------------------------- mensagens
  function handle(msg) {
    const now = performance.now();
    switch (msg.type) {
      case 'character':
        upsert(msg);
        break;
      case 'move': {
        const a = view.actors.get(msg.id);
        const plot = view.plots[msg.to];
        if (!a || !plot || view.pending.has(msg.id)) break;
        const s = spotFor(plot, msg.id, a.info.action);
        // no tempo acelerado a caminhada dura pouco: no mínimo 0,8 s para dar para ver
        a.moveTo(s.x, s.z, Math.max(0.8, msg.duration_s || 1), now);
        a.place = msg.to;
        break;
      }
      case 'bubble': {
        const a = view.actors.get(msg.id);
        if (!a) break;
        const text = msg.short || shortenBubble(msg.text, a.info.name, view.visual.bubbles.max_chars);
        overlay.bubble(a, text, msg.duration_s || bubbleDuration(text, view.visual.bubbles), now);
        if (a.anim === 'idle') a.play('talk', Math.min(3, msg.duration_s || 2), now);
        break;
      }
      case 'teleport':
        teleport(msg, now);
        break;
      case 'fog': {
        const plot = view.plots[msg.place];
        if (plot) setFog(plot, !!msg.on);
        break;
      }
      case 'weather':
        view.env.setWeather(msg);
        view.weatherLabel = msg.label;
        break;
      case 'clock':
        view.hours = worldHours(msg.ts);
        view.speed = msg.speed || 1;
        view.paused = !!msg.paused;
        break;
      case 'apparition':
        if (msg.screen === screenId) apparition(msg, now);
        break;
      case 'creature':
        setCreature(msg, !!msg.on);
        break;
      case 'structures': {
        const plot = view.plots[msg.place];
        if (plot) setStructures(plot, msg.structures || []);
        break;
      }
      case 'event':
        onEvent(msg.event, now);
        break;
      default:
        break;
    }
  }

  function onEvent(ev, now) {
    if (!ev) return;
    if (ev.type === 'funeral_started') view.env.funeral = true;
    if (ev.type === 'funeral_ended') view.env.funeral = false;
    if (ev.type === 'grave' && view.plots.cemetery) addGrave(view.plots.cemetery.built.root, view.plots.cemetery.graves++);
    if (ev.type === 'weather_changed' && ev.data && ev.data.temp != null) view.temp = ev.data.temp;
    const anim = (view.visual.event_animation || {})[ev.type];
    if (!anim || anim === 'fall' && ev.type === 'death') return; // a morte tem sequência própria
    const who = ev.type === 'stare' ? ev.actors : (ev.actors || []).slice(0, 2);
    const seconds = anim === 'fall' ? 2.6 : anim === 'stare' ? 5 : 3.5;
    const actors = who.map((id) => view.actors.get(id)).filter(Boolean);
    actors.forEach((a, i) => {
      a.play(anim, seconds, now);
      if (anim === 'fight' && actors.length > 1) a.faceTarget = actors[1 - i].root.position;
    });
    // no tombo, só quem caiu cai (o outro só olha)
    if (anim === 'fall' && actors[1]) actors[1].play('stare', 2, now);
  }

  // ------------------------------------------------------------ túnel
  function screenAngle(fromId, toId) {
    const sc = Object.fromEntries(view.screens.map((s) => [s.id, s]));
    const a = sc[fromId], b = sc[toId];
    if (!a || !b) return 0;
    const ax = a.position_cm.x + a.size_cm.width / 2, ay = a.position_cm.y + a.size_cm.height / 2;
    const bx = b.position_cm.x + b.size_cm.width / 2, by = b.position_cm.y + b.size_cm.height / 2;
    return Math.atan2(by - ay, bx - ax);
  }

  function portalScreenPos(portal) {
    const p = portal.getWorldPosition(new THREE.Vector3());
    p.y += 1;
    return overlay.project(p, view.camera, window.innerWidth, window.innerHeight);
  }

  function teleport(msg, now) {
    const id = msg.id;
    const ms = Math.max(400, (msg.duration_s || 2) * 1000);
    if (msg.from_screen === screenId) {
      const plot = view.plots[msg.from_place];
      const portal = plot && plot.portals[msg.to_place];
      if (msg.phase === 'start') {
        if (portal) portal.userData.activeUntil = now + ms;
        const a = view.actors.get(id);
        if (a && portal) {
          const p = portal.getWorldPosition(new THREE.Vector3());
          a.moveTo(p.x, p.z + 0.2, 0.5, now);
          a.leaving = true;
          setTimeout(() => {
            a.startFade('out', 0.55, performance.now(), () => {
              removeActor(id);
              overlay.streak(portalScreenPos(portal), screenAngle(msg.from_screen, msg.to_screen), false, Math.min(ms, 1500));
            });
          }, 520);
        } else if (a) {
          removeActor(id);
        }
      } else if (view.actors.has(id) && view.actors.get(id).place === msg.from_place) {
        // a simulação já o tirou daqui (chegou o fim antes da animação acabar)
        const a = view.actors.get(id);
        if (!a.fade) removeActor(id);
      }
    }
    if (msg.to_screen === screenId) {
      const plot = view.plots[msg.to_place];
      const portal = plot && plot.portals[msg.from_place];
      let pend = view.pending.get(id);
      if (!pend) {
        pend = { start: null, end: null, duration: msg.duration_s || 0, place: msg.to_place, from: msg.from_place, info: null };
        view.pending.set(id, pend);
      }
      if (msg.phase === 'start') {
        pend.start = now;
        if (portal) portal.userData.activeUntil = now + ms + 800;
        // a luz chegando pela borda da tela, do lado de onde ele vem
        if (portal) setTimeout(() => overlay.streak(portalScreenPos(portal), screenAngle(msg.to_screen, msg.from_screen), true, Math.min(1500, ms)), Math.max(0, ms - 1500));
      } else {
        pend.end = now;
        if (portal) portal.userData.activeUntil = Math.max(portal.userData.activeUntil, now + 800);
      }
    }
  }

  function stepPending(now) {
    for (const [id, p] of view.pending) {
      const at = teleportAppearAt(p.start, p.duration, p.end);
      if (at == null || now < at) continue;
      if (!p.info) {
        if (now - at > 4000) view.pending.delete(id); // nunca veio o estado: desiste
        continue;
      }
      view.pending.delete(id);
      const plot = view.plots[p.info.place] || view.plots[p.place];
      if (!plot) continue;
      const portal = plot.portals[p.from];
      const a = makeActor(p.info);
      const start = portal ? portal.getWorldPosition(new THREE.Vector3()) : plot.center.clone();
      a.root.position.set(start.x, 0, start.z + 0.3);
      a.place = plot.id;
      a.info = p.info;
      a.setAnim(animForAction(p.info.action, false, view.visual));
      overlay.name(a, p.info.name);
      a.startFade('in', 0.6, now, () => {
        const s = spotFor(plot, id, p.info.action);
        a.moveTo(s.x, s.z, 1.4, performance.now());
      });
      dbg.arrivals = (dbg.arrivals || 0) + 1;
      dbg.log.push({ at: Date.now(), kind: 'appeared', id, place: plot.id });
    }
  }

  // ---------------------------------------------------------- Aparição
  function apparition(msg, now) {
    const secs = msg.duration_s || 4;
    const g = new THREE.Group();
    const m = new THREE.MeshBasicMaterial({ color: '#05060a', transparent: true, opacity: 0.22, depthWrite: false, fog: false });
    // várias cópias deslocadas = silhueta "borrada"
    for (let i = 0; i < 6; i++) {
      const s = new THREE.Group();
      const body = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 1.2, 4.2, 7), m);
      body.position.y = 2.1;
      const head = new THREE.Mesh(new THREE.IcosahedronGeometry(0.75, 1), m);
      head.position.y = 4.9;
      const shoulders = new THREE.Mesh(new THREE.SphereGeometry(1.3, 7, 4), m);
      shoulders.position.y = 3.8;
      shoulders.scale.y = 0.45;
      s.add(body, head, shoulders);
      s.position.set((i - 2.5) * 0.18, (i % 2) * 0.12, (i % 3) * 0.15);
      g.add(s);
    }
    const cam = view.camera;
    // passa entre a câmera e o mundo, de um lado para o outro
    const fwd = new THREE.Vector3();
    cam.getWorldDirection(fwd);
    const right = new THREE.Vector3().crossVectors(fwd, cam.up).normalize();
    const mid = cam.position.clone().addScaledVector(fwd, view.env.camDist * 0.35);
    mid.y -= 3;
    const span = view.env.camDist * 0.45;
    g.userData = { t0: now, dur: 1700, from: mid.clone().addScaledVector(right, -span), to: mid.clone().addScaledVector(right, span) };
    g.lookAt(cam.position);
    view.scene.add(g);
    view.apparition = g;
    ghostLayer.classList.remove('on');
    void ghostLayer.offsetWidth;
    ghostLayer.classList.add('on');
    for (const a of view.actors.values()) a.play('stare', secs + 2, now + Math.random() * 400);
    dbg.log.push({ at: Date.now(), kind: 'apparition-shown' });
  }

  function stepApparition(now) {
    const g = view.apparition;
    if (!g) return;
    const k = (now - g.userData.t0) / g.userData.dur;
    if (k >= 1) { view.scene.remove(g); view.apparition = null; return; }
    g.position.lerpVectors(g.userData.from, g.userData.to, k);
    g.children.forEach((c, i) => (c.position.x = (i - 2.5) * 0.18 + Math.sin(now * 0.03 + i) * 0.12));
  }

  // ------------------------------------------------------------- quadro
  let last = performance.now();
  let lastFrame = 0;
  let frames = 0;
  let fpsAt = performance.now();
  const clock0 = performance.now();
  function frame(now) {
    requestAnimationFrame(frame);
    if (!view || !renderer) return;
    // limite de FPS por tela (world.yaml > telas[].fps_max)
    const minGap = 1000 / maxFps;
    if (now - lastFrame < minGap - 2) return;
    lastFrame = now;
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    const t = (now - clock0) / 1000;
    if (!view.paused) view.hours = (view.hours + (dt * view.speed) / 3600) % 24;
    const env = view.env.update(view.hours, dt, t);
    for (const p of Object.values(view.plots)) {
      if (!p.fog) p.built.update(t, env);
      else p.fog.userData.update(t);
      for (const portal of Object.values(p.portals)) {
        const u = portal.userData;
        const active = now < u.activeUntil;
        u.ring.rotation.z = t * (active ? 6 : 0.6) + u.phase;
        u.ring.material.color.set(active ? '#ffffff' : '#b388ff');
        u.inner.material.color.set(active ? (Math.sin(t * 20) > 0 ? '#e0aaff' : '#7b2cbf') : '#3c096c');
        u.ring.scale.setScalar(active ? 1.15 + Math.sin(t * 15) * 0.08 : 1);
      }
    }
    for (const pl of view.pointLights) pl.intensity = 2.5 * env.night + 0.2;
    stepPending(now);
    stepApparition(now);
    for (const a of view.actors.values()) {
      // quem está "andando" sem caminho (perambular, ou saindo para fora da tela) passeia pelo lugar
      if (a.anim === 'walk' && !a.path && !a.fade && now > a.wanderAt) {
        const plot = view.plots[a.place];
        if (plot) {
          const R = Math.random;
          a.moveTo(plot.center.x + (R() - 0.5) * 7, plot.center.z + (R() - 0.5) * 6 + 0.5, 2 + R() * 2, now);
          a.wanderAt = now + 3000 + R() * 2500;
        }
      }
      a.update(dt, t, now, view.camera);
    }
    for (const c of view.creatures.values()) c.position.y = Math.abs(Math.sin(t * 2 + c.position.x)) * 0.15;
    renderer.render(view.scene, view.camera);
    overlay.update(view.camera, view.actors, now, hiddenPlaces());
    // relógio
    if (overlay.opts.showClock) {
      const h = Math.floor(view.hours), m = Math.floor((view.hours - h) * 60);
      const temp = view.temp != null ? ` ${Math.round(view.temp)}°` : '';
      overlay.setHud(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')} · ${view.weatherLabel || ''}${temp}${view.env.funeral ? ' · funeral' : ''}`);
    }
    frames++;
    if (now - fpsAt > 1000) {
      dbg.fps = frames;
      frames = 0;
      fpsAt = now;
      dbg.actors = Object.fromEntries([...view.actors].map(([id, a]) => [id, { place: a.place, anim: a.override || a.anim, glb: !!a.glb }]));
      dbg.pending = [...view.pending.keys()];
      dbg.fog = [...hiddenPlaces()];
      dbg.hours = view.hours;
      dbg.night = env.night;
      dbg.rain = env.rain;
    }
  }
  requestAnimationFrame(frame);
  connect();
}
