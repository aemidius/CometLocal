/**
 * Helpers reutilizables para tests E2E.
 * Proporciona funciones para seed de datos y navegación determinista.
 */

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

/**
 * SPRINT C2.5.2: Retry con backoff exponencial para operaciones de seed.
 * Reintenta hasta 6 veces con delays: 200ms, 400ms, 800ms, 1600ms, 3200ms, 6400ms
 * Solo reintenta para errores de red (ECONNRESET/ECONNREFUSED) o status >=500 o 409
 */
async function seedRequestWithRetry(request, url, maxRetries = 6) {
    const delays = [200, 400, 800, 1600, 3200, 6400];
    let lastError = null;
    
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            const response = await request.post(url);
            const status = response.status();
            
            // Si es éxito o error 4xx (excepto 409), no reintentar
            if (response.ok() || (status >= 400 && status < 500 && status !== 409)) {
                if (!response.ok()) {
                    const text = await response.text();
                    throw new Error(`SEED FAILED: returned ${status}: ${text}`);
                }
                return response;
            }
            
            // Si es 409 (seed busy) o >=500, reintentar
            if (status === 409 || status >= 500) {
                const text = await response.text();
                lastError = new Error(`SEED FAILED: returned ${status}: ${text}`);
                if (attempt < maxRetries - 1) {
                    const delay = delays[attempt] || delays[delays.length - 1];
                    console.log(`[SEED] Retry ${attempt + 1}/${maxRetries} after ${delay}ms (status ${status})`);
                    await new Promise(resolve => setTimeout(resolve, delay));
                    continue;
                }
                throw lastError;
            }
            
            return response;
        } catch (error) {
            lastError = error;
            const errorMessage = error.message || String(error);
            const isNetworkError = errorMessage.includes('ECONNRESET') || 
                                   errorMessage.includes('ECONNREFUSED') ||
                                   errorMessage.includes('connect') ||
                                   errorMessage.includes('read');
            
            // Solo reintentar errores de red
            if (isNetworkError && attempt < maxRetries - 1) {
                const delay = delays[attempt] || delays[delays.length - 1];
                console.log(`[SEED] Retry ${attempt + 1}/${maxRetries} after ${delay}ms (network error: ${errorMessage})`);
                await new Promise(resolve => setTimeout(resolve, delay));
                continue;
            }
            // Si no es error de red o es el último intento, lanzar error
            throw error;
        }
    }
    
    throw lastError || new Error('SEED FAILED: Max retries exceeded');
}

/**
 * Resetea datos E2E creados (docs, snapshots, jobs persistidos).
 * @param {import('@playwright/test').Page | {request: import('@playwright/test').APIRequestContext}} pageOrRequest - Page o objeto con request
 */
async function seedReset(pageOrRequest) {
    const request = pageOrRequest.request || pageOrRequest;
    const response = await seedRequestWithRetry(request, `${BACKEND_URL}/api/test/seed/reset`);
    const status = response.status();
    console.log(`[SEED] reset status: ${status}`);
    return await response.json();
}

/**
 * Crea un set mínimo determinista de repositorio:
 * - company_key/person_key (E2E)
 * - 2-3 types
 * - 3-5 docs con PDFs dummy
 * - asegurar que el calendario tiene al menos 2 pendientes "missing"
 * 
 * @param {import('@playwright/test').Page | {request: import('@playwright/test').APIRequestContext}} pageOrRequest - Page o objeto con request
 * @returns {Promise<{company_key: string, person_key: string, type_ids: string[], doc_ids: string[], period_keys: string[]}>}
 */
async function seedBasicRepository(pageOrRequest) {
    const request = pageOrRequest.request || pageOrRequest;
    const response = await seedRequestWithRetry(request, `${BACKEND_URL}/api/test/seed/basic_repository`);
    const status = response.status();
    const json = await response.json();
    console.log(`[SEED] basic_repository status: ${status}`, json);
    return json;
}

/**
 * Crea snapshot FAKE con 2 pending_items y devuelve snapshot_id.
 * 
 * @param {import('@playwright/test').Page | {request: import('@playwright/test').APIRequestContext}} pageOrRequest - Page o objeto con request
 * @returns {Promise<{snapshot_id: string, created_at: string, pending_items_count: number}>}
 */
async function seedBasicSnapshot(pageOrRequest) {
    const request = pageOrRequest.request || pageOrRequest;
    const response = await seedRequestWithRetry(request, `${BACKEND_URL}/api/test/seed/basic_cae_snapshot`);
    return await response.json();
}

/**
 * Crea tipos específicos para tests de upload con nombres exactos:
 * - "Recibo Autónomos" (type_id: E2E_AUTONOMOS_RECEIPT)
 * - TEST_RC_CERTIFICATE
 * - TEST_DATE_REQUIRED
 * También crea company_key="E2E_TEDELAB" y person_key="E2E_EMILIO".
 * 
 * @param {import('@playwright/test').Page | {request: import('@playwright/test').APIRequestContext}} pageOrRequest - Page o objeto con request
 * @returns {Promise<{company_key: string, person_key: string, type_ids: object, doc_ids: string[], message: string}>}
 */
async function seedUploadPack(pageOrRequest) {
    const request = pageOrRequest.request || pageOrRequest;
    const response = await seedRequestWithRetry(request, `${BACKEND_URL}/api/test/seed/upload_pack`);
    const status = response.status();
    const json = await response.json();
    console.log(`[SEED] upload_pack status: ${status}`, json);
    return json;
}

/**
 * SPRINT C2.9.20: Instala captura GLOBAL de errores del navegador.
 * Debe ejecutarse ANTES de cualquier page.goto() a /repository.
 * 
 * @param {import('@playwright/test').Page} page
 * @param {boolean} pageAlreadyLoaded - Si true, usa evaluate en lugar de addInitScript
 */
function installBrowserErrorCapture(page, pageAlreadyLoaded = false) {
    const errorCaptureScript = () => {
        if (!window.__E2E_BROWSER_ERRORS__) {
            window.__E2E_BROWSER_ERRORS__ = [];
        }
        
        // Capturar window.onerror (solo si no está ya instalado)
        if (!window.__E2E_ERROR_HANDLER_INSTALLED__) {
            const originalOnError = window.onerror;
            window.onerror = function(message, filename, lineno, colno, error) {
                if (window.__E2E_BROWSER_ERRORS__) {
                    window.__E2E_BROWSER_ERRORS__.push({
                        type: 'error',
                        message: message || 'Unknown error',
                        filename: filename || 'unknown',
                        lineno: lineno || 0,
                        colno: colno || 0,
                        stack: error?.stack || '',
                        time: new Date().toISOString()
                    });
                }
                // Llamar al handler original si existe
                if (originalOnError) {
                    return originalOnError.apply(this, arguments);
                }
            };
            
            // Capturar unhandledrejection
            window.addEventListener('unhandledrejection', function(event) {
                if (window.__E2E_BROWSER_ERRORS__) {
                    window.__E2E_BROWSER_ERRORS__.push({
                        type: 'unhandledrejection',
                        message: event.reason?.message || String(event.reason) || 'Unhandled promise rejection',
                        filename: 'promise',
                        lineno: 0,
                        colno: 0,
                        stack: event.reason?.stack || '',
                        time: new Date().toISOString()
                    });
                }
            });
            
            window.__E2E_ERROR_HANDLER_INSTALLED__ = true;
        }
    };
    
    if (pageAlreadyLoaded) {
        // Si la página ya está cargada, usar evaluate
        page.evaluate(errorCaptureScript).catch(() => {
            // Ignorar si falla (página podría no estar lista)
        });
    } else {
        // Si la página aún no está cargada, usar addInitScript
        page.addInitScript(errorCaptureScript);
    }
    
    // Capturar pageerror (errores de parse/runtime que no se capturan con onerror)
    // Solo instalar una vez
    if (!page.__E2E_PAGEERROR_HANDLER_INSTALLED__) {
        page.on('pageerror', (error) => {
            console.log('[BROWSER_ERROR] pageerror:', error.message);
            console.log('[BROWSER_ERROR] stack:', error.stack);
        });
        page.__E2E_PAGEERROR_HANDLER_INSTALLED__ = true;
    }
    
    // SPRINT C2.9.22: Instalar handler de consola para capturar TODOS los logs (sin filtrar)
    // Solo instalar una vez
    if (!page.__E2E_CONSOLE_HANDLER_INSTALLED__) {
        page.on('console', (msg) => {
            const text = msg.text();
            const type = msg.type();
            // Loguear TODO en consola del runner (no filtrar por prefijos)
            console.log(`[CONSOLE ${type.toUpperCase()}]`, text);
        });
        page.__E2E_CONSOLE_HANDLER_INSTALLED__ = true;
    }
}

/**
 * Navega a una ruta con hash y espera a que esté lista.
 * SPRINT C2.9.20: Espera app-ready + __REPO_SCRIPT_LOADED__ (barrera ULTRA TEMPRANA).
 * NO espera __REPO_API_READY__, vistas, calendario, fetches, markers.
 * 
 * @param {import('@playwright/test').Page} page
 * @param {string} hash - Hash sin # (ej: 'calendario', 'buscar', 'subir')
 * @param {number} timeout - Timeout en ms (default: 15000)
 */
async function gotoHash(page, hash, timeout = 15000) {
    const fullHash = hash.startsWith('#') ? hash : `#${hash}`;
    
    // Navegar a /repository si no estamos ya ahí
    const currentUrl = page.url();
    const pageAlreadyLoaded = currentUrl.includes('/repository');
    
    // SPRINT C2.9.20: Instalar captura de errores ANTES de navegar (o después si ya está cargada)
    if (!pageAlreadyLoaded) {
        installBrowserErrorCapture(page, false);
        await page.goto(`${BACKEND_URL}/repository`, { waitUntil: 'domcontentloaded' });
    } else {
        // Si ya está cargada, instalar captura con evaluate
        installBrowserErrorCapture(page, true);
    }
    
    try {
        // SPRINT C2.9.20: Esperar app-ready + __REPO_SCRIPT_LOADED__ (barrera ULTRA TEMPRANA)
        // NO esperar __REPO_API_READY__, vistas, calendario, fetches, markers
        await page.waitForFunction(() => {
            const appReady = !!document.querySelector('[data-testid="app-ready"]') || 
                            !!document.getElementById('app-ready-marker') ||
                            window.__app_ready__ === true ||
                            (document.body && document.body.hasAttribute('data-testid') && document.body.getAttribute('data-testid') === 'app-ready');
            const scriptLoaded = window.__REPO_SCRIPT_LOADED__ === true;
            return appReady && scriptLoaded;
        }, { timeout });
        
        // Cambiar hash y salir
        await page.evaluate((hash) => {
            window.location.hash = hash;
        }, fullHash);
    } catch (error) {
        // SPRINT C2.9.20: Si falla por timeout, capturar errores y estado AUTOMÁTICAMENTE
        console.log('[BROWSER_ERRORS] Capturando errores del navegador después de timeout...');
        
        try {
            const browserErrors = await page.evaluate(() => {
                return window.__E2E_BROWSER_ERRORS__ || [];
            });
            console.log('[BROWSER_ERRORS]', JSON.stringify(browserErrors, null, 2));
        } catch (e) {
            console.log('[BROWSER_ERRORS] No se pudieron capturar errores (página cerrada):', e.message);
        }
        
        try {
            const pageState = await page.evaluate(() => {
                return {
                    readyState: document.readyState,
                    href: window.location.href,
                    hash: window.location.hash,
                    __REPO_SCRIPT_LOADED__: window.__REPO_SCRIPT_LOADED__,
                    __REPO_API_READY__: window.__REPO_API_READY__
                };
            });
            console.log('[PAGE_STATE]', JSON.stringify(pageState, null, 2));
        } catch (e) {
            console.log('[PAGE_STATE] No se pudo capturar estado (página cerrada):', e.message);
        }
        
        // Re-lanzar el error original
        throw error;
    }
}

/**
 * Espera a que un elemento con data-testid esté visible.
 * 
 * @param {import('@playwright/test').Page} page
 * @param {string} testId - Valor de data-testid
 * @param {number} timeout - Timeout en ms (default: 10000)
 */
async function waitForTestId(page, testId, timeout = 10000) {
    await page.waitForSelector(`[data-testid="${testId}"]`, { timeout, state: 'visible' });
}

/**
 * Espera a que un elemento con data-testid esté attached (no necesariamente visible).
 * 
 * @param {import('@playwright/test').Page} page
 * @param {string} testId - Valor de data-testid
 * @param {number} timeout - Timeout en ms (default: 10000)
 */
async function waitForTestIdAttached(page, testId, timeout = 10000) {
    await page.waitForSelector(`[data-testid="${testId}"]`, { timeout, state: 'attached' });
}

module.exports = {
    seedUploadPack,
    seedReset,
    seedBasicRepository,
    seedBasicSnapshot,
    installBrowserErrorCapture,
    gotoHash,
    waitForTestId,
    waitForTestIdAttached,
    BACKEND_URL,
};

