// Funções puras do viewer (sem Three.js e sem DOM): fáceis de testar com `npm test`.
// Tudo que é "regra" de visual e não é desenho mora aqui.

export const ANIMATIONS = ['idle', 'walk', 'talk', 'work', 'sleep', 'fall', 'fight', 'pray', 'dance', 'stare'];

// Usado só se o servidor não mandar `config.visual` (servidor antigo): o mesmo do world.yaml.
export const DEFAULT_VISUAL = {
  qualities: {
    baixa: { render_height: 160, rain_drops: 120, vertex_snap: true, extra_lights: 0, detail: 0.5 },
    media: { render_height: 240, rain_drops: 400, vertex_snap: true, extra_lights: 0, detail: 1.0 },
    alta: { render_height: 360, rain_drops: 900, vertex_snap: true, extra_lights: 6, detail: 1.3 },
  },
  bubbles: { min_seconds: 2.5, seconds_per_char: 0.06, max_seconds: 9, max_chars: 90 },
  action_animation: {},
  event_animation: { slapstick: 'fall', fight: 'fight', stare: 'stare', death: 'fall' },
  animation_fallback: {},
  show_names: true,
  show_clock: true,
  fog_near: 1.2,
  fog_far: 3.0,
};

/** Animação de uma ação (world.yaml > visual.animacao_por_acao). Sem ação = idle. */
export function animForAction(action, moving, visual) {
  if (moving) return 'walk';
  if (!action) return 'idle';
  const a = (visual && visual.action_animation && visual.action_animation[action]) || 'idle';
  return ANIMATIONS.includes(a) ? a : 'idle';
}

/** Nome de clipe "Armature|Walk_01" -> "walk01" (para comparar sem ligar para maiúsculas/prefixos). */
export function normalizeClipName(name) {
  let n = String(name || '').toLowerCase();
  if (n.includes('|')) n = n.slice(n.lastIndexOf('|') + 1);
  return n.replace(/[^a-z0-9]/g, '');
}

/**
 * Escolhe o clipe de um .glb para a animação `wanted`.
 * Procura: nome exato -> começa com -> contém; se não houver, tenta as substitutas
 * (visual.animacao_substituta) e por fim `idle`. Devolve {clip, name, exact}:
 * exact=false quer dizer que o viewer deve completar com movimento procedural.
 */
export function pickClip(clipNames, wanted, fallback = {}) {
  const norm = clipNames.map((n) => [n, normalizeClipName(n)]);
  const find = (w) => {
    for (const [orig, n] of norm) if (n === w) return orig;
    for (const [orig, n] of norm) if (n.startsWith(w)) return orig;
    for (const [orig, n] of norm) if (n.includes(w)) return orig;
    return null;
  };
  const direct = find(wanted);
  if (direct) return { clip: direct, name: wanted, exact: true };
  const chain = [...(fallback[wanted] || []), 'idle'];
  for (const alt of chain) {
    const c = find(alt);
    if (c) return { clip: c, name: alt, exact: false };
  }
  return { clip: clipNames[0] || null, name: null, exact: false };
}

/** O mesmo corte do servidor (server/ws.py): tira o "Nome: " e as aspas, encurta com …. */
export function shortenBubble(text, name, maxChars = 90) {
  let t = String(text || '').trim();
  if (name && t.startsWith(name + ':')) t = t.slice(name.length + 1).trim();
  if (t.length >= 2 && '"“'.includes(t[0]) && '"”'.includes(t[t.length - 1])) t = t.slice(1, -1).trim();
  if (t.length > maxChars) {
    let cut = t.slice(0, maxChars - 1);
    if (cut.includes(' ')) cut = cut.slice(0, cut.lastIndexOf(' '));
    t = cut.replace(/[,;:. ]+$/, '') + '…';
  }
  return t;
}

/** Duração do balão pelo tamanho do texto (o servidor já manda; isto é o plano B). */
export function bubbleDuration(text, cfg = DEFAULT_VISUAL.bubbles) {
  const s = cfg.min_seconds + String(text || '').length * cfg.seconds_per_char;
  return Math.min(cfg.max_seconds, s);
}

/**
 * Grade automática dos lugares de uma tela: quantas colunas e linhas para N
 * cenários quadrados caberem numa tela com esta proporção (largura/altura).
 * A câmera olha de cima em ângulo, então cada "linha" ocupa menos altura na
 * tela que uma coluna ocupa de largura (fator 0.62).
 */
export function gridLayout(n, aspect) {
  if (n <= 0) return { cols: 0, rows: 0 };
  let best = null;
  for (let cols = 1; cols <= n; cols++) {
    const rows = Math.ceil(n / cols);
    const w = cols;
    const h = rows * 0.62;
    // maior escala possível de cada cenário dentro da tela
    const scale = Math.min(aspect / w, 1 / h);
    const empty = cols * rows - n;
    const score = scale - empty * 0.01;
    if (!best || score > best.score) best = { cols, rows, score };
  }
  return { cols: best.cols, rows: best.rows };
}

/** Posição (x, z) do centro de cada lugar na grade, centrada na origem. */
export function gridPositions(ids, cols, plot, gap) {
  const rows = Math.ceil(ids.length / cols);
  const step = plot + gap;
  const out = {};
  ids.forEach((id, i) => {
    const r = Math.floor(i / cols);
    // a última linha, se incompleta, fica centralizada
    const inRow = r === rows - 1 ? ids.length - r * cols : cols;
    const c = i - r * cols;
    const x = (c - (inRow - 1) / 2) * step;
    const z = (r - (rows - 1) / 2) * step;
    out[id] = { x, z };
  });
  return out;
}

/** Hash estável de texto -> inteiro (posições "aleatórias" que não mudam a cada recarga). */
export function hashString(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Gerador pseudo-aleatório pequeno e determinístico (mulberry32). */
export function seededRandom(seed) {
  let a = typeof seed === 'number' ? seed >>> 0 : hashString(String(seed));
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Hora local do MUNDO (em horas, 0..24) a partir do ISO com fuso: "2026-11-10T09:41:00-03:00" -> 9.683. */
export function worldHours(ts) {
  const m = /T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(String(ts || ''));
  if (!m) return 12;
  return Number(m[1]) + Number(m[2]) / 60 + Number(m[3] || 0) / 3600;
}

/**
 * Quanto de "dia" há numa hora: 0 = noite fechada, 1 = dia pleno, com
 * amanhecer (5h-7h) e entardecer (17h30-19h) suaves.
 */
export function daylight(hours) {
  const h = ((hours % 24) + 24) % 24;
  const smooth = (a, b, x) => {
    const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
    return t * t * (3 - 2 * t);
  };
  return smooth(5, 7, h) * (1 - smooth(17.5, 19, h));
}

/** Força da chuva (0..1) pelo clima. No funeral (clima forçado com chuva) é sempre forte. */
export function rainIntensity(kind, forced, funeral) {
  const base = { garoa: 0.3, chuva: 0.65, tempestade: 1.0 }[kind] || 0;
  if (base > 0 && (forced || funeral)) return 1.0;
  return base;
}

/**
 * Quando o personagem aparece na tela de destino de um túnel: quando a luz
 * de LED chega (início + duração) ou quando a simulação disser que ele saiu
 * do túnel, o que vier por último. Tempos em ms (performance.now()).
 */
export function teleportAppearAt(startMs, durationS, endMs) {
  const byLed = startMs != null ? startMs + (durationS || 0) * 1000 : null;
  if (byLed == null) return endMs;
  if (endMs == null) return null; // ainda não saiu do túnel na simulação
  return Math.max(byLed, endMs);
}

// ----------------------------------------------------------------- aparência
// O placeholder lê os textos do YAML (chapeu, acessorio, aparencia). Se o João
// escrever "chapéu de palha", aparece um chapéu de palha. Palavras conhecidas:

const strip = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

const HAT_RULES = [
  ['palha', 'straw'], ['chef', 'chef'], ['guizo', 'jester'], ['couro', 'cowboy'], ['cowboy', 'cowboy'],
  ['feltro', 'felt'], ['vela', 'candles'], ['capacete', 'helmet'], ['lanterna', 'helmet'], ['arrepiado', 'spiky'],
  ['capuz', 'hood'], ['coroa', 'crown'], ['cartola', 'tophat'], ['bone', 'cap'], ['gorro', 'beanie'],
  ['chapeu', 'felt'],
];
export function hatKind(text) {
  const t = strip(text);
  if (!t || t === 'nenhum' || t === 'nenhuma') return null;
  for (const [word, kind] of HAT_RULES) if (t.includes(word)) return kind;
  return 'felt';
}

const ACCESSORY_RULES = [
  ['nariz', 'nose'], ['martelo', 'hammer'], ['prancheta', 'clipboard'], ['colher', 'spoon'], ['pano', 'towel'],
  ['cigarro', 'cigarette'], ['cesta', 'basket'], ['flor', 'basket'], ['malabar', 'juggling'], ['bolinha', 'juggling'],
  ['bolso', 'pockets'], ['apito', 'whistle'], ['regua', 'whistle'], ['leque', 'fan'], ['osso', 'bones'],
  ['colar', 'bones'], ['viola', 'guitar'], ['violao', 'guitar'], ['crucifixo', 'crucifix'], ['cruz', 'crucifix'],
  ['luva', 'gloves'], ['skate', 'skate'], ['carrinho', 'cart'], ['fone', 'headphones'], ['livro', 'book'],
  ['lanterna', 'lantern'], ['bengala', 'cane'],
];
/** Pode haver mais de um ("apito e régua"): devolve a lista sem repetição. */
export function accessoryKinds(text) {
  const t = strip(text);
  if (!t || t === 'nenhum' || t === 'nenhuma') return [];
  const out = [];
  for (const [word, kind] of ACCESSORY_RULES) if (t.includes(word) && !out.includes(kind)) out.push(kind);
  return out;
}

/** Roupa que muda a silhueta, lida da `aparencia` (a descrição da bible). */
export function outfitKind(appearance, accessory) {
  const t = strip(appearance) + ' ' + strip(accessory);
  if (t.includes('batina')) return 'cassock';
  if (t.includes('manto')) return 'robe';
  if (t.includes('vestido')) return 'dress';
  if (t.includes('macacao')) return 'overalls';
  if (t.includes('poncho')) return 'poncho';
  if (t.includes('avental')) return 'apron';
  if (t.includes('terno')) return 'suit';
  if (t.includes('casaco')) return 'coat';
  if (t.includes('moletom')) return 'hoodie';
  return 'plain';
}

/** Extras lidos da aparência: bolinhas (Palhaço), óculos, bigode, sardas, olhos grandes, monocelha... */
export function appearanceExtras(appearance) {
  const t = strip(appearance);
  const has = (w) => t.includes(w);
  return {
    dots: has('bolinha'),
    glasses: has('oculos'),
    mustache: has('bigode'),
    bigEyes: has('olhos grandes'),
    unibrow: has('monocelha'),
    bigShoes: has('sapatos enormes'),
    makeup: has('maquiagem'),
    thirdEye: has('olho pintado'),
    bald: has('careca'),
    jewels: has('joia'),
  };
}

/** Jeito de andar, lido do `movimento` do YAML ("Saltitando e dando estrelinhas" -> hop). */
const GAIT_RULES = [
  ['skate', 'skate'], ['saltit', 'hop'], ['pulando', 'hop'], ['estrel', 'hop'], ['arrast', 'shuffle'],
  ['desliza', 'glide'], ['flutua', 'glide'], ['zigue', 'zigzag'], ['passinhos', 'quick'], ['apressad', 'quick'],
  ['rapida', 'quick'], ['linha reta', 'stiff'], ['reto', 'stiff'], ['desfila', 'strut'], ['ginga', 'swing'],
  ['pesad', 'heavy'], ['furtiv', 'sneak'], ['encostado', 'sneak'], ['devagar', 'slow'], ['lento', 'slow'],
  ['cauteloso', 'slow'],
];
export function gaitKind(movement) {
  const t = strip(movement);
  for (const [word, kind] of GAIT_RULES) if (t.includes(word)) return kind;
  return 'normal';
}
