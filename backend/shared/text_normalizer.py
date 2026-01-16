"""
Normalización robusta de texto para matching y comparaciones.

Esta función debe usarse en TODAS las comparaciones de texto del sistema:
- Nombres de trabajadores
- DNI / NIF embebidos en texto
- Nombres de empresa PROPIA
- Nombres de empresa A COORDINAR (cliente)
- Plataformas
- Tipos de documento
- Aliases de plataforma
- Tokens de reglas
- Texto "Elemento" y "Tipo Documento" del grid CAE
- Filtros UI (buscadores en dropdowns)
- Cualquier campo textual usado en matching, filtrado o renderizado
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def normalize_text(text: Optional[str]) -> str:
    """
    Normalización robusta de texto para matching y comparaciones.
    
    Características:
    - Unicode NFKD normalization
    - Elimina diacríticos (acentos, tildes, diéresis, etc.)
    - Convierte "ñ" a "n" (NFKD normalmente lo cubre, pero aseguramos)
    - lower()
    - Elimina puntuación común (.,;:()[]{}"') convirtiéndola en espacios
    - Colapsa espacios múltiples
    - strip()
    
    Args:
        text: Texto a normalizar (puede ser None)
    
    Returns:
        Texto normalizado (string vacío si input es None o vacío)
    
    Ejemplos:
        normalize_text("Verdés Ochoa, Oriol") -> "verdes ochoa oriol"
        normalize_text("TEDELAB INGENIERÍA") -> "tedelab ingenieria"
        normalize_text("  F63161988  ") -> "f63161988"
        normalize_text("Emilio Roldán Molina") -> "emilio roldan molina"
        normalize_text("Niño") -> "nino"
    """
    if not text:
        return ""
    
    # Convertir a string si no lo es
    text_str = str(text)
    
    # Trim
    text_str = text_str.strip()
    
    if not text_str:
        return ""
    
    # Convertir a lowercase
    text_lower = text_str.lower()
    
    # Normalizar Unicode (NFKD) y eliminar diacríticos (tildes, diéresis, etc.)
    # NFKD descompone caracteres (ej: "é" -> "e" + "´", "ñ" -> "n" + "~")
    # Luego filtramos los caracteres de categoría "Mn" (Mark, Nonspacing) que son los diacríticos
    nfd = unicodedata.normalize('NFKD', text_lower)
    text_no_accents = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    
    # Asegurar que "ñ" se convierte a "n" (por si acaso NFKD no lo cubre completamente)
    text_no_accents = text_no_accents.replace('ñ', 'n').replace('Ñ', 'n')
    
    # Eliminar puntuación común convirtiéndola en espacios
    # Esto incluye: .,;:()[]{}"' y otros signos de puntuación
    punctuation_to_space = re.sub(r'[.,;:()\[\]{}"\']', ' ', text_no_accents)
    
    # Colapsar espacios múltiples a un solo espacio
    text_collapsed = re.sub(r'\s+', ' ', punctuation_to_space)
    
    # Trim final
    return text_collapsed.strip()


def normalize_text_robust(text: Optional[str]) -> str:
    """
    Normalización robusta de texto para matching y comparaciones.
    
    Características:
    - Case-insensitive (convierte a lowercase)
    - Accent-insensitive (elimina tildes, diéresis, etc.)
    - Normaliza espacios (colapsa múltiples espacios)
    - Elimina puntuación innecesaria (excepto alfanuméricos y espacios)
    - Trim (elimina espacios al inicio y final)
    
    Args:
        text: Texto a normalizar (puede ser None)
    
    Returns:
        Texto normalizado (string vacío si input es None o vacío)
    
    Ejemplos:
        normalize_text_robust("Verdés Ochoa, Oriol") -> "verdes ochoa oriol"
        normalize_text_robust("TEDELAB INGENIERÍA") -> "tedelab ingenieria"
        normalize_text_robust("  F63161988  ") -> "f63161988"
        normalize_text_robust("Emilio Roldán Molina") -> "emilio roldan molina"
    """
    if not text:
        return ""
    
    # Convertir a string si no lo es
    text_str = str(text)
    
    # Trim
    text_str = text_str.strip()
    
    if not text_str:
        return ""
    
    # Convertir a lowercase
    text_lower = text_str.lower()
    
    # Normalizar Unicode (NFKD) y eliminar diacríticos (tildes, diéresis, etc.)
    # NFKD descompone caracteres (ej: "é" -> "e" + "´")
    # Luego filtramos los caracteres de categoría "Mn" (Mark, Nonspacing) que son los diacríticos
    nfd = unicodedata.normalize('NFKD', text_lower)
    text_no_accents = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    
    # Colapsar espacios múltiples a un solo espacio
    text_collapsed = re.sub(r'\s+', ' ', text_no_accents)
    
    # Remover puntuación excepto alfanuméricos y espacios
    # Esto mantiene letras, números y espacios, pero elimina comas, puntos, paréntesis, etc.
    text_clean = re.sub(r'[^\w\s]', '', text_collapsed)
    
    # Trim final
    return text_clean.strip()


def normalize_company_name(company_text: str) -> str:
    """
    Normaliza nombre de empresa, eliminando códigos entre paréntesis.
    
    Ejemplo:
        normalize_company_name("TEDELAB INGENIERÍA (F63161988)") -> "tedelab ingenieria"
    
    Args:
        company_text: Texto de empresa que puede contener código entre paréntesis
    
    Returns:
        Nombre de empresa normalizado (sin código, sin tildes, lowercase)
    """
    if not company_text:
        return ""
    
    # Eliminar código entre paréntesis si existe
    text = company_text.strip()
    if " (" in text:
        text = text.split(" (", 1)[0].strip()
    
    # Aplicar normalización robusta
    return normalize_text(text)


def extract_company_code(company_text: str) -> Optional[str]:
    """
    Extrae código fiscal (tax_id) de un texto de empresa que puede contener formato "(CODIGO)".
    
    Ejemplo:
        extract_company_code("TEDELAB INGENIERÍA SCCL (F63161988)") -> "F63161988"
    
    Args:
        company_text: Texto de empresa que puede contener código entre paréntesis
    
    Returns:
        Código fiscal extraído (sin espacios, en mayúsculas) o None si no se encuentra
    """
    if not company_text:
        return None
    
    # Buscar patrón entre paréntesis: (F63161988), (B12345678), etc.
    match = re.search(r'\(([A-Z0-9]{8,9})\)', company_text.upper())
    if match:
        return match.group(1)
    
    return None


def normalize_for_matching(text1: Optional[str], text2: Optional[str]) -> tuple[str, str]:
    """
    Normaliza dos textos para comparación.
    
    Útil cuando se necesita comparar dos textos directamente.
    
    Args:
        text1: Primer texto
        text2: Segundo texto
    
    Returns:
        Tupla (text1_normalized, text2_normalized)
    """
    return normalize_text(text1), normalize_text(text2)


def normalize_for_match(text: Optional[str]) -> str:
    """
    Alias de normalize_text() por claridad semántica.
    
    Args:
        text: Texto a normalizar
    
    Returns:
        Texto normalizado
    """
    return normalize_text(text)


def contains_all_tokens(haystack: str, tokens: list[str]) -> bool:
    """
    Verifica si un texto normalizado contiene todos los tokens normalizados.
    
    Args:
        haystack: Texto donde buscar (se normaliza internamente)
        tokens: Lista de tokens a buscar (cada uno se normaliza internamente)
    
    Returns:
        True si todos los tokens están contenidos en haystack
    """
    if not tokens:
        return True
    
    haystack_norm = normalize_text(haystack)
    
    for token in tokens:
        if not token:
            continue
        token_norm = normalize_text(token)
        if token_norm not in haystack_norm:
            return False
    
    return True


def safe_join(*parts: Optional[str]) -> str:
    """
    Une partes no vacías con espacio.
    
    Args:
        *parts: Partes a unir (pueden ser None o vacías)
    
    Returns:
        String con partes unidas por espacio, sin espacios múltiples
    """
    non_empty = [str(p).strip() for p in parts if p and str(p).strip()]
    return ' '.join(non_empty)


def text_contains(normalized_text: str, normalized_search: str) -> bool:
    """
    Verifica si un texto normalizado contiene otro texto normalizado.
    
    Ambos textos deben estar normalizados con normalize_text().
    
    Args:
        normalized_text: Texto donde buscar (ya normalizado)
        normalized_search: Texto a buscar (ya normalizado)
    
    Returns:
        True si normalized_search está contenido en normalized_text
    """
    if not normalized_search:
        return True  # Si no hay búsqueda, siempre coincide
    
    return normalized_search in normalized_text

