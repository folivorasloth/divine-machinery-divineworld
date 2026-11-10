// Verificação de aceite da Fase 6 (guia 01): renomear um personagem e ver o nome novo na tela 3D
// SEM recarregar a página. A aba fica aberta o tempo todo; enquanto ela espera, siga o guia 01
// (troque o `nome:` no YAML, `tools.validate`, `tools.cli recarregar`).
//   node viewer/e2e/aceite_renomear.cjs <pasta dos prints> <id> "<nome novo>" [tela] [segundos]
//   ex.: node viewer/e2e/aceite_renomear.cjs docs/relatorios/img clown "O Bozó" parede_centro 120
const { chromium } = require('playwright');
const [IMG, id, newName, screen = 'parede_centro', waitS = '120'] = process.argv.slice(2);
const BASE = process.env.DW_URL || 'http://localhost:8000';
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  let loads = 0; page.on('load', () => loads++);
  await page.goto(`${BASE}/viewer/?screen=${screen}`);
  await page.waitForTimeout(3000);
  const domNames = () => page.evaluate(() => [...document.querySelectorAll('.name')].map((e) => e.textContent));
  const before = await page.evaluate((id) => { const l = window.__dw.live(); return { name: l.names[id], place: l.places[id], hellos: l.hellos }; }, id);
  before.dom = (await domNames()).filter((n) => n === before.name);
  console.log('ANTES ' + JSON.stringify(before));
  await page.screenshot({ path: `${IMG}/fase6_renomear_1_antes.png` });
  console.log('PRONTO: siga o guia 01 agora (a aba continua aberta)');
  const t0 = Date.now();
  let after = null;
  while (Date.now() - t0 < Number(waitS) * 1000) {
    await page.waitForTimeout(500);
    const l = await page.evaluate(() => window.__dw.live());
    if (l && l.names[id] === newName) { after = { name: l.names[id], place: l.places[id], hellos: l.hellos }; break; }
  }
  await page.waitForTimeout(1500);
  if (after) after.dom = (await domNames()).filter((n) => n === newName);
  await page.screenshot({ path: `${IMG}/fase6_renomear_2_depois.png` });
  console.log('DEPOIS ' + JSON.stringify({ after, pageLoads: loads, errs, seconds: (Date.now() - t0) / 1000 }));
  await browser.close();
  process.exit(after && after.dom.length ? 0 : 1);
})();
