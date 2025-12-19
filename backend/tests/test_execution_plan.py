"""
Tests para ExecutionPlan v2.8.0
"""

import pytest
from backend.agents.execution_plan import ExecutionPlan, PlannedSubGoal
from backend.agents.agent_runner import build_execution_plan, _decompose_goal
from backend.agents.execution_profile import ExecutionProfile
from backend.agents.document_repository import DocumentRepository
from pathlib import Path
import tempfile
import os


class TestExecutionPlan:
    """Tests para ExecutionPlan y PlannedSubGoal"""
    
    def test_planned_subgoal_to_dict(self):
        """PlannedSubGoal se serializa correctamente a dict"""
        subgoal = PlannedSubGoal(
            index=1,
            sub_goal="Buscar información sobre Ada Lovelace",
            strategy="wikipedia",
            expected_actions=["navigate"],
            documents_needed=[],
            may_retry=True,
        )
        
        result = subgoal.to_dict()
        
        assert result["index"] == 1
        assert result["sub_goal"] == "Buscar información sobre Ada Lovelace"
        assert result["strategy"] == "wikipedia"
        assert result["expected_actions"] == ["navigate"]
        assert result["documents_needed"] == []
        assert result["may_retry"] is True
    
    def test_execution_plan_to_dict(self):
        """ExecutionPlan se serializa correctamente a dict"""
        subgoals = [
            PlannedSubGoal(
                index=1,
                sub_goal="Test goal 1",
                strategy="wikipedia",
                expected_actions=["navigate"],
                documents_needed=[],
                may_retry=True,
            )
        ]
        
        plan = ExecutionPlan(
            goal="Test goal",
            execution_profile={"mode": "balanced"},
            context_strategies=["wikipedia"],
            sub_goals=subgoals,
        )
        
        result = plan.to_dict()
        
        assert result["goal"] == "Test goal"
        assert result["execution_profile"]["mode"] == "balanced"
        assert result["context_strategies"] == ["wikipedia"]
        assert len(result["sub_goals"]) == 1
        assert result["sub_goals"][0]["index"] == 1


class TestBuildExecutionPlan:
    """Tests para build_execution_plan"""
    
    def test_build_plan_wikipedia_strategy(self):
        """build_execution_plan infiere estrategia wikipedia correctamente"""
        goal = "Buscar información sobre Ada Lovelace en Wikipedia"
        sub_goals = _decompose_goal(goal)
        execution_profile = ExecutionProfile.default()
        context_strategies = ["wikipedia"]
        
        # Crear repositorio temporal vacío
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = DocumentRepository(Path(tmpdir))
            
            plan = build_execution_plan(
                goal=goal,
                sub_goals=sub_goals,
                execution_profile=execution_profile,
                context_strategies=context_strategies,
                document_repository=repo,
            )
            
            assert plan.goal == goal
            assert len(plan.sub_goals) > 0
            # Al menos un sub-goal debe tener strategy "wikipedia"
            has_wikipedia = any(sg.strategy == "wikipedia" for sg in plan.sub_goals)
            assert has_wikipedia
    
    def test_build_plan_images_strategy(self):
        """build_execution_plan infiere estrategia images correctamente"""
        goal = "Mostrar imágenes de Ada Lovelace"
        sub_goals = _decompose_goal(goal)
        execution_profile = ExecutionProfile.default()
        context_strategies = ["images"]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = DocumentRepository(Path(tmpdir))
            
            plan = build_execution_plan(
                goal=goal,
                sub_goals=sub_goals,
                execution_profile=execution_profile,
                context_strategies=context_strategies,
                document_repository=repo,
            )
            
            assert len(plan.sub_goals) > 0
            has_images = any(sg.strategy == "images" for sg in plan.sub_goals)
            assert has_images
    
    def test_build_plan_upload_detection(self):
        """build_execution_plan detecta intención de upload"""
        goal = "Sube el documento de reconocimiento médico de Juan Pérez"
        sub_goals = _decompose_goal(goal)
        execution_profile = ExecutionProfile.default()
        context_strategies = ["cae"]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Crear estructura de repositorio
            company_dir = Path(tmpdir) / "EmpresaTest"
            worker_dir = company_dir / "Juan Pérez"
            doc_dir = worker_dir / "reconocimiento_medico"
            doc_dir.mkdir(parents=True)
            
            # Crear archivo de prueba
            test_file = doc_dir / "reconocimiento.pdf"
            test_file.write_text("test content")
            
            repo = DocumentRepository(Path(tmpdir))
            
            plan = build_execution_plan(
                goal=goal,
                sub_goals=sub_goals,
                execution_profile=execution_profile,
                context_strategies=context_strategies,
                document_repository=repo,
            )
            
            assert len(plan.sub_goals) > 0
            # Al menos un sub-goal debe tener upload_file en expected_actions
            has_upload = any(
                "upload_file" in sg.expected_actions 
                for sg in plan.sub_goals
            )
            assert has_upload
    
    def test_build_plan_no_document_repository(self):
        """build_execution_plan funciona sin repositorio de documentos"""
        goal = "Buscar información sobre Ada Lovelace"
        sub_goals = _decompose_goal(goal)
        execution_profile = ExecutionProfile.default()
        context_strategies = ["wikipedia"]
        
        plan = build_execution_plan(
            goal=goal,
            sub_goals=sub_goals,
            execution_profile=execution_profile,
            context_strategies=context_strategies,
            document_repository=None,
        )
        
        assert plan.goal == goal
        assert len(plan.sub_goals) > 0
















