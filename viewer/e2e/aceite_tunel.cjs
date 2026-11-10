// Verificação de aceite da Fase 5 (precisa do Playwright: npm i -g playwright, ou NODE_PATH).
// Uso, com o servidor rodando em :8000 (--speed 300):
//   node viewer/e2e/aceite_tunel.cjs docs/relatorios/img parede_centro tela_homelab
// Abre duas abas (duas telas), espera alguém atravessar o túnel entre elas, tira prints e grava
// docs/relatorios/fase5_aceite_tunel.json com as mensagens do WebSocket.
// Critério de aceite: duas abas (telas diferentes) do mesmo mundo; um personagem atravessa pelo túnel.
const { chromium } = require('playwright');
const fs = require('fs');
const IMG = process.argv[2];
const A = process.argv[3] || 'parede_centro', B = process.argv[4] || 'tela_homelab';
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  const frames = { [A]: [], [B]: [] };
  const errors = [];
  const open = async (screen) => {
    const p = await ctx.newPage();
    p.on('pageerror', (e) => errors.push(`${screen}: ${e.message}`));
    p.on('console', (m) => { if (m.type() === 'error') errors.push(`${screen}: ${m.text()}`); });
    p.on('websocket', (ws) => ws.on('framereceived', (f) => {
      try { const m = JSON.parse(f.payload); if (m.type === 'teleport' || m.type === 'hello') frames[screen].push({ t: Date.now(), ...(m.type === 'hello' ? { type: 'hello', places: m.places.map((x) => x.id) } : m) }); } catch {}
    }));
    await p.goto(`http://localhost:8000/viewer/?screen=${screen}`);
    return p;
  };
  const pa = await open(A), pb = await open(B);
  await pa.waitForTimeout(3000);
  const state = async (p) => p.evaluate(() => ({ places: window.__dw.places, actors: Object.keys(window.__dw.actors), fps: window.__dw.fps }));
  console.log('A', JSON.stringify(await state(pa)));
  console.log('B', JSON.stringify(await state(pb)));
  await pa.screenshot({ path: `${IMG}/fase5_aba_${A}.png` });
  await pb.screenshot({ path: `${IMG}/fase5_aba_${B}.png` });
  // espera um teletransporte entre as duas telas (qualquer sentido)
  let tp = null;
  const deadline = Date.now() + 240000;
  const skipped = [];
  const seen = new Set();
  while (!tp && Date.now() < deadline) {
    await pa.waitForTimeout(50);
    const cand = frames[A].concat(frames[B]).find((m) => m.type === 'teleport' && m.phase === 'start' && !seen.has(m.t + m.id) &&
      [m.from_screen, m.to_screen].sort().join() === [A, B].sort().join());
    if (!cand) continue;
    seen.add(cand.t + cand.id);
    const po0 = cand.from_screen === A ? pa : pb;
    // só vale como prova se o personagem estava visível na tela de origem quando entrou no túnel
    if (await po0.evaluate((id) => window.__dw.live().actors.includes(id), cand.id)) tp = cand;
    else skipped.push(cand.id);
  }
  console.log('ignorados (não estavam visíveis na origem):', skipped);
  if (!tp) { console.log('NENHUM teletransporte entre', A, B); await browser.close(); process.exit(1); }
  const [po, pd] = tp.from_screen === A ? [pa, pb] : [pb, pa];
  console.log('TELEPORT START', JSON.stringify(tp));
  const inOriginBefore = true; // conferido no laço acima
  await po.waitForTimeout(300);
  await po.screenshot({ path: `${IMG}/fase5_tunel_1_origem_entrando.png` });
  await pd.waitForTimeout(Math.max(200, tp.duration_s * 500 - 350));
  await pd.screenshot({ path: `${IMG}/fase5_tunel_2_destino_portal_aceso.png` });
  const inDestDuring = await pd.evaluate((id) => window.__dw.live().actors.includes(id), tp.id);
  // espera aparecer no destino
  let appeared = false;
  for (let i = 0; i < 100 && !appeared; i++) { await pd.waitForTimeout(100); appeared = await pd.evaluate((id) => window.__dw.live().actors.includes(id), tp.id); }
  await pd.waitForTimeout(700);
  await pd.screenshot({ path: `${IMG}/fase5_tunel_3_destino_chegou.png` });
  await po.screenshot({ path: `${IMG}/fase5_tunel_4_origem_depois.png` });
  const inOriginAfter = await po.evaluate((id) => window.__dw.live().actors.includes(id), tp.id);
  const logD = await pd.evaluate(() => window.__dw.log.filter((l) => l.kind === 'appeared'));
  const result = { teleport: tp, skipped, inOriginBefore, inDestDuring, appearedInDest: appeared, inOriginAfter, appearedLog: logD,
    framesOrigin: frames[tp.from_screen].filter((m) => m.type === 'teleport' && m.id === tp.id),
    framesDest: frames[tp.to_screen].filter((m) => m.type === 'teleport' && m.id === tp.id),
    hellos: { [A]: frames[A].find((m) => m.type === 'hello').places, [B]: frames[B].find((m) => m.type === 'hello').places }, errors };
  fs.writeFileSync(`${IMG}/../fase5_aceite_tunel.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 1).slice(0, 3000));
  await browser.close();
})();
