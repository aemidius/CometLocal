const fs = require('fs');
const { chromium } = require('playwright');

async function main() {
  const network = {
    request: null,
    response: null,
  };

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

  // Cambio editable: status
  const statusSel = page.locator('#edit-doc-status');
  if (await statusSel.count()) {
    await statusSel.selectOption('reviewed');
  }

  // Guardar (esperamos que aparezca el alert de error en el caso BEFORE)
  await page.locator('button:has-text("Guardar")').click();
  await page.waitForTimeout(1000);

  await page.screenshot({ path: 'docs/evidence/edit_doc_500/01_before.png', fullPage: true });

  fs.writeFileSync(
    'docs/evidence/edit_doc_500/NETWORK.txt',
    [
      'REQUEST',
      JSON.stringify(network.request, null, 2),
      '',
      'RESPONSE',
      JSON.stringify(network.response, null, 2),
      '',
    ].join('\n')
  );

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});







