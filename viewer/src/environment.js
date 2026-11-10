// Céu, luz do dia e da noite, névoa de distância, chuva, relâmpago e a
// névoa que cobre o lugar de uma tela desligada.
import * as THREE from 'three';
import { glow } from './ps1.js';
import { daylight, rainIntensity, seededRandom } from './logic.js';
import { PLOT } from './places.js';

const SKY = {
  day: new THREE.Color('#8ecae6'),
  dawn: new THREE.Color('#f4a261'),
  night: new THREE.Color('#0b1026'),
  storm: new THREE.Color('#4a5568'),
  // lugares sinistros: azul de terror
  sinisterDay: new THREE.Color('#5c7a99'),
  sinisterNight: new THREE.Color('#03060f'),
};

export class Environment {
  constructor(scene, bounds, quality, visual, sinisterShare) {
    this.scene = scene;
    this.quality = quality;
    this.visual = visual;
    this.sinister = sinisterShare; // 0..1: quanto da tela é lugar sinistro
    this.size = Math.max(bounds.w, bounds.d);
    this.bounds = bounds;
    scene.background = new THREE.Color(SKY.day);
    scene.fog = new THREE.Fog(scene.background.clone(), 10, 100);

    this.hemi = new THREE.HemisphereLight('#ffffff', '#5a4a3a', 1.6);
    scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight('#fff4d6', 1.6);
    this.sun.position.set(20, 40, 15);
    scene.add(this.sun);
    scene.add(this.sun.target);

    this.weather = { kind: 'nublado', forced: null };
    this.funeral = false;
    this.flash = 0;
    this.nextFlash = 0;
    this.buildRain();
    this.night = 0;
  }

  buildRain() {
    const n = Math.max(0, this.quality.rain_drops | 0);
    const pos = new Float32Array(n * 6);
    const R = seededRandom('chuva');
    const { w, d, cx, cz } = this.bounds;
    this.drops = [];
    for (let i = 0; i < n; i++) {
      this.drops.push({ x: cx + (R() - 0.5) * (w + 6), y: R() * 14, z: cz + (R() - 0.5) * (d + 6), v: 18 + R() * 8 });
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    this.rainMat = new THREE.LineBasicMaterial({ color: '#b8c7e0', transparent: true, opacity: 0.6, fog: true });
    this.rain = new THREE.LineSegments(geo, this.rainMat);
    this.rain.frustumCulled = false;
    this.rain.visible = false;
    this.scene.add(this.rain);
  }

  setWeather(w) {
    this.weather = { kind: w.kind, forced: w.forced, label: w.label, temp: w.temp };
  }

  /** hours = hora do mundo; dt em s. */
  update(hours, dt, t) {
    const day = daylight(hours);
    this.night = 1 - day;
    const kind = this.weather.kind;
    const rain = rainIntensity(kind, this.weather.forced, this.funeral);
    const cloudy = kind === 'nublado' || kind === 'neblina' || rain > 0;
    // céu: noite -> amanhecer -> dia, puxado para o azul de terror nos lugares sinistros
    const dawn = Math.max(0, 1 - Math.abs(day - 0.5) * 2) * (hours < 12 ? 1 : 0.8);
    const sky = SKY.night.clone().lerp(SKY.day, day);
    sky.lerp(SKY.dawn, dawn * 0.35);
    const sinister = SKY.sinisterNight.clone().lerp(SKY.sinisterDay, day);
    sky.lerp(sinister, this.sinister * 0.6);
    if (cloudy) sky.lerp(SKY.storm.clone().multiplyScalar(0.3 + day * 0.7), 0.35 + rain * 0.4);
    // relâmpago na tempestade (e no funeral com chuva forte)
    if (rain >= 1 && t > this.nextFlash) {
      this.flash = 1;
      this.nextFlash = t + 3 + Math.random() * 7;
    }
    this.flash = Math.max(0, this.flash - dt * 4);
    const flash = this.flash > 0.5 ? 1 : this.flash > 0.2 ? 0.3 : 0;
    sky.lerp(new THREE.Color('#e8eeff'), flash * 0.7);
    this.scene.background.copy(sky);
    this.scene.fog.color.copy(sky);
    // névoa de distância (mais perto com neblina e chuva)
    const thick = kind === 'neblina' ? 0.55 : 1 - rain * 0.3;
    this.scene.fog.near = this.camDist * this.visual.fog_near * thick * 0.75;
    this.scene.fog.far = this.camDist * this.visual.fog_far * thick * 0.75;
    // luzes
    const nightBlue = new THREE.Color('#3a4a8a');
    this.hemi.color.set('#ffffff').lerp(nightBlue, this.night);
    this.hemi.groundColor.set('#6a5a4a').lerp(new THREE.Color('#10142a'), this.night);
    this.hemi.intensity = (0.55 + day * 1.25) * (cloudy ? 0.85 : 1) + flash * 2.5;
    this.sun.intensity = day * (cloudy ? 0.55 : 1.7);
    const a = ((hours - 6) / 12) * Math.PI; // sol nasce às 6 e se põe às 18
    const { cx, cz } = this.bounds;
    this.sun.position.set(cx + Math.cos(a) * 40, 10 + Math.max(0, Math.sin(a)) * 40, cz + 20);
    this.sun.target.position.set(cx, 0, cz);
    this.sun.color.set('#fff4d6').lerp(SKY.dawn, dawn * 0.5);
    // chuva
    this.rain.visible = rain > 0 && this.drops.length > 0;
    if (this.rain.visible) this.stepRain(dt, rain);
    return { night: this.night, rain };
  }

  stepRain(dt, intensity) {
    const arr = this.rain.geometry.attributes.position.array;
    const active = Math.floor(this.drops.length * intensity);
    const len = 0.35 + intensity * 0.4;
    for (let i = 0; i < this.drops.length; i++) {
      const d = this.drops[i];
      const j = i * 6;
      if (i >= active) {
        arr.fill(0, j, j + 6);
        continue;
      }
      d.y -= d.v * dt * (0.7 + intensity * 0.5);
      if (d.y < 0) d.y += 14;
      arr[j] = d.x; arr[j + 1] = d.y; arr[j + 2] = d.z;
      arr[j + 3] = d.x + 0.08; arr[j + 4] = d.y + len; arr[j + 5] = d.z;
    }
    this.rain.geometry.attributes.position.needsUpdate = true;
    this.rainMat.opacity = 0.35 + intensity * 0.4;
  }
}

/**
 * A névoa de uma tela desligada: nuvens cinzas densas cobrindo o lugar
 * inteiro. Quem está dentro some junto (fica "preso" até a tela voltar).
 */
export function buildFogBank(seed) {
  const g = new THREE.Group();
  const R = seededRandom('nevoa' + seed);
  const puffs = [];
  for (let i = 0; i < 22; i++) {
    const m = new THREE.Mesh(new THREE.IcosahedronGeometry(1.4 + R() * 1.4, 0), glow('#c9ced6', { opacity: 0.82, unique: true }));
    m.position.set((R() - 0.5) * PLOT * 0.95, 0.4 + R() * 3.2, (R() - 0.5) * PLOT * 0.95);
    m.scale.y = 0.6;
    m.material.depthWrite = false;
    g.add(m);
    puffs.push([m, R() * 6]);
  }
  const wall = new THREE.Mesh(new THREE.BoxGeometry(PLOT + 0.4, 4.5, PLOT + 0.4), glow('#aeb4bd', { opacity: 0.55, unique: true }));
  wall.position.y = 2.2;
  wall.material.depthWrite = false;
  g.add(wall);
  g.userData.update = (t) => {
    for (const [m, ph] of puffs) {
      m.position.x += Math.sin(t * 0.3 + ph) * 0.004;
      m.rotation.y = t * 0.05 + ph;
    }
  };
  return g;
}
