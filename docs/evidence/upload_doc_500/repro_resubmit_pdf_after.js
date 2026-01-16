const fs = require('fs');
const { chromium } = require('playwright');

async function main() {
  const net = { request: null, response: null, dialog: null };
  const pdfPath = 'data/AEAT-16-oct-2025.pdf';

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1365, height: 768 } });

  page.on('dialog', async (d) => {
    net.dialog = { type: d.type(), message: d.message() };
    await d.accept().catch(() => {});
  });

  page.on('request', (req) => {
    const url = req.url();
    if (url.includes('/api/repository/docs/') && url.endsWith('/pdf') && req.method() === 'PUT') {
      net.request = { url, method: req.method(), headers: req.headers() };
    }
  });

  page.on('response', async (res) => {
    const url = res.url();
    if (url.includes('/api/repository/docs/') && url.endsWith('/pdf') && res.request().method() === 'PUT') {
      let body = '';
      try {
        body = await res.text();
      } catch {}
      net.response = { url, status: res.status(), body };
    }
  });

  await page.goto('http://127.0.0.1:8000/repository#buscar', { waitUntil: 'networkidle' });
  await page.waitForSelector('button:has-text("Resubir")', { timeout: 20000 });

  await page.locator('button:has-text("Resubir")').first().click();

  // Resubir navega a #subir con replace_doc_id (window.replaceDocId) y requiere "Guardar todo"
  await page.waitForURL(/#subir/, { timeout: 20000 });
  await page.waitForSelector('[data-testid="upload-file-input"]', { timeout: 20000, state: 'attached' });

  // Obtener type_id prefill desde el hash (type_id=...)
  const prefillTypeId = await page.evaluate(() => {
    try {
      const hash = window.location.hash || '';
      const idx = hash.indexOf('?');
      if (idx === -1) return null;
      const sp = new URLSearchParams(hash.slice(idx + 1));
      return sp.get('type_id');
    } catch {
      return null;
    }
  });

  const fileInput = page.locator('[data-testid="upload-file-input"]');
  await fileInput.setInputFiles(pdfPath);

  // Esperar a que el archivo se procese y aparezca en la lista
  await page.waitForSelector('#upload-files-list', { timeout: 20000 });
  await page.waitForSelector('text=AEAT-16-oct-2025.pdf', { timeout: 20000 });
  await page.waitForTimeout(500);

  // Tomar el primer card y completar lo mínimo para que no falle validación
  const card = page.locator('[data-testid^="upload-card-"]').first();
  await card.waitFor({ timeout: 20000 });

  // Seleccionar tipo según prefill (si existe)
  if (prefillTypeId) {
    const typeSelect = card.locator('select.repo-upload-type-select');
    if (await typeSelect.count()) {
      await typeSelect.selectOption(prefillTypeId).catch(() => {});
      await page.waitForTimeout(300);
    }
  }

  // Si hay selector de empresa visible, elegir la primera opción válida
  const companySelect = card.locator('select.repo-upload-company-select');
  if (await companySelect.count()) {
    const opts = await companySelect.locator('option').all();
    if (opts.length > 1) {
      const val = await opts[1].getAttribute('value');
      if (val) await companySelect.selectOption(val);
    }
  }

  // Si issue_date es requerido y está vacío, poner hoy (YYYY-MM-DD)
  const issueDate = card.locator('input[type="date"][id^="upload-issue-date-"]');
  if (await issueDate.count()) {
    const v = await issueDate.inputValue();
    if (!v) {
      const iso = new Date().toISOString().slice(0, 10);
      await issueDate.fill(iso);
    }
  }

  // Si existe fecha inicio de vigencia (manual) y está vacía, poner hoy (YYYY-MM-DD)
  const validityStart = card.locator('[data-testid="validity-start-input"]');
  if (await validityStart.count()) {
    const v = await validityStart.inputValue();
    if (!v) {
      const iso = new Date().toISOString().slice(0, 10);
      await validityStart.fill(iso);
    }
  }

  const saveAll = page.locator('[data-testid="save-all"]');
  await saveAll.click();

  // Esperar al PUT /pdf
  const started = Date.now();
  while (!net.response && Date.now() - started < 15000) {
    await page.waitForTimeout(200);
  }

  await page.waitForTimeout(500);
  await page.screenshot({ path: 'docs/evidence/upload_doc_500/02_after.png', fullPage: true });

  fs.writeFileSync('docs/evidence/upload_doc_500/NETWORK_AFTER.json', JSON.stringify(net, null, 2) + '\n');

  if (!net.response) throw new Error('No se capturó response PUT /pdf');
  if (net.response.status !== 200) {
    throw new Error(`Expected 200, got ${net.response.status}. Body: ${net.response.body}`);
  }

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});


