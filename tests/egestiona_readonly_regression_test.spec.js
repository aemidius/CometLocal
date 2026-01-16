const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('HOTFIX: READ-ONLY Regression Test - UnboundLocalError prevention', () => {
    test('build_submission_plan_readonly NO debe devolver 500 ni UnboundLocalError', async ({ page }) => {
        const BACKEND_URL = 'http://127.0.0.1:8000';
        const EVIDENCE_DIR = path.join(__dirname, '..', 'docs', 'evidence', 'read_only_regression_fix');
        
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
        
        // Interceptar respuesta de red
        let networkResponse = null;
        let networkResponseBody = null;
        
        page.on('response', async (response) => {
            const url = response.url();
            if (url.includes('/runs/egestiona/build_submission_plan_readonly') && response.request().method() === 'POST') {
                console.log(`[REGRESSION TEST][NETWORK] Capturando respuesta de: ${url}`);
                networkResponse = {
                    url: url,
                    status: response.status(),
                    statusText: response.statusText(),
                    headers: response.headers(),
                    timestamp: new Date().toISOString()
                };
                
                try {
                    networkResponseBody = await response.text();
                    networkResponse.bodyRaw = networkResponseBody;
                    networkResponse.bodyRawLength = networkResponseBody.length;
                    
                    try {
                        networkResponse.bodyJson = JSON.parse(networkResponseBody);
                    } catch (parseError) {
                        networkResponse.bodyJsonParseError = parseError.message;
                    }
                } catch (bodyError) {
                    networkResponse.bodyError = bodyError.message;
                }
            }
        });
        
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
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'response.json'),
            JSON.stringify({
                status: response.status(),
                statusText: response.statusText(),
                headers: response.headers(),
                body: responseBody,
                bodyJson: (() => {
                    try {
                        return JSON.parse(responseBody);
                    } catch (e) {
                        return { parseError: e.message };
                    }
                })()
            }, null, 2),
            'utf-8'
        );
        
        // ASSERT: NO debe haber 500
        expect(response.status(), 'HTTP status NO debe ser 500 (Internal Server Error)').not.toBe(500);
        
        // ASSERT: Debe ser 200
        expect(response.status(), 'HTTP status debe ser 200').toBe(200);
        
        // ASSERT: Debe ser JSON válido
        let responseJson;
        try {
            responseJson = JSON.parse(responseBody);
        } catch (e) {
            throw new Error(`Respuesta NO es JSON válido: ${e.message}`);
        }
        
        // ASSERT: NO debe contener UnboundLocalError en el mensaje
        const responseStr = JSON.stringify(responseJson);
        expect(
            responseStr.toLowerCase().includes('unboundlocalerror'),
            'Respuesta NO debe contener "UnboundLocalError" en el mensaje'
        ).toBe(false);
        
        expect(
            responseStr.toLowerCase().includes('cannot access local variable'),
            'Respuesta NO debe contener "cannot access local variable" en el mensaje'
        ).toBe(false);
        
        // ASSERT: Si hay error, debe ser un error estructurado (no 500 crudo)
        if (responseJson.status === 'error') {
            expect(responseJson.error_code, 'Si hay error, debe tener error_code').toBeTruthy();
            expect(responseJson.message, 'Si hay error, debe tener message').toBeTruthy();
        }
        
        // ASSERT: Debe tener status (ok o error)
        expect(responseJson.status, 'Respuesta debe tener campo "status"').toBeTruthy();
        expect(['ok', 'error'], 'status debe ser "ok" o "error"').toContain(responseJson.status);
        
        // Guardar resumen
        const summary = {
            timestamp: new Date().toISOString(),
            httpStatus: response.status(),
            responseStatus: responseJson.status,
            hasError: responseJson.status === 'error',
            errorCode: responseJson.error_code || null,
            itemsCount: responseJson.items?.length || responseJson.plan?.length || 0,
            hasUnboundLocalError: responseStr.toLowerCase().includes('unboundlocalerror'),
            hasCannotAccessLocalVariable: responseStr.toLowerCase().includes('cannot access local variable'),
            testPassed: response.status() === 200 && 
                       !responseStr.toLowerCase().includes('unboundlocalerror') &&
                       !responseStr.toLowerCase().includes('cannot access local variable')
        };
        
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'regression_test_summary.json'),
            JSON.stringify(summary, null, 2),
            'utf-8'
        );
        
        console.log('\n=== RESUMEN DEL REGRESSION TEST ===');
        console.log(`HTTP Status: ${response.status()}`);
        console.log(`Response Status: ${responseJson.status}`);
        console.log(`Has Error: ${summary.hasError}`);
        console.log(`Error Code: ${summary.errorCode || 'N/A'}`);
        console.log(`Items Count: ${summary.itemsCount}`);
        console.log(`Has UnboundLocalError: ${summary.hasUnboundLocalError}`);
        console.log(`Has CannotAccessLocalVariable: ${summary.hasCannotAccessLocalVariable}`);
        console.log(`Test Passed: ${summary.testPassed}`);
        console.log(`Evidencias guardadas en: ${EVIDENCE_DIR}`);
        
        // ASSERT final: Test debe pasar
        expect(summary.testPassed, 'Regression test debe pasar (no 500, no UnboundLocalError)').toBe(true);
    });
});
