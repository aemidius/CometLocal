"""
Tests unitarios para agent_runner.py v1.4.8

Cubre:
- _build_image_search_query
- _goal_is_satisfied para objetivos de imágenes
- Motivos de early-stop
"""
import pytest
from backend.agents.agent_runner import (
    _build_image_search_query,
    _goal_is_satisfied,
    EarlyStopReason,
    _normalize_text_for_comparison,
)
from backend.shared.models import BrowserObservation


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

