const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('C2.15: AUTO-UPLOAD Real (Protected)', () => {
    test('build_auto_upload_plan + execute_auto_upload debe funcionar end-to-end', async ({ page }) => {
        // SPRINT C2.15: Este test SOLO se ejecuta si existe variable de entorno habilitadora
        const ENABLE_REAL_UPLOAD = process.env.EGESTIONA_REAL_UPLOAD_TEST === '1';
        
        if (!ENABLE_REAL_UPLOAD) {
            test.skip(true, 'Test protegido: requiere EGESTIONA_REAL_UPLOAD_TEST=1');
            return;
        }
        
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_15_auto_upload_plan');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Verificar que el servidor está corriendo
        console.log('[AUTO_UPLOAD_TEST] ⚠️ TEST REAL - Subirá documentos reales en e-gestiona');
        console.log('[AUTO_UPLOAD_TEST] Verificando que el backend está corriendo...');
        try {
            const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
            expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
            console.log('[AUTO_UPLOAD_TEST] ✅ Backend está corriendo');
        } catch (e) {
            throw new Error(`Backend no está corriendo en ${BACKEND_URL}. Inicia el servidor primero.`);
        }
        
        // 1) Construir plan de auto-upload
        console.log('[AUTO_UPLOAD_TEST] Paso 1: Construyendo plan de auto-upload...');
        const planResponse = await page.request.post(
            `${BACKEND_URL}/runs/egestiona/build_auto_upload_plan?coord=Aigues%20de%20Manresa&company_key=F63161988&person_key=erm&limit=200&only_target=true&max_items=200&max_pages=10`,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CLIENT-REQ-ID': `auto-upload-test-${Date.now()}`
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
        
        // ASSERT: Plan debe tener snapshot, decisions, summary
        expect(planJson.snapshot, 'snapshot debe existir').toBeDefined();
        expect(planJson.decisions, 'decisions debe ser array').toBeInstanceOf(Array);
        expect(planJson.summary, 'summary debe existir').toBeDefined();
        
        const summary = planJson.summary;
        console.log(`[AUTO_UPLOAD_TEST] Plan construido:`, {
            total: summary.total,
            auto_upload_count: summary.auto_upload_count,
            review_required_count: summary.review_required_count,
            no_match_count: summary.no_match_count,
        });
        
        // ASSERT: Cada decision debe tener pending_item_key, decision, reason_code, reason, confidence
        planJson.decisions.forEach((decision, idx) => {
            expect(decision.pending_item_key, `decision[${idx}].pending_item_key debe existir`).toBeDefined();
            expect(['AUTO_UPLOAD', 'REVIEW_REQUIRED', 'NO_MATCH'], `decision[${idx}].decision debe ser válido`).toContain(decision.decision);
            expect(decision.reason_code, `decision[${idx}].reason_code debe existir`).toBeDefined();
            expect(decision.reason, `decision[${idx}].reason debe existir`).toBeDefined();
            expect(typeof decision.confidence, `decision[${idx}].confidence debe ser número`).toBe('number');
        });
        
        // 2) Si hay >=1 AUTO_UPLOAD, ejecutar upload de 1 (smoke test)
        if (summary.auto_upload_count >= 1) {
            console.log(`[AUTO_UPLOAD_TEST] Paso 2: Ejecutando upload de 1 item (smoke test)...`);
            
            // Seleccionar primer item AUTO_UPLOAD
            const autoUploadDecisions = planJson.decisions.filter(d => d.decision === 'AUTO_UPLOAD');
            const firstItemKey = autoUploadDecisions[0].pending_item_key;
            
            console.log(`[AUTO_UPLOAD_TEST] Item seleccionado: ${firstItemKey}`);
            
            const uploadResponse = await page.request.post(
                `${BACKEND_URL}/runs/egestiona/execute_auto_upload`,
                {
                    headers: {
                        'Content-Type': 'application/json',
                        'X-USE-REAL-UPLOADER': '1',  // SPRINT C2.15: Header requerido
                        'X-CLIENT-REQ-ID': `auto-upload-exec-${Date.now()}`
                    },
                    data: {
                        coord: 'Aigues de Manresa',
                        company_key: 'F63161988',
                        person_key: 'erm',
                        only_target: true,
                        items: [firstItemKey],
                        max_uploads: 1,
                        stop_on_first_error: true,
                        rate_limit_seconds: 1.5,
                    }
                }
            );
            
            const uploadBody = await uploadResponse.text();
            let uploadJson;
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
            
            // ASSERT: Debe devolver status ok/partial/error (nunca 500)
            expect(uploadResponse.status(), 'HTTP status debe ser 200 (nunca 500)').toBe(200);
            
            // ASSERT: Debe tener results y summary
            expect(uploadJson.results, 'results debe ser array').toBeInstanceOf(Array);
            expect(uploadJson.summary, 'summary debe existir').toBeDefined();
            
            const uploadSummary = uploadJson.summary;
            console.log(`[AUTO_UPLOAD_TEST] Upload completado:`, {
                total: uploadSummary.total,
                success: uploadSummary.success,
                failed: uploadSummary.failed,
                skipped: uploadSummary.skipped,
            });
            
            // ASSERT: Cada result debe tener pending_item_key, success, reason
            uploadJson.results.forEach((result, idx) => {
                expect(result.pending_item_key, `result[${idx}].pending_item_key debe existir`).toBeDefined();
                expect(typeof result.success, `result[${idx}].success debe ser boolean`).toBe('boolean');
                expect(result.reason, `result[${idx}].reason debe existir`).toBeDefined();
            });
        } else {
            console.log(`[AUTO_UPLOAD_TEST] ⚠️ No hay items AUTO_UPLOAD, saltando ejecución de upload`);
        }
        
        // Guardar resumen del test
        const testSummary = {
            timestamp: new Date().toISOString(),
            test: 'egestiona_auto_upload_real',
            planHttpStatus: planResponse.status(),
            planStatus: planJson.status,
            planSummary: summary,
            decisionsCount: planJson.decisions.length,
            uploadExecuted: summary.auto_upload_count >= 1,
            uploadHttpStatus: summary.auto_upload_count >= 1 ? uploadResponse.status() : null,
            uploadStatus: summary.auto_upload_count >= 1 ? uploadJson.status : null,
            uploadSummary: summary.auto_upload_count >= 1 ? uploadJson.summary : null,
            testPassed: planResponse.status() === 200 && 
                       planJson.status === 'ok' &&
                       Array.isArray(planJson.decisions) &&
                       (summary.auto_upload_count === 0 || (uploadResponse.status() === 200 && uploadJson.status !== undefined)),
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(testSummary, null, 2),
            'utf-8'
        );
        
        console.log(`[AUTO_UPLOAD_TEST] ✅ Test completado. Resumen guardado en ${EVIDENCE_DIR}`);
        
        // ASSERT final: Test debe pasar
        expect(testSummary.testPassed, 
            `Test debe pasar (HTTP 200, status=ok, decisions es array, upload ejecutado si hay AUTO_UPLOAD)`
        ).toBe(true);
    });
});
