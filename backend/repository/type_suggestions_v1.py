"""
SPRINT C2.36: Type Suggestions Engine (read-only).

Sugerencias deterministas de tipos existentes para un pending item,
con scoring explicable (sin ML opaco).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Tuple
from datetime import date

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.document_matcher_v1 import DocumentMatcherV1, PendingItemV1
from backend.shared.document_repository_v1 import DocumentTypeV1
from backend.repository.text_utils import normalize_whitespace
from backend.shared.text_normalizer import normalize_text
from backend.config import DATA_DIR


class TypeSuggestionV1:
    """Sugerencia de tipo con score y razones."""
    
    def __init__(
        self,
        type_id: str,
        type_name: str,
        score: float,
        reasons: List[str]
    ):
        self.type_id = type_id
        self.type_name = type_name
        self.score = score
        self.reasons = reasons
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type_id": self.type_id,
            "type_name": self.type_name,
            "score": self.score,
            "reasons": self.reasons
        }


def suggest_types(
    pending: PendingItemV1,
    context: Dict[str, Any],
    limit: int = 3,
    base_dir: str | None = None
) -> List[TypeSuggestionV1]:
    """
    SPRINT C2.36: Sugiere tipos existentes para un pending item.
    
    Scoring determinista (sin ML):
    - +0.4 si nombre/alias coincide (normalizado)
    - +0.3 si scope coincide (company/worker)
    - +0.2 si plataforma coincide
    - +0.1 si período/validez compatible
    
    Args:
        pending: Item pendiente
        context: Contexto con company_key, person_key, platform_key, etc.
        limit: Número máximo de sugerencias (default: 3)
        base_dir: Directorio base (default: DATA_DIR)
    
    Returns:
        Lista de TypeSuggestionV1 ordenada por score descendente
    """
    if base_dir is None:
        base_dir = DATA_DIR
    
    store = DocumentRepositoryStoreV1(base_dir=base_dir)
    matcher = DocumentMatcherV1(store, base_dir=base_dir)
    
    # Obtener todos los tipos activos
    all_types = store.list_types(include_inactive=False)
    
    # Obtener contexto
    company_key = context.get("company_key") or context.get("own_company_key")
    person_key = context.get("person_key")
    platform_key = context.get("platform_key", "egestiona")
    
    # Normalizar texto del pending para matching
    pending_text = pending.get_base_text()
    pending_normalized = normalize_text(pending_text)
    
    suggestions: List[Tuple[DocumentTypeV1, float, List[str]]] = []
    
    for doc_type in all_types:
        if not doc_type.active:
            continue
        
        score = 0.0
        reasons: List[str] = []
        
        # 1. Match por nombre/alias (peso: 0.4)
        type_name_normalized = normalize_text(doc_type.name)
        if pending_normalized in type_name_normalized or type_name_normalized in pending_normalized:
            score += 0.4
            reasons.append(f"Nombre coincide: '{doc_type.name}'")
        
        # Match por aliases
        for alias in doc_type.platform_aliases:
            alias_normalized = normalize_text(alias)
            if alias_normalized in pending_normalized or pending_normalized in alias_normalized:
                score += 0.4
                reasons.append(f"Alias coincide: '{alias}'")
                break  # Solo contar una vez
        
        # 2. Match por scope (peso: 0.3)
        if doc_type.scope.value == "worker" and person_key:
            score += 0.3
            reasons.append("Scope coincide (worker)")
        elif doc_type.scope.value == "company" and company_key:
            score += 0.3
            reasons.append("Scope coincide (company)")
        
        # 3. Match por plataforma (peso: 0.2)
        # Verificar si el tipo tiene aliases para esta plataforma
        if doc_type.platform_aliases:
            # Asumimos que si tiene aliases, es compatible con la plataforma
            score += 0.2
            reasons.append(f"Plataforma compatible ({platform_key})")
        
        # 4. Match por período/validez (peso: 0.1)
        if pending.fecha_inicio and pending.fecha_fin:
            # Verificar si el tipo tiene validez periódica compatible
            if doc_type.validity_policy.mode.value in ("monthly", "annual"):
                score += 0.1
                reasons.append("Validez periódica compatible")
        
        # Solo añadir si tiene score > 0
        if score > 0.0:
            suggestions.append((doc_type, score, reasons))
    
    # Ordenar por score descendente
    suggestions.sort(key=lambda x: x[1], reverse=True)
    
    # Limitar y convertir a TypeSuggestionV1
    result = []
    for doc_type, score, reasons in suggestions[:limit]:
        result.append(TypeSuggestionV1(
            type_id=doc_type.type_id,
            type_name=doc_type.name,
            score=round(score, 2),
            reasons=reasons
        ))
    
    return result
