"""
Tests para VisualFlowEngine.

v3.5.0: Tests para el motor de inferencia de estado visual del flujo.
"""

import pytest
from backend.shared.models import BrowserObservation, VisualFlowState
from backend.agents.visual_flow import VisualFlowEngine


def test_visual_flow_initial_state_idle():
    """VisualFlowEngine debe devolver estado 'idle' o 'unknown' sin acción relevante."""
    engine = VisualFlowEngine()
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Página de ejemplo sin información relevante",
        clickable_texts=[],
        input_hints=[],
    )
    
    state = engine.infer_next_state(
        previous=None,
        action_type=None,
        observation=observation,
    )
    
    assert state.stage in ["idle", "unknown"]
    assert state.confidence >= 0.0


def test_visual_flow_after_upload_with_file_selected_text():
    """VisualFlowEngine debe detectar estado 'file_selected' o 'uploaded' después de upload."""
    engine = VisualFlowEngine()
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Archivo seleccionado: reconocimiento.pdf",
        clickable_texts=[],
        input_hints=[],
    )
    
    state = engine.infer_next_state(
        previous=None,
        action_type="upload_file",
        observation=observation,
    )
    
    assert state.stage in ["file_selected", "uploaded"]
    assert "click_save_button" in state.pending_actions
    assert state.confidence >= 0.7
    assert state.notes is not None


def test_visual_flow_after_save_success_text():
    """VisualFlowEngine debe detectar estado 'saved' cuando hay texto de guardado exitoso."""
    engine = VisualFlowEngine()
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Cambios guardados correctamente. Los datos han sido actualizados.",
        clickable_texts=[],
        input_hints=[],
    )
    
    state = engine.infer_next_state(
        previous=None,
        action_type="click",
        observation=observation,
    )
    
    assert state.stage == "saved"
    assert "click_confirm_button" in state.pending_actions
    assert state.confidence >= 0.85
    assert "guardado" in state.notes.lower()


def test_visual_flow_after_confirm_success_text():
    """VisualFlowEngine debe detectar estado 'confirmed' cuando hay texto de confirmación."""
    engine = VisualFlowEngine()
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Operación realizada con éxito. Los datos han sido enviados correctamente.",
        clickable_texts=[],
        input_hints=[],
    )
    
    state = engine.infer_next_state(
        previous=None,
        action_type="click",
        observation=observation,
    )
    
    assert state.stage == "confirmed"
    assert len(state.pending_actions) == 0
    assert state.confidence >= 0.9
    assert "confirmada" in state.notes.lower() or "exitosamente" in state.notes.lower()


def test_visual_flow_error_state():
    """VisualFlowEngine debe detectar estado 'error' cuando hay mensajes de error."""
    engine = VisualFlowEngine()
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Error al subir el archivo. El formato no está permitido.",
        clickable_texts=[],
        input_hints=[],
    )
    
    state = engine.infer_next_state(
        previous=None,
        action_type="upload_file",
        observation=observation,
    )
    
    assert state.stage == "error"
    assert len(state.pending_actions) == 0
    assert state.confidence >= 0.8
    assert "error" in state.notes.lower()


def test_visual_flow_accumulates_pending_actions():
    """VisualFlowEngine debe mantener coherencia en una secuencia de estados."""
    engine = VisualFlowEngine()
    
    # Paso 1: Upload
    obs1 = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Archivo seleccionado: documento.pdf",
        clickable_texts=[],
        input_hints=[],
    )
    state1 = engine.infer_next_state(
        previous=None,
        action_type="upload_file",
        observation=obs1,
    )
    assert state1.stage in ["file_selected", "uploaded"]
    assert "click_save_button" in state1.pending_actions
    
    # Paso 2: Guardado exitoso
    obs2 = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Cambios guardados correctamente",
        clickable_texts=[],
        input_hints=[],
    )
    state2 = engine.infer_next_state(
        previous=state1,
        action_type="click",
        observation=obs2,
    )
    assert state2.stage == "saved"
    assert "click_confirm_button" in state2.pending_actions
    
    # Paso 3: Confirmación exitosa
    obs3 = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Operación realizada con éxito",
        clickable_texts=[],
        input_hints=[],
    )
    state3 = engine.infer_next_state(
        previous=state2,
        action_type="click",
        observation=obs3,
    )
    assert state3.stage == "confirmed"
    assert len(state3.pending_actions) == 0


def test_visual_flow_uses_ocr_text():
    """VisualFlowEngine debe usar texto OCR si está disponible."""
    engine = VisualFlowEngine()
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Página de ejemplo",
        clickable_texts=[],
        input_hints=[],
        ocr_text="Cambios guardados correctamente. El documento ha sido actualizado.",
    )
    
    state = engine.infer_next_state(
        previous=None,
        action_type="click",
        observation=observation,
    )
    
    assert state.stage == "saved"
    assert state.confidence >= 0.85


def test_visual_flow_maintains_previous_state():
    """VisualFlowEngine debe mantener estado previo si no hay cambios detectados."""
    engine = VisualFlowEngine()
    
    previous_state = VisualFlowState(
        stage="file_selected",
        last_action="upload_file",
        pending_actions=["click_save_button"],
        notes="Archivo seleccionado",
        confidence=0.8,
    )
    
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Página sin cambios relevantes",
        clickable_texts=[],
        input_hints=[],
    )
    
    state = engine.infer_next_state(
        previous=previous_state,
        action_type="click",
        observation=observation,
    )
    
    # Debe mantener el estado previo pero con confianza reducida
    assert state.stage == "file_selected"
    assert "click_save_button" in state.pending_actions
    assert state.confidence < previous_state.confidence  # Confianza reducida

















