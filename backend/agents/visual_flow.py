"""
Motor de Visual Flow Awareness para rastrear el estado visual del flujo.

v3.5.0: Infiere el estado visual del flujo (ej. "archivo adjuntado", "pendiente de guardar")
basándose en acciones ejecutadas y texto visible/OCR, para orientar mejor la recuperación
visual y el análisis de resultados en formularios CAE/upload.
"""

import logging
from typing import Optional
import re

from backend.shared.models import VisualFlowState, BrowserObservation

logger = logging.getLogger(__name__)


# Palabras clave para detectar diferentes estados del flujo
UPLOAD_KEYWORDS = [
    "archivo seleccionado", "fichero seleccionado", "archivo adjunto", "archivo cargado",
    "archivo subido", "documento seleccionado", "documento adjunto", "documento cargado",
    "file selected", "file uploaded", "document attached", "file attached",
]

SAVE_SUCCESS_KEYWORDS = [
    "guardado correctamente", "cambios guardados", "registro actualizado",
    "datos guardados", "información guardada", "saved successfully", "changes saved",
    "guardado con éxito", "guardado exitosamente",
]

CONFIRM_SUCCESS_KEYWORDS = [
    "operación realizada con éxito", "enviado correctamente", "confirmado",
    "datos enviados", "operación completada", "proceso finalizado",
    "sent successfully", "submitted", "confirmed", "operation completed",
]

ERROR_KEYWORDS = [
    "error", "no se ha podido", "formato no permitido", "obligatorio",
    "campo requerido", "campo obligatorio", "ha ocurrido un error",
    "error al", "error en", "failed", "error occurred", "required field",
]


class VisualFlowEngine:
    """
    Motor para inferir el estado visual del flujo basándose en acciones y observaciones.
    
    v3.5.0: Usa heurísticas simples basadas en palabras clave para determinar el estado
    del flujo (idle, file_selected, uploaded, saved, confirmed, error, etc.).
    """
    
    def infer_next_state(
        self,
        previous: Optional[VisualFlowState],
        action_type: Optional[str],
        observation: BrowserObservation,
    ) -> VisualFlowState:
        """
        Infiere el siguiente estado visual del flujo.
        
        Args:
            previous: Estado visual anterior (None si es el primer paso)
            action_type: Tipo de acción ejecutada (ej. "upload_file", "click", "visual_click")
            observation: BrowserObservation con texto visible y OCR
            
        Returns:
            VisualFlowState con el estado inferido
        """
        # Construir texto combinado (visible + OCR)
        visible_text = observation.visible_text_excerpt or ""
        ocr_text = observation.ocr_text or ""
        combined_text = f"{visible_text}\n{ocr_text}".lower()
        
        # Normalizar action_type
        action_type_lower = (action_type or "").lower()
        
        # Inicializar estado base
        stage = "unknown"
        last_action = action_type
        pending_actions = []
        notes = None
        confidence = 0.5  # Confianza base
        
        # 1. Detectar errores (prioridad alta)
        if any(keyword in combined_text for keyword in ERROR_KEYWORDS):
            stage = "error"
            notes = "Se detectaron mensajes de error en la página"
            confidence = 0.8
            # Si hay error, no hay acciones pendientes
            pending_actions = []
            logger.debug("[visual-flow] Error state detected")
            return VisualFlowState(
                stage=stage,
                last_action=last_action,
                pending_actions=pending_actions,
                notes=notes,
                confidence=confidence,
            )
        
        # 2. Detectar confirmación exitosa (prioridad alta)
        if any(keyword in combined_text for keyword in CONFIRM_SUCCESS_KEYWORDS):
            stage = "confirmed"
            notes = "Operación confirmada exitosamente"
            confidence = 0.9
            pending_actions = []
            logger.debug("[visual-flow] Confirmed state detected")
            return VisualFlowState(
                stage=stage,
                last_action=last_action,
                pending_actions=pending_actions,
                notes=notes,
                confidence=confidence,
            )
        
        # 3. Detectar guardado exitoso
        if any(keyword in combined_text for keyword in SAVE_SUCCESS_KEYWORDS):
            stage = "saved"
            notes = "Cambios guardados correctamente"
            confidence = 0.85
            # Después de guardar, puede que falte confirmar
            pending_actions = ["click_confirm_button"]
            logger.debug("[visual-flow] Saved state detected")
            return VisualFlowState(
                stage=stage,
                last_action=last_action,
                pending_actions=pending_actions,
                notes=notes,
                confidence=confidence,
            )
        
        # 4. Detectar upload/selección de archivo
        if "upload_file" in action_type_lower or any(keyword in combined_text for keyword in UPLOAD_KEYWORDS):
            if "upload_file" in action_type_lower:
                # Acción explícita de upload
                stage = "uploaded"
                notes = "Archivo subido, pendiente de guardar"
                confidence = 0.8
                pending_actions = ["click_save_button"]
            else:
                # Solo texto que indica archivo seleccionado
                stage = "file_selected"
                notes = "Archivo seleccionado, pendiente de guardar"
                confidence = 0.7
                pending_actions = ["click_save_button"]
            logger.debug("[visual-flow] Upload/file_selected state detected")
            return VisualFlowState(
                stage=stage,
                last_action=last_action,
                pending_actions=pending_actions,
                notes=notes,
                confidence=confidence,
            )
        
        # 5. Si hay un estado previo, intentar mantener coherencia
        if previous:
            # Si el estado previo tenía acciones pendientes y no hemos detectado nada nuevo,
            # mantener el estado pero reducir confianza
            if previous.pending_actions:
                stage = previous.stage
                pending_actions = previous.pending_actions.copy()
                notes = previous.notes or "Estado mantenido del paso anterior"
                confidence = max(0.3, previous.confidence - 0.1)  # Reducir confianza gradualmente
                logger.debug(f"[visual-flow] Maintaining previous state: {stage}")
                return VisualFlowState(
                    stage=stage,
                    last_action=last_action or previous.last_action,
                    pending_actions=pending_actions,
                    notes=notes,
                    confidence=confidence,
                )
        
        # 6. Estado por defecto: unknown o idle
        if not previous:
            stage = "idle"
            notes = "Estado inicial del flujo"
            confidence = 0.5
        else:
            stage = "unknown"
            notes = "No se pudo determinar el estado visual"
            confidence = 0.3
        
        logger.debug(f"[visual-flow] Default state: {stage}")
        return VisualFlowState(
            stage=stage,
            last_action=last_action,
            pending_actions=pending_actions,
            notes=notes,
            confidence=confidence,
        )





















