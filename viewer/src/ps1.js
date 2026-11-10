// A "cara de PS1": materiais com sombreamento flat e vértices que tremem
// (vertex snapping), cores chapadas e imagem em baixa resolução ampliada sem
// suavizar (o canvas é pequeno e o CSS usa image-rendering: pixelated).
import * as THREE from 'three';

// Um uniform só para todos os materiais: metade da resolução interna.
// Os vértices são "arredondados" para essa grade depois da projeção.
export const snapUniform = { value: new THREE.Vector2(160, 120) };
export const snapEnabled = { value: 1 };

function addSnap(material) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uSnap = snapUniform;
    shader.uniforms.uSnapOn = snapEnabled;
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nuniform vec2 uSnap;\nuniform float uSnapOn;')
      .replace(
        '#include <project_vertex>',
        `#include <project_vertex>
        if (uSnapOn > 0.5) {
          // vertex snapping: arredonda a posição na tela para a grade de pixels
          vec4 snapped = gl_Position;
          snapped.xyz /= snapped.w;
          snapped.xy = floor(snapped.xy * uSnap + 0.5) / uSnap;
          snapped.xyz *= gl_Position.w;
          gl_Position = snapped;
        }`,
      );
  };
  material.customProgramCacheKey = () => 'ps1-snap';
  return material;
}

const cache = new Map();

/** Material comum (iluminado, flat). Cores iguais compartilham o mesmo material. */
export function mat(color, opts = {}) {
  const key = `l|${color}|${opts.emissive || ''}|${opts.opacity ?? 1}|${opts.side || 0}`;
  if (!opts.unique && cache.has(key)) return cache.get(key);
  const m = addSnap(
    new THREE.MeshLambertMaterial({
      color: new THREE.Color(color),
      flatShading: true,
      emissive: opts.emissive ? new THREE.Color(opts.emissive) : new THREE.Color(0x000000),
      emissiveIntensity: opts.emissiveIntensity ?? 1,
      transparent: (opts.opacity ?? 1) < 1,
      opacity: opts.opacity ?? 1,
      side: opts.side || THREE.FrontSide,
    }),
  );
  if (!opts.unique) cache.set(key, m);
  return m;
}

/** Material que brilha sozinho (lampião, vitral, LED): não depende da luz. */
export function glow(color, opts = {}) {
  const key = `b|${color}|${opts.opacity ?? 1}|${opts.fog ?? true}|${opts.additive || 0}`;
  if (!opts.unique && cache.has(key)) return cache.get(key);
  const m = addSnap(
    new THREE.MeshBasicMaterial({
      color: new THREE.Color(color),
      transparent: (opts.opacity ?? 1) < 1 || !!opts.additive,
      opacity: opts.opacity ?? 1,
      fog: opts.fog ?? true,
      depthWrite: !opts.additive && (opts.opacity ?? 1) >= 1,
      blending: opts.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
      side: opts.side || THREE.FrontSide,
    }),
  );
  if (!opts.unique) cache.set(key, m);
  return m;
}

/** Canvas pequeno + ampliação pixelada. `renderHeight` vem da qualidade da tela. */
export function setupRenderer(canvas, quality) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'low-power' });
  renderer.setPixelRatio(1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  snapEnabled.value = quality.vertex_snap ? 1 : 0;
  const resize = () => {
    const w = window.innerWidth || 640;
    const h = window.innerHeight || 360;
    const rh = Math.max(90, Math.round(quality.render_height));
    const rw = Math.max(120, Math.round((rh * w) / h));
    renderer.setSize(rw, rh, false);
    // a grade do snapping é mais grossa que o pixel (o PS1 tremia bastante)
    snapUniform.value.set(rw / 3, rh / 3);
    return { rw, rh, aspect: w / h };
  };
  return { renderer, resize };
}
