"""
Tests para el módulo Reasoning Spotlight.

v3.8.0: Tests para build_reasoning_spotlight y la generación de análisis previo de objetivos.
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from backend.agents.reasoning_spotlight import build_reasoning_spotlight
from backend.shared.models import ReasoningSpotlight, ReasoningInterpretation, ReasoningAmbiguity, ReasoningQuestion
from backend.agents.execution_profile import ExecutionProfile


def test_interpretations_generated():
    """Test: genera al menos 2 interpretaciones con confianza válida."""
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = json.dumps({
        "interpretations": [
            {"interpretation": "Interpretación 1: Subir documento de reconocimiento médico", "confidence": 0.85},
            {"interpretation": "Interpretación 2: Verificar estado del documento en la plataforma", "confidence": 0.70},
        ],
        "ambiguities": [],
        "recommended_questions": [],
        "perceived_risks": [],
        "llm_notes": "El objetivo parece ser sobre subir un documento médico."
    })
    
    async def run_test():
        with patch("backend.agents.reasoning_spotlight.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client
            
            spotlight = await build_reasoning_spotlight(
                raw_goal="Sube el documento de reconocimiento médico",
                execution_profile=None,
                is_batch=False,
            )
            
            assert spotlight is not None
            assert len(spotlight.interpretations) >= 2
            for interp in spotlight.interpretations:
                assert 0.0 <= interp.confidence <= 1.0
                assert interp.interpretation
    
    asyncio.run(run_test())


def test_ambiguities_detected():
    """Test: detecta ambigüedades en objetivos vagos."""
    
    async def run_test():
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = json.dumps({
            "interpretations": [
                {"interpretation": "Revisar documentos", "confidence": 0.5},
                {"interpretation": "Verificar estado de documentos", "confidence": 0.4},
            ],
            "ambiguities": [
                {"description": "No se especifica qué documentos revisar", "severity": "high"},
                {"description": "Falta identificar el trabajador o empresa", "severity": "medium"},
            ],
            "recommended_questions": [
                {"question": "¿Qué documentos específicamente?", "rationale": "El objetivo no especifica qué documentos"}
            ],
            "perceived_risks": ["Ambigüedad crítica sobre qué documentos revisar"],
            "llm_notes": "El objetivo es muy vago y requiere clarificación."
        })
        
        with patch("backend.agents.reasoning_spotlight.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client
            
            spotlight = await build_reasoning_spotlight(
                raw_goal="Revisa los documentos",
                execution_profile=None,
                is_batch=False,
            )
            
            assert spotlight is not None
            assert len(spotlight.ambiguities) > 0
            for amb in spotlight.ambiguities:
                assert amb.severity in ["low", "medium", "high"]
                assert amb.description
    
    asyncio.run(run_test())


def test_clarification_questions():
    """Test: genera preguntas en modo interactivo."""
    
    async def run_test():
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = json.dumps({
            "interpretations": [
                {"interpretation": "Subir documento", "confidence": 0.6},
                {"interpretation": "Verificar documento", "confidence": 0.4},
            ],
            "ambiguities": [
                {"description": "No se especifica qué documento", "severity": "high"}
            ],
            "recommended_questions": [
                {"question": "¿Qué documento específicamente?", "rationale": "Falta especificar el tipo de documento"},
                {"question": "¿Para qué trabajador?", "rationale": "Falta identificar el trabajador"}
            ],
            "perceived_risks": ["Ambigüedad sobre qué documento subir"],
            "llm_notes": "El objetivo requiere clarificación sobre el documento."
        })
        
        with patch("backend.agents.reasoning_spotlight.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client
            
            spotlight = await build_reasoning_spotlight(
                raw_goal="Sube el documento",
                execution_profile=ExecutionProfile.default(),  # Modo interactivo
                is_batch=False,
            )
            
            assert spotlight is not None
            assert len(spotlight.recommended_questions) > 0
            assert len(spotlight.recommended_questions) <= 3
            for q in spotlight.recommended_questions:
                assert q.question
                # rationale es opcional
    
    asyncio.run(run_test())


def test_no_questions_in_batch():
    """Test: si es batch, recommended_questions está vacío."""
    
    async def run_test():
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = json.dumps({
            "interpretations": [
                {"interpretation": "Subir documento", "confidence": 0.6},
            ],
            "ambiguities": [],
            "recommended_questions": [
                {"question": "¿Qué documento?", "rationale": "Test"}
            ],
            "perceived_risks": [],
            "llm_notes": "Test"
        })
        
        with patch("backend.agents.reasoning_spotlight.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client
            
            spotlight = await build_reasoning_spotlight(
                raw_goal="Sube el documento",
                execution_profile=None,
                is_batch=True,  # Modo batch
            )
            
            assert spotlight is not None
            # Aunque el LLM devuelva preguntas, deben ser filtradas en modo batch
            assert len(spotlight.recommended_questions) == 0
    
    asyncio.run(run_test())


def test_integration_in_response():
    """Test: el spotlight se puede construir y serializar correctamente."""
    from backend.shared.models import AgentAnswerResponse
    
    async def run_test():
        # Mock del spotlight
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = json.dumps({
            "interpretations": [
                {"interpretation": "Test interpretation", "confidence": 0.8},
                {"interpretation": "Test interpretation 2", "confidence": 0.7},
            ],
            "ambiguities": [],
            "recommended_questions": [],
            "perceived_risks": [],
            "llm_notes": "Test notes"
        })
        
        with patch("backend.agents.reasoning_spotlight.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client
            
            spotlight = await build_reasoning_spotlight(
                raw_goal="Test goal",
                execution_profile=None,
                is_batch=False,
            )
            
            # Verificar que el spotlight se puede usar en AgentAnswerResponse
            response = AgentAnswerResponse(
                goal="Test goal",
                final_answer="Test answer",
                steps=[],
                reasoning_spotlight=spotlight,
            )
            
            assert response.reasoning_spotlight is not None
            assert response.reasoning_spotlight.raw_goal == "Test goal"
            assert len(response.reasoning_spotlight.interpretations) >= 2
    
    asyncio.run(run_test())


def test_error_handling():
    """Test: manejo de errores devuelve spotlight válido."""
    async def run_test():
        with patch("backend.agents.reasoning_spotlight.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Connection error"))
            mock_openai.return_value = mock_client
            
            spotlight = await build_reasoning_spotlight(
                raw_goal="Test goal",
                execution_profile=None,
                is_batch=False,
            )
            
            # Debe devolver un spotlight válido incluso con error
            assert spotlight is not None
            assert spotlight.raw_goal == "Test goal"
            assert len(spotlight.interpretations) > 0
    
    asyncio.run(run_test())


def test_invalid_json_handling():
    """Test: manejo de JSON inválido devuelve spotlight válido."""
    async def run_test():
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "Invalid JSON {"
        
        with patch("backend.agents.reasoning_spotlight.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_openai.return_value = mock_client
            
            spotlight = await build_reasoning_spotlight(
                raw_goal="Test goal",
                execution_profile=None,
                is_batch=False,
            )
            
            # Debe devolver un spotlight válido incluso con JSON inválido
            assert spotlight is not None
            assert spotlight.raw_goal == "Test goal"
            assert len(spotlight.interpretations) >= 2  # Debe tener interpretaciones por defecto
    
    asyncio.run(run_test())

