"""
Helpers para cargar configuración y secrets de e-gestiona.

PASO 0: Reutilizar ConfigStoreV1 y SecretsStoreV1 existentes.
"""

from pathlib import Path
from typing import Dict, Optional

from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.secrets_store_v1 import SecretsStoreV1
from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.shared.platforms_v1 import PlatformV1, CoordinationV1
from backend.config import DATA_DIR


def get_platform_config(platform_id: str, base_dir: Optional[str | Path] = None) -> Optional[PlatformV1]:
    """
    Obtiene la configuración de una plataforma.
    
    Args:
        platform_id: ID de la plataforma (ej "egestiona")
        base_dir: Directorio base (default: DATA_DIR)
    
    Returns:
        PlatformV1 o None si no se encuentra
    """
    if base_dir is None:
        base_dir = DATA_DIR
    
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    platforms = store.load_platforms()
    
    # Buscar por key exacta
    plat = next((p for p in platforms.platforms if p.key == platform_id), None)
    if plat:
        return plat
    
    # Fallback: buscar por prefijo
    plat = next(
        (p for p in platforms.platforms if str(p.key or "").lower().startswith(str(platform_id).lower())),
        None
    )
    
    return plat


def get_coordination(platform_config: PlatformV1, label: str) -> Optional[CoordinationV1]:
    """
    Obtiene una coordination específica de una plataforma.
    
    Args:
        platform_config: Configuración de la plataforma
        label: Label de la coordination (ej "Aigües de Manresa" o "Aigues de Manresa")
    
    Returns:
        CoordinationV1 o None si no se encuentra
    """
    # Normalizar label: quitar acentos y convertir a lowercase para comparación
    def normalize_label(l: str) -> str:
        import unicodedata
        # Quitar acentos
        nfd = unicodedata.normalize('NFD', l)
        return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn').lower()
    
    label_normalized = normalize_label(label)
    
    # Buscar por label exacto primero
    coord = next((c for c in platform_config.coordinations if c.label == label), None)
    if coord:
        return coord
    
    # Fallback: buscar case-insensitive
    coord = next(
        (c for c in platform_config.coordinations if str(c.label or "").lower() == str(label).lower()),
        None
    )
    if coord:
        return coord
    
    # Fallback adicional: buscar normalizando acentos
    coord = next(
        (c for c in platform_config.coordinations if normalize_label(c.label or "") == label_normalized),
        None
    )
    
    return coord


def resolve_secret(password_ref: str, base_dir: Optional[str | Path] = None) -> Optional[str]:
    """
    Resuelve un secret desde el secrets store.
    
    IMPORTANTE: NUNCA loguear el valor del secret.
    
    Args:
        password_ref: Referencia al secret (ej "secret:aiguesdemanresa")
        base_dir: Directorio base (default: DATA_DIR)
    
    Returns:
        Valor del secret o None si no existe
    """
    if base_dir is None:
        base_dir = DATA_DIR
    
    base = ensure_data_layout(base_dir=base_dir)
    secrets_store = SecretsStoreV1(base_dir=base)
    return secrets_store.get_secret(password_ref)
