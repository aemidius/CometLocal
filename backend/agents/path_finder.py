"""
Path Finder: Algoritmo heurístico para priorizar rutas y detectar dead-ends/loops.

v5.0.0: Calcula heurísticas de relevancia y encuentra rutas óptimas.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from backend.agents.dom_explorer import DOMSnapshot
from backend.agents.visual_explorer import VisualSnapshot

logger = logging.getLogger(__name__)


@dataclass
class PathScore:
    """
    Score de una ruta potencial.
    
    v5.0.0: Contiene el score y metadatos de una ruta.
    """
    path: List[str]  # Lista de acciones/nodos
    score: float
    dom_relevance: float = 0.0
    visual_relevance: float = 0.0
    memory_bias: float = 0.0
    document_needs: float = 0.0
    reasons: List[str] = None
    
    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []


class PathFinder:
    """
    Encuentra rutas óptimas usando heurísticas.
    
    v5.0.0: Prioriza rutas basándose en DOM, visual, memoria y necesidades de documentos.
    """
    
    def __init__(self, memory_store: Optional[Any] = None):
        """
        Inicializa el path finder.
        
        Args:
            memory_store: Almacén de memoria opcional para bias
        """
        self.memory = memory_store
        self.visited_paths: List[List[str]] = []
        self.dead_ends: List[List[str]] = []
    
    def calculate_relevance_score(
        self,
        dom_snapshot: Optional[DOMSnapshot] = None,
        visual_snapshot: Optional[VisualSnapshot] = None,
        goal: str = "",
        document_needs: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Calcula score de relevancia heurística.
        
        Args:
            dom_snapshot: Snapshot del DOM
            visual_snapshot: Snapshot visual
            goal: Objetivo del agente
            document_needs: Necesidades de documentos (opcional)
            
        Returns:
            Score de relevancia [0, 1]
        """
        score = 0.0
        weights = {
            "dom": 0.3,
            "visual": 0.3,
            "memory": 0.2,
            "document": 0.2,
        }
        
        # DOM relevance
        dom_relevance = 0.0
        if dom_snapshot:
            # Más keywords CAE = más relevante
            if dom_snapshot.cae_keywords_found:
                dom_relevance += 0.3 * min(1.0, len(dom_snapshot.cae_keywords_found) / 5)
            
            # Más formularios = más relevante
            if dom_snapshot.forms:
                dom_relevance += 0.3 * min(1.0, len(dom_snapshot.forms) / 3)
            
            # Más botones = más relevante
            if dom_snapshot.buttons:
                dom_relevance += 0.2 * min(1.0, len(dom_snapshot.buttons) / 10)
            
            # Más inputs = más relevante (formularios)
            if dom_snapshot.inputs:
                dom_relevance += 0.2 * min(1.0, len(dom_snapshot.inputs) / 10)
        
        # Visual relevance
        visual_relevance = 0.0
        if visual_snapshot:
            # Más keywords CAE visuales = más relevante
            if visual_snapshot.cae_keywords_found:
                visual_relevance += 0.4 * min(1.0, len(visual_snapshot.cae_keywords_found) / 5)
            
            # Más botones visuales = más relevante
            if visual_snapshot.buttons_detected:
                visual_relevance += 0.3 * min(1.0, len(visual_snapshot.buttons_detected) / 5)
            
            # Más formularios visuales = más relevante
            if visual_snapshot.forms_detected:
                visual_relevance += 0.3 * min(1.0, len(visual_snapshot.forms_detected) / 3)
        
        # Memory bias
        memory_bias = 0.0
        if self.memory and goal:
            # Si hay memoria de rutas exitosas, aumentar bias
            # Por ahora, bias neutral
            memory_bias = 0.5
        
        # Document needs
        document_needs_score = 0.0
        if document_needs:
            # Si hay necesidades de documentos específicos, aumentar relevancia
            if document_needs.get("required_docs"):
                document_needs_score = 0.7
        
        # Score final ponderado
        score = (
            weights["dom"] * dom_relevance +
            weights["visual"] * visual_relevance +
            weights["memory"] * memory_bias +
            weights["document"] * document_needs_score
        )
        
        return min(1.0, score)
    
    def detect_dead_end(self, path: List[str], max_attempts: int = 3) -> bool:
        """
        Detecta si una ruta es un dead-end.
        
        Args:
            path: Ruta a evaluar
            max_attempts: Número máximo de intentos antes de considerar dead-end
            
        Returns:
            True si es un dead-end
        """
        # Si la ruta ya está marcada como dead-end
        if path in self.dead_ends:
            return True
        
        # Si se ha intentado muchas veces sin éxito
        attempts = sum(1 for visited in self.visited_paths if visited == path)
        if attempts >= max_attempts:
            self.dead_ends.append(path)
            return True
        
        return False
    
    def detect_loop(self, path: List[str]) -> bool:
        """
        Detecta si una ruta forma un loop.
        
        Args:
            path: Ruta a evaluar
            
        Returns:
            True si hay un loop
        """
        # Si hay nodos repetidos consecutivos
        if len(path) >= 2:
            for i in range(len(path) - 1):
                if path[i] == path[i + 1]:
                    return True
        
        # Si la ruta completa se repite
        if len(self.visited_paths) >= 2:
            last_two = self.visited_paths[-2:]
            if len(last_two) == 2 and last_two[0] == last_two[1] == path:
                return True
        
        return False
    
    def prioritize_paths(
        self,
        candidate_paths: List[List[str]],
        dom_snapshot: Optional[DOMSnapshot] = None,
        visual_snapshot: Optional[VisualSnapshot] = None,
        goal: str = "",
        document_needs: Optional[Dict[str, Any]] = None,
    ) -> List[PathScore]:
        """
        Prioriza rutas candidatas según heurísticas.
        
        Args:
            candidate_paths: Lista de rutas candidatas
            dom_snapshot: Snapshot del DOM
            visual_snapshot: Snapshot visual
            goal: Objetivo del agente
            document_needs: Necesidades de documentos
            
        Returns:
            Lista de PathScore ordenada por score (mayor primero)
        """
        scored_paths = []
        
        for path in candidate_paths:
            # Filtrar dead-ends y loops
            if self.detect_dead_end(path):
                continue
            if self.detect_loop(path):
                continue
            
            # Calcular score
            score = self.calculate_relevance_score(
                dom_snapshot=dom_snapshot,
                visual_snapshot=visual_snapshot,
                goal=goal,
                document_needs=document_needs,
            )
            
            # Construir razones
            reasons = []
            if dom_snapshot and dom_snapshot.cae_keywords_found:
                reasons.append(f"DOM keywords: {len(dom_snapshot.cae_keywords_found)}")
            if visual_snapshot and visual_snapshot.cae_keywords_found:
                reasons.append(f"Visual keywords: {len(visual_snapshot.cae_keywords_found)}")
            if document_needs:
                reasons.append("Document needs match")
            
            scored_paths.append(PathScore(
                path=path,
                score=score,
                dom_relevance=0.3 if dom_snapshot else 0.0,
                visual_relevance=0.3 if visual_snapshot else 0.0,
                memory_bias=0.2,
                document_needs=0.2 if document_needs else 0.0,
                reasons=reasons,
            ))
        
        # Ordenar por score descendente
        scored_paths.sort(key=lambda x: x.score, reverse=True)
        
        return scored_paths
    
    def suggest_alternative_path(
        self,
        failed_path: List[str],
        dom_snapshot: Optional[DOMSnapshot] = None,
        visual_snapshot: Optional[VisualSnapshot] = None,
    ) -> Optional[List[str]]:
        """
        Sugiere una ruta alternativa cuando una ruta falla.
        
        Args:
            failed_path: Ruta que falló
            dom_snapshot: Snapshot del DOM actual
            visual_snapshot: Snapshot visual actual
            
        Returns:
            Ruta alternativa sugerida o None
        """
        # Marcar como dead-end
        self.dead_ends.append(failed_path)
        
        # Buscar alternativa basada en DOM/visual
        alternative = []
        
        if dom_snapshot:
            # Intentar usar enlaces diferentes
            if dom_snapshot.links:
                alternative = ["navigate", dom_snapshot.links[0].get("href", "")]
        
        if visual_snapshot and not alternative:
            # Intentar usar botones visuales
            if visual_snapshot.buttons_detected:
                alternative = ["click_visual", visual_snapshot.buttons_detected[0].get("text", "")]
        
        return alternative if alternative else None
    
    def record_path_attempt(self, path: List[str], success: bool):
        """
        Registra un intento de ruta.
        
        Args:
            path: Ruta intentada
            success: Si fue exitosa
        """
        self.visited_paths.append(path)
        
        if not success:
            # Si falla múltiples veces, marcar como dead-end
            attempts = sum(1 for visited in self.visited_paths if visited == path)
            if attempts >= 3:
                self.dead_ends.append(path)

