"""
Tests unitarios para ExecutionProfile v1.9.0
"""
import pytest
from backend.agents.execution_profile import ExecutionProfile


class TestExecutionProfile:
    """Tests para ExecutionProfile"""
    
    def test_default_profile(self):
        """Crear perfil por defecto"""
        profile = ExecutionProfile.default()
        assert profile.mode == "balanced"
        assert profile.max_steps_per_subgoal is None
        assert profile.allow_wikipedia is True
        assert profile.allow_images is True
        assert profile.stop_on_first_success is False
    
    def test_fast_profile(self):
        """Crear perfil rápido"""
        profile = ExecutionProfile.fast()
        assert profile.mode == "fast"
        assert profile.max_steps_per_subgoal == 4
        assert profile.stop_on_first_success is True
    
    def test_thorough_profile(self):
        """Crear perfil exhaustivo"""
        profile = ExecutionProfile.thorough()
        assert profile.mode == "thorough"
        assert profile.max_steps_per_subgoal == 12
        assert profile.stop_on_first_success is False
    
    def test_from_goal_text_fast_keywords(self):
        """Inferir modo fast desde palabras clave"""
        test_cases = [
            "investiga rápidamente quién fue Ada Lovelace",
            "breve información sobre Python",
            "dame un resumen de la historia",
            "en resumen, quién fue Einstein",
        ]
        for goal in test_cases:
            profile = ExecutionProfile.from_goal_text(goal)
            assert profile.mode == "fast", f"Failed for: {goal}"
            assert profile.max_steps_per_subgoal == 4
            assert profile.stop_on_first_success is True
    
    def test_from_goal_text_thorough_keywords(self):
        """Inferir modo thorough desde palabras clave"""
        test_cases = [
            "investiga exhaustivamente quién fue Ada Lovelace",
            "información detallada sobre Python",
            "dame información a fondo de la historia",
        ]
        for goal in test_cases:
            profile = ExecutionProfile.from_goal_text(goal)
            assert profile.mode == "thorough", f"Failed for: {goal}"
            assert profile.max_steps_per_subgoal == 12
            assert profile.stop_on_first_success is False
    
    def test_from_goal_text_no_images(self):
        """Inferir restricción de imágenes"""
        test_cases = [
            "investiga solo en Wikipedia sobre Ada Lovelace",
            "solo wikipedia, sin imágenes",
            "no imágenes, solo texto",
        ]
        for goal in test_cases:
            profile = ExecutionProfile.from_goal_text(goal)
            assert profile.allow_images is False, f"Failed for: {goal}"
    
    def test_from_goal_text_no_wikipedia(self):
        """Inferir restricción de Wikipedia"""
        test_cases = [
            "solo imágenes de Ada Lovelace",
            "no wikipedia, solo imágenes",
        ]
        for goal in test_cases:
            profile = ExecutionProfile.from_goal_text(goal)
            assert profile.allow_wikipedia is False, f"Failed for: {goal}"
    
    def test_from_goal_text_max_steps(self):
        """Inferir límite de pasos desde el texto"""
        test_cases = [
            ("investiga con máx 5 pasos", 5),
            ("máximo 3 pasos sobre Python", 3),
            ("max 10 steps sobre historia", 10),
        ]
        for goal, expected_steps in test_cases:
            profile = ExecutionProfile.from_goal_text(goal)
            assert profile.max_steps_per_subgoal == expected_steps, f"Failed for: {goal}"
    
    def test_get_effective_max_steps(self):
        """Obtener max_steps efectivo"""
        profile = ExecutionProfile.default()
        assert profile.get_effective_max_steps(8) == 8
        
        profile.max_steps_per_subgoal = 5
        assert profile.get_effective_max_steps(8) == 5
    
    def test_should_skip_goal_images(self):
        """Saltar objetivos de imágenes si allow_images=False"""
        profile = ExecutionProfile.default()
        profile.allow_images = False
        
        assert profile.should_skip_goal("muéstrame imágenes de Ada Lovelace") is True
        assert profile.should_skip_goal("investiga quién fue Ada Lovelace en Wikipedia") is False
    
    def test_should_skip_goal_wikipedia(self):
        """Saltar objetivos de Wikipedia si allow_wikipedia=False"""
        profile = ExecutionProfile.default()
        profile.allow_wikipedia = False
        
        assert profile.should_skip_goal("investiga quién fue Ada Lovelace en Wikipedia") is True
        assert profile.should_skip_goal("muéstrame imágenes de Ada Lovelace") is False
    
    def test_to_dict(self):
        """Serializar perfil a diccionario"""
        profile = ExecutionProfile.fast()
        profile_dict = profile.to_dict()
        
        assert "mode" in profile_dict
        assert "max_steps_per_subgoal" in profile_dict
        assert "allow_wikipedia" in profile_dict
        assert "allow_images" in profile_dict
        assert "stop_on_first_success" in profile_dict
        assert profile_dict["mode"] == "fast"


class TestExecutionProfileIntegration:
    """Tests de integración de ExecutionProfile con el agente"""
    
    def test_profile_inference_combination(self):
        """Inferir múltiples características del perfil"""
        goal = "rápido, solo Wikipedia, máx 3 pasos"
        profile = ExecutionProfile.from_goal_text(goal)
        
        assert profile.mode == "fast"
        assert profile.allow_images is False
        assert profile.max_steps_per_subgoal == 3
    
    def test_profile_default_when_no_keywords(self):
        """Usar perfil default cuando no hay palabras clave"""
        goal = "investiga quién fue Ada Lovelace"
        profile = ExecutionProfile.from_goal_text(goal)
        
        assert profile.mode == "balanced"
        assert profile.max_steps_per_subgoal is None
        assert profile.allow_wikipedia is True
        assert profile.allow_images is True

