"""
Motor de intenciones del agente para acciones críticas.

v3.7.0: Construye intenciones explícitas del agente basadas en la acción que se va a ejecutar,
el sub-goal actual y el estado visual previo, permitiendo trazar la intención → acción → estado visual → contrato.
"""

import logging
import re
from typing import Optional

from backend.shared.models import AgentIntent, VisualFlowState, BrowserAction

logger = logging.getLogger(__name__)


def build_agent_intent_for_action(
    action: Optional[BrowserAction],
    sub_goal: Optional[str],
    sub_goal_index: Optional[int],
    visual_flow_state_before: Optional[VisualFlowState],
) -> Optional[AgentIntent]:
    """
    Construye una intención del agente para una acción dada.
    
    v3.7.0: Dada la acción que se va a ejecutar, el sub-goal actual y el estado visual previo,
    devuelve una AgentIntent si tiene sentido tener una intención para esta acción. Si no, devuelve None.
    
    Args:
        action: BrowserAction que se va a ejecutar (opcional)
        sub_goal: Texto del sub-goal actual (opcional)
        sub_goal_index: Índice del sub-goal actual (opcional)
        visual_flow_state_before: Estado visual previo a la acción (opcional)
        
    Returns:
        AgentIntent si la acción requiere una intención, None en caso contrario
    """
    if not action:
        return None
    
    action_type = action.type
    action_args = action.args or {}
    
    # Para acciones de upload
    if action_type == "upload_file":
        # Extraer descripción del sub-goal si está disponible
        description = None
        if sub_goal:
            # Buscar referencias a documentos o archivos en el sub-goal
            doc_patterns = [
                r"(?:subir|adjuntar|sube|adjunta)\s+(?:el\s+)?(?:archivo|documento|ficha)\s+(?:de\s+)?([^,\.]+)",
                r"(?:subir|adjuntar|sube|adjunta)\s+([^,\.]+)",
            ]
            for pattern in doc_patterns:
                match = re.search(pattern, sub_goal, re.IGNORECASE)
                if match:
                    doc_desc = match.group(1).strip()
                    description = f"Subir el archivo: {doc_desc}"
                    break
        
        if not description:
            description = "Subir un archivo al formulario"
        
        # Determinar related_stage basado en el estado previo
        related_stage = "file_selected"
        if visual_flow_state_before:
            # Si ya hay un archivo seleccionado, la intención es avanzar a "uploaded"
            if visual_flow_state_before.stage in ["file_selected", "uploaded"]:
                related_stage = "uploaded"
        
        tags = ["upload"]
        # Detectar si es un contexto CAE
        if sub_goal and ("cae" in sub_goal.lower() or "prevención" in sub_goal.lower() or "riesgos" in sub_goal.lower()):
            tags.append("cae")
        
        return AgentIntent(
            intent_type="upload_file",
            description=description,
            related_stage=related_stage,
            criticality="normal",
            tags=tags,
            sub_goal_index=sub_goal_index,
        )
    
    # Para acciones de click en botones críticos
    if action_type == "click_text":
        clicked_text = action_args.get("text", "").lower()
        
        # Detectar intención de guardar cambios
        save_keywords = ["guardar", "guardar cambios", "save", "save changes"]
        if any(keyword in clicked_text for keyword in save_keywords):
            description = f"Guardar cambios en el formulario"
            if sub_goal:
                # Intentar extraer más contexto del sub-goal
                if "guardar" in sub_goal.lower():
                    description = f"Guardar cambios: {sub_goal[:100]}"
            
            return AgentIntent(
                intent_type="save_changes",
                description=description,
                related_stage="saved",
                criticality="critical",
                tags=["save", "critical"],
                sub_goal_index=sub_goal_index,
            )
        
        # Detectar intención de confirmar/enviar
        confirm_keywords = ["confirmar", "enviar", "finalizar", "aceptar", "confirm", "submit", "send", "finalize"]
        if any(keyword in clicked_text for keyword in confirm_keywords):
            description = f"Confirmar o enviar el formulario"
            if sub_goal:
                if any(kw in sub_goal.lower() for kw in ["confirmar", "enviar", "finalizar"]):
                    description = f"Confirmar envío: {sub_goal[:100]}"
            
            return AgentIntent(
                intent_type="confirm_submission",
                description=description,
                related_stage="confirmed",
                criticality="critical",
                tags=["confirm", "critical"],
                sub_goal_index=sub_goal_index,
            )
        
        # Detectar intención de seleccionar archivo (click en botón de selección)
        select_keywords = ["seleccionar", "elegir", "adjuntar", "subir", "select", "choose", "attach", "upload"]
        if any(keyword in clicked_text for keyword in select_keywords):
            description = f"Seleccionar o adjuntar un archivo"
            if sub_goal:
                if any(kw in sub_goal.lower() for kw in ["seleccionar", "adjuntar", "subir"]):
                    description = f"Seleccionar archivo: {sub_goal[:100]}"
            
            return AgentIntent(
                intent_type="select_file",
                description=description,
                related_stage="file_selected",
                criticality="normal",
                tags=["upload", "select"],
                sub_goal_index=sub_goal_index,
            )
    
    # Para clicks visuales (v3.4.0)
    if action_type == "visual_click" or (action_type == "click_text" and action_args.get("visual_target")):
        # Similar a click_text, pero con contexto visual
        clicked_text = action_args.get("text", "").lower() or action_args.get("label", "").lower()
        
        if any(kw in clicked_text for kw in ["guardar", "save"]):
            return AgentIntent(
                intent_type="save_changes",
                description="Guardar cambios (click visual)",
                related_stage="saved",
                criticality="critical",
                tags=["save", "critical", "visual"],
                sub_goal_index=sub_goal_index,
            )
        
        if any(kw in clicked_text for kw in ["confirmar", "enviar", "confirm", "submit"]):
            return AgentIntent(
                intent_type="confirm_submission",
                description="Confirmar envío (click visual)",
                related_stage="confirmed",
                criticality="critical",
                tags=["confirm", "critical", "visual"],
                sub_goal_index=sub_goal_index,
            )
    
    # Para otras acciones (scroll, navegación, etc.), no hay intención específica
    return None














