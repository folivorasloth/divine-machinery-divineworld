// Textos por cima do 3D (HTML, não pixelado, para ler de longe): balões de
// fala, nomes, nomes dos lugares, relógio e o aviso de conexão.
import * as THREE from 'three';

const v = new THREE.Vector3();

export class Overlay {
  constructor(root, opts) {
    this.root = root;
    this.opts = opts;
    this.bubbles = []; // {el, actor, until, w, h}
    this.names = new Map(); // actorId -> el
    this.labels = []; // {el, pos}
    this.hud = document.createElement('div');
    this.hud.className = 'hud';
    this.hud.hidden = !opts.showClock;
    root.appendChild(this.hud);
    this.status = document.createElement('div');
    this.status.className = 'status';
    root.appendChild(this.status);
  }

  clear() {
    for (const b of this.bubbles) b.el.remove();
    this.bubbles = [];
    for (const el of this.names.values()) el.remove();
    this.names.clear();
    for (const l of this.labels) l.el.remove();
    this.labels = [];
  }

  setStatus(text) {
    this.status.textContent = text || '';
    this.status.hidden = !text;
  }

  setHud(text) {
    this.hud.textContent = text;
  }

  addLabel(text, pos, cls = 'place-label') {
    const el = document.createElement('div');
    el.className = cls;
    el.textContent = text;
    this.root.appendChild(el);
    const item = { el, pos: pos.clone(), hidden: false };
    this.labels.push(item);
    return item;
  }

  name(actor, text) {
    if (!this.opts.showNames) return;
    let el = this.names.get(actor.id);
    if (!el) {
      el = document.createElement('div');
      el.className = 'name';
      this.root.appendChild(el);
      this.names.set(actor.id, el);
    }
    if (el.textContent !== text) { el.textContent = text; el._w = 0; }
  }

  removeActor(id) {
    const el = this.names.get(id);
    if (el) el.remove();
    this.names.delete(id);
    this.bubbles = this.bubbles.filter((b) => {
      if (b.actor.id === id) { b.el.remove(); return false; }
      return true;
    });
  }

  /** Balão novo. Cada um tem no máximo um balão (o novo troca o velho). */
  bubble(actor, text, seconds, now) {
    for (const b of this.bubbles) if (b.actor === actor) { b.el.remove(); b.dead = true; }
    this.bubbles = this.bubbles.filter((b) => !b.dead);
    const el = document.createElement('div');
    el.className = 'bubble';
    el.textContent = text;
    this.root.appendChild(el);
    this.bubbles.push({ el, actor, until: now + seconds * 1000, born: now, w: 0, h: 0 });
    // muitos balões juntos poluem a parede: mantém os 4 mais novos
    while (this.bubbles.length > 4) this.bubbles.shift().el.remove();
  }

  project(pos, camera, w, h) {
    v.copy(pos).project(camera);
    return { x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h, behind: v.z > 1 };
  }

  update(camera, actors, now, hiddenPlaces) {
    const w = window.innerWidth;
    const h = window.innerHeight;
    for (const l of this.labels) {
      const p = this.project(l.pos, camera, w, h);
      l.el.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px) translate(-50%, 0)`;
      l.el.style.display = l.hidden ? 'none' : '';
    }
    // nomes: um por personagem, embaixo dos pés; se dois se encostam, o de trás some
    const tags = [];
    for (const a of actors.values()) {
      const el = this.names.get(a.id);
      if (!el) continue;
      const hidden = hiddenPlaces.has(a.place) || a.hidden;
      if (hidden) { el.style.display = 'none'; continue; }
      a.root.getWorldPosition(v);
      v.y -= 0.05;
      const p = this.project(v, camera, w, h);
      if (!el._w) { el.style.display = ''; el._w = el.offsetWidth || 60; el._h = el.offsetHeight || 12; }
      tags.push({ el, x: p.x, y: p.y });
    }
    tags.sort((a, b) => b.y - a.y); // de baixo (mais perto da câmera) para cima
    const taken = [];
    for (const t of tags) {
      const w2 = t.el._w, h2 = t.el._h;
      const hit = taken.some((o) => Math.abs(o.x - t.x) < (o.w + w2) / 2 && Math.abs(o.y - t.y) < (o.h + h2) / 2);
      t.el.style.display = hit ? 'none' : '';
      if (hit) continue;
      taken.push({ x: t.x, y: t.y, w: w2, h: h2 });
      t.el.style.transform = `translate(${t.x.toFixed(1)}px, ${t.y.toFixed(1)}px) translate(-50%, 2px)`;
    }
    // balões: acima da cabeça, empurrados para cima se encostarem num outro
    const placed = [];
    this.bubbles = this.bubbles.filter((b) => {
      if (now > b.until || !actors.has(b.actor.id)) { b.el.remove(); return false; }
      return true;
    });
    const sorted = [...this.bubbles].sort((a, b) => a.born - b.born);
    for (const b of sorted) {
      const hidden = hiddenPlaces.has(b.actor.place) || b.actor.hidden;
      b.el.style.display = hidden ? 'none' : '';
      if (hidden) continue;
      if (!b.w) { b.w = b.el.offsetWidth; b.h = b.el.offsetHeight; }
      const p = this.project(b.actor.headPosition(v), camera, w, h);
      let x = Math.min(w - b.w / 2 - 4, Math.max(b.w / 2 + 4, p.x));
      let y = p.y - b.h - 6;
      // y = topo do balão. Se encosta num já colocado, sobe para cima dele.
      for (let tries = 0; tries < 10; tries++) {
        const hit = placed.find((o) => Math.abs(o.x - x) < (o.w + b.w) / 2 + 2 && y < o.y + o.h + 3 && y + b.h > o.y - 3);
        if (!hit) break;
        y = hit.y - b.h - 6;
      }
      y = Math.max(2, y);
      placed.push({ x, y, w: b.w, h: b.h });
      const left = Math.max(0, (b.until - now) / 1000);
      b.el.style.opacity = left < 0.5 ? (left / 0.5).toFixed(2) : '1';
      b.el.style.transform = `translate(${(x - b.w / 2).toFixed(1)}px, ${y.toFixed(1)}px)`;
      b.el.style.setProperty('--tail', `${(p.x - (x - b.w / 2)).toFixed(0)}px`);
    }
  }

  /** Um risco de luz correndo até a borda da tela (o LED da parede começando/terminando). */
  streak(from, angle, inward, ms) {
    const el = document.createElement('div');
    el.className = 'streak';
    this.root.appendChild(el);
    const w = window.innerWidth, h = window.innerHeight;
    const dist = Math.hypot(w, h);
    const dx = Math.cos(angle) * dist, dy = -Math.sin(angle) * dist;
    const a = inward ? { x: from.x + dx, y: from.y + dy } : from;
    const b = inward ? from : { x: from.x + dx, y: from.y + dy };
    el.animate(
      [
        { transform: `translate(${a.x}px, ${a.y}px) scale(1)`, opacity: 1 },
        { transform: `translate(${b.x}px, ${b.y}px) scale(0.6)`, opacity: inward ? 1 : 0.2 },
      ],
      { duration: ms, easing: 'ease-in' },
    ).onfinish = () => el.remove();
  }
}
