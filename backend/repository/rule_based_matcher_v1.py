from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from backend.repository.submission_rules_store_v1 import SubmissionRulesStoreV1
from backend.shared.document_repository_v1 import SubmissionRuleV1, RuleScopeV1
from backend.shared.text_normalizer import normalize_text

if TYPE_CHECKING:
    from backend.repository.document_matcher_v1 import PendingItemV1


class RuleBasedMatcherV1:
    """
    Matcher basado en reglas de envío.
    Aplica reglas primero (si platform/coord match) y fallback a aliases si no hay match.
    """
    
    def __init__(self, rules_store: SubmissionRulesStoreV1):
        self.rules_store = rules_store
    
    def match_pending_item(
        self,
        pending: "PendingItemV1",
        platform_key: str,
        coord_label: Optional[str] = None,
        empresa_text: Optional[str] = None
    ) -> Optional[Tuple[SubmissionRuleV1, float, List[str]]]:
        """
        Intenta hacer matching de un pending item con reglas.
        
        Retorna:
        - (rule, confidence, reasons) si hay match
        - None si no hay match
        
        Reglas:
        - rule.enabled debe ser True
        - rule.platform_key debe coincidir con platform_key
        - rule.coord_label debe coincidir con coord_label (si ambos están definidos)
        - TODOS los tokens de pending_text_contains deben aparecer en el texto del pendiente
        - Si empresa_contains está definido, al menos uno debe aparecer en empresa_text
        """
        base_text = pending.get_base_text()
        base_normalized = normalize_text(base_text)
        empresa_normalized = normalize_text(empresa_text or "")
        
        # Cargar todas las reglas habilitadas
        all_rules = self.rules_store.list_rules(include_disabled=False)
        
        # Primero buscar reglas COORD exactas, luego GLOBAL (herencia)
        coord_rules = []
        global_rules = []
        
        for rule in all_rules:
            # Verificar platform_key
            if rule.platform_key != platform_key:
                continue
            
            # Separar por scope
            if rule.scope == RuleScopeV1.COORD:
                # Verificar coord_label
                if coord_label and rule.coord_label == coord_label:
                    coord_rules.append(rule)
            elif rule.scope == RuleScopeV1.GLOBAL:
                # Reglas GLOBAL aplican a todas las coords
                global_rules.append(rule)
        
        # Prioridad: primero COORD, luego GLOBAL
        rules_to_check = coord_rules + global_rules
        
        for rule in rules_to_check:
            
            # Verificar pending_text_contains: TODOS los tokens deben aparecer
            all_tokens_match = True
            for token in rule.match.pending_text_contains:
                token_normalized = normalize_text(token)
                if token_normalized not in base_normalized:
                    all_tokens_match = False
                    break
            
            if not all_tokens_match:
                continue
            
            # Verificar empresa_contains (opcional): al menos uno debe aparecer
            empresa_match = True
            if rule.match.empresa_contains and empresa_normalized:
                empresa_match = False
                for empresa_token in rule.match.empresa_contains:
                    empresa_token_normalized = normalize_text(empresa_token)
                    if empresa_token_normalized in empresa_normalized:
                        empresa_match = True
                        break
            elif rule.match.empresa_contains and not empresa_normalized:
                # La regla requiere empresa pero no se proporcionó
                empresa_match = False
            
            if not empresa_match:
                continue
            
            # Match encontrado
            confidence = 0.9  # Alta confianza para reglas
            reasons = [
                f"Matched rule {rule.rule_id}",
                f"Platform: {rule.platform_key}",
                f"Type: {rule.document_type_id}",
                f"Tokens matched: {', '.join(rule.match.pending_text_contains)}"
            ]
            
            return (rule, confidence, reasons)
        
        # No hay match
        return None


