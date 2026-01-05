/**
 * E2E: Resubir PDF de un documento existente
 * Cubre el endpoint PUT /api/repository/docs/{doc_id}/pdf (antes 500).
 */
const { test, expect } = require('@playwright/test');

test.describe('Subir documentos - Resubir PDF', () => {
  test('resubir desde Buscar documentos y guardar OK (200)', async ({ page }) => {
    const pdfPath = 'data/AEAT-16-oct-2025.pdf';

    await page.goto('http://127.0.0.1:8000/repository#buscar', { waitUntil: 'networkidle' });
    await page.waitForSelector('button:has-text("Resubir")', { timeout: 20000 });

    await page.locator('button:has-text("Resubir")').first().click();
    await page.waitForURL(/#subir/, { timeout: 20000 });

    // Capturar respuesta PUT /pdf
    const putPromise = page.waitForResponse((res) => {
      return res.url().includes('/api/repository/docs/') && res.url().endsWith('/pdf') && res.request().method() === 'PUT';
    });

    // Subir archivo
    const fileInput = page.locator('[data-testid="upload-file-input"]');
    await fileInput.setInputFiles(pdfPath);

    await page.waitForSelector('#upload-files-list', { timeout: 20000 });
    await page.waitForSelector('text=AEAT-16-oct-2025.pdf', { timeout: 20000 });

    const card = page.locator('[data-testid^="upload-card-"]').first();
    await card.waitFor({ timeout: 20000 });

    // Tomar type_id prefill desde el hash (type_id=...)
    const prefillTypeId = await page.evaluate(() => {
      const hash = window.location.hash || '';
      const idx = hash.indexOf('?');
      if (idx === -1) return null;
      const sp = new URLSearchParams(hash.slice(idx + 1));
      return sp.get('type_id');
    });
    if (prefillTypeId) {
      const typeSelect = card.locator('select.repo-upload-type-select');
      await typeSelect.selectOption(prefillTypeId);
    }

    // Completar fecha inicio de vigencia si aparece (manual)
    const validityStart = card.locator('[data-testid="validity-start-input"]');
    if (await validityStart.count()) {
      const v = await validityStart.inputValue();
      if (!v) await validityStart.fill(new Date().toISOString().slice(0, 10));
    }

    // Guardar todo
    await page.locator('[data-testid="save-all"]').click();

    const putRes = await putPromise;
    expect(putRes.status()).toBe(200);
    const body = await putRes.json();
    expect(body).toHaveProperty('sha256');
    expect(body).toHaveProperty('file_name_original');
  });
});


