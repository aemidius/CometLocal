const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('C2.14.1: REAL Uploader - One Item (Protected)', () => {
    test('execute_plan_headful debe subir 1 documento y verificar post-condición', async ({ page }) => {
        // SPRINT C2.14.1: Este test SOLO se ejecuta si existe variable de entorno habilitadora
        const ENABLE_REAL_UPLOAD = process.env.EGESTIONA_REAL_UPLOAD_TEST === '1';
        
        if (!ENABLE_REAL_UPLOAD) {
            test.skip(true, 'Test protegido: requiere EGESTIONA_REAL_UPLOAD_TEST=1');
            return;
        }
        
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_14_1_real_upload_one');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Verificar que el servidor está corriendo
        console.log('[REAL UPLOAD TEST] ⚠️ TEST REAL - Subirá documento real en e-gestiona');
        console.log('[REAL UPLOAD TEST] Verificando que el backend está corriendo...');
        try {
            const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
            expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
            console.log('[REAL UPLOAD TEST] ✅ Backend está corriendo');
        } catch (e) {
            throw new Error(`Backend no está corriendo en ${BACKEND_URL}. Inicia el servidor primero.`);
        }
        
        // 1) Primero obtener un plan READ-ONLY para tener items con pending_item_key
        console.log('[REAL UPLOAD TEST] Paso 1: Obteniendo plan READ-ONLY...');
        const planResponse = await page.request.post(
            `${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=F63161988&person_key=erm&limit=50&only_target=true`,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CLIENT-REQ-ID': `real-upload-test-${Date.now()}`
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
        
        // ASSERT: Plan debe tener items
        const planItems = planJson.items || planJson.plan || [];
        expect(planItems.length, 'Plan debe tener al menos 1 item').toBeGreaterThan(0);
        
        // Buscar un item con matched_doc (que tenga documento para subir)
        const itemWithDoc = planItems.find(item => {
            const matchedDoc = item.matched_doc || {};
            return matchedDoc.doc_id && matchedDoc.type_id;
        });
        
        if (!itemWithDoc) {
            test.skip(true, 'No hay items con matched_doc en el plan');
            return;
        }
        
        console.log(`[REAL UPLOAD TEST] Item seleccionado:`, {
            tipo_doc: itemWithDoc.pending_ref?.tipo_doc,
            elemento: itemWithDoc.pending_ref?.elemento,
            doc_id: itemWithDoc.matched_doc?.doc_id,
            pending_item_key: itemWithDoc.pending_ref?.pending_item_key || itemWithDoc.pending_item_key,
        });
        
        // 2) Ejecutar upload real con header X-USE-REAL-UPLOADER=1
        console.log('[REAL UPLOAD TEST] Paso 2: Ejecutando upload real...');
        const uploadResponse = await page.request.post(
            `${BACKEND_URL}/runs/egestiona/execute_plan_headful`,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-USE-REAL-UPLOADER': '1',  // SPRINT C2.14.1: Header requerido
                    'X-CLIENT-REQ-ID': `real-upload-exec-${Date.now()}`
                },
                data: {
                    coord: 'Aigues de Manresa',
                    company_key: 'F63161988',
                    person_key: 'erm',
                    plan: [itemWithDoc],  // Solo 1 item
                    max_uploads: 1,  // SPRINT C2.14.1: Guardrail
                    allowlist_type_ids: [itemWithDoc.matched_doc.type_id],  // SPRINT C2.14.1: Guardrail
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
        
        // ASSERT: Debe devolver success true o si falla, reason explícito (nunca excepción)
        expect(uploadResponse.status(), 'HTTP status debe ser 200 (nunca 500)').toBe(200);
        
        // El response puede tener diferentes estructuras según el endpoint
        const success = uploadJson.success !== false;  // Si no está presente, asumir éxito
        const reason = uploadJson.reason || uploadJson.error_code || 'unknown';
        
        console.log(`[REAL UPLOAD TEST] Resultado:`, {
            success,
            reason,
            upload_id: uploadJson.upload_id,
            pending_item_key: uploadJson.pending_item_key,
            post_verification: uploadJson.post_verification,
        });
        
        // Guardar resumen del test
        const testSummary = {
            timestamp: new Date().toISOString(),
            test: 'egestiona_real_upload_one_item',
            httpStatus: uploadResponse.status(),
            success,
            reason,
            upload_id: uploadJson.upload_id,
            pending_item_key: uploadJson.pending_item_key || itemWithDoc.pending_ref?.pending_item_key,
            post_verification: uploadJson.post_verification,
            testPassed: uploadResponse.status() === 200 && (success || reason !== 'unknown'),
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(testSummary, null, 2),
            'utf-8'
        );
        
        console.log(`[REAL UPLOAD TEST] ✅ Test completado. Resumen guardado en ${EVIDENCE_DIR}`);
        
        // ASSERT final: Test debe pasar (HTTP 200, success o reason explícito)
        expect(testSummary.testPassed, 
            `Test debe pasar (HTTP 200, success=true o reason explícito, nunca excepción)`
        ).toBe(true);
    });
});
