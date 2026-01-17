"""
Helper para detectar y manejar paginación en grids de eGestiona.

SPRINT C2.14.1: Soporta paginación completa para obtener snapshot completo
de todos los pendientes visibles en todas las páginas.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import time
import re


def detect_pagination_controls(frame: Any) -> Dict[str, Any]:
    """
    Detecta controles de paginación en el frame.
    
    Args:
        frame: Playwright frame que contiene el grid
    
    Returns:
        Dict con:
        - has_pagination: bool - Si hay controles de paginación detectados
        - next_button: Dict | None - Info del botón "next" (>)
        - prev_button: Dict | None - Info del botón "prev" (<)
        - first_button: Dict | None - Info del botón "first" (<<)
        - last_button: Dict | None - Info del botón "last" (>>)
        - page_info: Dict | None - Info del texto "Página X de Y"
        - controls_html: str - HTML del contenedor de paginación (para debug)
    """
    result = {
        "has_pagination": False,
        "next_button": None,
        "prev_button": None,
        "first_button": None,
        "last_button": None,
        "page_info": None,
        "controls_html": None,
    }
    
    try:
        # Evaluar en el frame para buscar controles de paginación
        pagination_info = frame.evaluate("""() => {
            function norm(s) { return (s || '').replace(/\\s+/g, ' ').trim(); }
            
            // Buscar contenedor de paginación (común en DHTMLX: .dhx_paging, .paging, etc.)
            const paginationSelectors = [
                '.dhx_paging',
                '.paging',
                '.pagination',
                '[class*="paging"]',
                '[class*="pagination"]',
                '[id*="paging"]',
                '[id*="pagination"]',
            ];
            
            let paginationContainer = null;
            for (const sel of paginationSelectors) {
                const elem = document.querySelector(sel);
                if (elem) {
                    paginationContainer = elem;
                    break;
                }
            }
            
            // Si no se encuentra contenedor específico, buscar botones de paginación directamente
            if (!paginationContainer) {
                const allButtons = Array.from(document.querySelectorAll('button, input[type="button"], a'));
                const pagButtons = allButtons.filter(btn => {
                    const text = norm(btn.innerText || btn.textContent || btn.value || '');
                    return /^[<>]{1,2}$/.test(text) || 
                           /siguiente|next|anterior|prev|primera|first|última|last/i.test(text);
                });
                if (pagButtons.length > 0) {
                    paginationContainer = pagButtons[0].parentElement || document.body;
                }
            }
            
            if (!paginationContainer) {
                return { found: false };
            }
            
            const containerHtml = paginationContainer.outerHTML.substring(0, 1000);
            
            // Buscar botones
            const buttons = Array.from(paginationContainer.querySelectorAll('button, input[type="button"], a'));
            
            function getButtonInfo(btn, expectedText) {
                const text = norm(btn.innerText || btn.textContent || btn.value || '');
                const isMatch = expectedText.test(text) || 
                               (expectedText === '>' && text === '>' || text.includes('siguiente') || text.includes('next')) ||
                               (expectedText === '<' && text === '<' || text.includes('anterior') || text.includes('prev')) ||
                               (expectedText === '<<' && text === '<<' || text.includes('primera') || text.includes('first')) ||
                               (expectedText === '>>' && text === '>>' || text.includes('última') || text.includes('last'));
                
                if (isMatch) {
                    try {
                        const isVisible = btn.offsetParent !== null;
                        const isEnabled = !btn.disabled && !btn.hasAttribute('disabled');
                        const bbox = btn.getBoundingClientRect();
                        return {
                            text: text,
                            isVisible: isVisible,
                            isEnabled: isEnabled,
                            boundingBox: bbox ? { x: bbox.x, y: bbox.y, width: bbox.width, height: bbox.height } : null,
                            selector: btn.tagName.toLowerCase() + (btn.id ? '#' + btn.id : '') + (btn.className ? '.' + btn.className.split(' ')[0] : ''),
                        };
                    } catch (e) {
                        return null;
                    }
                }
                return null;
            }
            
            const nextBtn = buttons.find(btn => getButtonInfo(btn, '>'));
            const prevBtn = buttons.find(btn => getButtonInfo(btn, '<'));
            const firstBtn = buttons.find(btn => getButtonInfo(btn, '<<'));
            const lastBtn = buttons.find(btn => getButtonInfo(btn, '>>'));
            
            // Buscar texto "Página X de Y"
            const pageInfoPattern = /página\\s+(\\d+)\\s+de\\s+(\\d+)/i;
            const containerText = norm(paginationContainer.innerText || '');
            let pageInfo = null;
            const match = containerText.match(pageInfoPattern);
            if (match) {
                pageInfo = {
                    current: parseInt(match[1]),
                    total: parseInt(match[2]),
                    text: match[0],
                };
            }
            
            return {
                found: true,
                nextButton: nextBtn ? getButtonInfo(nextBtn, '>') : null,
                prevButton: prevBtn ? getButtonInfo(prevBtn, '<') : null,
                firstButton: firstBtn ? getButtonInfo(firstBtn, '<<') : null,
                lastButton: lastBtn ? getButtonInfo(lastBtn, '>>') : null,
                pageInfo: pageInfo,
                containerHtml: containerHtml,
            };
        }""")
        
        if pagination_info.get("found"):
            result["has_pagination"] = True
            result["next_button"] = pagination_info.get("nextButton")
            result["prev_button"] = pagination_info.get("prevButton")
            result["first_button"] = pagination_info.get("firstButton")
            result["last_button"] = pagination_info.get("lastButton")
            result["page_info"] = pagination_info.get("pageInfo")
            result["controls_html"] = pagination_info.get("containerHtml")
    
    except Exception as e:
        # Si hay error, asumir que no hay paginación
        result["error"] = str(e)
    
    return result


def wait_for_page_change(
    frame: Any,
    initial_signature: Optional[str] = None,
    initial_row_count: Optional[int] = None,
    timeout_seconds: float = 10.0,
) -> bool:
    """
    Espera a que la página del grid cambie después de un click de paginación.
    
    Args:
        frame: Playwright frame que contiene el grid
        initial_signature: Firma de la primera fila antes del cambio (opcional)
        initial_row_count: Conteo de filas antes del cambio (opcional)
        timeout_seconds: Timeout máximo para esperar
    
    Returns:
        bool - True si se detectó cambio, False si timeout
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Verificar si cambió el contador de registros
            if initial_row_count is not None:
                current_count = frame.locator("table.obj.row20px tbody tr").count()
                if current_count != initial_row_count:
                    return True
            
            # Verificar si cambió la firma de la primera fila
            if initial_signature:
                try:
                    first_row_text = frame.evaluate("""() => {
                        const firstRow = document.querySelector('table.obj.row20px tbody tr');
                        if (!firstRow) return '';
                        return (firstRow.innerText || '').substring(0, 100);
                    }""")
                    if first_row_text and first_row_text != initial_signature:
                        return True
                except Exception:
                    pass
            
            # Verificar si hay overlay de loading
            loading_selectors = [
                r'text=/loading\.\.\./i',
                r'text=/cargando\.\.\./i',
                '[class*="loading"]',
                '[id*="loading"]',
            ]
            
            has_loading = False
            for selector in loading_selectors:
                try:
                    if frame.locator(selector).count() > 0:
                        has_loading = True
                        break
                except Exception:
                    continue
            
            # Si hay loading, esperar a que desaparezca
            if has_loading:
                time.sleep(0.3)
                continue
            
            # Si no hay loading y ya pasó tiempo suficiente, considerar que cambió
            if time.time() - start_time > 2.0:
                # Verificar que hay filas
                try:
                    row_count = frame.locator("table.obj.row20px tbody tr").count()
                    if row_count > 0:
                        return True
                except Exception:
                    pass
            
            time.sleep(0.3)
        except Exception:
            time.sleep(0.3)
    
    return False


def click_pagination_button(
    frame: Any,
    button_info: Dict[str, Any],
    evidence_dir: Optional[Any] = None,
) -> bool:
    """
    Hace click en un botón de paginación de forma robusta.
    
    Args:
        frame: Playwright frame que contiene el grid
        button_info: Info del botón (de detect_pagination_controls)
        evidence_dir: Directorio para evidencias (opcional)
    
    Returns:
        bool - True si el click fue exitoso
    """
    if not button_info or not button_info.get("isVisible") or not button_info.get("isEnabled"):
        return False
    
    try:
        # Intentar click por selector de texto
        button_text = button_info.get("text", "")
        if button_text:
            try:
                # Buscar botón por texto exacto
                button_locator = frame.locator(f'button:has-text("{button_text}"), input[type="button"][value="{button_text}"], a:has-text("{button_text}")')
                if button_locator.count() > 0:
                    button_locator.first.click(timeout=5000)
                    return True
            except Exception:
                pass
        
        # Intentar click por posición (boundingBox)
        bbox = button_info.get("boundingBox")
        if bbox:
            try:
                frame.click(bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2, timeout=5000)
                return True
            except Exception:
                pass
        
        # Intentar click por selector genérico
        selector = button_info.get("selector")
        if selector:
            try:
                frame.locator(selector).first.click(timeout=5000)
                return True
            except Exception:
                pass
    
    except Exception as e:
        if evidence_dir:
            try:
                error_path = evidence_dir / "pagination_click_error.txt"
                with open(error_path, "w", encoding="utf-8") as f:
                    f.write(f"Error clicking pagination button: {e}\n")
                    f.write(f"Button info: {button_info}\n")
            except Exception:
                pass
    
    return False
