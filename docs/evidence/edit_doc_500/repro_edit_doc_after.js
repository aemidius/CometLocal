const fs = require('fs');
const { chromium, expect } = require('playwright');

async function main() {
  const network = { request: null, response: null };

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1365, height: 768 } });

  page.on('request', (req) => {
    const url = req.url();
    if (url.includes('/api/repository/docs/') && req.method() === 'PUT') {
      network.request = {
        url,
        method: req.method(),
        postData: req.postData(),
        headers: req.headers(),
      };
    }
  });

  page.on('response', async (res) => {
    const url = res.url();
    if (url.includes('/api/repository/docs/') && res.request().method() === 'PUT') {
      let body = '';
      try {
        body = await res.text();
      } catch {}
      network.response = { url, status: res.status(), body };
    }
  });

  await page.goto('http://127.0.0.1:8000/repository#buscar', { waitUntil: 'networkidle' });
  await page.waitForSelector('button:has-text("Editar")', { timeout: 20000 });
  await page.locator('button:has-text("Editar")').first().click();
  await page.waitForSelector('#edit-doc-modal-overlay', { timeout: 10000 });

  const statusSel = page.locator('#edit-doc-status');
  const current = (await statusSel.inputValue()).trim();
  const next = current === 'reviewed' ? 'draft' : 'reviewed';
  await statusSel.selectOption(next);

  await page.locator('button:has-text("Guardar")').click();

  // Modal debería cerrar al guardar OK
  await page.waitForSelector('#edit-doc-modal-overlay', { state: 'detached', timeout: 20000 });
  await page.waitForTimeout(800);

  await page.screenshot({ path: 'docs/evidence/edit_doc_500/02_after.png', fullPage: true });

  fs.writeFileSync(
    'docs/evidence/edit_doc_500/NETWORK_AFTER.json',
    JSON.stringify(network, null, 2) + '\n'
  );

  if (!network.response || network.response.status !== 200) {
    throw new Error(`Expected PUT to return 200, got ${network.response ? network.response.status : 'no response captured'}`);
  }

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});







