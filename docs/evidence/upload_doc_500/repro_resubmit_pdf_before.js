const fs = require('fs');
const { chromium } = require('playwright');

async function main() {
  const net = { request: null, response: null, dialog: null };
  const pdfPath = 'data/test_dummy.pdf';

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

  // Click "Resubir" del primer documento
  await page.locator('button:has-text("Resubir")').first().click();

  // El flujo de resubir usa input[type=file] asociado al drawer/subida.
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles(pdfPath);

  // Intentar enviar: hay un botón de acción que suele ser "Guardar todo" o similar en subir.
  // Si no aparece, el listener de cambio debería disparar el PUT igualmente en este flujo.
  const saveAll = page.locator('[data-testid="save-all"]');
  if (await saveAll.count()) {
    await saveAll.click();
  }

  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'docs/evidence/upload_doc_500/01_before.png', fullPage: true });

  fs.writeFileSync('docs/evidence/upload_doc_500/NETWORK_BEFORE.json', JSON.stringify(net, null, 2) + '\n');

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});







