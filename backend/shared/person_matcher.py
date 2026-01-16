"""
Funciones robustas para matching de personas en texto de eGestiona.

Soporta formatos como:
- "Verdés Ochoa, Oriol (38133024J)"
- "Oriol Verdés Ochoa"
- Comparación por DNI
- Normalización de acentos, espacios, puntuación
"""
from __future__ import annotations

import re
from typing import List, Optional

from backend.shared.people_v1 import PersonV1
from backend.shared.text_normalizer import normalize_text


def extract_dni_from_text(text: str) -> Optional[str]:
    """
    Extrae DNI/NIE/NIF de un texto que puede contener formato "(DNI)" o similar.
    Retorna el DNI sin espacios, en mayúsculas, o None si no se encuentra.
    """
    if not text:
        return None
    
    # Buscar patrón entre paréntesis: (38133024J), (37330395S), etc.
    match = re.search(r'\(([A-Z0-9]{8,9})\)', text.upper())
    if match:
        return match.group(1)
    
    # Buscar DNI sin paréntesis al final del texto
    match = re.search(r'\b([0-9]{8}[A-Z]|[XYZ][0-9]{7}[A-Z])\b', text.upper())
    if match:
        return match.group(1)
    
    return None


def build_person_match_tokens(person: PersonV1) -> List[str]:
    """
    Construye tokens de matching para una persona.
    
    Retorna lista de strings normalizados que pueden aparecer en el texto de eGestiona:
    - "nombre ap1 ap2"
    - "ap1 ap2 nombre"
    - "ap1 ap2, nombre"
    - Variantes con un solo apellido
    - DNI si existe
    """
    tokens = []
    
    full_name = person.full_name.strip()
    if not full_name:
        return tokens
    
    # Normalizar nombre completo
    name_normalized = normalize_text(full_name)
    if name_normalized:
        tokens.append(name_normalized)
    
    # Dividir nombre en partes
    parts = full_name.split()
    if len(parts) >= 2:
        # Asumir: primera parte es nombre, resto son apellidos
        nombre = parts[0]
        apellidos = parts[1:]
        
        # Token: "apellido1 apellido2 nombre"
        if len(apellidos) >= 2:
            ap1 = normalize_text(apellidos[0])
            ap2 = normalize_text(apellidos[1])
            nom = normalize_text(nombre)
            tokens.append(f"{ap1} {ap2} {nom}")
            tokens.append(f"{ap1} {ap2}, {nom}")  # Con coma
        elif len(apellidos) == 1:
            ap1 = normalize_text(apellidos[0])
            nom = normalize_text(nombre)
            tokens.append(f"{ap1} {nom}")
            tokens.append(f"{ap1}, {nom}")  # Con coma
        
        # Token: "nombre apellido1 apellido2"
        if len(apellidos) >= 2:
            nom = normalize_text(nombre)
            ap1 = normalize_text(apellidos[0])
            ap2 = normalize_text(apellidos[1])
            tokens.append(f"{nom} {ap1} {ap2}")
        elif len(apellidos) == 1:
            nom = normalize_text(nombre)
            ap1 = normalize_text(apellidos[0])
            tokens.append(f"{nom} {ap1}")
    
    # Añadir DNI si existe
    if person.tax_id:
        dni_clean = person.tax_id.strip().upper().replace(' ', '')
        if dni_clean:
            tokens.append(dni_clean)
    
    # Eliminar duplicados manteniendo orden
    seen = set()
    unique_tokens = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            unique_tokens.append(token)
    
    return unique_tokens


def match_person_in_element(person: PersonV1, element_text: str) -> bool:
    """
    Verifica si una persona coincide con el texto de la columna "Elemento" de eGestiona.
    
    Retorna True si:
    - El DNI coincide (preferente), o
    - Cualquiera de los tokens de nombre está contenido en el texto normalizado
    
    Args:
        person: Persona a buscar
        element_text: Texto de la columna "Elemento" (ej: "Verdés Ochoa, Oriol (38133024J)")
    
    Returns:
        True si hay match, False en caso contrario
    """
    if not element_text:
        return False
    
    # Normalizar texto del elemento
    element_normalized = normalize_text(element_text)
    
    # Extraer DNI del elemento
    element_dni = extract_dni_from_text(element_text)
    
    # Si hay DNI en la persona y en el elemento, comparar directamente
    if person.tax_id and element_dni:
        person_dni_clean = person.tax_id.strip().upper().replace(' ', '')
        if person_dni_clean == element_dni:
            return True
    
    # Construir tokens de matching de la persona
    person_tokens = build_person_match_tokens(person)
    
    # Verificar si algún token está contenido en el texto normalizado
    for token in person_tokens:
        if token and token in element_normalized:
            return True
    
    return False

