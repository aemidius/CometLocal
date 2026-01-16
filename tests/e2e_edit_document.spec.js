/**
 * E2E: Editar documento (modal Buscar documentos)
 * - Verifica que Guardar no devuelve 500
 * - Verifica persistencia (GET /api/repository/docs)
 */
const { test, expect } = require('@playwright/test');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

function pickNextStatus(current) {
  return current === 'reviewed' ? 'draft' : 'reviewed';
}

// SPRINT C2.2.2: Helpers para abrir y cerrar modal de edición
async function openEditModal(page, index = 0) {
    // SPRINT C2.9: Usar buscar-action-edit (testid correcto según frontend)
    const btn = page.locator('[data-testid="buscar-action-edit"]').nth(index);
    await btn.click({ force: true });
    await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'attached', timeout: 8000 });
    await page.waitForSelector('[data-testid="edit-doc-modal-open"]', { state: 'attached', timeout: 8000 });
}

async function closeEditModalAfterSave(page) {
    // Click guardar (SOLO data-testid)
    const saveButton = page.locator('[data-testid="edit-doc-save"]');
    await saveButton.click();
    // Esperar que el modal se cierre (el modal se cierra después de guardar exitosamente)
    await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'detached', timeout: 15000 });
}

test.describe('Buscar documentos - Editar documento', () => {
  test.setTimeout(60000); // SPRINT C2.9: Aumentar timeout para tests que pueden tardar
  let seedData;
  
  test.beforeAll(async ({ request }) => {
    // Reset y seed básico usando request (no page)
    await seedReset({ request });
    seedData = await seedBasicRepository({ request });
  });
  
  test.beforeEach(async ({ page }) => {
    // SPRINT C2.2.1: Añadir listeners de consola y errores para diagnóstico
    page.on('console', msg => console.log('[BROWSER]', msg.type(), msg.text()));
    page.on('pageerror', err => console.log('[PAGEERROR]', err.message));
    
    // Navigate usando helper
    await gotoHash(page, 'buscar');
    // SPRINT C2.9: Esperar señal de vista ready
    // SPRINT C2.9.8: Esperar view-buscar-ready con state: attached (markers hidden)
    await page.waitForSelector('[data-testid="view-buscar-ready"]', { timeout: 20000, state: 'attached' });
    // SPRINT C2.9: Esperar marcador determinista de resultados renderizados (attached, no visible)
    // Nota: performSearch() puede tardar, así que aumentamos timeout a 20s
    await page.waitForSelector('[data-testid="buscar-results-ready"]', { timeout: 20000, state: 'attached' });
    // SPRINT C2.9: Verificar que hay resultados (no vacío)
    const resultsMarker = page.locator('[data-testid="buscar-results-ready"]');
    const isEmpty = await resultsMarker.getAttribute('data-empty');
    if (isEmpty === 'true') {
      throw new Error('No se encontraron documentos en buscar para editar - el seed puede no haber creado documentos');
    }
    // SPRINT C2.9: Esperar a que aparezcan los botones de editar usando data-testid
    await page.waitForSelector('[data-testid="buscar-action-edit"]', { timeout: 10000 });
  });

  // SPRINT C2.2.2: Asegurar independencia entre tests - cerrar modal si queda abierto
  test.afterEach(async ({ page }) => {
    const overlayCount = await page.locator('[data-testid="edit-doc-modal-overlay"]').count();
    if (overlayCount > 0) {
      await page.keyboard.press('Escape');
      await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'detached', timeout: 3000 }).catch(() => {});
    }
  });

  test('editar documento y guardar OK (200), modal cierra y persiste', async ({ page }) => {
    const putPromise = page.waitForResponse((res) => {
      return res.url().includes('/api/repository/docs/') && res.request().method() === 'PUT';
    });

    // SPRINT C2.2.2: Usar helper para abrir modal
    await openEditModal(page, 0);

    // Toggle status (SOLO data-testid)
    const statusSel = page.locator('[data-testid="edit-doc-status"]');
    const current = (await statusSel.inputValue()).trim();
    const next = pickNextStatus(current);
    await statusSel.selectOption(next);

    // Click guardar (SOLO data-testid)
    const saveButton = page.locator('[data-testid="edit-doc-save"]');
    await saveButton.click();
    
    const putRes = await putPromise;
    
    // SPRINT C2.2.2: Esperar que el modal se cierre después de guardar exitosamente
    // El modal se cierra después de performSearch(), que puede tomar tiempo
    await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'detached', timeout: 20000 });
    expect(putRes.status()).toBe(200);
    const putBody = await putRes.json();
    expect(putBody).toHaveProperty('doc_id');
    const docId = putBody.doc_id;

    // Persistencia: GET docs y verificar status actualizado para ese doc_id
    const docsRes = await page.request.get('http://127.0.0.1:8000/api/repository/docs');
    expect(docsRes.status()).toBe(200);
    const docs = await docsRes.json();
    const found = docs.find((d) => (d.doc_id || d.id) === docId);
    expect(found, `Documento ${docId} no encontrado tras guardar`).toBeTruthy();
    expect(found.status).toBe(next);
  });

  test('cambiar "Estado de tramitación" (Borrador <-> Revisado) y guardar', async ({ page }) => {
    const putPromise = page.waitForResponse((res) => {
      return res.url().includes('/api/repository/docs/') && res.request().method() === 'PUT';
    });

    // SPRINT C2.2.2: Usar helper para abrir modal
    await openEditModal(page, 0);

    const statusSel = page.locator('[data-testid="edit-doc-status"]');
    const current = (await statusSel.inputValue()).trim();
    const next = pickNextStatus(current);
    await statusSel.selectOption(next);

    // Click guardar (SOLO data-testid)
    const saveButton = page.locator('[data-testid="edit-doc-save"]');
    await saveButton.click();
    
    const putRes = await putPromise;
    
    // SPRINT C2.2.2: Esperar que el modal se cierre después de guardar exitosamente
    // El modal se cierra después de performSearch(), que puede tomar tiempo
    await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'detached', timeout: 20000 });
    expect(putRes.status()).toBe(200);
    const putBody = await putRes.json();
    expect(putBody.status).toBe(next);
  });

  test('cambiar "Fecha inicio de vigencia" y guardar; computed_validity coherente', async ({ page }) => {
    const putPromise = page.waitForResponse((res) => {
      return res.url().includes('/api/repository/docs/') && res.request().method() === 'PUT';
    });

    // SPRINT C2.2.2: Usar helper para abrir modal
    await openEditModal(page, 0);

    // SPRINT C2.2.2: Esperar a que el input exista dentro del modal (SOLO data-testid)
    const dateInput = page.locator('[data-testid="edit-doc-validity-start-date"]');
    await expect(dateInput).toBeVisible();

    // Cambiar a una fecha distinta (sumar 1 día respecto a hoy)
    const today = new Date();
    const d = new Date(today.getTime() + 24 * 60 * 60 * 1000);
    const iso = d.toISOString().slice(0, 10); // YYYY-MM-DD
    await dateInput.fill(iso);

    // Click guardar (SOLO data-testid)
    const saveButton = page.locator('[data-testid="edit-doc-save"]');
    await saveButton.click();
    
    const putRes = await putPromise;
    
    // SPRINT C2.2.2: Esperar que el modal se cierre después de guardar exitosamente
    // El modal se cierra después de performSearch(), que puede tomar tiempo
    await page.waitForSelector('[data-testid="edit-doc-modal-overlay"]', { state: 'detached', timeout: 20000 });
    expect(putRes.status()).toBe(200);
    const putBody = await putRes.json();

    // Verificar que se persistió en extracted
    expect(putBody.extracted).toBeTruthy();
    expect(putBody.extracted.validity_start_date).toBe(iso);

    // Coherencia mínima de validez calculada
    expect(putBody.computed_validity).toBeTruthy();
    const { valid_from, valid_to } = putBody.computed_validity;
    expect(valid_from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(valid_to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(new Date(valid_from).getTime()).toBeLessThanOrEqual(new Date(valid_to).getTime());
  });
});






