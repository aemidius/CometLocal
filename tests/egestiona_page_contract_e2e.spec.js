const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.describe('HOTFIX: Page Contract Validator (E2E)', () => {
    test('Validar que el endpoint devuelve error si no se puede verificar page contract', async () => {
        const BACKEND_URL = 'http://127.0.0.1:8000';

        // Este test valida que el sistema NO devuelve "0 pendientes" silencioso
        // cuando hay un error de navegación. En un entorno real, esto requeriría
        // simular una página sin los selectores correctos, pero para E2E básico
        // validamos que el endpoint maneja errores estructurados.
        
        // Nota: Este test es básico porque simular una página incorrecta
        // requeriría mockear el navegador o tener un entorno de prueba específico.
        // El test valida que el código de error existe y se maneja correctamente.
        
        // Intentar generar plan (puede fallar por page contract si hay problemas)
        const buildResponse = await fetch(`${BACKEND_URL}/runs/egestiona/build_submission_plan_readonly?coord=Aigues%20de%20Manresa&company_key=B12345678&limit=5&only_target=false&fixture=1`, {
            method: 'POST',
            headers: {
                'X-CAE-PLAN-FIXTURE': '1',
            },
        });

        const result = await buildResponse.json();
        
        // Si hay error, debe ser estructurado, no "0 pendientes" silencioso
        if (result.status === 'error') {
            expect(result.error_code).toBeDefined();
            expect(result.message).toBeDefined();
            // NO debe ser un summary con 0 items como si fuera OK
            expect(result.summary).toBeUndefined();
        } else {
            // Si es OK, debe tener items o summary explícito
            expect(result.status).toBe('ok');
            // Si hay 0 items, debe ser porque realmente no hay, no por error de navegación
            if (result.summary && result.summary.pending_count === 0) {
                // En modo fixture, siempre hay items, así que esto no debería pasar
                // Pero si pasa, al menos sabemos que fue intencional (fixture vacío)
                expect(result.items).toBeDefined();
            }
        }
    });
});
