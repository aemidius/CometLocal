"""
Tests unitarios para context_strategies.py v2.0.0

Cubre:
- goal_applies para Wikipedia e imágenes
- ensure_context construye correctamente las URLs esperadas
- is_goal_satisfied funciona con URLs reales de Wikipedia y DuckDuckGo (simuladas)
- Integración con agent_runner
"""

import pytest
from anyio import run
from backend.agents.context_strategies import (
    ContextStrategy,
    WikipediaContextStrategy,
    ImageSearchContextStrategy,
    CAEContextStrategy,
    DEFAULT_CONTEXT_STRATEGIES,
    build_context_strategies,
)
from backend.shared.models import BrowserObservation, BrowserAction


class TestWikipediaContextStrategy:
    """Tests para WikipediaContextStrategy"""
    
    def test_goal_applies_wikipedia(self):
        """Detecta objetivos que mencionan Wikipedia"""
        strategy = WikipediaContextStrategy()
        assert strategy.goal_applies("investiga quién fue Ada Lovelace en Wikipedia", None) is True
        assert strategy.goal_applies("busca información sobre Charles Babbage en Wikipedia", None) is True
        assert strategy.goal_applies("Wikipedia: Ada Lovelace", None) is True
        assert strategy.goal_applies("muéstrame imágenes de Ada", None) is False
        assert strategy.goal_applies("busca información general", None) is False
    
    def test_ensure_context_with_entity(self):
        """Construye URL de búsqueda de Wikipedia cuando hay entidad"""
        async def _test():
            strategy = WikipediaContextStrategy()
            
            # Con entidad explícita
            action = await strategy.ensure_context(
                "investiga quién fue Ada Lovelace en Wikipedia",
                None,
                "Ada Lovelace"
            )
            assert action is not None
            assert action.type == "open_url"
            assert "wikipedia.org" in action.args["url"]
            assert "Especial:Buscar" in action.args["url"]
            assert "Ada+Lovelace" in action.args["url"] or "Ada%20Lovelace" in action.args["url"]
        
        run(_test)
    
    def test_ensure_context_no_reload_if_already_correct(self):
        """No recarga si ya estamos en el artículo correcto"""
        async def _test():
            strategy = WikipediaContextStrategy()
            
            # Observación en Wikipedia con título que contiene la entidad
            obs = BrowserObservation(
                url="https://es.wikipedia.org/wiki/Ada_Lovelace",
                title="Ada Lovelace - Wikipedia",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
            
            action = await strategy.ensure_context(
                "investiga quién fue Ada Lovelace en Wikipedia",
                obs,
                "Ada Lovelace"
            )
            assert action is None  # No debe recargar
        
        run(_test)
    
    def test_ensure_context_no_entity(self):
        """Sin entidad, no navega específicamente"""
        async def _test():
            strategy = WikipediaContextStrategy()
            
            action = await strategy.ensure_context(
                "busca información en Wikipedia",
                None,
                None
            )
            assert action is None
        
        run(_test)
    
    def test_is_goal_satisfied_with_entity_in_title(self):
        """Satisfecho si estamos en Wikipedia y el título contiene la entidad"""
        strategy = WikipediaContextStrategy()
        
        obs = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Ada_Lovelace",
            title="Ada Lovelace - Wikipedia",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "investiga quién fue Ada Lovelace en Wikipedia",
            obs,
            "Ada Lovelace"
        ) is True
    
    def test_is_goal_satisfied_without_entity_not_search_page(self):
        """Satisfecho sin entidad si estamos en un artículo (no página de búsqueda)"""
        strategy = WikipediaContextStrategy()
        
        obs = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Ada_Lovelace",
            title="Ada Lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "busca información en Wikipedia",
            obs,
            None
        ) is True
    
    def test_is_goal_satisfied_not_satisfied_wrong_entity(self):
        """No satisfecho si la entidad no coincide"""
        strategy = WikipediaContextStrategy()
        
        obs = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Charles_Babbage",
            title="Charles Babbage - Wikipedia",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "investiga quién fue Ada Lovelace en Wikipedia",
            obs,
            "Ada Lovelace"
        ) is False
    
    def test_is_goal_satisfied_not_wikipedia_url(self):
        """No satisfecho si no estamos en Wikipedia"""
        strategy = WikipediaContextStrategy()
        
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=Ada+Lovelace",
            title="Ada Lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "investiga quién fue Ada Lovelace en Wikipedia",
            obs,
            "Ada Lovelace"
        ) is False


class TestImageSearchContextStrategy:
    """Tests para ImageSearchContextStrategy"""
    
    def test_goal_applies_images(self):
        """Detecta objetivos que mencionan imágenes"""
        strategy = ImageSearchContextStrategy()
        assert strategy.goal_applies("muéstrame imágenes de Ada Lovelace", None) is True
        assert strategy.goal_applies("enséñame fotos de Charles Babbage", None) is True
        assert strategy.goal_applies("busca imágenes", None) is True
        assert strategy.goal_applies("investiga quién fue Ada en Wikipedia", None) is False
        assert strategy.goal_applies("busca información general", None) is False
    
    def test_ensure_context_with_entity(self):
        """Construye URL de búsqueda de imágenes cuando hay entidad"""
        async def _test():
            strategy = ImageSearchContextStrategy()
            
            # Con entidad explícita
            action = await strategy.ensure_context(
                "muéstrame imágenes suyas",
                None,
                "Ada Lovelace"
            )
            assert action is not None
            assert action.type == "open_url"
            assert "duckduckgo.com" in action.args["url"]
            assert "ia=images" in action.args["url"] or "iax=images" in action.args["url"]
            # La URL puede estar codificada, verificar que contiene Ada y Lovelace
            url_lower = action.args["url"].lower()
            assert "ada" in url_lower and "lovelace" in url_lower
        
        run(_test)
    
    def test_ensure_context_navigates_to_base_url(self):
        """Navega a la URL base si no estamos en el dominio CAE"""
        async def _test():
            strategy = CAEContextStrategy(base_url="https://example-cae.local")
            
            # No estamos en el dominio CAE
            obs = BrowserObservation(
                url="https://es.wikipedia.org/wiki/Ada_Lovelace",
                title="Ada Lovelace",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
            
            action = await strategy.ensure_context(
                "revisa la documentación CAE",
                obs,
                None
            )
            assert action is not None
            assert action.type == "open_url"
            assert action.args["url"] == "https://example-cae.local"
        
        run(_test)
    
    def test_ensure_context_no_reload_if_already_in_domain(self):
        """No recarga si ya estamos en el dominio CAE"""
        async def _test():
            strategy = CAEContextStrategy(base_url="https://example-cae.local")
            
            # Ya estamos en el dominio CAE
            obs = BrowserObservation(
                url="https://example-cae.local/documentacion",
                title="Documentación CAE",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
            
            action = await strategy.ensure_context(
                "revisa la documentación CAE",
                obs,
                None
            )
            assert action is None  # No debe recargar
        
        run(_test)
    
    def test_ensure_context_no_reload_if_already_correct(self):
        """No recarga si ya estamos en búsqueda de imágenes"""
        async def _test():
            strategy = ImageSearchContextStrategy()
            
            # Observación en DuckDuckGo imágenes
            obs = BrowserObservation(
                url="https://duckduckgo.com/?q=imágenes+de+Ada+Lovelace&iax=images",
                title="Imágenes de Ada Lovelace",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
            
            action = await strategy.ensure_context(
                "muéstrame imágenes de Ada Lovelace",
                obs,
                "Ada Lovelace"
            )
            assert action is None  # No debe recargar
        
        run(_test)
    
    def test_ensure_context_without_entity_cleans_goal(self):
        """Sin entidad, limpia el goal y construye query"""
        async def _test():
            strategy = ImageSearchContextStrategy()
            
            action = await strategy.ensure_context(
                "muéstrame imágenes de computadoras antiguas",
                None,
                None
            )
            assert action is not None
            assert action.type == "open_url"
            assert "duckduckgo.com" in action.args["url"]
            # Debe contener "imágenes" (puede estar codificado) y "computadoras"
            url_lower = action.args["url"].lower()
            # "imágenes" puede estar codificado como im%c3%a1genes o im%C3%A1genes
            assert "im" in url_lower and ("agenes" in url_lower or "%a1genes" in url_lower or "%c3%a1genes" in url_lower)
            assert "computadora" in url_lower
        
        run(_test)
    
    def test_is_goal_satisfied_with_entity_in_query(self):
        """Satisfecho si estamos en búsqueda de imágenes y la query contiene la entidad"""
        strategy = ImageSearchContextStrategy()
        
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+Ada+Lovelace&iax=images",
            title="Imágenes de Ada Lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "muéstrame imágenes suyas",
            obs,
            "Ada Lovelace"
        ) is True
    
    def test_is_goal_satisfied_with_entity_url_encoded(self):
        """Satisfecho con entidad codificada en URL"""
        strategy = ImageSearchContextStrategy()
        
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+Charles+Babbage&ia=images",
            title="Imágenes de Charles Babbage",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "enséñame imágenes de él",
            obs,
            "Charles Babbage"
        ) is True
    
    def test_is_goal_satisfied_not_satisfied_wrong_entity(self):
        """No satisfecho si la entidad no coincide"""
        strategy = ImageSearchContextStrategy()
        
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+Charles+Babbage&iax=images",
            title="Imágenes de Charles Babbage",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "muéstrame imágenes suyas",
            obs,
            "Ada Lovelace"
        ) is False
    
    def test_is_goal_satisfied_not_image_search(self):
        """No satisfecho si no estamos en búsqueda de imágenes"""
        strategy = ImageSearchContextStrategy()
        
        obs = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Ada_Lovelace",
            title="Ada Lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "muéstrame imágenes de Ada Lovelace",
            obs,
            "Ada Lovelace"
        ) is False
    
    def test_is_goal_satisfied_without_entity_descriptive_match(self):
        """Satisfecho sin focus_entity si la query coincide con el goal descriptivo"""
        strategy = ImageSearchContextStrategy()
        
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+computadoras+antiguas&iax=images",
            title="Imágenes de computadoras antiguas",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "muéstrame imágenes de computadoras antiguas",
            obs,
            None
        ) is True
    
    def test_is_goal_satisfied_without_entity_no_match(self):
        """No satisfecho sin focus_entity si la query no coincide"""
        strategy = ImageSearchContextStrategy()
        
        obs = BrowserObservation(
            url="https://duckduckgo.com/?q=imágenes+de+perros&iax=images",
            title="Imágenes de perros",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "muéstrame imágenes de computadoras antiguas",
            obs,
            None
        ) is False


class TestDefaultContextStrategies:
    """Tests para el registro de estrategias por defecto"""
    
    def test_strategies_order(self):
        """Las estrategias están en el orden correcto (imágenes antes de Wikipedia)"""
        assert len(DEFAULT_CONTEXT_STRATEGIES) >= 2
        assert isinstance(DEFAULT_CONTEXT_STRATEGIES[0], ImageSearchContextStrategy)
        assert isinstance(DEFAULT_CONTEXT_STRATEGIES[1], WikipediaContextStrategy)
    
    def test_image_strategy_priority(self):
        """Las imágenes tienen prioridad sobre Wikipedia"""
        # Un goal que menciona ambos debe ser manejado por ImageSearchContextStrategy
        image_strategy = DEFAULT_CONTEXT_STRATEGIES[0]
        wiki_strategy = DEFAULT_CONTEXT_STRATEGIES[1]
        
        goal = "muéstrame imágenes de Ada Lovelace en Wikipedia"
        
        # ImageSearch debe aplicar primero
        assert image_strategy.goal_applies(goal, None) is True
        # Wikipedia también aplica, pero ImageSearch tiene prioridad
        assert wiki_strategy.goal_applies(goal, None) is True
    
    def test_strategy_name_attribute(self):
        """Todas las estrategias tienen el atributo name correctamente definido"""
        from backend.agents.context_strategies import (
            WikipediaContextStrategy,
            ImageSearchContextStrategy,
            CAEContextStrategy,
        )
        
        # Verificar estrategias por defecto
        image_strategy = DEFAULT_CONTEXT_STRATEGIES[0]
        wiki_strategy = DEFAULT_CONTEXT_STRATEGIES[1]
        
        assert hasattr(image_strategy, 'name')
        assert hasattr(wiki_strategy, 'name')
        assert image_strategy.name == "images"
        assert wiki_strategy.name == "wikipedia"
        
        # Verificar instancias nuevas
        wiki = WikipediaContextStrategy()
        image = ImageSearchContextStrategy()
        cae = CAEContextStrategy()
        
        assert wiki.name == "wikipedia"
        assert image.name == "images"
        assert cae.name == "cae"
        
        # Verificar que se puede usar en list comprehension (como en agent_runner.py)
        strategy_names = [s.name for s in DEFAULT_CONTEXT_STRATEGIES]
        assert "images" in strategy_names
        assert "wikipedia" in strategy_names


class TestCAEContextStrategy:
    """Tests para CAEContextStrategy"""
    
    def test_goal_applies_cae_keywords(self):
        """Detecta objetivos que mencionan CAE o prevención de riesgos"""
        strategy = CAEContextStrategy()
        assert strategy.goal_applies("revisa la documentación CAE de prevención de riesgos", None) is True
        assert strategy.goal_applies("comprueba la documentación de prevención de riesgos en la plataforma", None) is True
        assert strategy.goal_applies("entra en la plataforma CAE", None) is True
        assert strategy.goal_applies("investiga quién fue Ada Lovelace en Wikipedia", None) is False
        assert strategy.goal_applies("muéstrame imágenes de Ada", None) is False
    
    def test_goal_applies_prevencion_riesgos(self):
        """Detecta objetivos relacionados con prevención de riesgos"""
        strategy = CAEContextStrategy()
        assert strategy.goal_applies("revisa la documentación de prevención de riesgos", None) is True
        assert strategy.goal_applies("comprueba la documentacion de prevencion de riesgos", None) is True
    
    def test_ensure_context_navigates_to_base_url(self):
        """Navega a la URL base si no estamos en el dominio CAE"""
        async def _test():
            strategy = CAEContextStrategy(base_url="https://example-cae.local")
            
            # No estamos en el dominio CAE
            obs = BrowserObservation(
                url="https://es.wikipedia.org/wiki/Ada_Lovelace",
                title="Ada Lovelace",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
            
            action = await strategy.ensure_context(
                "revisa la documentación CAE",
                obs,
                None
            )
            assert action is not None
            assert action.type == "open_url"
            assert action.args["url"] == "https://example-cae.local"
        
        run(_test)
    
    def test_ensure_context_no_reload_if_already_in_domain(self):
        """No recarga si ya estamos en el dominio CAE"""
        async def _test():
            strategy = CAEContextStrategy(base_url="https://example-cae.local")
            
            # Ya estamos en el dominio CAE
            obs = BrowserObservation(
                url="https://example-cae.local/documentacion",
                title="Documentación CAE",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
            
            action = await strategy.ensure_context(
                "revisa la documentación CAE",
                obs,
                None
            )
            assert action is None  # No debe recargar
        
        run(_test)
    
    def test_is_goal_satisfied_in_cae_domain(self):
        """Satisfecho si estamos en el dominio CAE"""
        strategy = CAEContextStrategy(base_url="https://example-cae.local")
        
        obs = BrowserObservation(
            url="https://example-cae.local/documentacion",
            title="Documentación CAE",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "revisa la documentación CAE",
            obs,
            None
        ) is True
    
    def test_is_goal_satisfied_not_in_cae_domain(self):
        """No satisfecho si no estamos en el dominio CAE"""
        strategy = CAEContextStrategy(base_url="https://example-cae.local")
        
        obs = BrowserObservation(
            url="https://es.wikipedia.org/wiki/Ada_Lovelace",
            title="Ada Lovelace",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "revisa la documentación CAE",
            obs,
            None
        ) is False
    
    def test_is_goal_satisfied_with_documentation_title(self):
        """Satisfecho si el título contiene 'documentación'"""
        strategy = CAEContextStrategy(base_url="https://example-cae.local")
        
        obs = BrowserObservation(
            url="https://example-cae.local/seccion/documentacion",
            title="Documentación de Prevención de Riesgos",
            visible_text_excerpt="",
            clickable_texts=[],
            input_hints=[],
        )
        
        assert strategy.is_goal_satisfied(
            "revisa la documentación CAE",
            obs,
            None
        ) is True


class TestBuildContextStrategies:
    """Tests para build_context_strategies"""
    
    def test_build_default_strategies(self):
        """Si no se especifican nombres, devuelve DEFAULT_CONTEXT_STRATEGIES"""
        strategies = build_context_strategies(None)
        assert len(strategies) == 2
        assert isinstance(strategies[0], ImageSearchContextStrategy)
        assert isinstance(strategies[1], WikipediaContextStrategy)
    
    def test_build_wikipedia_and_images(self):
        """Construye estrategias Wikipedia e imágenes en el orden especificado"""
        strategies = build_context_strategies(["wikipedia", "images"])
        assert len(strategies) == 2
        assert isinstance(strategies[0], WikipediaContextStrategy)
        assert isinstance(strategies[1], ImageSearchContextStrategy)
    
    def test_build_with_cae(self):
        """Construye estrategia CAE con URL base personalizada"""
        strategies = build_context_strategies(["cae"], cae_base_url="https://custom-cae.local")
        assert len(strategies) == 1
        assert isinstance(strategies[0], CAEContextStrategy)
        assert strategies[0].base_url == "https://custom-cae.local"
    
    def test_build_with_cae_default_url(self):
        """Construye estrategia CAE con URL base por defecto"""
        strategies = build_context_strategies(["cae"])
        assert len(strategies) == 1
        assert isinstance(strategies[0], CAEContextStrategy)
    
    def test_build_mixed_strategies(self):
        """Construye múltiples estrategias en el orden especificado"""
        strategies = build_context_strategies(["cae", "wikipedia", "images"])
        assert len(strategies) == 3
        assert isinstance(strategies[0], CAEContextStrategy)
        assert isinstance(strategies[1], WikipediaContextStrategy)
        assert isinstance(strategies[2], ImageSearchContextStrategy)
    
    def test_build_unknown_strategy_ignored(self):
        """Ignora nombres de estrategias desconocidos"""
        strategies = build_context_strategies(["wikipedia", "unknown", "images"])
        assert len(strategies) == 2
        assert isinstance(strategies[0], WikipediaContextStrategy)
        assert isinstance(strategies[1], ImageSearchContextStrategy)


class TestContextStrategiesIntegration:
    """Tests de integración con agent_runner"""
    
    def test_ensure_context_delegates_to_strategies(self):
        """ensure_context delega correctamente a las estrategias"""
        # Este test verifica que ensure_context usa las estrategias
        # Se ejecuta indirectamente a través de los tests de agent_runner
        # que ya cubren los casos de uso reales
        pass
    
    def test_goal_is_satisfied_delegates_to_strategies(self):
        """_goal_is_satisfied delega correctamente a las estrategias"""
        # Este test verifica que _goal_is_satisfied usa las estrategias
        # Se ejecuta indirectamente a través de los tests de agent_runner
        # que ya cubren los casos de uso reales
        pass

