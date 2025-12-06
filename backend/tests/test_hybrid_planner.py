"""
Tests para Hybrid Planner v5.0.0
"""

import pytest
pytestmark = pytest.mark.asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from backend.agents.hybrid_planner import HybridPlanner
from backend.agents.dom_explorer import DOMExplorer, DOMSnapshot
from backend.agents.visual_explorer import VisualExplorer, VisualSnapshot
from backend.agents.path_finder import PathFinder
from backend.shared.models import (
    PlannerNode,
    PlannerGraph,
    PlannerNodeResult,
    HybridPlannerSettings,
)


class TestHybridPlanner:
    """Tests para HybridPlanner"""
    
    @pytest.fixture
    def mock_browser(self):
        """Mock de BrowserController"""
        browser = MagicMock()
        browser.page = MagicMock()
        return browser
    
    @pytest.fixture
    def mock_ocr_service(self):
        """Mock de OCRService"""
        ocr_service = MagicMock()
        ocr_service.enabled = True
        return ocr_service
    
    @pytest.fixture
    def planner(self, mock_browser, mock_ocr_service):
        """Instancia de HybridPlanner para tests"""
        settings = HybridPlannerSettings(
            enable=True,
            max_dynamic_nodes=10,
            allow_visual_exploration=True,
            allow_dom_exploration=True,
            allow_llm_planning=True,
        )
        return HybridPlanner(
            browser_controller=mock_browser,
            ocr_service=mock_ocr_service,
            memory_store=None,
            settings=settings,
        )
    
    def test_build_initial_graph(self, planner):
        """Test que construye grafo inicial correctamente"""
        goal = "Subir documento CAE"
        graph = planner.build_initial_graph(goal)
        
        assert isinstance(graph, PlannerGraph)
        assert graph.goal == goal
        assert graph.entrypoint in graph.nodes
        assert "dom_explore_root" in graph.nodes or "visual_explore_root" in graph.nodes
        assert "detect_forms" in graph.nodes
        assert "detect_buttons" in graph.nodes
    
    def test_build_initial_graph_without_dom_exploration(self):
        """Test que construye grafo sin exploración DOM si está deshabilitada"""
        settings = HybridPlannerSettings(
            enable=True,
            allow_dom_exploration=False,
            allow_visual_exploration=True,
        )
        mock_browser = MagicMock()
        planner = HybridPlanner(
            browser_controller=mock_browser,
            ocr_service=None,
            settings=settings,
        )
        
        graph = planner.build_initial_graph("Test goal")
        assert "dom_explore_root" not in graph.nodes
        assert "visual_explore_root" in graph.nodes
    
    @pytest.mark.asyncio
    async def test_execute_node_explore_dom(self, planner, mock_browser):
        """Test ejecución de nodo explore_dom"""
        # Mock DOMExplorer
        dom_snapshot = DOMSnapshot(
            links=[{"href": "/test", "text": "Test"}],
            buttons=[{"text": "Submit"}],
            inputs=[],
            forms=[],
            cae_keywords_found=["cae", "prevención"],
        )
        
        with patch.object(planner.dom_explorer, 'take_snapshot', return_value=dom_snapshot):
            node = PlannerNode(
                node_id="test_dom",
                title="Test DOM",
                type="explore_dom",
            )
            graph = PlannerGraph(nodes={}, entrypoint="test_dom", goal="Test")
            
            result = await planner.execute_node(node, graph)
            
            assert result.success
            assert result.node_id == "test_dom"
            assert "links_count" in result.details
            assert "cae_keywords" in result.details
    
    @pytest.mark.asyncio
    async def test_execute_node_explore_visual(self, planner, mock_browser):
        """Test ejecución de nodo explore_visual"""
        visual_snapshot = VisualSnapshot(
            buttons_detected=[{"text": "Subir", "x": 100, "y": 200}],
            texts_detected=[],
            modals_detected=[],
            forms_detected=[],
            cae_keywords_found=["documentación"],
        )
        
        with patch.object(planner.visual_explorer, 'take_snapshot', return_value=visual_snapshot):
            node = PlannerNode(
                node_id="test_visual",
                title="Test Visual",
                type="explore_visual",
            )
            graph = PlannerGraph(nodes={}, entrypoint="test_visual", goal="Test")
            
            result = await planner.execute_node(node, graph)
            
            assert result.success
            assert "buttons_count" in result.details
            assert "cae_keywords" in result.details
    
    def test_dynamic_node_generator_modals(self, planner):
        """Test generación de nodos dinámicos para modales"""
        visual_snapshot = VisualSnapshot(
            modals_detected=[
                {"text": "Confirmar", "x": 100, "y": 200},
            ],
        )
        
        new_nodes = planner.dynamic_node_generator(
            current_node_id="test_node",
            visual_snapshot=visual_snapshot,
        )
        
        assert len(new_nodes) > 0
        assert any("modal" in node.node_id for node in new_nodes)
        assert all(node.dynamic for node in new_nodes)
    
    def test_dynamic_node_generator_buttons(self, planner):
        """Test generación de nodos dinámicos para botones"""
        visual_snapshot = VisualSnapshot(
            buttons_detected=[
                {"text": "Subir documento", "x": 100, "y": 200},
            ],
        )
        
        new_nodes = planner.dynamic_node_generator(
            current_node_id="test_node",
            visual_snapshot=visual_snapshot,
        )
        
        assert len(new_nodes) > 0
        assert any("button" in node.node_id for node in new_nodes)
    
    def test_dynamic_node_generator_max_nodes(self, planner):
        """Test que respeta max_dynamic_nodes"""
        planner.dynamic_nodes_count = 10  # Max alcanzado
        
        new_nodes = planner.dynamic_node_generator(
            current_node_id="test_node",
            visual_snapshot=VisualSnapshot(modals_detected=[{"text": "Test"}]),
        )
        
        assert len(new_nodes) == 0


class TestPathFinder:
    """Tests para PathFinder"""
    
    def test_detect_dead_end(self):
        """Test detección de dead-end"""
        path_finder = PathFinder()
        path = ["node1", "node2", "node3"]
        
        # Primera vez no es dead-end
        assert not path_finder.detect_dead_end(path)
        
        # Después de múltiples intentos, sí
        path_finder.record_path_attempt(path, success=False)
        path_finder.record_path_attempt(path, success=False)
        path_finder.record_path_attempt(path, success=False)
        
        assert path_finder.detect_dead_end(path)
    
    def test_detect_loop(self):
        """Test detección de loops"""
        path_finder = PathFinder()
        
        # Loop con nodos consecutivos
        path_with_loop = ["node1", "node2", "node2", "node3"]
        assert path_finder.detect_loop(path_with_loop)
        
        # Sin loop
        path_no_loop = ["node1", "node2", "node3"]
        assert not path_finder.detect_loop(path_no_loop)
    
    def test_calculate_relevance_score(self):
        """Test cálculo de score de relevancia"""
        path_finder = PathFinder()
        
        dom_snapshot = DOMSnapshot(
            cae_keywords_found=["cae", "prevención"],
            forms=[{"id": "form1"}],
            buttons=[{"text": "Submit"}],
        )
        
        visual_snapshot = VisualSnapshot(
            cae_keywords_found=["documentación"],
            buttons_detected=[{"text": "Subir"}],
        )
        
        score = path_finder.calculate_relevance_score(
            dom_snapshot=dom_snapshot,
            visual_snapshot=visual_snapshot,
            goal="Test",
        )
        
        assert 0.0 <= score <= 1.0
        assert score > 0.0  # Debería tener algún score positivo


class TestDOMExplorer:
    """Tests para DOMExplorer"""
    
    @pytest.fixture
    def mock_browser(self):
        """Mock de BrowserController"""
        browser = MagicMock()
        browser.page = MagicMock()
        return browser
    
    @pytest.mark.asyncio
    async def test_extract_all_links(self, mock_browser):
        """Test extracción de enlaces"""
        explorer = DOMExplorer(mock_browser)
        
        mock_browser.page.evaluate = AsyncMock(return_value=[
            {"href": "/test", "text": "Test Link", "selector": "a[href='/test']"},
        ])
        
        links = await explorer.extract_all_links()
        
        assert len(links) > 0
        assert links[0]["href"] == "/test"
    
    @pytest.mark.asyncio
    async def test_take_snapshot(self, mock_browser):
        """Test toma de snapshot completo"""
        explorer = DOMExplorer(mock_browser)
        
        mock_browser.page.evaluate = AsyncMock(return_value=[])
        
        snapshot = await explorer.take_snapshot()
        
        assert isinstance(snapshot, DOMSnapshot)
        assert snapshot.links is not None
        assert snapshot.buttons is not None
        assert snapshot.inputs is not None


class TestVisualExplorer:
    """Tests para VisualExplorer"""
    
    @pytest.fixture
    def mock_browser(self):
        """Mock de BrowserController"""
        browser = MagicMock()
        browser.page = MagicMock()
        return browser
    
    @pytest.fixture
    def mock_ocr_service(self):
        """Mock de OCRService"""
        ocr_service = MagicMock()
        ocr_service.enabled = True
        return ocr_service
    
    @pytest.mark.asyncio
    async def test_detect_visual_buttons(self, mock_browser, mock_ocr_service):
        """Test detección de botones visuales"""
        explorer = VisualExplorer(mock_browser, mock_ocr_service)
        
        # Mock OCR blocks
        class MockOCRBlock:
            def __init__(self, text, x, y, width, height):
                self.text = text
                self.x = x
                self.y = y
                self.width = width
                self.height = height
        
        ocr_blocks = [
            MockOCRBlock("Subir documento", 100, 200, 150, 30),
        ]
        
        buttons = await explorer.detect_visual_buttons(ocr_blocks)
        
        assert len(buttons) > 0
        assert any("subir" in b["text"].lower() for b in buttons)
    
    @pytest.mark.asyncio
    async def test_take_snapshot(self, mock_browser, mock_ocr_service):
        """Test toma de snapshot visual"""
        explorer = VisualExplorer(mock_browser, mock_ocr_service)
        
        # Mock sin OCR blocks
        snapshot = await explorer.take_snapshot(ocr_blocks=[])
        
        assert isinstance(snapshot, VisualSnapshot)
        assert snapshot.buttons_detected is not None
        assert snapshot.texts_detected is not None

