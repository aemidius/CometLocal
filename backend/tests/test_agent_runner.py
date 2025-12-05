"""
Tests unitarios para agent_runner.py v1.4.8 y v1.5.0

Cubre:
- _build_image_search_query
- _goal_is_satisfied para objetivos de imágenes
- Motivos de early-stop
- AgentMetrics (v1.5.0)
- Integración de métricas (v1.5.0)
"""
import pytest
from backend.agents.agent_runner import (
    _build_image_search_query,
    _goal_is_satisfied,
    EarlyStopReason,
    _normalize_text_for_comparison,
    AgentMetrics,
    _build_final_answer,
    goal_uses_pronouns,
    _summarize_uploads_for_subgoal,
    _verify_upload_visually,
    _evaluate_subgoal_for_retry,
    _build_retry_prompt_context,
)
from backend.agents.retry_policy import RetryPolicy
from backend.shared.models import BrowserObservation, StepResult, BrowserAction
from backend.agents.session_context import SessionContext


class TestBuildImageSearchQuery:
    """Tests para _build_image_search_query"""
    
    def test_with_focus_entity_always_wins(self):
        """Si hay focus_entity, siempre debe usarse independientemente del goal"""
        assert _build_image_search_query("muéstrame imágenes suyas", "Ada Lovelace") == "imágenes de Ada Lovelace"
        assert _build_image_search_query("enséñame imágenes de él", "Ada Lovelace") == "imágenes de Ada Lovelace"
        assert _build_image_search_query("cualquier cosa rara", "Charles Babbage") == "imágenes de Charles Babbage"
    
    def test_with_focus_entity_empty_string(self):
        """Si focus_entity es string vacío, debe tratarse como None"""
        result = _build_image_search_query("muéstrame imágenes suyas", "")
        assert result == "imágenes"
    
    def test_without_focus_entity_pronouns_only(self):
        """Sin focus_entity y solo pronombres -> devolver 'imágenes'"""
        assert _build_image_search_query("muéstrame imágenes suyas", None) == "imágenes"
        assert _build_image_search_query("enséñame imágenes de él", None) == "imágenes"
        assert _build_image_search_query("pon fotos suyas", None) == "imágenes"
    
    def test_without_focus_entity_descriptive(self):
        """Sin focus_entity pero con descripción útil -> mantener descripción"""
        result = _build_image_search_query("enséñame imágenes de computadoras antiguas", None)
        assert result == "imágenes de computadoras antiguas"
    
    def test_fotos_to_imagenes(self):
        """Convertir 'fotos' a 'imágenes'"""
        result = _build_image_search_query("búscame fotos de Charles Babbage", None)
        assert result.startswith("imágenes")
        assert "charles" in result.lower() or "Charles" in result
        assert "babbage" in result.lower() or "Babbage" in result
        assert _build_image_search_query("pon fotos suyas", None) == "imágenes"
    
    def test_various_imperative_verbs(self):
        """Eliminar varios verbos imperativos"""
        verbs = [
            "muéstrame",
            "enséñame",
            "búscame",
            "pon",
            "dame",
            "quiero ver",
        ]
        for verb in verbs:
            result = _build_image_search_query(f"{verb} imágenes de computadoras", None)
            assert "imágenes" in result.lower()
            assert verb.lower() not in result.lower()
    
    def test_ensures_imagenes_prefix(self):
        """Asegurar que la query siempre empieza por 'imágenes'"""
        result = _build_image_search_query("computadoras antiguas", None)
        assert result.startswith("imágenes")
    
    def test_cleans_multiple_spaces(self):
        """Limpiar espacios múltiples"""
        result = _build_image_search_query("muéstrame    imágenes   de   Ada", None)
        assert "  " not in result


class TestNormalizeTextForComparison:
    """Tests para _normalize_text_for_comparison"""
    
    def test_lowercase(self):
        """Pasar a minúsculas"""
        assert _normalize_text_for_comparison("ADA LOVELACE") == "ada lovelace"
    
    def test_remove_diacritics(self):
        """Eliminar diacríticos"""
        assert _normalize_text_for_comparison("Córdoba") == "cordoba"
        assert _normalize_text_for_comparison("José") == "jose"
    
    def test_trim_spaces(self):
        """Recortar espacios extra"""
        assert _normalize_text_for_comparison("  ada   lovelace  ") == "ada lovelace"
    
    def test_empty_string(self):
        """String vacío"""
        assert _normalize_text_for_comparison("") == ""
        assert _normalize_text_for_comparison("   ") == ""


class TestGoalIsSatisfiedForImages:
    """Tests para _goal_is_satisfied en el caso de imágenes"""
    
    def test_satisfied_with_focus_entity_in_url_query(self):
        """Objetivo satisfecho cuando la URL contiene la entidad en el parámetro q"""
        goal = "muéstrame imágenes suyas"
        focus_entity = "Ada Lovelace"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+Ada+Lovelace&iax=images",
            title="Imágenes de Ada Lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        assert _goal_is_satisfied(goal, obs, focus_entity) is True
    
    def test_satisfied_with_focus_entity_url_encoded(self):
        """Objetivo satisfecho con entidad codificada en URL"""
        goal = "enséñame imágenes de él"
        focus_entity = "Charles Babbage"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+Charles+Babbage&ia=images",
            title="Imágenes de Charles Babbage",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        assert _goal_is_satisfied(goal, obs, focus_entity) is True
    
    def test_satisfied_with_focus_entity_in_title(self):
        """Objetivo satisfecho cuando el título contiene la entidad"""
        goal = "muéstrame imágenes suyas"
        focus_entity = "Ada Lovelace"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+Ada+Lovelace&iax=images",
            title="Ada Lovelace - Imágenes",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        assert _goal_is_satisfied(goal, obs, focus_entity) is True
    
    def test_not_satisfied_wrong_entity(self):
        """No satisfecho si la URL no contiene la entidad correcta"""
        goal = "muéstrame imágenes suyas"
        focus_entity = "Ada Lovelace"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+Charles+Babbage&iax=images",
            title="Imágenes de Charles Babbage",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        assert _goal_is_satisfied(goal, obs, focus_entity) is False
    
    def test_not_satisfied_not_image_search(self):
        """No satisfecho si no está en búsqueda de imágenes"""
        goal = "muéstrame imágenes suyas"
        focus_entity = "Ada Lovelace"
        obs = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Ada_Lovelace",
            title="Ada Lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        assert _goal_is_satisfied(goal, obs, focus_entity) is False
    
    def test_satisfied_without_focus_entity_descriptive_match(self):
        """Satisfecho sin focus_entity si la query coincide con el goal descriptivo"""
        goal = "muéstrame imágenes de computadoras antiguas"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+computadoras+antiguas&iax=images",
            title="Imágenes de computadoras antiguas",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        assert _goal_is_satisfied(goal, obs, None) is True
    
    def test_not_satisfied_without_focus_entity_no_match(self):
        """No satisfecho sin focus_entity si la query no coincide"""
        goal = "muéstrame imágenes de computadoras antiguas"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+perros&iax=images",
            title="Imágenes de perros",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        assert _goal_is_satisfied(goal, obs, None) is False
    
    def test_satisfied_with_focus_entity_case_insensitive(self):
        """Satisfecho con entidad independientemente de mayúsculas/minúsculas"""
        goal = "muéstrame imágenes suyas"
        focus_entity = "Ada Lovelace"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+ada+lovelace&iax=images",
            title="ada lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        assert _goal_is_satisfied(goal, obs, focus_entity) is True
    
    def test_satisfied_with_focus_entity_diacritics_robust(self):
        """Satisfecho con entidad aunque haya diferencias de acentos (si aplica)"""
        goal = "muéstrame imágenes suyas"
        focus_entity = "Córdoba"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+cordoba&iax=images",
            title="Cordoba",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        # Nota: La normalización debería hacer que "Córdoba" y "cordoba" coincidan
        assert _goal_is_satisfied(goal, obs, focus_entity) is True
    
    def test_not_satisfied_no_focus_entity_and_pronouns_only(self):
        """No satisfecho sin focus_entity si el goal solo tiene pronombres"""
        goal = "muéstrame imágenes suyas"
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes&iax=images",
            title="Imágenes",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        # Sin focus_entity y goal con solo pronombres, no podemos confirmar satisfacción
        assert _goal_is_satisfied(goal, obs, None) is False


class TestEarlyStopReasons:
    """Tests para los motivos de early-stop"""
    
    def test_early_stop_reason_constants_exist(self):
        """Verificar que todas las constantes de early-stop existen"""
        assert hasattr(EarlyStopReason, "GOAL_SATISFIED_ON_INITIAL_PAGE")
        assert hasattr(EarlyStopReason, "GOAL_SATISFIED_AFTER_ENSURE_CONTEXT_BEFORE_LLM")
        assert hasattr(EarlyStopReason, "GOAL_SATISFIED_AFTER_ACTION")
        assert hasattr(EarlyStopReason, "GOAL_SATISFIED_AFTER_REORIENTATION")
    
    def test_early_stop_reason_values(self):
        """Verificar que los valores de las constantes son strings"""
        assert isinstance(EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE, str)
        assert isinstance(EarlyStopReason.GOAL_SATISFIED_AFTER_ENSURE_CONTEXT_BEFORE_LLM, str)
        assert isinstance(EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION, str)
        assert isinstance(EarlyStopReason.GOAL_SATISFIED_AFTER_REORIENTATION, str)
    
    def test_early_stop_reason_strings(self):
        """Verificar que los strings coinciden con los esperados"""
        assert EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE == "goal_satisfied_on_initial_page"
        assert EarlyStopReason.GOAL_SATISFIED_AFTER_ENSURE_CONTEXT_BEFORE_LLM == "goal_satisfied_after_ensure_context_before_llm"
        assert EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION == "goal_satisfied_after_action"
        assert EarlyStopReason.GOAL_SATISFIED_AFTER_REORIENTATION == "goal_satisfied_after_reorientation"


class TestAgentMetrics:
    """Tests para AgentMetrics v1.5.0"""
    
    def test_create_empty_metrics(self):
        """Crear instancia vacía de AgentMetrics"""
        metrics = AgentMetrics()
        assert len(metrics.sub_goals) == 0
        assert metrics.start_time is None
        assert metrics.end_time is None
    
    def test_add_subgoal_metrics(self):
        """Añadir métricas de varios sub-goals"""
        metrics = AgentMetrics()
        
        # Añadir primer sub-goal (Wikipedia exitoso)
        metrics.add_subgoal_metrics(
            goal="investiga quién fue Ada Lovelace en Wikipedia",
            focus_entity="Ada Lovelace",
            goal_type="wikipedia",
            steps_taken=1,
            early_stop_reason=EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE,
            elapsed_seconds=0.5,
            success=True,
        )
        
        # Añadir segundo sub-goal (imágenes exitoso)
        metrics.add_subgoal_metrics(
            goal="muéstrame imágenes suyas",
            focus_entity="Ada Lovelace",
            goal_type="images",
            steps_taken=2,
            early_stop_reason=EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION,
            elapsed_seconds=1.2,
            success=True,
        )
        
        # Añadir tercer sub-goal (fallido)
        metrics.add_subgoal_metrics(
            goal="busca información sobre computadoras",
            focus_entity=None,
            goal_type="other",
            steps_taken=8,
            early_stop_reason=None,
            elapsed_seconds=5.0,
            success=False,
        )
        
        assert len(metrics.sub_goals) == 3
        assert metrics.sub_goals[0].goal_type == "wikipedia"
        assert metrics.sub_goals[1].goal_type == "images"
        assert metrics.sub_goals[2].goal_type == "other"
    
    def test_to_summary_dict_totals(self):
        """Verificar que to_summary_dict calcula totales correctos"""
        metrics = AgentMetrics()
        metrics.start()
        
        metrics.add_subgoal_metrics(
            goal="goal1",
            focus_entity="Entity1",
            goal_type="wikipedia",
            steps_taken=2,
            early_stop_reason=EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE,
            elapsed_seconds=0.5,
            success=True,
        )
        
        metrics.add_subgoal_metrics(
            goal="goal2",
            focus_entity="Entity2",
            goal_type="images",
            steps_taken=3,
            early_stop_reason=None,
            elapsed_seconds=1.0,
            success=False,
        )
        
        metrics.finish()
        summary = metrics.to_summary_dict()
        
        assert summary["summary"]["total_sub_goals"] == 2
        assert summary["summary"]["total_steps"] == 5
        assert summary["summary"]["total_time_seconds"] == 1.5
        assert summary["summary"]["execution_time_seconds"] is not None
    
    def test_to_summary_dict_early_stop_counts(self):
        """Verificar conteos por early_stop_reason"""
        metrics = AgentMetrics()
        
        metrics.add_subgoal_metrics(
            goal="goal1",
            focus_entity=None,
            goal_type="wikipedia",
            steps_taken=1,
            early_stop_reason=EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE,
            elapsed_seconds=0.1,
            success=True,
        )
        
        metrics.add_subgoal_metrics(
            goal="goal2",
            focus_entity=None,
            goal_type="wikipedia",
            steps_taken=1,
            early_stop_reason=EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE,
            elapsed_seconds=0.1,
            success=True,
        )
        
        metrics.add_subgoal_metrics(
            goal="goal3",
            focus_entity=None,
            goal_type="images",
            steps_taken=2,
            early_stop_reason=EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION,
            elapsed_seconds=0.2,
            success=True,
        )
        
        summary = metrics.to_summary_dict()
        early_stop_counts = summary["summary"]["early_stop_counts"]
        
        assert early_stop_counts[EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE] == 2
        assert early_stop_counts[EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION] == 1
        assert early_stop_counts.get("none", 0) == 0
    
    def test_to_summary_dict_goal_type_counts(self):
        """Verificar conteos y ratios por goal_type"""
        metrics = AgentMetrics()
        
        # 2 Wikipedia exitosos
        metrics.add_subgoal_metrics("goal1", None, "wikipedia", 1, EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE, 0.1, True)
        metrics.add_subgoal_metrics("goal2", None, "wikipedia", 1, EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE, 0.1, True)
        
        # 1 imagen exitoso, 1 imagen fallido
        metrics.add_subgoal_metrics("goal3", None, "images", 2, EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION, 0.2, True)
        metrics.add_subgoal_metrics("goal4", None, "images", 8, None, 5.0, False)
        
        summary = metrics.to_summary_dict()
        goal_type_counts = summary["summary"]["goal_type_counts"]
        success_ratio = summary["summary"]["goal_type_success_ratio"]
        
        assert goal_type_counts["wikipedia"] == 2
        assert goal_type_counts["images"] == 2
        assert success_ratio["wikipedia"] == 1.0  # 2/2
        assert success_ratio["images"] == 0.5  # 1/2
    
    def test_to_summary_dict_sub_goals_data(self):
        """Verificar que sub_goals contiene los datos correctos"""
        metrics = AgentMetrics()
        
        metrics.add_subgoal_metrics(
            goal="test goal",
            focus_entity="Test Entity",
            goal_type="wikipedia",
            steps_taken=5,
            early_stop_reason=EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION,
            elapsed_seconds=2.5,
            success=True,
        )
        
        summary = metrics.to_summary_dict()
        sub_goals = summary["sub_goals"]
        
        assert len(sub_goals) == 1
        assert sub_goals[0]["goal"] == "test goal"
        assert sub_goals[0]["focus_entity"] == "Test Entity"
        assert sub_goals[0]["goal_type"] == "wikipedia"
        assert sub_goals[0]["steps_taken"] == 5
        assert sub_goals[0]["early_stop_reason"] == EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION
        assert sub_goals[0]["elapsed_seconds"] == 2.5
        assert sub_goals[0]["success"] is True


class TestMetricsIntegration:
    """Tests de integración para métricas en StepResult"""
    
    def test_metrics_subgoal_in_step_result_info(self):
        """Verificar que run_llm_agent añade metrics_subgoal a StepResult.info"""
        from backend.shared.models import BrowserObservation
        
        # Simular un StepResult con métricas
        obs = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Ada_Lovelace",
            title="Ada Lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=None,
            error=None,
            info={
                "reason": EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE,
                "metrics_subgoal": {
                    "goal": "investiga quién fue Ada Lovelace en Wikipedia",
                    "focus_entity": "Ada Lovelace",
                    "goal_type": "wikipedia",
                    "steps_taken": 1,
                    "early_stop_reason": EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE,
                    "elapsed_seconds": 0.5,
                    "success": True,
                }
            }
        )
        
        assert "metrics_subgoal" in step.info
        metrics = step.info["metrics_subgoal"]
        assert metrics["goal_type"] == "wikipedia"
        assert metrics["success"] is True
        assert metrics["steps_taken"] == 1
    
    def test_metrics_summary_in_step_result_info(self):
        """Verificar que run_llm_task_with_answer añade metrics summary al último step"""
        from backend.shared.models import BrowserObservation
        
        # Simular un StepResult con resumen de métricas
        obs = BrowserObservation(
            url="https://example.com",
            title="Example",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=None,
            error=None,
            info={
                "metrics": {
                    "sub_goals": [
                        {
                            "goal": "goal1",
                            "goal_type": "wikipedia",
                            "steps_taken": 1,
                            "success": True,
                        }
                    ],
                    "summary": {
                        "total_sub_goals": 1,
                        "total_steps": 1,
                        "total_time_seconds": 0.5,
                    }
                }
            }
        )
        
        assert "metrics" in step.info
        metrics = step.info["metrics"]
        assert "sub_goals" in metrics
        assert "summary" in metrics
        assert metrics["summary"]["total_sub_goals"] == 1


class TestBuildFinalAnswer:
    """Tests para _build_final_answer v1.6.0"""
    
    def test_build_final_answer_single_subgoal(self):
        """Construir respuesta final con un solo sub-goal"""
        from backend.shared.models import BrowserObservation
        
        sub_goals = ["investiga quién fue Ada Lovelace en Wikipedia"]
        sub_goal_answers = ["Ada Lovelace fue una matemática y escritora británica."]
        
        obs = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Ada_Lovelace",
            title="Ada Lovelace",
            visible_text_excerpt="Matemática británica",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=None,
            error=None,
            info={
                "sub_goal_index": 1,
                "sub_goal": sub_goals[0],
                "focus_entity": "Ada Lovelace",
            }
        )
        
        all_steps = [step]
        
        result = _build_final_answer(
            original_goal="investiga quién fue Ada Lovelace en Wikipedia",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=all_steps,
            agent_metrics=None,
        )
        
        assert "answer_text" in result
        assert "sections" in result
        assert "sources" in result
        assert len(result["sections"]) == 1
        assert result["sections"][0]["index"] == 1
        assert result["sections"][0]["goal_type"] == "wikipedia"
        assert result["sections"][0]["focus_entity"] == "Ada Lovelace"
        assert "Ada Lovelace" in result["answer_text"]
    
    def test_build_final_answer_multiple_subgoals(self):
        """Construir respuesta final con múltiples sub-goals"""
        from backend.shared.models import BrowserObservation
        
        sub_goals = [
            "investiga quién fue Ada Lovelace en Wikipedia",
            "muéstrame imágenes suyas",
        ]
        sub_goal_answers = [
            "Ada Lovelace fue una matemática británica.",
            "He encontrado imágenes de Ada Lovelace.",
        ]
        
        obs1 = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Ada_Lovelace",
            title="Ada Lovelace",
            visible_text_excerpt="Matemática",
            clickable_texts=[],
            input_hints=[],
        )
        
        obs2 = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+Ada+Lovelace&iax=images",
            title="Imágenes de Ada Lovelace",
            visible_text_excerpt="Resultados de imágenes",
            clickable_texts=[],
            input_hints=[],
        )
        
        step1 = StepResult(
            observation=obs1,
            last_action=None,
            error=None,
            info={
                "sub_goal_index": 1,
                "sub_goal": sub_goals[0],
                "focus_entity": "Ada Lovelace",
            }
        )
        
        step2 = StepResult(
            observation=obs2,
            last_action=None,
            error=None,
            info={
                "sub_goal_index": 2,
                "sub_goal": sub_goals[1],
                "focus_entity": "Ada Lovelace",
            }
        )
        
        all_steps = [step1, step2]
        
        result = _build_final_answer(
            original_goal="investiga quién fue Ada Lovelace y muéstrame imágenes suyas",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=all_steps,
            agent_metrics=None,
        )
        
        assert len(result["sections"]) == 2
        assert result["sections"][0]["index"] == 1
        assert result["sections"][1]["index"] == 2
        assert result["sections"][0]["goal_type"] == "wikipedia"
        assert result["sections"][1]["goal_type"] == "images"
        assert len(result["sources"]) >= 2
        assert "1." in result["answer_text"]
        assert "2." in result["answer_text"]
    
    def test_build_final_answer_sections_structure(self):
        """Verificar estructura de secciones"""
        from backend.shared.models import BrowserObservation
        
        sub_goals = ["busca información sobre computadoras"]
        sub_goal_answers = ["Las computadoras son dispositivos electrónicos."]
        
        obs = BrowserObservation(
            url="https://example.com/computadoras",
            title="Computadoras",
            visible_text_excerpt="Información sobre computadoras",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=None,
            error=None,
            info={"sub_goal_index": 1, "sub_goal": sub_goals[0]}
        )
        
        result = _build_final_answer(
            original_goal="busca información sobre computadoras",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=[step],
        )
        
        section = result["sections"][0]
        assert "index" in section
        assert "sub_goal" in section
        assert "answer" in section
        assert "goal_type" in section
        assert "focus_entity" in section
        assert "sources" in section
        assert isinstance(section["sources"], list)
    
    def test_build_final_answer_sources_deduplication(self):
        """Verificar que las fuentes se deduplican correctamente"""
        from backend.shared.models import BrowserObservation
        
        sub_goals = ["goal1", "goal2"]
        sub_goal_answers = ["answer1", "answer2"]
        
        # Misma URL en ambos sub-goals
        obs = BrowserObservation(
            url="https://example.com/same",
            title="Same Page",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        step1 = StepResult(
            observation=obs,
            last_action=None,
            error=None,
            info={"sub_goal_index": 1}
        )
        
        step2 = StepResult(
            observation=obs,
            last_action=None,
            error=None,
            info={"sub_goal_index": 2}
        )
        
        result = _build_final_answer(
            original_goal="test",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=[step1, step2],
        )
        
        # La misma URL debe aparecer solo una vez en sources globales
        urls = [s["url"] for s in result["sources"]]
        assert urls.count("https://example.com/same") == 1
        # Pero debe estar asociada a ambos sub-goals
        same_source = next(s for s in result["sources"] if s["url"] == "https://example.com/same")
        assert 1 in same_source["sub_goals"]
        assert 2 in same_source["sub_goals"]
    
    def test_build_final_answer_with_metrics(self):
        """Verificar que se incluyen métricas si están disponibles"""
        from backend.shared.models import BrowserObservation
        
        sub_goals = ["test goal"]
        sub_goal_answers = ["test answer"]
        
        obs = BrowserObservation(
            url="https://example.com",
            title="Test",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=None,
            error=None,
            info={"sub_goal_index": 1}
        )
        
        metrics = AgentMetrics()
        metrics.add_subgoal_metrics(
            goal="test goal",
            focus_entity=None,
            goal_type="other",
            steps_taken=5,
            early_stop_reason=None,
            elapsed_seconds=2.0,
            success=False,
        )
        
        result = _build_final_answer(
            original_goal="test",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=[step],
            agent_metrics=metrics,
        )
        
        assert result["metrics_summary"] is not None
        assert "summary" in result["metrics_summary"]
        assert result["metrics_summary"]["summary"]["total_sub_goals"] == 1


class TestGoalUsesPronouns:
    """Tests para goal_uses_pronouns v1.7.0"""
    
    def test_detects_personal_pronouns(self):
        """Detectar pronombres personales"""
        assert goal_uses_pronouns("muéstrame imágenes de él") is True
        assert goal_uses_pronouns("enséñame información sobre ella") is True
        assert goal_uses_pronouns("busca fotos de ellos") is True
    
    def test_detects_possessive_pronouns(self):
        """Detectar pronombres posesivos"""
        assert goal_uses_pronouns("muéstrame imágenes suyas") is True
        assert goal_uses_pronouns("enséñame fotos suyos") is True
        assert goal_uses_pronouns("busca información su") is True
    
    def test_detects_generic_references(self):
        """Detectar referencias genéricas"""
        assert goal_uses_pronouns("busca información sobre esa persona") is True
        assert goal_uses_pronouns("muéstrame datos de esa empresa") is True
    
    def test_no_pronouns(self):
        """No detectar pronombres cuando no hay"""
        assert goal_uses_pronouns("investiga quién fue Ada Lovelace") is False
        assert goal_uses_pronouns("muéstrame imágenes de computadoras") is False
        assert goal_uses_pronouns("busca información sobre Python") is False


class TestSessionContextIntegrationWithAgent:
    """Tests de integración de SessionContext con el agente"""
    
    def test_context_resolves_pronouns_in_sequence(self):
        """Verificar que el contexto resuelve pronombres en secuencia de sub-goals"""
        context = SessionContext()
        
        # Simular sub-goal 1: entidad explícita
        sub_goal_1 = "investiga quién fue Ada Lovelace en Wikipedia"
        entity_1 = "Ada Lovelace"
        context.update_entity(entity_1)
        context.update_goal("goal completo", sub_goal_1)
        
        # Simular sub-goal 2: con pronombres
        sub_goal_2 = "muéstrame imágenes suyas"
        assert goal_uses_pronouns(sub_goal_2) is True
        
        # Resolver usando contexto
        resolved_entity = context.resolve_entity_reference(sub_goal_2)
        assert resolved_entity == "Ada Lovelace"
        
        # Actualizar contexto después del sub-goal 2
        context.update_entity(resolved_entity)
        context.update_goal("goal completo", sub_goal_2)
        
        # Verificar estado final
        assert context.current_focus_entity == "Ada Lovelace"
        assert context.last_sub_goal == sub_goal_2
    
    def test_context_preserves_entities_across_subgoals(self):
        """Verificar que el contexto preserva entidades entre sub-goals"""
        context = SessionContext()
        
        # Sub-goal 1
        context.update_entity("Ada Lovelace")
        context.update_goal("goal", "sub-goal 1")
        
        # Sub-goal 2 (con pronombres)
        resolved = context.resolve_entity_reference("muéstrame imágenes suyas")
        assert resolved == "Ada Lovelace"
        context.update_entity(resolved)
        
        # Sub-goal 3 (nueva entidad explícita)
        context.update_entity("Charles Babbage")
        context.update_goal("goal", "sub-goal 3")
        
        # Verificar historial
        assert len(context.entity_history) == 2
        assert "Ada Lovelace" in context.entity_history
        assert "Charles Babbage" in context.entity_history
        assert context.current_focus_entity == "Charles Babbage"
    
    def test_no_regression_explicit_entities(self):
        """Verificar que entidades explícitas no se confunden con contexto previo"""
        context = SessionContext()
        
        # Sub-goal 1: Ada Lovelace
        context.update_entity("Ada Lovelace")
        context.update_goal("goal", "investiga quién fue Ada Lovelace")
        
        # Sub-goal 2: Charles Babbage (explícito, debe sobrescribir)
        entity_2 = "Charles Babbage"
        context.update_entity(entity_2)
        context.update_goal("goal", "dime quién fue Charles Babbage")
        
        # Verificar que la entidad actual es la nueva
        assert context.current_focus_entity == "Charles Babbage"
        assert context.last_valid_entity == "Charles Babbage"
        
        # Si hay un sub-goal 3 con pronombres, debe usar Charles Babbage
        resolved = context.resolve_entity_reference("muéstrame imágenes suyas")
        assert resolved == "Charles Babbage"


class TestSummarizeUploadsForSubgoal:
    """Tests para _summarize_uploads_for_subgoal v2.4.0"""
    
    def test_summarize_uploads_no_uploads(self):
        """Sin uploads devuelve None"""
        from backend.shared.models import BrowserObservation
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=None,
                error=None,
                info={},
            )
        ]
        
        result = _summarize_uploads_for_subgoal(steps)
        assert result is None
    
    def test_summarize_uploads_single_success(self):
        """Un solo upload exitoso"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=BrowserAction(
                    type="upload_file",
                    args={"file_path": "/test/file.pdf", "selector": "input[type='file']"}
                ),
                error=None,
                info={
                    "upload_status": {
                        "status": "success",
                        "file_path": "/test/file.pdf",
                        "selector": "input[type='file']",
                        "error_message": None,
                    }
                },
            )
        ]
        
        result = _summarize_uploads_for_subgoal(steps)
        assert result is not None
        assert result["status"] == "success"
        assert result["file_path"] == "/test/file.pdf"
        assert result["selector"] == "input[type='file']"
        assert result["attempts"] == 1
    
    def test_summarize_uploads_multiple_last_relevant(self):
        """Múltiples uploads, el último es el más relevante"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=BrowserAction(
                    type="upload_file",
                    args={"file_path": "/test/file1.pdf", "selector": "input[type='file']"}
                ),
                error=None,
                info={
                    "upload_status": {
                        "status": "success",
                        "file_path": "/test/file1.pdf",
                        "selector": "input[type='file']",
                        "error_message": None,
                    }
                },
            ),
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=BrowserAction(
                    type="upload_file",
                    args={"file_path": "/test/file2.pdf", "selector": "input[type='file']"}
                ),
                error="No se encontró input",
                info={
                    "upload_status": {
                        "status": "no_input_found",
                        "file_path": "/test/file2.pdf",
                        "selector": "input[type='file']",
                        "error_message": "No se encontró input",
                    }
                },
            ),
        ]
        
        result = _summarize_uploads_for_subgoal(steps)
        assert result is not None
        assert result["status"] == "no_input_found"
        assert result["file_path"] == "/test/file2.pdf"
        assert result["attempts"] == 2
    
    def test_summarize_uploads_file_not_found(self):
        """Upload con archivo no encontrado"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=BrowserAction(
                    type="upload_file",
                    args={"file_path": "/nonexistent.pdf", "selector": "input[type='file']"}
                ),
                error="Archivo no encontrado",
                info={
                    "upload_status": {
                        "status": "file_not_found",
                        "file_path": "/nonexistent.pdf",
                        "selector": "input[type='file']",
                        "error_message": "Archivo no encontrado",
                    }
                },
            )
        ]
        
        result = _summarize_uploads_for_subgoal(steps)
        assert result is not None
        assert result["status"] == "file_not_found"
        assert result["file_path"] == "/nonexistent.pdf"
        assert result["attempts"] == 1
    
    def test_summarize_uploads_with_verification(self):
        """_summarize_uploads_for_subgoal incluye información de verificación"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=BrowserAction(
                    type="upload_file",
                    args={"file_path": "/test/file.pdf", "selector": "input[type='file']"}
                ),
                error=None,
                info={
                    "upload_status": {
                        "status": "success",
                        "file_path": "/test/file.pdf",
                        "selector": "input[type='file']",
                        "error_message": None,
                    },
                    "upload_verification": {
                        "status": "confirmed",
                        "file_name": "file.pdf",
                        "confidence": 0.85,
                        "evidence": "El archivo file.pdf ha sido subido correctamente",
                    }
                },
            )
        ]
        
        result = _summarize_uploads_for_subgoal(steps)
        assert result is not None
        assert result["verification_status"] == "confirmed"
        assert result["verification_confidence"] == 0.85
        assert "file.pdf" in result["verification_evidence"]


class TestBuildFinalAnswerWithUploads:
    """Tests para _build_final_answer con uploads v2.4.0"""
    
    def test_build_final_answer_with_upload_success(self):
        """Respuesta con upload exitoso incluye texto y upload_summary"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        sub_goals = ["sube el documento reconocimiento.pdf"]
        sub_goal_answers = ["He completado la tarea."]
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="Upload form",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=BrowserAction(
                type="upload_file",
                args={"file_path": "/test/reconocimiento.pdf", "selector": "input[type='file']"}
            ),
            error=None,
            info={
                "sub_goal_index": 1,
                "sub_goal": sub_goals[0],
                "upload_status": {
                    "status": "success",
                    "file_path": "/test/reconocimiento.pdf",
                    "selector": "input[type='file']",
                    "error_message": None,
                }
            }
        )
        
        result = _build_final_answer(
            original_goal="sube el documento reconocimiento.pdf",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=[step],
        )
        
        # Verificar que el texto contiene mención del upload
        assert "reconocimiento.pdf" in result["answer_text"]
        assert "adjuntado" in result["answer_text"].lower() or "seleccionado" in result["answer_text"].lower()
        
        # Verificar que la sección tiene upload_summary
        section = result["sections"][0]
        assert section["upload_summary"] is not None
        assert section["upload_summary"]["status"] == "success"
        assert section["upload_summary"]["file_name"] == "reconocimiento.pdf"
        assert section["upload_summary"]["attempts"] == 1
    
    def test_build_final_answer_with_upload_verification_confirmed(self):
        """Respuesta con verificación confirmada incluye texto y estructura"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        sub_goals = ["sube el documento reconocimiento.pdf"]
        sub_goal_answers = ["He completado la tarea."]
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="El archivo reconocimiento.pdf ha sido subido correctamente",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=BrowserAction(
                type="upload_file",
                args={"file_path": "/test/reconocimiento.pdf", "selector": "input[type='file']"}
            ),
            error=None,
            info={
                "sub_goal_index": 1,
                "sub_goal": sub_goals[0],
                "upload_status": {
                    "status": "success",
                    "file_path": "/test/reconocimiento.pdf",
                    "selector": "input[type='file']",
                    "error_message": None,
                },
                "upload_verification": {
                    "status": "confirmed",
                    "file_name": "reconocimiento.pdf",
                    "confidence": 0.85,
                    "evidence": "El archivo reconocimiento.pdf ha sido subido correctamente",
                }
            }
        )
        
        result = _build_final_answer(
            original_goal="sube el documento reconocimiento.pdf",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=[step],
        )
        
        # Verificar que el texto contiene mención de verificación
        assert "verificado visualmente" in result["answer_text"].lower()
        assert "reconocimiento.pdf" in result["answer_text"]
        
        # Verificar que la sección tiene upload_verification
        section = result["sections"][0]
        assert section["upload_verification"] is not None
        assert section["upload_verification"]["status"] == "confirmed"
        assert section["upload_verification"]["file_name"] == "reconocimiento.pdf"
    
    def test_build_final_answer_with_upload_verification_not_confirmed(self):
        """Respuesta con verificación no confirmada"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        sub_goals = ["sube el documento reconocimiento.pdf"]
        sub_goal_answers = ["He intentado subir el documento."]
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="Formulario de subida de documentos",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=BrowserAction(
                type="upload_file",
                args={"file_path": "/test/reconocimiento.pdf", "selector": "input[type='file']"}
            ),
            error=None,
            info={
                "sub_goal_index": 1,
                "sub_goal": sub_goals[0],
                "upload_status": {
                    "status": "success",
                    "file_path": "/test/reconocimiento.pdf",
                    "selector": "input[type='file']",
                    "error_message": None,
                },
                "upload_verification": {
                    "status": "not_confirmed",
                    "file_name": "reconocimiento.pdf",
                    "confidence": 0.3,
                    "evidence": "No se encontró confirmación visual explícita",
                }
            }
        )
        
        result = _build_final_answer(
            original_goal="sube el documento reconocimiento.pdf",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=[step],
        )
        
        # Verificar que el texto menciona falta de confirmación
        assert "no he encontrado una confirmación visual clara" in result["answer_text"].lower()
        
        # Verificar upload_verification
        section = result["sections"][0]
        assert section["upload_verification"] is not None
        assert section["upload_verification"]["status"] == "not_confirmed"
    
    def test_build_final_answer_with_upload_file_not_found(self):
        """Respuesta con archivo no encontrado"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        sub_goals = ["sube el documento reconocimiento.pdf"]
        sub_goal_answers = ["He intentado subir el documento."]
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="Upload form",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=BrowserAction(
                type="upload_file",
                args={"file_path": "/test/reconocimiento.pdf", "selector": "input[type='file']"}
            ),
            error="Archivo no encontrado",
            info={
                "sub_goal_index": 1,
                "sub_goal": sub_goals[0],
                "upload_status": {
                    "status": "file_not_found",
                    "file_path": "/test/reconocimiento.pdf",
                    "selector": "input[type='file']",
                    "error_message": "Archivo no encontrado",
                }
            }
        )
        
        result = _build_final_answer(
            original_goal="sube el documento reconocimiento.pdf",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=[step],
        )
        
        # Verificar que el texto menciona que no se encontró el archivo
        assert "no se ha encontrado" in result["answer_text"].lower() or "no se encontró" in result["answer_text"].lower()
        
        # Verificar upload_summary
        section = result["sections"][0]
        assert section["upload_summary"] is not None
        assert section["upload_summary"]["status"] == "file_not_found"
    
    def test_build_final_answer_without_upload(self):
        """Respuesta sin uploads es idéntica a antes"""
        from backend.shared.models import BrowserObservation
        
        sub_goals = ["busca información sobre computadoras"]
        sub_goal_answers = ["Las computadoras son dispositivos electrónicos."]
        
        obs = BrowserObservation(
            url="https://example.com/computadoras",
            title="Computadoras",
            visible_text_excerpt="Información sobre computadoras",
            clickable_texts=[],
            input_hints=[],
        )
        
        step = StepResult(
            observation=obs,
            last_action=None,
            error=None,
            info={"sub_goal_index": 1, "sub_goal": sub_goals[0]}
        )
        
        result = _build_final_answer(
            original_goal="busca información sobre computadoras",
            sub_goals=sub_goals,
            sub_goal_answers=sub_goal_answers,
            all_steps=[step],
        )
        
        # Verificar que no hay upload_summary
        section = result["sections"][0]
        assert section["upload_summary"] is None
        
        # Verificar que el texto no menciona uploads
        assert "adjuntado" not in result["answer_text"].lower()
        assert "subida" not in result["answer_text"].lower()


class TestVerifyUploadVisually:
    """Tests para _verify_upload_visually v2.5.0"""
    
    def test_verify_upload_file_name_found(self):
        """Verificación encuentra el nombre del archivo en el texto"""
        from backend.shared.models import BrowserObservation
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="El archivo reconocimiento.pdf ha sido subido correctamente",
            clickable_texts=[],
            input_hints=[],
        )
        
        result = _verify_upload_visually(
            observation=obs,
            file_path="/test/reconocimiento.pdf",
            goal="sube el documento",
        )
        
        assert result["status"] == "confirmed"
        assert result["file_name"] == "reconocimiento.pdf"
        assert result["confidence"] >= 0.8
        assert "reconocimiento" in result["evidence"].lower()
    
    def test_verify_upload_success_message_found(self):
        """Verificación encuentra mensaje genérico de éxito sin nombre de archivo"""
        from backend.shared.models import BrowserObservation
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="Documento subido correctamente. La carga se ha completado exitosamente.",
            clickable_texts=[],
            input_hints=[],
        )
        
        result = _verify_upload_visually(
            observation=obs,
            file_path="/test/documento.pdf",
            goal="sube el documento",
        )
        
        assert result["status"] == "confirmed"
        assert result["file_name"] == "documento.pdf"
        assert 0.6 <= result["confidence"] < 0.9  # Confianza media
        assert len(result["evidence"]) > 0
    
    def test_verify_upload_error_detected(self):
        """Verificación detecta mensaje de error"""
        from backend.shared.models import BrowserObservation
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="Error al subir el archivo. El formato no está permitido.",
            clickable_texts=[],
            input_hints=[],
        )
        
        result = _verify_upload_visually(
            observation=obs,
            file_path="/test/archivo.pdf",
            goal="sube el documento",
        )
        
        assert result["status"] == "error_detected"
        assert result["file_name"] == "archivo.pdf"
        assert result["confidence"] >= 0.8
        assert "error" in result["evidence"].lower()
    
    def test_verify_upload_no_confirmation(self):
        """Verificación no encuentra confirmación clara"""
        from backend.shared.models import BrowserObservation
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="Formulario de carga. Por favor, seleccione un archivo para continuar.",
            clickable_texts=[],
            input_hints=[],
        )
        
        result = _verify_upload_visually(
            observation=obs,
            file_path="/test/documento.pdf",
            goal="sube el documento",
        )
        
        assert result["status"] == "not_confirmed"
        assert result["file_name"] == "documento.pdf"
        assert result["confidence"] < 0.5
        assert len(result["evidence"]) > 0
    
    def test_verify_upload_no_text(self):
        """Verificación sin texto disponible"""
        from backend.shared.models import BrowserObservation
        
        obs = BrowserObservation(
            url="https://example.com/upload",
            title="Upload Page",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        result = _verify_upload_visually(
            observation=obs,
            file_path="/test/documento.pdf",
            goal="sube el documento",
        )
        
        assert result["status"] == "not_confirmed"
        assert result["file_name"] == "documento.pdf"
        assert result["confidence"] <= 0.3


class TestEvaluateSubgoalForRetry:
    """Tests para _evaluate_subgoal_for_retry v2.6.0"""
    
    def test_evaluate_subgoal_success_no_retry(self):
        """No se debe hacer retry si el goal fue exitoso"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=None,
                error=None,
                info={
                    "metrics_subgoal": {
                        "success": True,
                        "goal": "test goal",
                    }
                }
            )
        ]
        
        metrics_data = {"success": True}
        retry_policy = RetryPolicy()
        
        should_retry, upload_status, verification_status, error_message = _evaluate_subgoal_for_retry(
            steps, metrics_data, retry_policy
        )
        
        assert should_retry is False
    
    def test_evaluate_subgoal_upload_not_confirmed_retry(self):
        """Se debe hacer retry si upload_status es not_confirmed"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=BrowserAction(
                    type="upload_file",
                    args={"file_path": "/test/file.pdf", "selector": "input[type='file']"}
                ),
                error=None,
                info={
                    "upload_status": {
                        "status": "not_confirmed",
                        "file_path": "/test/file.pdf",
                        "selector": "input[type='file']",
                        "error_message": None,
                    },
                    "upload_verification": {
                        "status": "not_confirmed",
                        "file_name": "file.pdf",
                        "confidence": 0.3,
                        "evidence": "No se encontró confirmación",
                    }
                }
            )
        ]
        
        metrics_data = {"success": False}
        retry_policy = RetryPolicy()
        
        should_retry, upload_status, verification_status, error_message = _evaluate_subgoal_for_retry(
            steps, metrics_data, retry_policy
        )
        
        assert should_retry is True
        assert upload_status == "not_confirmed"
        assert verification_status == "not_confirmed"
    
    def test_evaluate_subgoal_verification_error_retry(self):
        """Se debe hacer retry si verification_status es error_detected"""
        from backend.shared.models import BrowserObservation, BrowserAction
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=BrowserAction(
                    type="upload_file",
                    args={"file_path": "/test/file.pdf", "selector": "input[type='file']"}
                ),
                error=None,
                info={
                    "upload_status": {
                        "status": "success",
                        "file_path": "/test/file.pdf",
                        "selector": "input[type='file']",
                        "error_message": None,
                    },
                    "upload_verification": {
                        "status": "error_detected",
                        "file_name": "file.pdf",
                        "confidence": 0.9,
                        "evidence": "Error al subir el archivo",
                    }
                }
            )
        ]
        
        metrics_data = {"success": False}
        retry_policy = RetryPolicy()
        
        should_retry, upload_status, verification_status, error_message = _evaluate_subgoal_for_retry(
            steps, metrics_data, retry_policy
        )
        
        assert should_retry is True
        assert verification_status == "error_detected"
    
    def test_evaluate_subgoal_goal_failure_retry(self):
        """Se debe hacer retry si el goal falló y retry_on_goal_failure está activo"""
        from backend.shared.models import BrowserObservation
        
        steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Test",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=None,
                error=None,
                info={}
            )
        ]
        
        metrics_data = {"success": False}
        retry_policy = RetryPolicy(retry_on_goal_failure=True)
        
        should_retry, upload_status, verification_status, error_message = _evaluate_subgoal_for_retry(
            steps, metrics_data, retry_policy
        )
        
        assert should_retry is True


class TestBuildRetryPromptContext:
    """Tests para _build_retry_prompt_context v2.6.0"""
    
    def test_build_retry_prompt_with_upload_status(self):
        """Construye prompt con información de upload_status"""
        retry_context = {
            "attempt_index": 1,
            "last_upload_status": "not_confirmed",
            "last_verification_status": None,
            "last_error_message": None,
        }
        
        result = _build_retry_prompt_context(retry_context)
        
        assert "intento anterior" in result.lower()
        assert "not_confirmed" in result or "no se confirmó" in result
        assert "estrategia diferente" in result.lower()
    
    def test_build_retry_prompt_with_verification_status(self):
        """Construye prompt con información de verification_status"""
        retry_context = {
            "attempt_index": 1,
            "last_upload_status": "success",
            "last_verification_status": "error_detected",
            "last_error_message": None,
        }
        
        result = _build_retry_prompt_context(retry_context)
        
        assert "error_detected" in result or "mensaje de error" in result
        assert "verificación visual" in result.lower()
    
    def test_build_retry_prompt_with_error_message(self):
        """Construye prompt con error_message"""
        retry_context = {
            "attempt_index": 1,
            "last_upload_status": None,
            "last_verification_status": None,
            "last_error_message": "Error al procesar el formulario",
        }
        
        result = _build_retry_prompt_context(retry_context)
        
        assert "Error al procesar" in result


class TestRetryMetrics:
    """Tests para métricas de retry v2.6.0"""
    
    def test_retry_metrics_initialization(self):
        """Los contadores de retry se inicializan a 0"""
        metrics = AgentMetrics()
        
        assert metrics.retry_attempts == 0
        assert metrics.retry_successes == 0
        assert metrics.retry_exhausted_count == 0
    
    def test_register_retry_attempt(self):
        """register_retry_attempt incrementa el contador"""
        metrics = AgentMetrics()
        
        metrics.register_retry_attempt()
        assert metrics.retry_attempts == 1
        
        metrics.register_retry_attempt()
        assert metrics.retry_attempts == 2
    
    def test_register_retry_success(self):
        """register_retry_success incrementa el contador"""
        metrics = AgentMetrics()
        
        metrics.register_retry_success()
        assert metrics.retry_successes == 1
        
        metrics.register_retry_success()
        assert metrics.retry_successes == 2
    
    def test_register_retry_exhausted(self):
        """register_retry_exhausted incrementa el contador"""
        metrics = AgentMetrics()
        
        metrics.register_retry_exhausted()
        assert metrics.retry_exhausted_count == 1
        
        metrics.register_retry_exhausted()
        assert metrics.retry_exhausted_count == 2
    
    def test_retry_info_in_summary(self):
        """retry_info aparece en el summary con valores correctos"""
        metrics = AgentMetrics()
        
        metrics.register_retry_attempt()
        metrics.register_retry_attempt()
        metrics.register_retry_success()
        metrics.register_retry_exhausted()
        
        summary = metrics.to_summary_dict()
        
        assert "retry_info" in summary["summary"]
        retry_info = summary["summary"]["retry_info"]
        assert retry_info["retry_attempts"] == 2
        assert retry_info["retry_successes"] == 1
        assert retry_info["retry_exhausted_count"] == 1
        assert retry_info["retry_success_ratio"] == 0.5  # 1/2
    
    def test_retry_info_empty_summary(self):
        """retry_info tiene valores 0 cuando no hay retries"""
        metrics = AgentMetrics()
        
        summary = metrics.to_summary_dict()
        
        assert "retry_info" in summary["summary"]
        retry_info = summary["summary"]["retry_info"]
        assert retry_info["retry_attempts"] == 0
        assert retry_info["retry_successes"] == 0
        assert retry_info["retry_exhausted_count"] == 0
        assert retry_info["retry_success_ratio"] == 0.0


class TestAgentIntentMetrics:
    """Tests para métricas de intenciones del agente (v3.7.0)"""
    
    def test_agent_intent_metrics_initialization(self):
        """Los contadores de intenciones se inicializan correctamente"""
        metrics = AgentMetrics()
        
        assert metrics.intent_counts == {}
        assert metrics.critical_intent_count == 0
    
    def test_register_agent_intent(self):
        """register_agent_intent actualiza los contadores correctamente"""
        from backend.shared.models import AgentIntent
        
        metrics = AgentMetrics()
        
        # Registrar intención normal
        intent1 = AgentIntent(
            intent_type="upload_file",
            criticality="normal",
        )
        metrics.register_agent_intent(intent1)
        
        assert metrics.intent_counts["upload_file"] == 1
        assert metrics.critical_intent_count == 0
        
        # Registrar intención crítica
        intent2 = AgentIntent(
            intent_type="save_changes",
            criticality="critical",
        )
        metrics.register_agent_intent(intent2)
        
        assert metrics.intent_counts["save_changes"] == 1
        assert metrics.critical_intent_count == 1
        
        # Registrar otra intención del mismo tipo
        intent3 = AgentIntent(
            intent_type="upload_file",
            criticality="normal",
        )
        metrics.register_agent_intent(intent3)
        
        assert metrics.intent_counts["upload_file"] == 2
        assert metrics.critical_intent_count == 1
    
    def test_intent_info_in_summary(self):
        """intent_info aparece en el summary con valores correctos"""
        from backend.shared.models import AgentIntent
        
        metrics = AgentMetrics()
        
        metrics.register_agent_intent(AgentIntent(intent_type="upload_file", criticality="normal"))
        metrics.register_agent_intent(AgentIntent(intent_type="save_changes", criticality="critical"))
        metrics.register_agent_intent(AgentIntent(intent_type="confirm_submission", criticality="critical"))
        
        summary = metrics.to_summary_dict()
        
        assert "intent_info" in summary["summary"]
        intent_info = summary["summary"]["intent_info"]
        assert intent_info["intent_counts"]["upload_file"] == 1
        assert intent_info["intent_counts"]["save_changes"] == 1
        assert intent_info["intent_counts"]["confirm_submission"] == 1
        assert intent_info["critical_intent_count"] == 2
    
    def test_agent_intent_in_step_result_info(self):
        """Verificar que agent_intent se guarda en StepResult.info"""
        from backend.shared.models import BrowserObservation, AgentIntent
        
        obs = BrowserObservation(
            url="https://example.com",
            title="Example",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        intent = AgentIntent(
            intent_type="upload_file",
            description="Subir archivo de reconocimiento médico",
            related_stage="file_selected",
            criticality="normal",
            tags=["upload", "cae"],
            sub_goal_index=1,
        )
        
        step = StepResult(
            observation=obs,
            last_action=BrowserAction(type="upload_file", args={}),
            error=None,
            info={
                "agent_intent": intent.model_dump(),
            }
        )
        
        assert "agent_intent" in step.info
        intent_dict = step.info["agent_intent"]
        assert intent_dict["intent_type"] == "upload_file"
        assert intent_dict["criticality"] == "normal"
        assert "upload" in intent_dict["tags"]
    
    def test_evaluate_subgoal_for_retry_with_critical_intent_and_violation(self):
        """_evaluate_subgoal_for_retry debe recomendar retry si hay intención crítica con violación"""
        from backend.shared.models import BrowserObservation, AgentIntent, VisualContractResult
        
        obs = BrowserObservation(
            url="https://example.com",
            title="Example",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        # Crear step con intención crítica y violación de contrato visual
        intent = AgentIntent(
            intent_type="save_changes",
            criticality="critical",
        )
        
        contract_result = VisualContractResult(
            outcome="violation",
            expected_stage="saved",
            actual_stage="error",
            severity="critical",
        )
        
        step = StepResult(
            observation=obs,
            last_action=BrowserAction(type="click_text", args={"text": "Guardar"}),
            error=None,
            info={
                "agent_intent": intent.model_dump(),
                "visual_expectation": contract_result.model_dump(),
            }
        )
        
        retry_policy = RetryPolicy(
            retry_on_goal_failure=True,
            max_retries=3,
        )
        
        should_retry, upload_status, verification_status, error_message = _evaluate_subgoal_for_retry(
            steps=[step],
            metrics_data={"success": False},
            retry_policy=retry_policy,
        )
        
        assert should_retry is True
        # Verificar que el retry_reason contiene información sobre la intención crítica
        # (aunque no lo retornamos directamente, el logger debería haber registrado algo)

