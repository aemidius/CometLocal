const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { seedReset, seedBasicRepository, gotoHash } = require('./helpers/e2eSeed');

test.describe('Repository Settings Configuration', () => {
    let seedData;
    
    test.beforeAll(async ({ request }) => {
        // Reset y seed básico usando request (no page)
        await seedReset({ request });
        seedData = await seedBasicRepository({ request });
    });
    
    test.beforeEach(async ({ page }) => {
        // SPRINT B2: Navigate usando helper (sin hash para inicio, esperar app-ready)
        await page.goto('http://127.0.0.1:8000/repository');
        await page.waitForSelector('[data-testid="app-ready"]', { timeout: 10000 });
    });

    test('A) API: GET settings devuelve repository_root_dir no vacío', async ({ request }) => {
        const response = await request.get('http://127.0.0.1:8000/api/repository/settings');
        expect(response.ok()).toBeTruthy();
        
        const settings = await response.json();
        expect(settings).toHaveProperty('repository_root_dir');
        expect(settings.repository_root_dir).toBeTruthy();
        expect(settings.repository_root_dir.length).toBeGreaterThan(0);
        
        console.log('Current repository_root_dir:', settings.repository_root_dir);
    });

    test('A) API: PUT settings con ruta temporal crea directorio', async ({ request }) => {
        const testDir = path.join(__dirname, '..', 'data', 'repository_test_api');
        const testPath = path.resolve(testDir).replace(/\\/g, '\\\\');
        
        // Limpiar si existe
        if (fs.existsSync(testDir)) {
            fs.rmSync(testDir, { recursive: true, force: true });
        }
        
        const response = await request.put('http://127.0.0.1:8000/api/repository/settings', {
            data: {
                repository_root_dir: testPath
            }
        });
        
        expect(response.ok()).toBeTruthy();
        
        const settings = await response.json();
        expect(settings.repository_root_dir).toBeTruthy();
        
        // Verificar que el directorio se creó
        const resolvedPath = path.resolve(settings.repository_root_dir);
        expect(fs.existsSync(resolvedPath)).toBeTruthy();
        
        // Verificar que es escribible
        const testFile = path.join(resolvedPath, '.write_test');
        fs.writeFileSync(testFile, 'test');
        expect(fs.existsSync(testFile)).toBeTruthy();
        fs.unlinkSync(testFile);
        
        console.log('Test directory created and writable:', resolvedPath);
        
        // Restaurar ruta original
        const originalResponse = await request.get('http://127.0.0.1:8000/api/repository/settings');
        const originalSettings = await originalResponse.json();
        const defaultPath = path.join(__dirname, '..', 'data', 'repository');
        await request.put('http://127.0.0.1:8000/api/repository/settings', {
            data: {
                repository_root_dir: path.resolve(defaultPath)
            }
        });
    });

    test('B) UI: Cambiar ruta desde Configuración', async ({ page }) => {
        // SPRINT C2.1: Esperar señal de vista y UI lista usando gotoHash
        await gotoHash(page, 'configuracion');
        await page.waitForSelector('[data-testid="settings-ui-ready"]', { timeout: 15000 });
        await page.waitForSelector('#config-repository-root', { timeout: 10000 });
        
        // Obtener ruta actual
        const currentPath = await page.locator('#config-repository-root').inputValue();
        console.log('Current path:', currentPath);
        
        // Cambiar a ruta de prueba
        const testDir = path.join(__dirname, '..', 'data', 'repository_test_ui');
        const testPath = path.resolve(testDir);
        
        await page.fill('#config-repository-root', testPath);
        
        // Probar ruta
        await page.click('button:has-text("Probar ruta")');
        // SPRINT C2.1: Esperar a que el mensaje cambie de "Probando..." a "válida"
        const testMessage = page.locator('#config-message');
        await expect(testMessage).toBeVisible();
        await expect(testMessage).toContainText('válida', { timeout: 10000 });
        const testText = await testMessage.textContent();
        expect(testText).toContain('válida');
        
        // Guardar
        await page.click('button:has-text("Guardar")');
        // SPRINT C2.1: Esperar a que el mensaje cambie de "Guardando..." a "guardada"
        const saveMessage = page.locator('#config-message');
        await expect(saveMessage).toBeVisible();
        // Esperar a que el mensaje contenga "guardada" (puede tardar un momento)
        await expect(saveMessage).toContainText('guardada', { timeout: 10000 });
        const saveText = await saveMessage.textContent();
        expect(saveText).toContain('guardada');
        
        // Verificar que el directorio se creó
        expect(fs.existsSync(testPath)).toBeTruthy();
        
        console.log('UI test: Directory created at:', testPath);
    });

    test('C) Upload usando ruta cambiada', async ({ page }) => {
        const evidenceDir = path.join(__dirname, '..', 'docs', 'evidence', 'repo_settings');
        if (!fs.existsSync(evidenceDir)) {
            fs.mkdirSync(evidenceDir, { recursive: true });
        }
        
        // 1. Cambiar ruta a una de prueba
        // SPRINT C2.1: Esperar señal de vista y UI lista usando gotoHash
        await gotoHash(page, 'configuracion');
        await page.waitForSelector('[data-testid="settings-ui-ready"]', { timeout: 15000 });
        await page.waitForSelector('#config-repository-root', { timeout: 10000 });
        
        const testDir = path.join(__dirname, '..', 'data', 'repository_test_upload');
        const testPath = path.resolve(testDir);
        
        await page.fill('#config-repository-root', testPath);
        await page.click('button:has-text("Guardar")');
        await page.waitForTimeout(2000);
        
        // Captura después de cambiar ruta
        await page.screenshot({ path: path.join(evidenceDir, '01_settings_changed.png'), fullPage: true });
        
        // 2. Ir a Subir documentos usando helper
        await gotoHash(page, 'subir');
        
        // 3. Esperar un momento para que el servidor recargue la configuración
        await page.waitForTimeout(2000);
        
        // 3. Subir un PDF de prueba
        const testPdfPath = path.join(__dirname, '..', 'data', 'AEAT-16-oct-2025.pdf');
        if (!fs.existsSync(testPdfPath)) {
            test.skip('PDF de prueba no encontrado');
            return;
        }
        
        const fileInput = page.locator('[data-testid="upload-input"]');
        await fileInput.setInputFiles(testPdfPath);
        
        await page.waitForSelector('.file-card:has(select.repo-upload-type-select)', { timeout: 10000 });
        // SPRINT B2: Esperar usando expect en lugar de waitForTimeout
        
        // Seleccionar tipo
        const select = page.locator('select.repo-upload-type-select').first();
        const options = await select.locator('option').all();
        if (options.length > 1) {
            await select.selectOption({ index: 1 });
            // SPRINT B2: Esperar usando expect en lugar de waitForTimeout
        }
        
        // Captura antes de subir
        await page.screenshot({ path: path.join(evidenceDir, '02_before_upload.png'), fullPage: true });
        
        // Subir
        const submitButton = page.locator('button:has-text("Subir")').first();
        if (await submitButton.isVisible()) {
            await submitButton.click();
            await page.waitForTimeout(5000); // Esperar más tiempo para que se procese
        }
        
        // Captura después de subir
        await page.screenshot({ path: path.join(evidenceDir, '03_after_upload.png'), fullPage: true });
        
        // 4. Verificar que el archivo se guardó en la nueva ruta
        const docsDir = path.join(testPath, 'docs');
        const metaDir = path.join(testPath, 'meta');
        
        // Esperar un momento más para que el archivo se escriba
        await page.waitForTimeout(2000);
        
        expect(fs.existsSync(docsDir)).toBeTruthy();
        expect(fs.existsSync(metaDir)).toBeTruthy();
        
        // Buscar PDFs en la nueva ruta
        const pdfFiles = fs.existsSync(docsDir) ? fs.readdirSync(docsDir).filter(f => f.endsWith('.pdf')) : [];
        const jsonFiles = fs.existsSync(metaDir) ? fs.readdirSync(metaDir).filter(f => f.endsWith('.json')) : [];
        
        console.log('Upload test: Checking directories:', { docsDir, metaDir, docsExists: fs.existsSync(docsDir), metaExists: fs.existsSync(metaDir) });
        console.log('Upload test: PDFs found:', pdfFiles);
        console.log('Upload test: JSONs found:', jsonFiles);
        
        // Si no hay archivos, verificar la ruta original también (por si el servidor no recargó)
        if (pdfFiles.length === 0) {
            const defaultDocsDir = path.join(__dirname, '..', 'data', 'repository', 'docs');
            const defaultPdfFiles = fs.existsSync(defaultDocsDir) ? fs.readdirSync(defaultDocsDir).filter(f => f.endsWith('.pdf')) : [];
            console.log('Upload test: PDFs in default location:', defaultPdfFiles);
        }
        
        expect(pdfFiles.length).toBeGreaterThan(0);
        expect(jsonFiles.length).toBeGreaterThan(0);
        
        console.log('Upload test: PDFs found in new path:', pdfFiles);
        console.log('Upload test: JSONs found in new path:', jsonFiles);
        
        // Leer el último JSON para obtener doc_id
        if (jsonFiles.length > 0) {
            const lastJson = jsonFiles[jsonFiles.length - 1];
            const jsonPath = path.join(metaDir, lastJson);
            const docData = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));
            const docId = docData.doc_id;
            
            // Verificar que el PDF existe
            const pdfPath = path.join(docsDir, `${docId}.pdf`);
            expect(fs.existsSync(pdfPath)).toBeTruthy();
            
            console.log('Upload test: Document uploaded to:', pdfPath);
            
            // Guardar evidencia
            const report = {
                test_path: testPath,
                doc_id: docId,
                pdf_path: pdfPath,
                json_path: jsonPath,
                pdf_exists: fs.existsSync(pdfPath),
                timestamp: new Date().toISOString()
            };
            
            fs.writeFileSync(
                path.join(evidenceDir, 'report.json'),
                JSON.stringify(report, null, 2)
            );
        }
        
        // 5. Restaurar ruta original usando helper
        await gotoHash(page, 'configuracion');
        await page.waitForSelector('#config-repository-root', { timeout: 10000 });
        
        const defaultPath = path.join(__dirname, '..', 'data', 'repository');
        await page.fill('#config-repository-root', path.resolve(defaultPath));
        await page.click('button:has-text("Guardar")');
        // SPRINT B2: Esperar usando expect en lugar de waitForTimeout
    });
});

