const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('C2.13.9a: READ-ONLY Backend Regression - Grid Search Fix + Instrumentation', () => {
    test('build_submission_plan_readonly debe devolver items_count >= 1 cuando hay pendientes reales', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_13_9a');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Verificar que el servidor está corriendo
        console.log('[REGRESSION TEST] Verificando que el backend está corriendo...');
        try {
            const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
            expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
            console.log('[REGRESSION TEST] ✅ Backend está corriendo');
        } catch (e) {
            throw new Error(`Backend no está corriendo en ${BACKEND_URL}. Inicia el servidor primero.`);
        }
        
        // Hacer request directo al endpoint
        console.log('[REGRESSION TEST] Haciendo POST al endpoint build_submission_plan_readonly...');
        const response = await page.request.post(
            `${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=F63161988&person_key=erm&limit=50&only_target=true`,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CLIENT-REQ-ID': `regression-test-${Date.now()}`
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
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'response.json'),
            JSON.stringify({
                status: response.status(),
                statusText: response.statusText(),
                headers: response.headers(),
                body: responseJson
            }, null, 2),
            'utf-8'
        );
        
        // ASSERT: NO debe haber 500
        expect(response.status(), 'HTTP status NO debe ser 500').not.toBe(500);
        
        // ASSERT: Debe ser 200
        expect(response.status(), 'HTTP status debe ser 200').toBe(200);
        
        // ASSERT: Debe tener status (ok o error)
        expect(responseJson.status, 'Respuesta debe tener campo "status"').toBeTruthy();
        expect(['ok', 'error'], 'status debe ser "ok" o "error"').toContain(responseJson.status);
        
        // Analizar respuesta
        const itemsCount = responseJson.items?.length || responseJson.plan?.length || 0;
        const summary = responseJson.summary || {};
        const pendingCount = summary.pending_count || itemsCount;
        const diagnostics = responseJson.diagnostics || {};
        const searchResult = diagnostics.search_result || {};
        
        // Guardar resumen
        const testSummary = {
            timestamp: new Date().toISOString(),
            httpStatus: response.status(),
            responseStatus: responseJson.status,
            itemsCount: itemsCount,
            pendingCount: pendingCount,
            hasError: responseJson.status === 'error',
            errorCode: responseJson.error_code || null,
            diagnostics: diagnostics,
            searchClicked: searchResult.search_clicked || false,
            searchRowsBefore: searchResult.rows_before || 0,
            searchRowsAfter: searchResult.rows_after || 0,
            testPassed: response.status() === 200 && 
                       responseJson.status === 'ok' && 
                       itemsCount >= 1
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(testSummary, null, 2),
            'utf-8'
        );
        
        // Resumen
        console.log('\n=== RESUMEN DEL REGRESSION TEST ===');
        console.log(`HTTP Status: ${response.status()}`);
        console.log(`Response Status: ${responseJson.status}`);
        console.log(`Items Count: ${itemsCount}`);
        console.log(`Pending Count: ${pendingCount}`);
        console.log(`Search Clicked: ${testSummary.searchClicked}`);
        console.log(`Search Rows Before: ${testSummary.searchRowsBefore}`);
        console.log(`Search Rows After: ${testSummary.searchRowsAfter}`);
        console.log(`Test Passed: ${testSummary.testPassed}`);
        console.log(`Evidencias guardadas en: ${EVIDENCE_DIR}`);
        
        // ASSERT: Si hay error, debe ser estructurado (no 500 crudo)
        if (responseJson.status === 'error') {
            expect(responseJson.error_code, 'Si hay error, debe tener error_code').toBeTruthy();
            expect(responseJson.message, 'Si hay error, debe tener message').toBeTruthy();
            
            // Si el error es "no_rows_after_search", adjuntar response.json a evidence
            if (responseJson.error_code === 'no_rows_after_search' || diagnostics.reason === 'no_rows_after_search') {
                console.warn('[REGRESSION TEST] ⚠️ Error "no_rows_after_search" detectado. Verificar evidencias.');
            }
        }
        
        // ASSERT: NO debe haber error_code grid_parse_mismatch
        if (responseJson.status === 'error' && responseJson.error_code === 'grid_parse_mismatch') {
            console.error('[REGRESSION TEST] ❌ Error grid_parse_mismatch: UI muestra registros pero parser extrajo 0 filas.');
            console.error(`[REGRESSION TEST] Counter text: ${testSummary.diagnostics?.counter_text || 'N/A'}`);
            console.error(`[REGRESSION TEST] Counter count: ${testSummary.diagnostics?.counter_count || 'N/A'}`);
            console.error(`[REGRESSION TEST] Rows data count: ${testSummary.diagnostics?.rows_data_count || 'N/A'}`);
        }
        
        // ASSERT: Si status=ok, items_count debe ser >= 1 (hay pendientes reales)
        if (responseJson.status === 'ok') {
            if (itemsCount === 0) {
                console.warn('[REGRESSION TEST] ⚠️ items_count=0. Verificar si hay pendientes reales en e-gestiona.');
                console.warn('[REGRESSION TEST] Si hay pendientes reales, esto indica un problema con el scraping.');
                
                // Si se intentó búsqueda y sigue vacío, es un problema
                if (testSummary.searchClicked && testSummary.searchRowsAfter === 0) {
                    console.error('[REGRESSION TEST] ❌ Se intentó búsqueda pero rows_after=0. Problema con scraping.');
                }
            } else {
                console.log(`[REGRESSION TEST] ✅ items_count=${itemsCount} - Scraping funcionó correctamente`);
            }
        }
        
        // ASSERT: NO debe haber error_code grid_parse_mismatch
        expect(
            responseJson.error_code,
            'NO debe haber error_code grid_parse_mismatch (indica problema con selectores del grid)'
        ).not.toBe('grid_parse_mismatch');
        
        // ASSERT final: Test debe pasar (HTTP 200, status=ok, items_count >= 1)
        // Nota: Permitir items_count=0 solo si realmente no hay pendientes (validar manualmente)
        expect(testSummary.testPassed, 
            `Test debe pasar (HTTP 200, status=ok, items_count >= 1). ` +
            `Si items_count=0 pero hay pendientes reales, esto indica un problema con el scraping.`
        ).toBe(true);
    });
});
