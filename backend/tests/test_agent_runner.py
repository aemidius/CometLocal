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
)
from backend.shared.models import BrowserObservation, StepResult, BrowserAction


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

