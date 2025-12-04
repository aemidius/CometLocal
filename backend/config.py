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

