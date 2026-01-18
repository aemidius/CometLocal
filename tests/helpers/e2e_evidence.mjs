/**
 * SPRINT C2.28: Helper para guardar evidencias post-fallo en tests E2E.
 * 
 * Guarda:
 * - screenshot final
 * - console_log.txt
 * - last_network.json
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Almacenamiento global para console logs y network requests
const evidenceStore = new Map();

/**
 * Inicializa captura de evidencias para un test.
 * Debe llamarse en beforeEach.
 * 
 * @param {string} testId - ID único del test
 * @param {import('@playwright/test').Page} page - Página de Playwright
 */
export function initEvidenceCapture(testId, page) {
  const consoleMessages = [];
  const networkRequests = [];

  // Capturar console logs
  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    const location = msg.location();
    consoleMessages.push({
      type,
      text,
      location: location ? `${location.url}:${location.lineNumber}` : null,
      timestamp: new Date().toISOString()
    });
  });

  // Capturar network requests
  page.on('request', request => {
    networkRequests.push({
      method: request.method(),
      url: request.url(),
      headers: Object.fromEntries(Object.entries(request.headers())),
      postData: request.postData(),
      timestamp: new Date().toISOString()
    });
  });

  page.on('response', response => {
    const request = response.request();
    const url = request.url();
    const method = request.method();
    
    // Buscar request existente
    const existing = networkRequests.find(r => r.url === url && r.method === method);
    if (existing) {
      existing.status = response.status();
      existing.statusText = response.statusText();
      existing.responseHeaders = Object.fromEntries(Object.entries(response.headers()));
    }
  });

  evidenceStore.set(testId, { consoleMessages, networkRequests });
}

/**
 * Guarda evidencias cuando un test falla.
 * 
 * @param {import('@playwright/test').TestInfo} testInfo - Información del test
 * @param {import('@playwright/test').Page} page - Página de Playwright
 */
export async function saveFailureEvidence(testInfo, page) {
  if (testInfo.status !== 'failed') {
    // Limpiar store si el test pasó
    const testId = `${testInfo.file}_${testInfo.title}`;
    evidenceStore.delete(testId);
    return;
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const specName = path.basename(testInfo.file, '.spec.js');
  const testName = testInfo.title.replace(/[^a-zA-Z0-9]/g, '_');
  const evidenceDir = path.join(
    process.cwd(),
    'docs',
    'evidence',
    'e2e_failures',
    specName,
    `${testName}_${timestamp}`
  );

  // Crear directorio de evidencias
  if (!fs.existsSync(evidenceDir)) {
    fs.mkdirSync(evidenceDir, { recursive: true });
  }

  try {
    // 1) Screenshot final
    const screenshotPath = path.join(evidenceDir, 'screenshot_final.png');
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {
      // Si falla el screenshot, continuar
    });

    // 2) Console logs (desde store)
    const testId = `${testInfo.file}_${testInfo.title}`;
    const stored = evidenceStore.get(testId);
    const consoleMessages = stored?.consoleMessages || [];

    const consoleLogPath = path.join(evidenceDir, 'console_log.txt');
    const consoleLogContent = consoleMessages.length > 0
      ? consoleMessages
          .map(msg => `[${msg.timestamp}] [${msg.type}] ${msg.text}${msg.location ? ` (${msg.location})` : ''}`)
          .join('\n')
      : 'No console messages captured';
    fs.writeFileSync(consoleLogPath, consoleLogContent);

    // 3) Network requests (desde store, últimos 50)
    const networkRequests = stored?.networkRequests || [];
    const lastNetwork = networkRequests.slice(-50);
    const networkPath = path.join(evidenceDir, 'last_network.json');
    fs.writeFileSync(networkPath, JSON.stringify(lastNetwork, null, 2));

    // 4) Información del test
    const testInfoPath = path.join(evidenceDir, 'test_info.json');
    fs.writeFileSync(testInfoPath, JSON.stringify({
      testTitle: testInfo.title,
      testFile: testInfo.file,
      status: testInfo.status,
      duration: testInfo.duration,
      error: testInfo.error ? {
        message: testInfo.error.message,
        stack: testInfo.error.stack
      } : null,
      timestamp: new Date().toISOString()
    }, null, 2));

    // Limpiar store
    evidenceStore.delete(testId);

  } catch (error) {
    // Si falla guardar evidencias, al menos loguear
    console.error('[E2E Evidence] Error saving evidence:', error);
  }
}
