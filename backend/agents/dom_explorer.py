"""
DOM Explorer: Exploración automática del DOM para detectar elementos relevantes.

v5.0.0: Extrae información estructural del DOM para planificación autónoma.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DOMSnapshot:
    """
    Snapshot del estado del DOM.
    
    v5.0.0: Contiene información estructurada sobre elementos del DOM.
    """
    links: List[Dict[str, Any]] = None
    buttons: List[Dict[str, Any]] = None
    inputs: List[Dict[str, Any]] = None
    tables: List[Dict[str, Any]] = None
    navigation_panels: List[Dict[str, Any]] = None
    cae_keywords_found: List[str] = None
    forms: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.links is None:
            self.links = []
        if self.buttons is None:
            self.buttons = []
        if self.inputs is None:
            self.inputs = []
        if self.tables is None:
            self.tables = []
        if self.navigation_panels is None:
            self.navigation_panels = []
        if self.cae_keywords_found is None:
            self.cae_keywords_found = []
        if self.forms is None:
            self.forms = []


class DOMExplorer:
    """
    Explorador del DOM para extraer información estructural.
    
    v5.0.0: Proporciona funciones para explorar y analizar el DOM.
    """
    
    def __init__(self, browser_controller):
        """
        Inicializa el explorador DOM.
        
        Args:
            browser_controller: Instancia de BrowserController
        """
        self.browser = browser_controller
    
    async def extract_all_links(self) -> List[Dict[str, Any]]:
        """
        Extrae todos los enlaces del DOM.
        
        Returns:
            Lista de enlaces con href, text, selector
        """
        if not self.browser.page:
            return []
        
        try:
            links = await self.browser.page.evaluate("""
                () => {
                    const allLinks = [];
                    document.querySelectorAll('a[href]').forEach(link => {
                        allLinks.push({
                            href: link.href,
                            text: link.innerText.trim(),
                            selector: `a[href="${link.getAttribute('href')}"]`,
                        });
                    });
                    return allLinks;
                }
            """)
            return links
        except Exception as e:
            logger.warning(f"[dom-explorer] Error extracting links: {e}")
            return []
    
    async def extract_all_buttons(self) -> List[Dict[str, Any]]:
        """
        Extrae todos los botones del DOM.
        
        Returns:
            Lista de botones con text, type, selector
        """
        if not self.browser.page:
            return []
        
        try:
            buttons = await self.browser.page.evaluate("""
                () => {
                    const allButtons = [];
                    // Botones <button>
                    document.querySelectorAll('button').forEach(btn => {
                        allButtons.push({
                            text: btn.innerText.trim(),
                            type: btn.type,
                            selector: `button:has-text("${btn.innerText.trim()}")`,
                            tag: 'button',
                        });
                    });
                    // Inputs tipo button/submit
                    document.querySelectorAll('input[type="button"], input[type="submit"]').forEach(btn => {
                        allButtons.push({
                            text: btn.value || btn.getAttribute('aria-label') || '',
                            type: btn.type,
                            selector: `input[type="${btn.type}"][value="${btn.value}"]`,
                            tag: 'input',
                        });
                    });
                    return allButtons;
                }
            """)
            return buttons
        except Exception as e:
            logger.warning(f"[dom-explorer] Error extracting buttons: {e}")
            return []
    
    async def extract_all_inputs(self) -> List[Dict[str, Any]]:
        """
        Extrae todos los inputs del DOM.
        
        Returns:
            Lista de inputs con type, name, id, selector
        """
        if not self.browser.page:
            return []
        
        try:
            inputs = await self.browser.page.evaluate("""
                () => {
                    const allInputs = [];
                    document.querySelectorAll('input, textarea, select').forEach(input => {
                        allInputs.push({
                            type: input.type || input.tagName.toLowerCase(),
                            name: input.name || '',
                            id: input.id || '',
                            selector: input.id ? `#${input.id}` : (input.name ? `[name="${input.name}"]` : ''),
                            placeholder: input.placeholder || '',
                        });
                    });
                    return allInputs;
                }
            """)
            return inputs
        except Exception as e:
            logger.warning(f"[dom-explorer] Error extracting inputs: {e}")
            return []
    
    async def detect_cae_keywords(self) -> List[str]:
        """
        Detecta keywords relacionados con CAE en el DOM.
        
        Returns:
            Lista de keywords encontrados
        """
        if not self.browser.page:
            return []
        
        cae_keywords = [
            "cae", "prevención", "prevencion", "riesgos laborales",
            "documentación", "documentacion", "trabajador", "trabajadores",
            "subir", "adjuntar", "documento", "expedición", "expedicion",
            "reconocimiento médico", "formación", "formacion", "prl",
        ]
        
        try:
            page_text = await self.browser.page.evaluate("() => document.body.innerText.toLowerCase()")
            found_keywords = [kw for kw in cae_keywords if kw in page_text]
            return found_keywords
        except Exception as e:
            logger.warning(f"[dom-explorer] Error detecting CAE keywords: {e}")
            return []
    
    async def detect_tables(self) -> List[Dict[str, Any]]:
        """
        Detecta tablas en el DOM.
        
        Returns:
            Lista de tablas con headers y row count
        """
        if not self.browser.page:
            return []
        
        try:
            tables = await self.browser.page.evaluate("""
                () => {
                    const allTables = [];
                    document.querySelectorAll('table').forEach(table => {
                        const headers = [];
                        table.querySelectorAll('th').forEach(th => {
                            headers.push(th.innerText.trim());
                        });
                        const rowCount = table.querySelectorAll('tr').length;
                        allTables.push({
                            headers: headers,
                            rowCount: rowCount,
                            selector: 'table',
                        });
                    });
                    return allTables;
                }
            """)
            return tables
        except Exception as e:
            logger.warning(f"[dom-explorer] Error detecting tables: {e}")
            return []
    
    async def detect_navigation_panels(self) -> List[Dict[str, Any]]:
        """
        Detecta paneles de navegación (menús, sidebars).
        
        Returns:
            Lista de paneles con links y estructura
        """
        if not self.browser.page:
            return []
        
        try:
            panels = await self.browser.page.evaluate("""
                () => {
                    const allPanels = [];
                    // Buscar nav, aside, elementos con clase menu/sidebar
                    const selectors = ['nav', 'aside', '[class*="menu"]', '[class*="sidebar"]', '[class*="navigation"]'];
                    selectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(panel => {
                            const links = [];
                            panel.querySelectorAll('a').forEach(link => {
                                links.push({
                                    text: link.innerText.trim(),
                                    href: link.href,
                                });
                            });
                            if (links.length > 0) {
                                allPanels.push({
                                    selector: sel,
                                    links: links,
                                });
                            }
                        });
                    });
                    return allPanels;
                }
            """)
            return panels
        except Exception as e:
            logger.warning(f"[dom-explorer] Error detecting navigation panels: {e}")
            return []
    
    async def detect_forms(self) -> List[Dict[str, Any]]:
        """
        Detecta formularios en el DOM.
        
        Returns:
            Lista de formularios con inputs y estructura
        """
        if not self.browser.page:
            return []
        
        try:
            forms = await self.browser.page.evaluate("""
                () => {
                    const allForms = [];
                    document.querySelectorAll('form').forEach(form => {
                        const inputs = [];
                        form.querySelectorAll('input, textarea, select').forEach(input => {
                            inputs.push({
                                type: input.type || input.tagName.toLowerCase(),
                                name: input.name || '',
                                id: input.id || '',
                            });
                        });
                        allForms.push({
                            id: form.id || '',
                            action: form.action || '',
                            method: form.method || '',
                            inputs: inputs,
                            selector: form.id ? `#${form.id}` : 'form',
                        });
                    });
                    return allForms;
                }
            """)
            return forms
        except Exception as e:
            logger.warning(f"[dom-explorer] Error detecting forms: {e}")
            return []
    
    async def take_snapshot(self) -> DOMSnapshot:
        """
        Toma un snapshot completo del DOM.
        
        Returns:
            DOMSnapshot con toda la información extraída
        """
        logger.debug("[dom-explorer] Taking DOM snapshot...")
        
        links = await self.extract_all_links()
        buttons = await self.extract_all_buttons()
        inputs = await self.extract_all_inputs()
        tables = await self.detect_tables()
        navigation_panels = await self.detect_navigation_panels()
        cae_keywords = await self.detect_cae_keywords()
        forms = await self.detect_forms()
        
        snapshot = DOMSnapshot(
            links=links,
            buttons=buttons,
            inputs=inputs,
            tables=tables,
            navigation_panels=navigation_panels,
            cae_keywords_found=cae_keywords,
            forms=forms,
        )
        
        logger.debug(
            f"[dom-explorer] Snapshot taken: {len(links)} links, {len(buttons)} buttons, "
            f"{len(inputs)} inputs, {len(forms)} forms, {len(cae_keywords)} CAE keywords"
        )
        
        return snapshot



