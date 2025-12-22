import os

# Defaults apuntando a LM Studio local
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://127.0.0.1:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")  # LM Studio ignora la key
# El usuario debe sobreescribir LLM_MODEL con el Model ID real de LM Studio
LLM_MODEL = os.getenv("LLM_MODEL", "local-model")

# Default search engine preferences for the planner.
# These are intended to be overridden in the future from a UI or a config file.
DEFAULT_SEARCH_ENGINE = "duckduckgo"  # possible future values: "duckduckgo", "google"
DEFAULT_SEARCH_BASE_URL = "https://duckduckgo.com"
DEFAULT_IMAGE_SEARCH_URL_TEMPLATE = (
    "https://duckduckgo.com/?q={query}&ia=images&iax=images"
)

# v2.1.0: Configuración para plataformas CAE
DEFAULT_CAE_BASE_URL = os.getenv("CAE_BASE_URL", "https://example-cae.local")

# v2.2.0: Configuración para repositorio de documentos
DOCUMENT_REPOSITORY_BASE_DIR = os.getenv("CAE_DOCS_BASE_DIR", os.path.join(os.path.expanduser("~"), "CAE_Documents"))

# v3.0.0: Configuración para ejecución batch
ENABLE_BATCH_PERSISTENCE = os.getenv("ENABLE_BATCH_PERSISTENCE", "true").lower() == "true"
# H7.8: unificar artefactos locales bajo data/
BATCH_RUNS_DIR = os.getenv("BATCH_RUNS_DIR", "data/runs")

# v3.3.0: Configuración para OCR/visión
VISION_OCR_ENABLED = os.getenv("VISION_OCR_ENABLED", "true").lower() == "true"
VISION_OCR_PROVIDER = os.getenv("VISION_OCR_PROVIDER", "lmstudio")

# v3.9.0: Configuración para memoria persistente
MEMORY_BASE_DIR = os.getenv("MEMORY_BASE_DIR", "memory")

# v5.2.0: Configuración de memoria visual
VISUAL_MEMORY_BASE_DIR = os.getenv("VISUAL_MEMORY_BASE_DIR", "memory/visual")
VISUAL_MEMORY_ENABLED = bool(int(os.getenv("VISUAL_MEMORY_ENABLED", "1")))

# v4.9.0: URLs por defecto para portales
DEFAULT_PORTAL_A_URL = os.getenv("DEFAULT_PORTAL_A_URL", "http://127.0.0.1:8000/simulation/portal_a/login.html")
DEFAULT_PORTAL_B_URL = os.getenv("DEFAULT_PORTAL_B_URL", "http://127.0.0.1:8000/simulation/portal_b/login.html")

