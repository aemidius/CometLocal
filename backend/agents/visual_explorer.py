"""
Visual Explorer: Exploración visual usando OCR para detectar elementos no visibles en DOM.

v5.0.0: Usa OCR para identificar botones, textos y formularios visuales.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VisualSnapshot:
    """
    Snapshot del estado visual de la página.
    
    v5.0.0: Contiene información extraída mediante OCR.
    """
    buttons_detected: List[Dict[str, Any]] = None
    texts_detected: List[Dict[str, Any]] = None
    modals_detected: List[Dict[str, Any]] = None
    forms_detected: List[Dict[str, Any]] = None
    cae_keywords_found: List[str] = None
    coordinates_map: Dict[str, tuple] = None  # text -> (x, y)
    
    def __post_init__(self):
        if self.buttons_detected is None:
            self.buttons_detected = []
        if self.texts_detected is None:
            self.texts_detected = []
        if self.modals_detected is None:
            self.modals_detected = []
        if self.forms_detected is None:
            self.forms_detected = []
        if self.cae_keywords_found is None:
            self.cae_keywords_found = []
        if self.coordinates_map is None:
            self.coordinates_map = {}


class VisualExplorer:
    """
    Explorador visual usando OCR.
    
    v5.0.0: Detecta elementos visuales que no están en el DOM.
    """
    
    def __init__(self, browser_controller, ocr_service: Optional[Any] = None):
        """
        Inicializa el explorador visual.
        
        Args:
            browser_controller: Instancia de BrowserController
            ocr_service: Servicio OCR opcional
        """
        self.browser = browser_controller
        self.ocr_service = ocr_service
    
    async def detect_visual_buttons(self, ocr_blocks: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """
        Detecta botones visuales usando OCR.
        
        Args:
            ocr_blocks: Bloques OCR opcionales (si ya están disponibles)
            
        Returns:
            Lista de botones detectados con texto y coordenadas
        """
        if not self.ocr_service or not self.ocr_service.enabled:
            return []
        
        button_keywords = [
            "subir", "adjuntar", "guardar", "confirmar", "enviar", "continuar",
            "siguiente", "aceptar", "cancelar", "cerrar", "buscar", "filtrar",
        ]
        
        buttons = []
        
        try:
            if ocr_blocks is None:
                # Obtener OCR blocks del screenshot actual
                if self.browser.page:
                    screenshot_path = await self.browser.take_screenshot()
                    if screenshot_path:
                        ocr_result = await self.ocr_service.analyze_screenshot(screenshot_path)
                        if ocr_result and ocr_result.blocks:
                            ocr_blocks = ocr_result.blocks
            
            if ocr_blocks:
                for block in ocr_blocks:
                    text_lower = block.text.lower() if hasattr(block, 'text') else str(block).lower()
                    for keyword in button_keywords:
                        if keyword in text_lower:
                            buttons.append({
                                "text": block.text if hasattr(block, 'text') else str(block),
                                "x": block.x if hasattr(block, 'x') else 0,
                                "y": block.y if hasattr(block, 'y') else 0,
                                "width": block.width if hasattr(block, 'width') else 0,
                                "height": block.height if hasattr(block, 'height') else 0,
                                "keyword": keyword,
                            })
                            break
            
            return buttons
        except Exception as e:
            logger.warning(f"[visual-explorer] Error detecting visual buttons: {e}")
            return []
    
    async def detect_cae_keywords_visual(self, ocr_blocks: Optional[List[Any]] = None) -> List[str]:
        """
        Detecta keywords CAE en el texto visual.
        
        Args:
            ocr_blocks: Bloques OCR opcionales
            
        Returns:
            Lista de keywords encontrados
        """
        if not self.ocr_service or not self.ocr_service.enabled:
            return []
        
        cae_keywords = [
            "cae", "prevención", "prevencion", "riesgos laborales",
            "documentación", "documentacion", "trabajador", "trabajadores",
            "subir documento", "adjuntar", "expedición", "expedicion",
            "reconocimiento médico", "formación", "formacion", "prl",
        ]
        
        found_keywords = []
        
        try:
            if ocr_blocks is None:
                if self.browser.page:
                    screenshot_path = await self.browser.take_screenshot()
                    if screenshot_path:
                        ocr_result = await self.ocr_service.analyze_screenshot(screenshot_path)
                        if ocr_result and ocr_result.blocks:
                            ocr_blocks = ocr_result.blocks
            
            if ocr_blocks:
                full_text = " ".join([block.text if hasattr(block, 'text') else str(block) for block in ocr_blocks]).lower()
                for keyword in cae_keywords:
                    if keyword in full_text:
                        found_keywords.append(keyword)
            
            return found_keywords
        except Exception as e:
            logger.warning(f"[visual-explorer] Error detecting CAE keywords: {e}")
            return []
    
    async def detect_modals(self, ocr_blocks: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """
        Detecta modales o popups visuales.
        
        Args:
            ocr_blocks: Bloques OCR opcionales
            
        Returns:
            Lista de modales detectados
        """
        if not self.ocr_service or not self.ocr_service.enabled:
            return []
        
        modal_keywords = ["confirmar", "aceptar", "cancelar", "cerrar", "modal", "popup", "ventana"]
        modals = []
        
        try:
            if ocr_blocks is None:
                if self.browser.page:
                    screenshot_path = await self.browser.take_screenshot()
                    if screenshot_path:
                        ocr_result = await self.ocr_service.analyze_screenshot(screenshot_path)
                        if ocr_result and ocr_result.blocks:
                            ocr_blocks = ocr_result.blocks
            
            if ocr_blocks:
                # Buscar bloques que contengan keywords de modal
                for block in ocr_blocks:
                    text_lower = (block.text if hasattr(block, 'text') else str(block)).lower()
                    for keyword in modal_keywords:
                        if keyword in text_lower:
                            modals.append({
                                "text": block.text if hasattr(block, 'text') else str(block),
                                "x": block.x if hasattr(block, 'x') else 0,
                                "y": block.y if hasattr(block, 'y') else 0,
                            })
                            break
            
            return modals
        except Exception as e:
            logger.warning(f"[visual-explorer] Error detecting modals: {e}")
            return []
    
    async def detect_visual_forms(self, ocr_blocks: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """
        Detecta formularios visuales (etiquetas, campos).
        
        Args:
            ocr_blocks: Bloques OCR opcionales
            
        Returns:
            Lista de formularios detectados
        """
        if not self.ocr_service or not self.ocr_service.enabled:
            return []
        
        form_keywords = ["fecha", "nombre", "documento", "código", "código", "trabajador"]
        forms = []
        
        try:
            if ocr_blocks is None:
                if self.browser.page:
                    screenshot_path = await self.browser.take_screenshot()
                    if screenshot_path:
                        ocr_result = await self.ocr_service.analyze_screenshot(screenshot_path)
                        if ocr_result and ocr_result.blocks:
                            ocr_blocks = ocr_result.blocks
            
            if ocr_blocks:
                # Agrupar bloques cercanos que parecen formularios
                for block in ocr_blocks:
                    text_lower = (block.text if hasattr(block, 'text') else str(block)).lower()
                    for keyword in form_keywords:
                        if keyword in text_lower:
                            forms.append({
                                "label": block.text if hasattr(block, 'text') else str(block),
                                "x": block.x if hasattr(block, 'x') else 0,
                                "y": block.y if hasattr(block, 'y') else 0,
                            })
                            break
            
            return forms
        except Exception as e:
            logger.warning(f"[visual-explorer] Error detecting visual forms: {e}")
            return []
    
    async def build_coordinates_map(self, ocr_blocks: Optional[List[Any]] = None) -> Dict[str, tuple]:
        """
        Construye un mapa de coordenadas texto -> (x, y).
        
        Args:
            ocr_blocks: Bloques OCR opcionales
            
        Returns:
            Diccionario texto -> (x, y)
        """
        coordinates_map = {}
        
        try:
            if ocr_blocks is None:
                if self.browser.page:
                    screenshot_path = await self.browser.take_screenshot()
                    if screenshot_path and self.ocr_service and self.ocr_service.enabled:
                        ocr_result = await self.ocr_service.analyze_screenshot(screenshot_path)
                        if ocr_result and ocr_result.blocks:
                            ocr_blocks = ocr_result.blocks
            
            if ocr_blocks:
                for block in ocr_blocks:
                    text = block.text if hasattr(block, 'text') else str(block)
                    x = block.x if hasattr(block, 'x') else 0
                    y = block.y if hasattr(block, 'y') else 0
                    coordinates_map[text] = (x, y)
            
            return coordinates_map
        except Exception as e:
            logger.warning(f"[visual-explorer] Error building coordinates map: {e}")
            return {}
    
    async def take_snapshot(self, ocr_blocks: Optional[List[Any]] = None) -> VisualSnapshot:
        """
        Toma un snapshot visual completo.
        
        Args:
            ocr_blocks: Bloques OCR opcionales (si ya están disponibles)
            
        Returns:
            VisualSnapshot con toda la información visual
        """
        logger.debug("[visual-explorer] Taking visual snapshot...")
        
        buttons = await self.detect_visual_buttons(ocr_blocks)
        keywords = await self.detect_cae_keywords_visual(ocr_blocks)
        modals = await self.detect_modals(ocr_blocks)
        forms = await self.detect_visual_forms(ocr_blocks)
        coordinates = await self.build_coordinates_map(ocr_blocks)
        
        # Extraer textos detectados
        texts = []
        if ocr_blocks:
            for block in ocr_blocks:
                texts.append({
                    "text": block.text if hasattr(block, 'text') else str(block),
                    "x": block.x if hasattr(block, 'x') else 0,
                    "y": block.y if hasattr(block, 'y') else 0,
                })
        
        snapshot = VisualSnapshot(
            buttons_detected=buttons,
            texts_detected=texts,
            modals_detected=modals,
            forms_detected=forms,
            cae_keywords_found=keywords,
            coordinates_map=coordinates,
        )
        
        logger.debug(
            f"[visual-explorer] Snapshot taken: {len(buttons)} buttons, {len(keywords)} keywords, "
            f"{len(modals)} modals, {len(forms)} forms"
        )
        
        return snapshot














