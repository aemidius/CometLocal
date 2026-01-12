/**
 * SPRINT C2.9.22: Test mínimo para capturar errores JS tempranos
 * Verifica que el script se carga correctamente sin errores de parse/runtime
 */

const { test, expect } = require('@playwright/test');
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

test.describe('Smoke: Repository Boot', () => {
    test('Debe cargar sin errores JS tempranos', async ({ page }) => {
        // PASO 1: Instalar captura de errores ANTES de navegar
        const { installBrowserErrorCapture } = require('./helpers/e2eSeed');
        installBrowserErrorCapture(page, false);
        
        // Instalar handler de consola para capturar TODOS los logs (sin filtrar)
        const consoleMessages = [];
        page.on('console', (msg) => {
            const text = msg.text();
            const type = msg.type();
            consoleMessages.push({ type, text, time: new Date().toISOString() });
            // Loguear TODO en consola del runner
            console.log(`[CONSOLE ${type.toUpperCase()}]`, text);
        });
        
        // Instalar handler de pageerror
        const pageErrors = [];
        page.on('pageerror', (error) => {
            pageErrors.push({
                message: error.message,
                stack: error.stack,
                time: new Date().toISOString()
            });
            console.log('[PAGEERROR]', error.message);
            console.log('[PAGEERROR] Stack:', error.stack);
        });
        
        // PASO 2: Navegar a /repository
        await page.goto(`${BACKEND_URL}/repository`, { 
            waitUntil: 'domcontentloaded' 
        });
        
        // PASO 3: Esperar señales en orden
        // 1) document.readyState
        await page.waitForFunction(() => {
            return document.readyState === 'interactive' || document.readyState === 'complete';
        }, { timeout: 5000 });
        console.log('[SMOKE] document.readyState OK');
        
        // 2) window.__REPO_SCRIPT_LOADED__
        await page.waitForFunction(() => {
            return window.__REPO_SCRIPT_LOADED__ === true;
        }, { timeout: 10000 });
        console.log('[SMOKE] __REPO_SCRIPT_LOADED__ OK');
        
        // 3) app-ready (opcional)
        const hasAppReady = await page.evaluate(() => {
            return !!document.querySelector('[data-testid="app-ready"]') ||
                   !!document.getElementById('app-ready-marker') ||
                   window.__app_ready__ === true ||
                   (document.body && document.body.hasAttribute('data-testid') && 
                    document.body.getAttribute('data-testid') === 'app-ready');
        });
        console.log('[SMOKE] app-ready:', hasAppReady);
        
        // PASO 4: Dump de errores y estado
        const browserErrors = await page.evaluate(() => {
            return window.__E2E_BROWSER_ERRORS__ || [];
        });
        
        const pageState = await page.evaluate(() => {
            return {
                readyState: document.readyState,
                href: window.location.href,
                hash: window.location.hash,
                __REPO_SCRIPT_LOADED__: window.__REPO_SCRIPT_LOADED__,
                __REPO_BOOTSTRAP_DONE__: window.__REPO_BOOTSTRAP_DONE__,
                __app_ready__: window.__app_ready__,
                hasAppReadyEl: !!document.querySelector('[data-testid="app-ready"]') ||
                              !!document.getElementById('app-ready-marker') ||
                              (document.body && document.body.hasAttribute('data-testid') && 
                               document.body.getAttribute('data-testid') === 'app-ready')
            };
        });
        
        // PASO 5: Imprimir resultados
        console.log('\n========== BROWSER_ERRORS ==========');
        console.log(JSON.stringify(browserErrors, null, 2));
        console.log('\n========== PAGE_STATE ==========');
        console.log(JSON.stringify(pageState, null, 2));
        console.log('\n========== PAGEERRORS ==========');
        console.log(JSON.stringify(pageErrors, null, 2));
        console.log('\n========== CONSOLE MESSAGES (first 20) ==========');
        consoleMessages.slice(0, 20).forEach(msg => {
            console.log(`[${msg.type}] ${msg.text}`);
        });
        
        // PASO 6: Verificar que NO hay errores
        if (browserErrors.length > 0) {
            console.error('\n❌ ERRORES JS DETECTADOS:');
            browserErrors.forEach(err => {
                console.error(`  - ${err.type}: ${err.message}`);
                console.error(`    File: ${err.filename}:${err.lineno}:${err.colno}`);
                if (err.stack) {
                    console.error(`    Stack: ${err.stack}`);
                }
            });
        }
        
        if (pageErrors.length > 0) {
            console.error('\n❌ PAGEERRORS DETECTADOS:');
            pageErrors.forEach(err => {
                console.error(`  - ${err.message}`);
                if (err.stack) {
                    console.error(`    Stack: ${err.stack}`);
                }
            });
        }
        
        // El test FALLA si hay errores
        expect(browserErrors.length).toBe(0);
        expect(pageErrors.length).toBe(0);
        
        // Verificar que __REPO_SCRIPT_LOADED__ está presente
        expect(pageState.__REPO_SCRIPT_LOADED__).toBe(true);
    });
});
