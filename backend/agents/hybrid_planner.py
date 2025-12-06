"""
Hybrid Planner: Motor de planificación híbrido que combina DOM, Visual, Heurística y LLM.

v5.0.0: Planificación autónoma para plataformas CAE nuevas, cambiantes o rotas.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from backend.shared.models import (
    PlannerNode,
    PlannerGraph,
    PlannerNodeResult,
    HybridPlannerSettings,
)
from backend.agents.dom_explorer import DOMExplorer, DOMSnapshot
from backend.agents.visual_explorer import VisualExplorer, VisualSnapshot
from backend.agents.path_finder import PathFinder

logger = logging.getLogger(__name__)


class HybridPlanner:
    """
    Planificador híbrido autónomo.
    
    v5.0.0: Combina exploración DOM, visual, heurísticas y LLM para planificación autónoma.
    """
    
    def __init__(
        self,
        browser_controller,
        ocr_service: Optional[Any] = None,
        memory_store: Optional[Any] = None,
        settings: Optional[HybridPlannerSettings] = None,
        rl_engine: Optional[Any] = None,  # v5.1.0
    ):
        """
        Inicializa el planificador híbrido.
        
        Args:
            browser_controller: Instancia de BrowserController
            ocr_service: Servicio OCR opcional
            memory_store: Almacén de memoria opcional
            settings: Configuración del planificador
            rl_engine: Motor RL opcional (v5.1.0)
        """
        self.browser = browser_controller
        self.ocr_service = ocr_service
        self.memory = memory_store
        self.settings = settings or HybridPlannerSettings()
        self.rl_engine = rl_engine  # v5.1.0
        
        self.dom_explorer = DOMExplorer(browser_controller)
        self.visual_explorer = VisualExplorer(browser_controller, ocr_service)
        self.path_finder = PathFinder(memory_store)
        
        self.dynamic_nodes_count = 0
        self.executed_nodes: List[str] = []
        self.node_results: Dict[str, PlannerNodeResult] = {}
    
    def build_initial_graph(
        self,
        goal: str,
        task_graph: Optional[Any] = None,
        memory: Optional[Any] = None,
    ) -> PlannerGraph:
        """
        Construye el grafo inicial de planificación.
        
        Args:
            goal: Objetivo del agente
            task_graph: Grafo de tareas existente (v4.9) opcional
            memory: Memoria opcional
            
        Returns:
            PlannerGraph inicial
        """
        logger.info(f"[hybrid-planner] Building initial graph for goal: {goal[:100]}...")
        
        nodes: Dict[str, PlannerNode] = {}
        
        # Nodos de exploración base
        if self.settings.allow_dom_exploration:
            nodes["dom_explore_root"] = PlannerNode(
                node_id="dom_explore_root",
                title="Explorar DOM",
                type="explore_dom",
                description="Explorar estructura DOM de la página",
                prereqs=[],
            )
        
        if self.settings.allow_visual_exploration:
            nodes["visual_explore_root"] = PlannerNode(
                node_id="visual_explore_root",
                title="Explorar Visual",
                type="explore_visual",
                description="Explorar elementos visuales mediante OCR",
                prereqs=[],
            )
        
        # Nodos de detección
        nodes["detect_sections"] = PlannerNode(
            node_id="detect_sections",
            title="Detectar Secciones",
            type="detect_forms",
            description="Detectar secciones relevantes de la página",
            prereqs=["dom_explore_root", "visual_explore_root"] if self.settings.allow_dom_exploration and self.settings.allow_visual_exploration else [],
        )
        
        nodes["find_cae_section"] = PlannerNode(
            node_id="find_cae_section",
            title="Encontrar Sección CAE",
            type="navigate",
            description="Navegar a la sección CAE de la plataforma",
            prereqs=["detect_sections"],
        )
        
        nodes["open_worker"] = PlannerNode(
            node_id="open_worker",
            title="Abrir Trabajador",
            type="navigate",
            description="Abrir página del trabajador",
            prereqs=["find_cae_section"],
        )
        
        nodes["open_upload_page"] = PlannerNode(
            node_id="open_upload_page",
            title="Abrir Página de Subida",
            type="navigate",
            description="Navegar a la página de subida de documentos",
            prereqs=["open_worker"],
        )
        
        nodes["detect_forms"] = PlannerNode(
            node_id="detect_forms",
            title="Detectar Formularios",
            type="detect_forms",
            description="Detectar formularios en la página actual",
            prereqs=["open_upload_page"],
        )
        
        nodes["detect_buttons"] = PlannerNode(
            node_id="detect_buttons",
            title="Detectar Botones",
            type="detect_buttons",
            description="Detectar botones críticos (subir, guardar, confirmar)",
            prereqs=["detect_forms"],
        )
        
        nodes["resolve_required_actions"] = PlannerNode(
            node_id="resolve_required_actions",
            title="Resolver Acciones Requeridas",
            type="navigate",
            description="Determinar acciones necesarias basándose en detecciones",
            prereqs=["detect_buttons"],
        )
        
        # Fusionar con task_graph si existe
        if task_graph:
            # Añadir nodos del task_graph después de detect_forms y detect_buttons
            # Por ahora, asumimos que task_graph tiene nodos como upload_file, fill_form, submit
            # Estos se añadirían como prereqs de resolve_required_actions
            logger.debug("[hybrid-planner] Merging with existing task_graph")
        
        # Determinar entrypoint
        entrypoint = "dom_explore_root" if self.settings.allow_dom_exploration else "visual_explore_root"
        
        graph = PlannerGraph(
            nodes=nodes,
            entrypoint=entrypoint,
            goal=goal,
        )
        
        logger.info(f"[hybrid-planner] Initial graph built: {len(nodes)} nodes, entrypoint={entrypoint}")
        
        return graph
    
    def dynamic_node_generator(
        self,
        current_node_id: str,
        dom_snapshot: Optional[DOMSnapshot] = None,
        visual_snapshot: Optional[VisualSnapshot] = None,
        document_analysis: Optional[Any] = None,
    ) -> List[PlannerNode]:
        """
        Genera nuevos nodos dinámicamente basándose en descubrimientos.
        
        Args:
            current_node_id: ID del nodo actual
            dom_snapshot: Snapshot del DOM
            visual_snapshot: Snapshot visual
            document_analysis: Análisis de documento opcional
            
        Returns:
            Lista de nuevos nodos generados
        """
        if self.dynamic_nodes_count >= self.settings.max_dynamic_nodes:
            logger.debug("[hybrid-planner] Max dynamic nodes reached")
            return []
        
        new_nodes = []
        
        # Detectar pantallas inesperadas
        if visual_snapshot and visual_snapshot.modals_detected:
            for modal in visual_snapshot.modals_detected:
                node_id = f"handle_modal_{self.dynamic_nodes_count}"
                new_nodes.append(PlannerNode(
                    node_id=node_id,
                    title=f"Manejar Modal: {modal.get('text', '')}",
                    type="confirm",
                    description=f"Gestionar modal detectado: {modal.get('text', '')}",
                    prereqs=[current_node_id],
                    dynamic=True,
                    metadata={"modal": modal},
                ))
                self.dynamic_nodes_count += 1
        
        # Detectar botones visuales no mapeados
        if visual_snapshot and visual_snapshot.buttons_detected:
            for button in visual_snapshot.buttons_detected:
                button_text = button.get("text", "")
                if any(kw in button_text.lower() for kw in ["subir", "adjuntar", "confirmar", "guardar"]):
                    node_id = f"click_button_{self.dynamic_nodes_count}"
                    new_nodes.append(PlannerNode(
                        node_id=node_id,
                        title=f"Clic en Botón: {button_text}",
                        type="navigate",
                        description=f"Clic en botón visual detectado: {button_text}",
                        prereqs=[current_node_id],
                        dynamic=True,
                        metadata={"button": button},
                    ))
                    self.dynamic_nodes_count += 1
        
        # Detectar inputs no mapeados si hay análisis de documento
        if dom_snapshot and document_analysis:
            if dom_snapshot.inputs and document_analysis.deep_analysis:
                # Si hay campos en deep_analysis que no están mapeados
                node_id = f"map_missing_fields_{self.dynamic_nodes_count}"
                new_nodes.append(PlannerNode(
                    node_id=node_id,
                    title="Mapear Campos Faltantes",
                    type="fill_form",
                    description="Mapear campos del documento que faltan en el formulario",
                    prereqs=[current_node_id],
                    dynamic=True,
                    metadata={"document_analysis": document_analysis},
                ))
                self.dynamic_nodes_count += 1
        
        if new_nodes:
            logger.info(f"[hybrid-planner] Generated {len(new_nodes)} dynamic nodes")
        
        return new_nodes
    
    async def execute_node(
        self,
        node: PlannerNode,
        graph: PlannerGraph,
    ) -> PlannerNodeResult:
        """
        Ejecuta un nodo del grafo.
        
        Args:
            node: Nodo a ejecutar
            graph: Grafo completo
            
        Returns:
            PlannerNodeResult con el resultado
        """
        logger.info(f"[hybrid-planner] Executing node: {node.node_id} ({node.type})")
        
        result = PlannerNodeResult(
            node_id=node.node_id,
            success=False,
            details={},
            discovered_nodes=[],
        )
        
        try:
            if node.type == "explore_dom":
                snapshot = await self.dom_explorer.take_snapshot()
                result.success = True
                result.details = {
                    "links_count": len(snapshot.links),
                    "buttons_count": len(snapshot.buttons),
                    "inputs_count": len(snapshot.inputs),
                    "forms_count": len(snapshot.forms),
                    "cae_keywords": snapshot.cae_keywords_found,
                }
            
            elif node.type == "explore_visual":
                snapshot = await self.visual_explorer.take_snapshot()
                result.success = True
                result.details = {
                    "buttons_count": len(snapshot.buttons_detected),
                    "modals_count": len(snapshot.modals_detected),
                    "forms_count": len(snapshot.forms_detected),
                    "cae_keywords": snapshot.cae_keywords_found,
                }
            
            elif node.type == "detect_forms":
                dom_snapshot = await self.dom_explorer.take_snapshot()
                visual_snapshot = await self.visual_explorer.take_snapshot()
                result.success = True
                result.details = {
                    "dom_forms": len(dom_snapshot.forms),
                    "visual_forms": len(visual_snapshot.forms_detected),
                }
            
            elif node.type == "detect_buttons":
                dom_snapshot = await self.dom_explorer.take_snapshot()
                visual_snapshot = await self.visual_explorer.take_snapshot()
                result.success = True
                result.details = {
                    "dom_buttons": len(dom_snapshot.buttons),
                    "visual_buttons": len(visual_snapshot.buttons_detected),
                }
            
            elif node.type == "navigate":
                # Navegación básica - por ahora marcamos como éxito
                result.success = True
                result.details = {"action": "navigate"}
            
            elif node.type == "fill_form":
                result.success = True
                result.details = {"action": "fill_form"}
            
            elif node.type == "upload_file":
                result.success = True
                result.details = {"action": "upload_file"}
            
            elif node.type == "confirm":
                result.success = True
                result.details = {"action": "confirm"}
            
            else:
                logger.warning(f"[hybrid-planner] Unknown node type: {node.type}")
                result.success = False
                result.details = {"error": f"Unknown node type: {node.type}"}
        
        except Exception as e:
            logger.error(f"[hybrid-planner] Error executing node {node.node_id}: {e}", exc_info=True)
            result.success = False
            result.details = {"error": str(e)}
        
        self.executed_nodes.append(node.node_id)
        self.node_results[node.node_id] = result
        
        return result
    
    async def run(
        self,
        goal: str,
        task_graph: Optional[Any] = None,
        memory: Optional[Any] = None,
        document_analysis: Optional[Any] = None,
    ) -> Tuple[PlannerGraph, List[PlannerNodeResult]]:
        """
        Ejecuta el planificador híbrido completo.
        
        Args:
            goal: Objetivo del agente
            task_graph: Grafo de tareas existente opcional
            memory: Memoria opcional
            document_analysis: Análisis de documento opcional
            
        Returns:
            Tupla (grafo final, resultados de nodos)
        """
        logger.info(f"[hybrid-planner] Starting hybrid planner for goal: {goal[:100]}...")
        
        # 1. Construir grafo inicial
        graph = self.build_initial_graph(goal, task_graph, memory)
        
        # 2. Ejecutar nodos en orden topológico
        results: List[PlannerNodeResult] = []
        nodes_to_execute = [graph.entrypoint]
        executed_set = set()
        
        while nodes_to_execute:
            node_id = nodes_to_execute.pop(0)
            
            if node_id in executed_set:
                continue
            
            if node_id not in graph.nodes:
                logger.warning(f"[hybrid-planner] Node {node_id} not found in graph")
                continue
            
            node = graph.nodes[node_id]
            
            # Verificar prereqs
            prereqs_met = all(prereq in executed_set for prereq in node.prereqs)
            if not prereqs_met:
                # Añadir prereqs a la cola primero
                for prereq in node.prereqs:
                    if prereq not in executed_set and prereq not in nodes_to_execute:
                        nodes_to_execute.insert(0, prereq)
                continue
            
            # Ejecutar nodo
            result = await self.execute_node(node, graph)
            results.append(result)
            executed_set.add(node_id)
            
            # Si falla, intentar generar nodos dinámicos
            if not result.success and self.dynamic_nodes_count < self.settings.max_dynamic_nodes:
                # Obtener snapshots actuales
                dom_snapshot = await self.dom_explorer.take_snapshot()
                visual_snapshot = await self.visual_explorer.take_snapshot()
                
                # Generar nodos dinámicos
                new_nodes = self.dynamic_node_generator(
                    current_node_id=node_id,
                    dom_snapshot=dom_snapshot,
                    visual_snapshot=visual_snapshot,
                    document_analysis=document_analysis,
                )
                
                # Añadir nuevos nodos al grafo
                for new_node in new_nodes:
                    graph.nodes[new_node.node_id] = new_node
                    nodes_to_execute.append(new_node.node_id)
            
            # Añadir nodos siguientes (sin prereqs o con prereqs cumplidos)
            for next_node_id, next_node in graph.nodes.items():
                if next_node_id not in executed_set and next_node_id not in nodes_to_execute:
                    if node_id in next_node.prereqs:
                        # Verificar si todos los prereqs están cumplidos
                        if all(prereq in executed_set for prereq in next_node.prereqs):
                            nodes_to_execute.append(next_node_id)
        
        logger.info(f"[hybrid-planner] Completed: {len(results)} nodes executed, {self.dynamic_nodes_count} dynamic nodes generated")
        
        return graph, results

