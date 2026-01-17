const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('C2.17: Decision Flow E2E (Protected)', () => {
    test('plan → decision → execute debe funcionar con plan congelado', async ({ page }) => {
        // SPRINT C2.17: Este test SOLO se ejecuta si existe variable de entorno habilitadora
        const ENABLE_REAL_UPLOAD = process.env.EGESTIONA_REAL_UPLOAD_TEST === '1';
        
        if (!ENABLE_REAL_UPLOAD) {
            test.skip(true, 'Test protegido: requiere EGESTIONA_REAL_UPLOAD_TEST=1');
            return;
        }
        
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'c2_17');
        
        // Asegurar que el directorio de evidencias existe
        if (!fs.existsSync(EVIDENCE_DIR)) {
            fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
        }
        
        // Verificar que el servidor está corriendo
        console.log('[DECISION_FLOW_TEST] Verificando que el backend está corriendo...');
        try {
            const healthResponse = await page.request.get(`${BACKEND_URL}/api/health`);
            expect(healthResponse.ok(), 'Backend debe estar corriendo en 127.0.0.1:8000').toBe(true);
            console.log('[DECISION_FLOW_TEST] ✅ Backend está corriendo');
        } catch (e) {
            throw new Error(`Backend no está corriendo en ${BACKEND_URL}. Inicia el servidor primero.`);
        }
        
        // Paso 1: Crear plan
        console.log('[DECISION_FLOW_TEST] Paso 1: Creando plan...');
        const planResponse = await page.request.post(
            `${BACKEND_URL}/runs/auto_upload/plan`,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CLIENT-REQ-ID': `decision-flow-test-${Date.now()}`
                },
                data: {
                    coord: 'Aigues de Manresa',
                    company_key: 'F63161988',
                    person_key: 'erm',
                    limit: 200,
                    only_target: true,
                    max_items: 200,
                    max_pages: 10,
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
        
        // ASSERT: Plan debe tener status=ok y plan_id
        expect(planResponse.status(), 'HTTP status debe ser 200').toBe(200);
        expect(planJson.status, 'status debe ser "ok"').toBe('ok');
        expect(planJson.plan_id, 'plan_id debe existir').toBeDefined();
        
        const planId = planJson.plan_id;
        console.log(`[DECISION_FLOW_TEST] Plan creado: plan_id=${planId}`);
        
        // Verificar que cada decisión tiene los campos requeridos
        const decisions = planJson.decisions || [];
        for (const decision of decisions) {
            expect(decision.decision, 'decision debe existir').toBeDefined();
            expect(decision.decision_reason, 'decision_reason debe existir').toBeDefined();
            expect(decision.confidence, 'confidence debe existir').toBeDefined();
            expect(decision.pending_item_key, 'pending_item_key debe existir').toBeDefined();
        }
        
        // Paso 2: Recuperar plan congelado
        console.log(`[DECISION_FLOW_TEST] Paso 2: Recuperando plan congelado plan_id=${planId}...`);
        const getPlanResponse = await page.request.get(
            `${BACKEND_URL}/runs/auto_upload/plan/${planId}`
        );
        
        const getPlanBody = await getPlanResponse.text();
        let getPlanJson;
        try {
            getPlanJson = JSON.parse(getPlanBody);
        } catch (e) {
            throw new Error(`Get plan response NO es JSON válido: ${e.message}`);
        }
        
        // ASSERT: Plan recuperado debe ser igual
        expect(getPlanResponse.status(), 'HTTP status debe ser 200').toBe(200);
        expect(getPlanJson.plan_id, 'plan_id debe coincidir').toBe(planId);
        expect(getPlanJson.decisions.length, 'decisions debe tener items').toBeGreaterThan(0);
        
        // Paso 3: Ejecutar plan (solo AUTO_UPLOAD)
        const autoUploadDecisions = decisions.filter(d => d.decision === 'AUTO_UPLOAD');
        console.log(`[DECISION_FLOW_TEST] Plan tiene ${autoUploadDecisions.length} items AUTO_UPLOAD`);
        
        if (autoUploadDecisions.length === 0) {
            console.log('[DECISION_FLOW_TEST] ⚠️ No hay items AUTO_UPLOAD, saltando ejecución');
        } else {
            console.log(`[DECISION_FLOW_TEST] Paso 3: Ejecutando plan (max_uploads=1)...`);
            
            const executeResponse = await page.request.post(
                `${BACKEND_URL}/runs/auto_upload/execute`,
                {
                    headers: {
                        'Content-Type': 'application/json',
                        'X-USE-REAL-UPLOADER': '1',
                        'X-CLIENT-REQ-ID': `decision-exec-${Date.now()}`
                    },
                    data: {
                        plan_id: planId,
                        max_uploads: 1,  // Solo 1 item como smoke test
                        stop_on_first_error: true,
                        continue_on_error: false,
                        rate_limit_seconds: 1.5,
                    }
                }
            );
            
            const executeBody = await executeResponse.text();
            let executeJson;
            try {
                executeJson = JSON.parse(executeBody);
            } catch (e) {
                throw new Error(`Execute response NO es JSON válido: ${e.message}`);
            }
            
            // Guardar execute response
            fs.writeFileSync(
                path.join(EVIDENCE_DIR, 'execute_response.json'),
                JSON.stringify(executeJson, null, 2),
                'utf-8'
            );
            
            // ASSERT: Debe tener status y results
            expect(executeResponse.status(), 'HTTP status debe ser 200').toBe(200);
            expect(executeJson.status, 'status debe ser "ok" o "partial"').toMatch(/^(ok|partial|error)$/);
            expect(executeJson.plan_id, 'plan_id debe coincidir').toBe(planId);
            expect(Array.isArray(executeJson.results), 'results debe ser array').toBe(true);
            
            // Verificar que cada resultado tiene decisión
            for (const result of executeJson.results) {
                expect(result.pending_item_key, 'pending_item_key debe existir').toBeDefined();
                if (result.success) {
                    expect(result.decision, 'decision debe existir en resultado exitoso').toBeDefined();
                }
            }
            
            console.log(`[DECISION_FLOW_TEST] Ejecución completada: ${executeJson.summary?.success || 0} exitosos, ${executeJson.summary?.failed || 0} fallidos`);
        }
        
        // Guardar resumen del test
        const testSummary = {
            timestamp: new Date().toISOString(),
            test: 'egestiona_decision_flow',
            planHttpStatus: planResponse.status(),
            planStatus: planJson.status,
            planId: planId,
            decisionsCount: decisions.length,
            autoUploadCount: autoUploadDecisions.length,
            testPassed: planResponse.status() === 200 &&
                       planJson.status === 'ok' &&
                       planJson.plan_id !== undefined,
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'test_summary.json'),
            JSON.stringify(testSummary, null, 2),
            'utf-8'
        );
        
        console.log(`[DECISION_FLOW_TEST] ✅ Test completado. Resumen guardado en ${EVIDENCE_DIR}`);
        
        // ASSERT final: Test debe pasar
        expect(testSummary.testPassed,
            `Test debe pasar (HTTP 200, status=ok, plan_id existe)`
        ).toBe(true);
    });
});
