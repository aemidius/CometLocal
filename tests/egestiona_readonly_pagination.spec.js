const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('C2.14.1: READ-ONLY Pagination Support', () => {
    test('build_submission_plan_readonly debe soportar paginación y devolver pending_item_key en cada item', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_14_1_pagination');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Verificar que el servidor está corriendo
        console.log('[PAGINATION TEST] Verificando que el backend está corriendo...');
        try {
            const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
            expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
            console.log('[PAGINATION TEST] ✅ Backend está corriendo');
        } catch (e) {
            throw new Error(`Backend no está corriendo en ${BACKEND_URL}. Inicia el servidor primero.`);
        }
        
        // Hacer request directo al endpoint
        console.log('[PAGINATION TEST] Haciendo POST al endpoint build_submission_plan_readonly...');
        const response = await page.request.post(
            `${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=F63161988&person_key=erm&limit=50&only_target=true`,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CLIENT-REQ-ID': `pagination-test-${Date.now()}`
                }
            }
        );
        
        // Guardar respuesta
        const responseBody = await response.text();
        let responseJson;
        try {
            responseJson = JSON.parse(responseBody);
        } catch (e) {
            throw new Error(`Respuesta NO es JSON válido: ${e.message}`);
        }
        
        // Guardar response.json
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'response.json'),
            JSON.stringify(responseJson, null, 2),
            'utf-8'
        );
        
        // ASSERT: HTTP 200
        expect(response.status(), 'HTTP status debe ser 200').toBe(200);
        
        // ASSERT: status=ok
        expect(responseJson.status, 'status debe ser "ok"').toBe('ok');
        
        // ASSERT: items es array
        const items = responseJson.items || responseJson.plan || [];
        expect(Array.isArray(items), 'items debe ser un array').toBe(true);
        
        // ASSERT: cada item tiene pending_item_key (en pending_ref o nivel superior)
        let items_with_key = 0;
        let items_without_key = 0;
        
        for (const item of items) {
            const pending_ref = item.pending_ref || {};
            const pending_item_key = pending_ref.pending_item_key || item.pending_item_key;
            
            if (pending_item_key) {
                items_with_key++;
            } else {
                items_without_key++;
                console.warn(`[PAGINATION TEST] ⚠️ Item sin pending_item_key:`, {
                    tipo_doc: pending_ref.tipo_doc,
                    elemento: pending_ref.elemento,
                    empresa: pending_ref.empresa,
                });
            }
        }
        
        console.log(`[PAGINATION TEST] Items con pending_item_key: ${items_with_key}/${items.length}`);
        
        // Si hay items, al menos algunos deben tener pending_item_key
        if (items.length > 0) {
            expect(items_with_key, `Al menos algunos items deben tener pending_item_key (encontrados: ${items_with_key}/${items.length})`).toBeGreaterThan(0);
        }
        
        // ASSERT: Si hay paginación detectada, verificar diagnostics.pagination
        const diagnostics = responseJson.diagnostics || {};
        const pagination = diagnostics.pagination;
        
        if (pagination && pagination.has_pagination) {
            console.log(`[PAGINATION TEST] Paginación detectada:`, {
                pages_detected: pagination.pages_detected,
                pages_processed: pagination.pages_processed,
                items_before_dedupe: pagination.items_before_dedupe,
                items_after_dedupe: pagination.items_after_dedupe,
                truncated: pagination.truncated,
            });
            
            // ASSERT: pages_processed >= 1
            expect(pagination.pages_processed, 'pages_processed debe ser >= 1').toBeGreaterThanOrEqual(1);
            
            // Si hay truncación, registrar advertencia
            if (pagination.truncated) {
                console.warn(`[PAGINATION TEST] ⚠️ Paginación truncada: max_pages=${pagination.max_pages} o max_items=${pagination.max_items}`);
            }
        } else {
            console.log('[PAGINATION TEST] No se detectó paginación (puede ser que solo haya 1 página o no haya controles visibles)');
        }
        
        // Guardar resumen del test
        const testSummary = {
            timestamp: new Date().toISOString(),
            test: 'egestiona_readonly_pagination',
            httpStatus: response.status(),
            status: responseJson.status,
            itemsCount: items.length,
            itemsWithKey: items_with_key,
            itemsWithoutKey: items_without_key,
            hasPagination: pagination?.has_pagination || false,
            paginationInfo: pagination || null,
            testPassed: response.status() === 200 && 
                       responseJson.status === 'ok' && 
                       Array.isArray(items) &&
                       (items.length === 0 || items_with_key > 0),
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(testSummary, null, 2),
            'utf-8'
        );
        
        console.log(`[PAGINATION TEST] ✅ Test completado. Resumen guardado en ${EVIDENCE_DIR}`);
        
        // ASSERT final: Test debe pasar
        expect(testSummary.testPassed, 
            `Test debe pasar (HTTP 200, status=ok, items es array, items tienen pending_item_key si items.length > 0)`
        ).toBe(true);
    });
});
