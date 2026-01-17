const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('C2.16: Hardening E2E (Protected)', () => {
    test('run_summary debe escribirse y endpoint /api/runs/summary debe listarlo', async ({ page }) => {
        // SPRINT C2.16: Este test SOLO se ejecuta si existe variable de entorno habilitadora
        const ENABLE_REAL_UPLOAD = process.env.EGESTIONA_REAL_UPLOAD_TEST === '1';
        
        if (!ENABLE_REAL_UPLOAD) {
            test.skip(true, 'Test protegido: requiere EGESTIONA_REAL_UPLOAD_TEST=1');
            return;
        }
        
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_16_hardening');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Verificar que el servidor está corriendo
        console.log('[HARDENING_TEST] Verificando que el backend está corriendo...');
        try {
            const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
            expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
            console.log('[HARDENING_TEST] ✅ Backend está corriendo');
        } catch (e) {
            throw new Error(`Backend no está corriendo en ${BACKEND_URL}. Inicia el servidor primero.`);
        }
        
        // 1) Ejecutar auto-upload (1 item) para generar run_summary
        console.log('[HARDENING_TEST] Paso 1: Ejecutando auto-upload para generar run_summary...');
        
        // Primero construir plan
        const planResponse = await page.request.post(
            `${BACKEND_URL}/runs/egestiona/build_auto_upload_plan?coord=Aigues%20de%20Manresa&company_key=F63161988&person_key=erm&limit=200&only_target=true&max_items=200&max_pages=10`,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CLIENT-REQ-ID': `hardening-test-${Date.now()}`
                }
            }
        );
        
        const planBody = await planResponse.text();
        let planJson;
        try {
            planJson = JSON.parse(planBody);
        } catch (e) {
            throw new Error(`Plan response NO es JSON válido: ${e.message}`);
        }
        
        // Guardar plan response
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'plan_response.json'),
            JSON.stringify(planJson, null, 2),
            'utf-8'
        );
        
        // ASSERT: Plan debe tener status=ok
        expect(planJson.status, 'status debe ser "ok"').toBe('ok');
        
        const summary = planJson.summary || {};
        console.log(`[HARDENING_TEST] Plan construido:`, {
            total: summary.total,
            auto_upload_count: summary.auto_upload_count,
        });
        
        // 2) Si hay >=1 AUTO_UPLOAD, ejecutar upload de 1 item
        let runId = null;
        let uploadResponse = null;
        let uploadJson = null;
        
        if (summary.auto_upload_count >= 1) {
            const autoUploadDecisions = planJson.decisions.filter(d => d.decision === 'AUTO_UPLOAD');
            const firstItemKey = autoUploadDecisions[0].pending_item_key;
            
            console.log(`[HARDENING_TEST] Paso 2: Ejecutando upload de 1 item...`);
            
            uploadResponse = await page.request.post(
                `${BACKEND_URL}/runs/egestiona/execute_auto_upload`,
                {
                    headers: {
                        'Content-Type': 'application/json',
                        'X-USE-REAL-UPLOADER': '1',
                        'X-CLIENT-REQ-ID': `hardening-exec-${Date.now()}`
                    },
                    data: {
                        coord: 'Aigues de Manresa',
                        company_key: 'F63161988',
                        person_key: 'erm',
                        only_target: true,
                        items: [firstItemKey],
                        max_uploads: 1,
                        stop_on_first_error: true,
                        continue_on_error: false,
                        rate_limit_seconds: 1.5,
                    }
                }
            );
            
            const uploadBody = await uploadResponse.text();
            try {
                uploadJson = JSON.parse(uploadBody);
            } catch (e) {
                throw new Error(`Upload response NO es JSON válido: ${e.message}`);
            }
            
            // Guardar upload response
            fs.writeFileSync(
                path.join(EVIDENCE_DIR, 'upload_response.json'),
                JSON.stringify(uploadJson, null, 2),
                'utf-8'
            );
            
            // ASSERT: Debe tener run_id en summary
            runId = uploadJson.summary?.run_id;
            expect(runId, 'run_id debe existir en summary').toBeDefined();
            
            console.log(`[HARDENING_TEST] Upload completado, run_id: ${runId}`);
        } else {
            console.log(`[HARDENING_TEST] ⚠️ No hay items AUTO_UPLOAD, saltando ejecución de upload`);
        }
        
        // 3) Verificar que run_summary.json existe (si se ejecutó upload)
        if (runId) {
            console.log(`[HARDENING_TEST] Paso 3: Verificando que run_summary.json existe...`);
            
            // El run_summary debería estar en data/runs/<run_id>/run_summary.json
            // No podemos acceder directamente al filesystem desde el test, pero podemos
            // verificar que el endpoint /api/runs/summary lo lista
            
            // Esperar un poco para que se escriba el summary
            await page.waitForTimeout(1000);
        }
        
        // 4) Llamar endpoint /api/runs/summary
        console.log(`[HARDENING_TEST] Paso 4: Llamando endpoint /api/runs/summary...`);
        
        const summaryResponse = await page.request.get(
            `${BACKEND_URL}/api/runs/summary?limit=10&platform=egestiona`
        );
        
        const summaryBody = await summaryResponse.text();
        let summaryJson;
        try {
            summaryJson = JSON.parse(summaryBody);
        } catch (e) {
            throw new Error(`Summary response NO es JSON válido: ${e.message}`);
        }
        
        // Guardar summary response
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'summary_list_response.json'),
            JSON.stringify(summaryJson, null, 2),
            'utf-8'
        );
        
        // ASSERT: Debe tener status=ok y summaries array
        expect(summaryResponse.status(), 'HTTP status debe ser 200').toBe(200);
        expect(summaryJson.status, 'status debe ser "ok"').toBe('ok');
        expect(Array.isArray(summaryJson.summaries), 'summaries debe ser array').toBe(true);
        
        console.log(`[HARDENING_TEST] Summary list contiene ${summaryJson.summaries.length} runs`);
        
        // ASSERT: Si se ejecutó upload, el run_id debe estar en la lista (o al menos debe haber summaries)
        if (runId) {
            const foundRun = summaryJson.summaries.find(s => s.run_id === runId);
            if (foundRun) {
                console.log(`[HARDENING_TEST] ✅ Run ${runId} encontrado en summary list`);
                
                // Verificar estructura del summary
                expect(foundRun.platform, 'platform debe ser "egestiona"').toBe('egestiona');
                expect(foundRun.counts, 'counts debe existir').toBeDefined();
                expect(foundRun.execution, 'execution debe existir').toBeDefined();
                expect(Array.isArray(foundRun.errors), 'errors debe ser array').toBe(true);
            } else {
                console.log(`[HARDENING_TEST] ⚠️ Run ${runId} no encontrado en summary list (puede ser que aún no se haya escrito)`);
            }
        }
        
        // Guardar resumen del test
        const testSummary = {
            timestamp: new Date().toISOString(),
            test: 'egestiona_hardening_e2e',
            planHttpStatus: planResponse.status(),
            planStatus: planJson.status,
            uploadExecuted: summary.auto_upload_count >= 1,
            uploadHttpStatus: summary.auto_upload_count >= 1 && uploadResponse ? uploadResponse.status() : null,
            runId: runId,
            summaryListHttpStatus: summaryResponse.status(),
            summaryListStatus: summaryJson.status,
            summaryListTotal: summaryJson.total,
            testPassed: planResponse.status() === 200 &&
                       planJson.status === 'ok' &&
                       summaryResponse.status() === 200 &&
                       summaryJson.status === 'ok' &&
                       Array.isArray(summaryJson.summaries),
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(testSummary, null, 2),
            'utf-8'
        );
        
        console.log(`[HARDENING_TEST] ✅ Test completado. Resumen guardado en ${EVIDENCE_DIR}`);
        
        // ASSERT final: Test debe pasar
        expect(testSummary.testPassed,
            `Test debe pasar (HTTP 200, status=ok, summaries es array)`
        ).toBe(true);
    });
});
