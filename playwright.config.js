const path = require('path');
const fs = require('fs');

// Determinar el comando de Python a usar
function getPythonCommand() {
  const venvPythonWin = path.join(__dirname, '.venv', 'Scripts', 'python.exe');
  const venvPythonUnix = path.join(__dirname, '.venv', 'bin', 'python');
  
  if (process.platform === 'win32') {
    // Windows: intentar .venv\Scripts\python.exe primero
    if (fs.existsSync(venvPythonWin)) {
      return `"${venvPythonWin}" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`;
    }
    // Fallback: usar python del PATH (asumiendo venv activada o python global)
    return 'python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000';
  } else {
    // Unix/Linux/Mac: intentar .venv/bin/python primero
    if (fs.existsSync(venvPythonUnix)) {
      return `"${venvPythonUnix}" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`;
    }
    // Fallback: usar python3 o python del PATH
    return 'python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000';
  }
}

// SPRINT C2.28: Configuración para guardar evidencias post-fallo
// (path y fs ya están declarados arriba)

module.exports = {
  testDir: './tests',
  timeout: 30000,
  use: {
    baseURL: 'http://127.0.0.1:8000', // Fijado: siempre usar este baseURL
    headless: false,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure', // SPRINT C2.28: Incluir trace para debugging
  },
  // SPRINT C2.28: El helper de evidencias se inicializa en cada test
  // No se necesita globalSetup ya que el directorio se crea automáticamente
  webServer: {
    // SPRINT C2.9.18: Permitir 2 ejecuciones seguidas sin "port already used"
    reuseExistingServer: true,
    command: getPythonCommand(),
    url: 'http://127.0.0.1:8000/api/health',
    timeout: 120000,
    cwd: __dirname,
    env: {
      // Asegurar que se use el entorno correcto
      PYTHONUNBUFFERED: '1',
      E2E_SEED_ENABLED: '1',  // Habilitar seed para tests E2E
      CAE_COORDINATION_MODE: 'FAKE',  // Modo FAKE para coordinación en E2E
      CAE_FAKE_FAIL_AFTER_ITEM: '1',  // v1.9.1: Forzar fallo FAKE después del primer item para tests E2E
      CAE_EXECUTOR_MODE: 'FAKE',  // v1.9.1: Asegurar modo FAKE para tests E2E
      // SPRINT C2.10.2: Aislar datos E2E en directorio separado
      REPOSITORY_DATA_DIR: 'data/repository_e2e',
      // SPRINT C2.36.1: Guardrail anti-contaminación - forzar entorno test para E2E
      ENVIRONMENT: 'test',
    },
    stdout: 'pipe',
    stderr: 'pipe',
  },
};











