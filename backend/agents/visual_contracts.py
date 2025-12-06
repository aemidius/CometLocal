"""
Motor de contratos visuales para evaluar expectativas vs estado observado.

v3.6.0: Compara el estado visual esperado tras una acción con el estado visual
observado, permitiendo detectar violaciones y desajustes en el flujo de trabajo.
"""

import logging
from typing import Optional

from backend.shared.models import VisualExpectation, VisualFlowState, VisualContractResult

logger = logging.getLogger(__name__)


def build_visual_expectation_for_action(
    action_type: Optional[str],
    visual_flow_state_before: Optional[VisualFlowState],
) -> Optional[VisualExpectation]:
    """
    Construye una expectativa visual para una acción dada.
    
    v3.6.0: Dada la acción actual y el estado visual previo, devuelve una VisualExpectation
    si tiene sentido tener una expectativa para esta acción. Si no, devuelve None.
    
    Args:
        action_type: Tipo de acción ejecutada (ej. "upload_file", "click", "visual_click")
        visual_flow_state_before: Estado visual previo a la acción (opcional)
        
    Returns:
        VisualExpectation si la acción requiere una expectativa, None en caso contrario
    """
    if not action_type:
        return None
    
    action_type_lower = action_type.lower()
    
    # Para acciones de upload
    if action_type_lower == "upload_file":
        return VisualExpectation(
            expected_stage="file_selected",
            allowed_stages=["file_selected", "uploaded", "saved", "confirmed"],
            expected_keywords=["archivo seleccionado", "archivo subido", "archivo adjuntado", "file selected", "file uploaded"],
            description="Tras subir un archivo, debería verse como seleccionado o subido.",
            severity="normal",
        )
    
    # Para acciones de click en botones críticos
    # Nota: En el futuro, cuando tengamos tipos de acción más específicos (ej. "click_save_button"),
    # podemos añadir expectativas más precisas aquí.
    # Por ahora, si la acción es "click" y el estado previo sugiere que estamos en un punto crítico,
    # podemos inferir expectativas.
    
    if action_type_lower == "click":
        # Si el estado previo indica que acabamos de subir un archivo, esperamos guardar
        if visual_flow_state_before and visual_flow_state_before.stage in ["file_selected", "uploaded"]:
            # Inferir que probablemente se hizo click en "Guardar"
            return VisualExpectation(
                expected_stage="saved",
                allowed_stages=["saved", "confirmed"],
                expected_keywords=["guardado", "guardado correctamente", "cambios guardados", "saved", "saved successfully"],
                description="Tras hacer click en Guardar, debería verse como guardado o confirmado.",
                severity="critical",
            )
        
        # Si el estado previo indica que acabamos de guardar, esperamos confirmar
        if visual_flow_state_before and visual_flow_state_before.stage == "saved":
            # Inferir que probablemente se hizo click en "Confirmar"
            return VisualExpectation(
                expected_stage="confirmed",
                allowed_stages=["confirmed"],
                expected_keywords=["confirmado", "enviado correctamente", "operación realizada", "confirmed", "sent successfully"],
                description="Tras hacer click en Confirmar, debería verse como confirmado.",
                severity="critical",
            )
    
    # Para clicks visuales (v3.4.0)
    if action_type_lower == "visual_click":
        # Similar a click, pero con expectativas basadas en el estado previo
        if visual_flow_state_before:
            if visual_flow_state_before.stage in ["file_selected", "uploaded"]:
                return VisualExpectation(
                    expected_stage="saved",
                    allowed_stages=["saved", "confirmed"],
                    expected_keywords=["guardado", "guardado correctamente", "saved"],
                    description="Tras click visual en Guardar, debería verse como guardado.",
                    severity="critical",
                )
            elif visual_flow_state_before.stage == "saved":
                return VisualExpectation(
                    expected_stage="confirmed",
                    allowed_stages=["confirmed"],
                    expected_keywords=["confirmado", "enviado", "confirmed"],
                    description="Tras click visual en Confirmar, debería verse como confirmado.",
                    severity="critical",
                )
    
    # Para otras acciones (scroll, navegación, etc.), no hay expectativa específica
    return None


def evaluate_visual_contract(
    expectation: VisualExpectation,
    state: Optional[VisualFlowState],
) -> VisualContractResult:
    """
    Evalúa un contrato visual comparando la expectativa con el estado observado.
    
    v3.6.0: Compara la expectativa con el estado visual actual y devuelve un VisualContractResult
    indicando si hay match, mismatch, violation o unknown.
    
    Args:
        expectation: VisualExpectation con el estado esperado
        state: VisualFlowState observado (opcional)
        
    Returns:
        VisualContractResult con el resultado de la evaluación
    """
    # Si no hay estado observado o es unknown, no podemos evaluar
    if state is None or state.stage == "unknown":
        return VisualContractResult(
            outcome="unknown",
            expected_stage=expectation.expected_stage,
            actual_stage=None,
            description="No se pudo determinar el estado visual observado.",
            severity=expectation.severity,
        )
    
    actual_stage = state.stage
    
    # Violación: si el estado es error, siempre es una violación
    if actual_stage == "error":
        return VisualContractResult(
            outcome="violation",
            expected_stage=expectation.expected_stage,
            actual_stage=actual_stage,
            description="El estado visual indica errores visibles en la página.",
            severity=expectation.severity,
        )
    
    # Match: si el estado coincide con la expectativa
    if expectation.expected_stage:
        if actual_stage == expectation.expected_stage:
            return VisualContractResult(
                outcome="match",
                expected_stage=expectation.expected_stage,
                actual_stage=actual_stage,
                description=f"El estado visual observado ({actual_stage}) coincide con el esperado ({expectation.expected_stage}).",
                severity=expectation.severity,
            )
    
    # Match: si el estado está en allowed_stages
    if expectation.allowed_stages and actual_stage in expectation.allowed_stages:
        return VisualContractResult(
            outcome="match",
            expected_stage=expectation.expected_stage,
            actual_stage=actual_stage,
            description=f"El estado visual observado ({actual_stage}) está en las etapas aceptables.",
            severity=expectation.severity,
        )
    
    # Mismatch: si hay una expectativa clara pero el estado no coincide
    if expectation.expected_stage:
        # Estados "cercanos" pueden considerarse como mismatch en lugar de violation
        # Por ejemplo, "file_selected" vs "uploaded" son cercanos
        stage_hierarchy = {
            "idle": 0,
            "select_file": 1,
            "file_selected": 2,
            "uploaded": 2,  # Mismo nivel que file_selected
            "saved": 3,
            "confirmed": 4,
        }
        
        expected_level = stage_hierarchy.get(expectation.expected_stage, -1)
        actual_level = stage_hierarchy.get(actual_stage, -1)
        
        # Si el estado actual está "más adelante" que el esperado, puede ser aceptable
        if expected_level >= 0 and actual_level > expected_level:
            # Verificar si está en allowed_stages
            if expectation.allowed_stages and actual_stage in expectation.allowed_stages:
                return VisualContractResult(
                    outcome="match",
                    expected_stage=expectation.expected_stage,
                    actual_stage=actual_stage,
                    description=f"El estado visual ({actual_stage}) está más adelante que el esperado ({expectation.expected_stage}), pero es aceptable.",
                    severity=expectation.severity,
                )
        
        # Si no coincide y no está en allowed_stages, es un mismatch
        return VisualContractResult(
            outcome="mismatch",
            expected_stage=expectation.expected_stage,
            actual_stage=actual_stage,
            description=f"El estado visual observado ({actual_stage}) no coincide con el esperado ({expectation.expected_stage}).",
            severity=expectation.severity,
        )
    
    # Si no hay expectativa clara pero hay allowed_stages, verificar
    if expectation.allowed_stages:
        if actual_stage not in expectation.allowed_stages:
            return VisualContractResult(
                outcome="mismatch",
                expected_stage=expectation.expected_stage,
                actual_stage=actual_stage,
                description=f"El estado visual ({actual_stage}) no está en las etapas aceptables.",
                severity=expectation.severity,
            )
    
    # En caso de duda, unknown
    return VisualContractResult(
        outcome="unknown",
        expected_stage=expectation.expected_stage,
        actual_stage=actual_stage,
        description="No se pudo determinar si el estado visual cumple con la expectativa.",
        severity=expectation.severity,
    )




