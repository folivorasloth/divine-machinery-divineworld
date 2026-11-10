// /viewer/layout.html — o mapa físico das telas na parede (world.yaml > telas)
// e dos túneis entre elas, para o João conferir posição, tamanho e o caminho
// do LED. Ao vivo pelo /ws/chat: névoa e cada teletransporte acendendo a linha.
import './style.css';

const NS = 'http://www.w3.org/2000/svg';
const svg = document.getElementById('wall');
const details = document.getElementById('details');
const state = { hello: null, fog: new Set(), lines: {} };
window.__layout = state;

function el(name, attrs = {}, parent = svg) {
  const e = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  parent.appendChild(e);
  return e;
}

const center = (s) => ({ x: s.position_cm.x + s.size_cm.width / 2, y: s.position_cm.y + s.size_cm.height / 2 });

export function tunnelsBetweenScreens(hello) {
  const screenOf = {};
  for (const s of hello.screens) for (const p of s.places) screenOf[p] = s.id;
  const seen = new Set();
  const out = [];
  for (const p of hello.places) {
    for (const c of p.connections || []) {
      if (c.kind !== 'tunel') continue;
      const a = screenOf[p.id], b = screenOf[c.to];
      const key = [p.id, c.to].sort().join('|');
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ from: p.id, to: c.to, fromScreen: a || null, toScreen: b || null });
    }
  }
  return out;
}

function draw() {
  const hello = state.hello;
  svg.innerHTML = '';
  const screens = hello.screens;
  const xs = screens.flatMap((s) => [s.position_cm.x, s.position_cm.x + s.size_cm.width]);
  const ys = screens.flatMap((s) => [s.position_cm.y, s.position_cm.y + s.size_cm.height]);
  const minX = Math.min(0, ...xs) - 20, maxX = Math.max(...xs) + 20;
  const maxY = Math.max(...ys) + 25;
  // y da parede cresce para cima; no SVG cresce para baixo
  svg.setAttribute('viewBox', `${minX} ${-maxY} ${maxX - minX} ${maxY + 12}`);
  el('line', { x1: minX, y1: 0, x2: maxX, y2: 0, class: 'floor' });
  el('text', { x: minX + 2, y: 6, class: 'tunnel-label' }).textContent = 'chão (y = 0 cm)';
  const names = Object.fromEntries(hello.places.map((p) => [p.id, p.name]));
  const byId = Object.fromEntries(screens.map((s) => [s.id, s]));
  const speed = hello.config?.tunnel?.led_speed_cm_per_s || 60;
  const minDur = hello.config?.tunnel?.min_duration_s || 2;
  state.lines = {};
  const pairCount = {};
  const labels = []; // desenhados por último, por cima das telas
  for (const t of tunnelsBetweenScreens(hello)) {
    if (!t.fromScreen || !t.toScreen || t.fromScreen === t.toScreen) continue;
    const a = center(byId[t.fromScreen]), b = center(byId[t.toScreen]);
    const dist = Math.hypot(b.x - a.x, b.y - a.y);
    const dur = Math.max(minDur, dist / speed);
    const line = el('line', { x1: a.x, y1: -a.y, x2: b.x, y2: -b.y, class: 'tunnel' });
    // dois túneis entre as mesmas telas: um rótulo embaixo do outro
    const pair = [t.fromScreen, t.toScreen].sort().join('|');
    pairCount[pair] = (pairCount[pair] || 0) + 1;
    const mx = (a.x + b.x) / 2, my = -(a.y + b.y) / 2 - 2 + (pairCount[pair] - 1) * 4;
    labels.push([mx, my, `${names[t.from]} ⇄ ${names[t.to]} · ${Math.round(dist)} cm · ${dur.toFixed(1)} s`]);
    state.lines[[t.from, t.to].sort().join('|')] = { line, a, b };
  }
  for (const s of screens) {
    const offline = s.places.length > 0 && s.places.every((p) => state.fog.has(p));
    const g = el('g', { class: 'screen' + (offline ? ' offline' : '') });
    el('rect', { x: s.position_cm.x, y: -(s.position_cm.y + s.size_cm.height), width: s.size_cm.width, height: s.size_cm.height, rx: 1.5 }, g);
    const title = `${s.name}${offline ? ' (névoa)' : ''}`;
    // título cabe na largura da tela (telas pequenas, letra menor)
    const fs = Math.min(4.2, (s.size_cm.width - 3) / (title.length * 0.55));
    el('text', { x: s.position_cm.x + 2, y: -(s.position_cm.y + s.size_cm.height) + 2 + fs, style: `font-size:${fs.toFixed(2)}px` }, g).textContent = title;
    const list = s.places.map((p) => names[p] || p);
    // lista dos lugares em linhas curtas dentro do retângulo
    const lines = [];
    let cur = '';
    const maxChars = Math.max(10, Math.floor(s.size_cm.width / 1.45));
    for (const n of list) {
      if ((cur + ', ' + n).length > maxChars && cur) { lines.push(cur); cur = n; } else cur = cur ? cur + ', ' + n : n;
    }
    if (cur) lines.push(cur);
    lines.forEach((ln, i) => {
      el('text', { x: s.position_cm.x + 2, y: -(s.position_cm.y + s.size_cm.height) + 10.5 + i * 3.4, class: 'places' }, g).textContent = ln;
    });
  }
  for (const [x, y, text] of labels) {
    const tx = el('text', { x, y, 'text-anchor': 'middle', class: 'tunnel-label' });
    tx.textContent = text;
    const bb = tx.getBBox();
    const bg = el('rect', { x: bb.x - 1, y: bb.y - 0.4, width: bb.width + 2, height: bb.height + 0.8, rx: 1, class: 'label-bg' });
    svg.insertBefore(bg, tx);
  }
  details.innerHTML = '';
  for (const s of screens) {
    const offline = s.places.every((p) => state.fog.has(p));
    const card = document.createElement('div');
    card.className = 'card' + (offline ? ' offline' : '');
    card.innerHTML = `<h3></h3><p class="pos"></p><p class="q"></p><p class="pl"></p><p><a>abrir esta tela</a></p>`;
    card.querySelector('h3').textContent = `${s.name} (${s.id})`;
    card.querySelector('.pos').textContent = `posição ${s.position_cm.x}×${s.position_cm.y} cm · tamanho ${s.size_cm.width}×${s.size_cm.height} cm`;
    card.querySelector('.q').textContent = `qualidade ${s.quality || 'media'} · até ${s.max_fps || 30} FPS${offline ? ' · NA NÉVOA' : ''}`;
    card.querySelector('.pl').textContent = s.places.map((p) => names[p] || p).join(', ');
    card.querySelector('a').href = `./?screen=${encodeURIComponent(s.id)}`;
    details.appendChild(card);
  }
  const outside = hello.places.filter((p) => !screens.some((s) => s.places.includes(p.id)));
  if (outside.length) {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = '<h3>Fora de qualquer tela</h3><p></p>';
    card.querySelector('p').textContent = outside.map((p) => p.name).join(', ') + ' — continuam existindo, só ninguém vê.';
    details.appendChild(card);
  }
}

function led(ev) {
  const d = ev.data || {};
  const key = [d.from_place, d.to_place].sort().join('|');
  const l = state.lines[key];
  if (!l) return;
  const byId = Object.fromEntries(state.hello.screens.map((s) => [s.id, s]));
  const a = center(byId[d.from_screen] || {}) , b = center(byId[d.to_screen] || {});
  if (!byId[d.from_screen] || !byId[d.to_screen]) return;
  l.line.classList.add('active');
  const dot = el('circle', { r: 2.2, class: 'led', cx: a.x, cy: -a.y });
  const ms = Math.max(300, (d.duration_s || 2) * 1000);
  const t0 = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - t0) / ms);
    dot.setAttribute('cx', a.x + (b.x - a.x) * k);
    dot.setAttribute('cy', -(a.y + (b.y - a.y) * k));
    if (k < 1) requestAnimationFrame(step);
    else { dot.remove(); l.line.classList.remove('active'); }
  };
  requestAnimationFrame(step);
  state.teleports = (state.teleports || 0) + 1;
}

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/chat`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'hello') {
      state.hello = msg;
      state.fog = new Set(msg.places.filter((p) => p.fog).map((p) => p.id));
      draw();
    } else if (msg.type === 'event' && state.hello) {
      const ev = msg.event;
      if (ev.type === 'teleport_started') led(ev);
      if (ev.type === 'fog_on' || ev.type === 'fog_off') {
        if (ev.type === 'fog_on') state.fog.add(ev.place); else state.fog.delete(ev.place);
        draw();
      }
    }
  };
  ws.onclose = () => setTimeout(connect, 2000);
}
connect();
