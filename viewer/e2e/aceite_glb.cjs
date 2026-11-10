// Verificação de aceite da Fase 5: o .glb troca o placeholder (precisa do Playwright).
//   node viewer/e2e/aceite_glb.cjs docs/relatorios/img 1_sem_glb
//   python -m tools.exemplo_glb chief && node viewer/e2e/aceite_glb.cjs docs/relatorios/img 2_com_glb
//   rm viewer/public/models/characters/chief.glb
const { chromium } = require('playwright');
const IMG = process.argv[2], tag = process.argv[3];
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  const reqs = []; page.on('response', (r) => { if (r.url().includes('models')) reqs.push(r.status() + ' ' + r.url()); });
  await page.goto('http://localhost:8000/viewer/?screen=parede_centro');
  await page.waitForTimeout(2500);
  const place = await page.evaluate(() => window.__dw.live().places.chief);
  await page.goto(`http://localhost:8000/viewer/?screen=parede_centro&foco=${place}`);
  await page.waitForTimeout(3000);
  const info = await page.evaluate(() => ({ models: window.__dw.characterModels || [], clips: window.__dw.clips || {}, chief: window.__dw.live().places.chief }));
  await page.screenshot({ path: `${IMG}/fase5_glb_${tag}.png` });
  console.log(JSON.stringify({ place, ...info, reqs, errs }));
  await browser.close();
})();
