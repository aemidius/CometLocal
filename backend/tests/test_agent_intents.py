"""
Tests para el módulo de intenciones del agente.

v3.7.0: Tests para build_agent_intent_for_action y la construcción de intenciones.
"""

import pytest
from backend.agents.agent_intents import build_agent_intent_for_action
from backend.shared.models import BrowserAction, VisualFlowState


def test_build_agent_intent_for_upload():
    """Test: construir intención para acción de upload."""
    action = BrowserAction(
        type="upload_file",
        args={"file_path": "/path/to/file.pdf", "selector": "input[type='file']"}
    )
    sub_goal = "Sube el archivo de reconocimiento médico"
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal=sub_goal,
        sub_goal_index=1,
        visual_flow_state_before=None,
    )
    
    assert intent is not None
    assert intent.intent_type == "upload_file"
    assert intent.related_stage == "file_selected"
    assert intent.criticality == "normal"
    assert "upload" in intent.tags
    assert intent.sub_goal_index == 1
    assert "reconocimiento médico" in intent.description.lower() or "archivo" in intent.description.lower()


def test_build_agent_intent_for_upload_with_cae_context():
    """Test: construir intención para upload con contexto CAE."""
    action = BrowserAction(
        type="upload_file",
        args={"file_path": "/path/to/file.pdf"}
    )
    sub_goal = "Sube el documento de prevención de riesgos laborales en la plataforma CAE"
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal=sub_goal,
        sub_goal_index=1,
        visual_flow_state_before=None,
    )
    
    assert intent is not None
    assert intent.intent_type == "upload_file"
    assert "cae" in intent.tags


def test_build_agent_intent_for_save_changes():
    """Test: construir intención para guardar cambios."""
    action = BrowserAction(
        type="click_text",
        args={"text": "Guardar cambios"}
    )
    sub_goal = "Guarda los cambios en el formulario"
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal=sub_goal,
        sub_goal_index=2,
        visual_flow_state_before=None,
    )
    
    assert intent is not None
    assert intent.intent_type == "save_changes"
    assert intent.related_stage == "saved"
    assert intent.criticality == "critical"
    assert "save" in intent.tags
    assert "critical" in intent.tags


def test_build_agent_intent_for_confirm_submission():
    """Test: construir intención para confirmar envío."""
    action = BrowserAction(
        type="click_text",
        args={"text": "Confirmar"}
    )
    sub_goal = "Confirma el envío del formulario"
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal=sub_goal,
        sub_goal_index=3,
        visual_flow_state_before=None,
    )
    
    assert intent is not None
    assert intent.intent_type == "confirm_submission"
    assert intent.related_stage == "confirmed"
    assert intent.criticality == "critical"
    assert "confirm" in intent.tags
    assert "critical" in intent.tags


def test_build_agent_intent_for_select_file():
    """Test: construir intención para seleccionar archivo."""
    action = BrowserAction(
        type="click_text",
        args={"text": "Seleccionar archivo"}
    )
    sub_goal = "Selecciona el archivo a subir"
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal=sub_goal,
        sub_goal_index=1,
        visual_flow_state_before=None,
    )
    
    assert intent is not None
    assert intent.intent_type == "select_file"
    assert intent.related_stage == "file_selected"
    assert intent.criticality == "normal"
    assert "upload" in intent.tags or "select" in intent.tags


def test_build_agent_intent_for_irrelevant_action():
    """Test: acciones irrelevantes no generan intención."""
    action = BrowserAction(
        type="open_url",
        args={"url": "https://example.com"}
    )
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal="Navega a la página",
        sub_goal_index=1,
        visual_flow_state_before=None,
    )
    
    assert intent is None


def test_build_agent_intent_for_scroll_action():
    """Test: acciones de scroll no generan intención."""
    action = BrowserAction(
        type="noop",
        args={}
    )
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal="Desplázate por la página",
        sub_goal_index=1,
        visual_flow_state_before=None,
    )
    
    assert intent is None


def test_build_agent_intent_with_visual_flow_state():
    """Test: construir intención considerando el estado visual previo."""
    action = BrowserAction(
        type="upload_file",
        args={"file_path": "/path/to/file.pdf"}
    )
    visual_flow_state_before = VisualFlowState(
        stage="file_selected",
        confidence=0.8,
    )
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal="Sube el archivo",
        sub_goal_index=1,
        visual_flow_state_before=visual_flow_state_before,
    )
    
    assert intent is not None
    assert intent.intent_type == "upload_file"
    # Si ya hay un archivo seleccionado, la intención puede apuntar a "uploaded"
    assert intent.related_stage in ["file_selected", "uploaded"]


def test_build_agent_intent_for_visual_click_save():
    """Test: construir intención para click visual en guardar."""
    action = BrowserAction(
        type="click_text",
        args={"text": "Guardar", "visual_target": True}
    )
    
    intent = build_agent_intent_for_action(
        action=action,
        sub_goal="Guarda los cambios",
        sub_goal_index=2,
        visual_flow_state_before=None,
    )
    
    assert intent is not None
    assert intent.intent_type == "save_changes"
    assert intent.criticality == "critical"


def test_build_agent_intent_returns_none_for_none_action():
    """Test: retornar None si la acción es None."""
    intent = build_agent_intent_for_action(
        action=None,
        sub_goal="Cualquier objetivo",
        sub_goal_index=1,
        visual_flow_state_before=None,
    )
    
    assert intent is None
















