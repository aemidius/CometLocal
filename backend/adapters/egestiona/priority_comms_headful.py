"""
Helper para cerrar automáticamente el modal de "Comunicados prioritarios" en eGestiona.

Este modal bloqueante aparece después del login en algunos clientes (ej: Aigues de Manresa)
y requiere marcar todos los comunicados como leídos antes de poder cerrarlo.

VERSIÓN 3: Descubrimiento automático del DOM real + fallbacks robustos
"""

from __future__ import annotations

import time
import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from playwright.sync_api import Page, Frame, TimeoutError as PlaywrightTimeoutError


class PriorityCommsModalNotDismissed(Exception):
    """Excepción específica cuando no se puede cerrar el modal de comunicados prioritarios."""
    pass


class DhxBlockerNotDismissed(Exception):
    """Excepción específica cuando no se puede cerrar un overlay DHTMLX bloqueante."""
    pass


def dump_clickables(context: Page | Frame, scope_name: str, evidence_dir: Path) -> List[Dict[str, Any]]:
    """
    Descubre y guarda todos los elementos clickables en el contexto dado.
    
    Args:
        context: Página o frame de Playwright
        scope_name: Nombre del scope (para el archivo JSON)
        evidence_dir: Directorio donde guardar el JSON
    
    Returns:
        Lista de elementos clickables con información detallada
    """
    clickables = []
    selectors = ["button", "a", "[role=button]", "input[type=button]", "input[type=submit]", "[onclick]"]
    
    try:
        for selector in selectors:
            try:
                elements = context.locator(selector)
                count = elements.count()
                for i in range(count):
                    try:
                        elem = elements.nth(i)
                        # Verificar si es visible (con timeout corto para no bloquear)
                        try:
                            if not elem.is_visible(timeout=200):
                                continue
                        except Exception:
                            # Si no se puede verificar visibilidad, incluir de todas formas
                            pass
                        
                        # Obtener información del elemento
                        try:
                            text = elem.text_content() or ""
                            text = text.strip()[:200]  # Limitar tamaño
                        except Exception:
                            text = ""
                        
                        try:
                            value = elem.get_attribute("value") or ""
                            value = value.strip()[:200]
                        except Exception:
                            value = ""
                        
                        try:
                            aria_label = elem.get_attribute("aria-label") or ""
                        except Exception:
                            aria_label = ""
                        
                        try:
                            title = elem.get_attribute("title") or ""
                        except Exception:
                            title = ""
                        
                        try:
                            elem_id = elem.get_attribute("id") or ""
                        except Exception:
                            elem_id = ""
                        
                        try:
                            class_name = elem.get_attribute("class") or ""
                        except Exception:
                            class_name = ""
                        
                        try:
                            tag_name = elem.evaluate("el => el.tagName.toLowerCase()")
                        except Exception:
                            tag_name = ""
                        
                        try:
                            outer_html = elem.evaluate("el => el.outerHTML") or ""
                            outer_html = outer_html[:500]  # Limitar tamaño
                        except Exception:
                            outer_html = ""
                        
                        try:
                            onclick = elem.get_attribute("onclick") or ""
                            onclick = onclick[:200]
                        except Exception:
                            onclick = ""
                        
                        # Obtener bounding box
                        try:
                            bbox = elem.bounding_box()
                            bbox_info = {"x": bbox["x"], "y": bbox["y"], "width": bbox["width"], "height": bbox["height"]} if bbox else None
                        except Exception:
                            bbox_info = None
                        
                        clickable_info = {
                            "selector": selector,
                            "index": i,
                            "tagName": tag_name,
                            "text": text,
                            "value": value,
                            "aria-label": aria_label,
                            "title": title,
                            "id": elem_id,
                            "className": class_name,
                            "onclick": onclick,
                            "outerHTML": outer_html,
                            "boundingBox": bbox_info,
                        }
                        clickables.append(clickable_info)
                    except Exception as e:
                        # Continuar con siguiente elemento
                        continue
            except Exception:
                continue
        
        # Guardar JSON
        json_path = evidence_dir / f"clickables_{scope_name}.json"
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(clickables, f, indent=2, ensure_ascii=False)
            print(f"[PRIORITY_COMMS] Clickables dump guardado: {json_path} ({len(clickables)} elementos)")
        except Exception as e:
            print(f"[PRIORITY_COMMS] Error al guardar JSON {json_path}: {e}")
            # Intentar guardar en un archivo alternativo
            try:
                alt_path = evidence_dir / f"clickables_{scope_name}_alt.json"
                with open(alt_path, "w", encoding="utf-8") as f:
                    json.dump(clickables, f, indent=2, ensure_ascii=False)
                print(f"[PRIORITY_COMMS] Clickables dump guardado en archivo alternativo: {alt_path}")
            except Exception as e2:
                print(f"[PRIORITY_COMMS] Error al guardar archivo alternativo: {e2}")
        
    except Exception as e:
        print(f"[PRIORITY_COMMS] Error en dump_clickables: {e}")
    
    return clickables


def dismiss_priority_comms_if_present(
    page: Page,
    evidence_dir: Path,
    timeout_seconds: int = 30,
    max_iterations: int = 20,
) -> bool:
    """
    Detecta y cierra el modal de "Comunicados prioritarios" si está presente.
    
    Args:
        page: Página de Playwright (puede ser main page o frame)
        evidence_dir: Directorio donde guardar screenshots de evidence
        timeout_seconds: Timeout máximo para cerrar el modal
        max_iterations: Máximo número de iteraciones para marcar comunicados
    
    Returns:
        True si el modal estaba presente y se cerró, False si no estaba presente
    
    Raises:
        PriorityCommsModalNotDismissed: Si el modal está presente pero no se puede cerrar
    """
    start_time = time.time()
    
    # 1) Detectar si el modal está presente
    modal_detected = False
    modal_frame: Optional[Frame] = None
    
    # Textos clave para detectar el modal
    title_texts = [
        "Comunicados prioritarios",
        "comunicados prioritarios",
        "COMUNICADOS PRIORITARIOS",
        "Avisos, comunicados y noticias sin leer",
    ]
    
    # PRIMERO: Buscar iframe específico de ComunicadosPrioritarios (más confiable)
    try:
        iframe_locator = page.locator('iframe[src*="ComunicadosPrioritarios"]')
        if iframe_locator.count() > 0:
            for frame in page.frames:
                if "ComunicadosPrioritarios" in frame.url:
                    modal_frame = frame
                    modal_detected = True
                    print(f"[PRIORITY_COMMS] Modal detectado en iframe: {frame.url}")
                    break
    except Exception as e:
        print(f"[PRIORITY_COMMS] Error al buscar iframe: {e}")
    
    # SEGUNDO: Si no se encontró el iframe, buscar por texto
    if not modal_detected:
        for title_text in title_texts:
            try:
                locator = page.locator(f'text="{title_text}"')
                if locator.count() > 0:
                    modal_detected = True
                    modal_frame = None
                    break
            except Exception:
                pass
    
    # Si no se detectó el modal, retornar False (no hacer nada)
    if not modal_detected:
        return False
    
    # 2) Modal detectado: proceder a cerrarlo
    print(f"[PRIORITY_COMMS] Modal detectado, iniciando cierre...")
    
    # Esperar a que el iframe esté cargado si es necesario
    if modal_frame:
        try:
            modal_frame.wait_for_load_state("domcontentloaded", timeout=10000)
            time.sleep(1.5)  # Dar tiempo adicional
            print(f"[PRIORITY_COMMS] Iframe cargado: {modal_frame.url}")
        except Exception as e:
            print(f"[PRIORITY_COMMS] Advertencia: No se pudo esperar carga del iframe: {e}")
    
    # Screenshot inicial
    if evidence_dir is not None:
        try:
            screenshot_path = evidence_dir / "priority_comms_modal_initial.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"[PRIORITY_COMMS] Screenshot inicial guardado: {screenshot_path}")
        except Exception as e:
            print(f"[PRIORITY_COMMS] Error al guardar screenshot inicial: {e}")
    else:
        print(f"[DHX_BLOCKER] evidence_dir None, skip screenshot")
    
    # CLICKABLES DISCOVERY DUMP
    print(f"[PRIORITY_COMMS] Generando clickables discovery dump...")
    try:
        clickables_page = dump_clickables(page, "page", evidence_dir)
        print(f"[PRIORITY_COMMS] Clickables page: {len(clickables_page)} elementos")
    except Exception as e:
        print(f"[PRIORITY_COMMS] Error al generar clickables page: {e}")
        clickables_page = []
    
    if modal_frame:
        try:
            frame_name = modal_frame.url.split('/')[-1] if modal_frame.url else "frame_unknown"
            frame_name = frame_name.replace('.aspx', '').replace('.asp', '')[:50]  # Limitar tamaño
            clickables_frame = dump_clickables(modal_frame, f"frame_{frame_name}", evidence_dir)
            print(f"[PRIORITY_COMMS] Clickables frame: {len(clickables_frame)} elementos")
        except Exception as e:
            print(f"[PRIORITY_COMMS] Error al generar clickables frame: {e}")
            clickables_frame = []
    
    # 3) Localizar y parsear el contador "No leído: X"
    unread_count = None
    unread_patterns = [
        r"No leído:\s*(\d+)",
        r"no leído:\s*(\d+)",
        r"NO LEÍDO:\s*(\d+)",
        r"(\d+)\s*no leído",
        r"(\d+)\s*No leído",
    ]
    
    # Determinar el contexto (frame o página principal)
    ctx = modal_frame if modal_frame else page
    
    # Buscar contador en el contexto
    for pattern in unread_patterns:
        try:
            text_content = ctx.content()
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                unread_count = int(match.group(1))
                print(f"[PRIORITY_COMMS] Contador encontrado: {unread_count} no leídos")
                break
        except Exception:
            pass
    
    # Si no se encontró por regex, buscar por texto visible
    if unread_count is None:
        try:
            unread_text_locator = ctx.locator('text=/No leído|no leído|NO LEÍDO/i')
            if unread_text_locator.count() > 0:
                text = unread_text_locator.first.text_content()
                match = re.search(r'(\d+)', text or "")
                if match:
                    unread_count = int(match.group(1))
                    print(f"[PRIORITY_COMMS] Contador encontrado en texto visible: {unread_count}")
        except Exception:
            pass
    
    # Si no se encontró contador, asumir que hay comunicados y proceder
    if unread_count is None:
        print(f"[PRIORITY_COMMS] No se encontró contador, asumiendo que hay comunicados por marcar")
        unread_count = 1  # Asumir al menos uno
    
    # 4) Mientras haya comunicados no leídos, marcarlos como leídos
    iteration = 0
    while unread_count > 0 and iteration < max_iterations:
        if time.time() - start_time > timeout_seconds:
            raise PriorityCommsModalNotDismissed(
                f"Timeout después de {timeout_seconds}s intentando cerrar el modal de comunicados prioritarios"
            )
        
        iteration += 1
        print(f"[PRIORITY_COMMS] Iteración {iteration}: {unread_count} comunicados no leídos")
        
        # Screenshot antes de la iteración
        if evidence_dir is not None:
            try:
                screenshot_path = evidence_dir / f"priority_comms_before_iter_{iteration}.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                pass
        
        # 4a) Abrir un comunicado no leído (click en título/link)
        comm_opened = False
        try:
            if modal_frame:
                # Buscar en el frame - intentar varios selectores
                comm_links = None
                try:
                    comm_links = modal_frame.locator('a[href]:not([href=""]), a:not([href=""]), [role="link"]')
                    if comm_links.count() == 0:
                        comm_links = modal_frame.locator('tr, li, [onclick], [class*="comunicado"], [class*="item"], [class*="titulo"]')
                except Exception:
                    pass
            else:
                comm_links = page.locator('.dhtmlx_window_active a, .dhtmlx_window_active [role="link"]')
            
            if comm_links and comm_links.count() > 0:
                first_link = comm_links.first
                try:
                    first_link.click(timeout=5000)
                    print(f"[PRIORITY_COMMS] Click en comunicado (iteración {iteration})")
                    time.sleep(1.5)
                    comm_opened = True
                except Exception as e:
                    print(f"[PRIORITY_COMMS] Error al hacer click en comunicado: {e}")
                    try:
                        first_link.click(force=True, timeout=3000)
                        time.sleep(1.5)
                        comm_opened = True
                        print(f"[PRIORITY_COMMS] Click forzado en comunicado (iteración {iteration})")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[PRIORITY_COMMS] Error buscando comunicado: {e}")
        
        # 4b) Pulsar "Marcar como leído" (primero en page, luego en frame)
        mark_read_clicked = False
        mark_read_patterns = [
            r"marcar como le[ií]do",
            r"Marcar como le[ií]do",
            r"marcar",
            r"Marcar",
        ]
        
        # Intentar en page primero
        for text_pattern in mark_read_patterns:
            try:
                # Buscar cualquier elemento que contenga el texto (no solo botones)
                text_locator = page.locator(f'text=/{text_pattern}/i')
                if text_locator.count() > 0:
                    # Intentar hacer click directamente
                    try:
                        text_locator.first.click(timeout=3000)
                        print(f"[PRIORITY_COMMS] Click en 'Marcar como leído' (page, texto directo, iteración {iteration})")
                        mark_read_clicked = True
                        break
                    except Exception:
                        # Si no es clickable, buscar ancestor clickable
                        try:
                            clickable_ancestor = text_locator.first.locator("xpath=ancestor-or-self::*[self::a or self::button or @role='button' or @onclick][1]")
                            if clickable_ancestor.count() > 0:
                                clickable_ancestor.first.click(timeout=3000)
                                print(f"[PRIORITY_COMMS] Click en 'Marcar como leído' (page, ancestor clickable, iteración {iteration})")
                                mark_read_clicked = True
                                break
                        except Exception:
                            # Fallback: click por coordenadas
                            try:
                                bbox = text_locator.first.bounding_box()
                                if bbox:
                                    center_x = bbox["x"] + bbox["width"] / 2
                                    center_y = bbox["y"] + bbox["height"] / 2
                                    page.mouse.click(center_x, center_y)
                                    print(f"[PRIORITY_COMMS] Click por coordenadas en 'Marcar como leído' (page, iteración {iteration})")
                                    mark_read_clicked = True
                                    break
                            except Exception:
                                pass
            except Exception:
                pass
        
        # Si no se encontró en page, intentar en frame
        if not mark_read_clicked and modal_frame:
            for text_pattern in mark_read_patterns:
                try:
                    text_locator = modal_frame.locator(f'text=/{text_pattern}/i')
                    if text_locator.count() > 0:
                        # Intentar hacer click directamente
                        try:
                            text_locator.first.click(timeout=3000)
                            print(f"[PRIORITY_COMMS] Click en 'Marcar como leído' (frame, texto directo, iteración {iteration})")
                            mark_read_clicked = True
                            break
                        except Exception:
                            # Si no es clickable, buscar ancestor clickable
                            try:
                                clickable_ancestor = text_locator.first.locator("xpath=ancestor-or-self::*[self::a or self::button or @role='button' or @onclick][1]")
                                if clickable_ancestor.count() > 0:
                                    clickable_ancestor.first.click(timeout=3000)
                                    print(f"[PRIORITY_COMMS] Click en 'Marcar como leído' (frame, ancestor clickable, iteración {iteration})")
                                    mark_read_clicked = True
                                    break
                            except Exception:
                                # Fallback: click por coordenadas
                                try:
                                    bbox = text_locator.first.bounding_box()
                                    if bbox:
                                        center_x = bbox["x"] + bbox["width"] / 2
                                        center_y = bbox["y"] + bbox["height"] / 2
                                        page.mouse.click(center_x, center_y)
                                        print(f"[PRIORITY_COMMS] Click por coordenadas en 'Marcar como leído' (frame, iteración {iteration})")
                                        mark_read_clicked = True
                                        break
                                except Exception:
                                    pass
                except Exception:
                    pass
        
        # Si aún no se encontró, buscar por cualquier botón que contenga "marcar" o "leído"
        if not mark_read_clicked:
            try:
                all_buttons = page.locator('button, a, input[type="button"], input[type="submit"]')
                for i in range(min(all_buttons.count(), 20)):
                    try:
                        btn = all_buttons.nth(i)
                        btn_text = btn.text_content() or ""
                        if any(word in btn_text.lower() for word in ["marcar", "leído", "leido"]):
                            btn.click(timeout=3000)
                            print(f"[PRIORITY_COMMS] Click en botón encontrado por texto: '{btn_text}' (iteración {iteration})")
                            mark_read_clicked = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        
        if not mark_read_clicked:
            print(f"[PRIORITY_COMMS] No se encontró botón 'Marcar como leído' en iteración {iteration}")
        
        # 4c) Esperar a que el contador cambie
        time.sleep(2.0)
        
        # Releer el contador
        new_unread_count = None
        for pattern in unread_patterns:
            try:
                text_content = ctx.content()
                match = re.search(pattern, text_content, re.IGNORECASE)
                if match:
                    new_unread_count = int(match.group(1))
                    break
            except Exception:
                pass
        
        if new_unread_count is not None:
            if new_unread_count < unread_count:
                print(f"[PRIORITY_COMMS] Contador bajó: {unread_count} -> {new_unread_count}")
                unread_count = new_unread_count
            else:
                print(f"[PRIORITY_COMMS] Contador no cambió, asumiendo que bajó en 1")
                unread_count = max(0, unread_count - 1)
        else:
            print(f"[PRIORITY_COMMS] No se pudo leer contador, asumiendo que bajó en 1")
            unread_count = max(0, unread_count - 1)
        
        # Screenshot después de la iteración
        if evidence_dir is not None:
            try:
                screenshot_path = evidence_dir / f"priority_comms_after_iter_{iteration}.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                pass
    
    # 5) Cuando unread_count == 0, cerrar el modal
    if unread_count > 0:
        # Guardar evidence del estado final
        if evidence_dir is not None:
            try:
                screenshot_path = evidence_dir / "priority_comms_modal_failed.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                
                html_path = evidence_dir / "priority_comms_modal_failed.html"
                html_content = page.content()
                html_path.write_text(html_content, encoding='utf-8')
                
                # Regenerar clickables dump en caso de fallo
                dump_clickables(page, "page_failed", evidence_dir)
                if modal_frame:
                    dump_clickables(modal_frame, f"frame_failed_{modal_frame.url.split('/')[-1]}", evidence_dir)
            except Exception as e:
                print(f"[PRIORITY_COMMS] Error al guardar evidence de fallo: {e}")
        
        raise PriorityCommsModalNotDismissed(
            f"No se pudieron marcar todos los comunicados como leídos después de {iteration} iteraciones. "
            f"Quedan {unread_count} comunicados no leídos. Revisar clickables_*.json en evidence."
        )
    
    print(f"[PRIORITY_COMMS] Todos los comunicados marcados como leídos, cerrando modal...")
    
    # Buscar botón "Cerrar" o icono de cierre
    close_button = None
    
    # Intentar cerrar por JS si es DHTMLX
    try:
        dhx_wins = page.evaluate("""
            () => {
                if (window.dhxWins) return 'dhxWins';
                if (window.dhtmlXWindows) return 'dhtmlXWindows';
                return null;
            }
        """)
        if dhx_wins:
            print(f"[PRIORITY_COMMS] DHTMLX detectado: {dhx_wins}")
            closed = page.evaluate(f"""
                () => {{
                    try {{
                        var wins = window.{dhx_wins};
                        if (wins) {{
                            var allWins = wins.getWindows();
                            for (var i = 0; i < allWins.length; i++) {{
                                var win = allWins[i];
                                var title = win.getTitle ? win.getTitle() : '';
                                if (title && title.toLowerCase().indexOf('comunicado') >= 0) {{
                                    win.close();
                                    return true;
                                }}
                            }}
                        }}
                    }} catch(e) {{
                        return false;
                    }}
                    return false;
                }}
            """)
            if closed:
                print(f"[PRIORITY_COMMS] Modal cerrado por JS DHTMLX")
                time.sleep(1.0)
                if _is_modal_closed(page, title_texts):
                    return True
    except Exception as e:
        print(f"[PRIORITY_COMMS] Error al cerrar por JS: {e}")
    
    # Buscar botón de cerrar específico (dhtmlx_button_close_default)
    try:
        close_button = page.locator('.dhtmlx_window_active .dhtmlx_button_close_default').first
        if close_button.count() > 0:
            try:
                if close_button.is_visible(timeout=1000):
                    close_button.click(timeout=5000)
                    print(f"[PRIORITY_COMMS] Click en botón 'Cerrar' DHTMLX")
                    time.sleep(1.5)
                else:
                    close_button = None
            except Exception:
                close_button = None
    except Exception:
        close_button = None
    
    # Fallback: pulsar Escape o click en backdrop
    if not _is_modal_closed(page, title_texts):
        try:
            page.keyboard.press("Escape")
            time.sleep(1.0)
            print(f"[PRIORITY_COMMS] Pulsado Escape")
        except Exception:
            pass
        
        if not _is_modal_closed(page, title_texts):
            try:
                backdrop = page.locator('.dhx_modal_cover_dv, .dhx_modal_cover_ifr')
                if backdrop.count() > 0:
                    backdrop.first.click(timeout=3000)
                    time.sleep(0.5)
                    print(f"[PRIORITY_COMMS] Click en backdrop")
            except Exception:
                pass
    
    # 6) Confirmar que el modal desapareció
    if not _is_modal_closed(page, title_texts):
        if evidence_dir is not None:
            try:
                screenshot_path = evidence_dir / "priority_comms_modal_not_closed.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                
                html_path = evidence_dir / "priority_comms_modal_not_closed.html"
                html_content = page.content()
                html_path.write_text(html_content, encoding='utf-8')
            except Exception as e:
                print(f"[PRIORITY_COMMS] Error al guardar evidence final: {e}")
        
        raise PriorityCommsModalNotDismissed(
            "El modal de comunicados prioritarios no se pudo cerrar después de todos los intentos. "
            "Revisar evidence en el directorio de runs."
        )
    
    # Screenshot final (modal cerrado)
    if evidence_dir is not None:
        try:
            screenshot_path = evidence_dir / "priority_comms_modal_closed.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"[PRIORITY_COMMS] Modal cerrado exitosamente. Screenshot final: {screenshot_path}")
        except Exception as e:
            print(f"[PRIORITY_COMMS] Error al guardar screenshot final: {e}")
    else:
        print(f"[DHX_BLOCKER] evidence_dir None, skip screenshot")
        print(f"[PRIORITY_COMMS] Error al guardar screenshot final: {e}")
    
    return True


def _is_modal_closed(page: Page, title_texts: list[str]) -> bool:
    """Verifica si el modal está cerrado (no visible)."""
    try:
        # Verificar si la ventana DHTMLX activa aún existe
        dhtmlx_window = page.locator('.dhtmlx_window_active')
        if dhtmlx_window.count() > 0:
            try:
                iframe_in_window = page.locator('.dhtmlx_window_active iframe[src*="ComunicadosPrioritarios"]')
                if iframe_in_window.count() > 0:
                    if iframe_in_window.first.is_visible(timeout=500):
                        return False
            except Exception:
                pass
        
        # Buscar textos del modal en la página principal
        for title_text in title_texts:
            locator = page.locator(f'text="{title_text}"')
            if locator.count() > 0:
                try:
                    if locator.first.is_visible(timeout=500):
                        return False
                except Exception:
                    pass
        
        # Buscar en frames también
        for frame in page.frames:
            if "ComunicadosPrioritarios" in frame.url:
                return False
        
        return True
    except Exception:
        return True


def _is_dhx_window_closed(page: Page, title_pattern: str) -> bool:
    """Verifica si una ventana DHTMLX con título que coincide con el patrón está cerrada."""
    try:
        # Buscar ventanas DHTMLX activas
        dhtmlx_windows = page.locator('.dhtmlx_window_active')
        if dhtmlx_windows.count() == 0:
            return True
        
        # Verificar si alguna ventana tiene el título que coincide
        for i in range(dhtmlx_windows.count()):
            try:
                window = dhtmlx_windows.nth(i)
                # Buscar el título dentro de la ventana
                title_locator = window.locator('.dhtmlx_window_title, .dhx_wins_cont_inner_title')
                if title_locator.count() > 0:
                    title_text = title_locator.first.text_content() or ""
                    if re.search(title_pattern, title_text, re.IGNORECASE):
                        # Verificar si está visible
                        if window.is_visible(timeout=500):
                            return False
            except Exception:
                continue
        
        # También buscar por texto en toda la página
        title_locator = page.locator(f'text=/{title_pattern}/i')
        if title_locator.count() > 0:
            try:
                if title_locator.first.is_visible(timeout=500):
                    return False
            except Exception:
                pass
        
        return True
    except Exception:
        return True


def dismiss_news_notices_if_present(
    page: Page,
    evidence_dir: Path,
    timeout_seconds: int = 10,
) -> bool:
    """
    Detecta y cierra la ventana "Avisos, comunicados y noticias sin leer" si está presente.
    
    IMPORTANTE: Cierra SIEMPRE, incluso si el contador es 0 o no existe.
    
    Args:
        page: Página de Playwright
        evidence_dir: Directorio donde guardar screenshots de evidence
        timeout_seconds: Timeout máximo para cerrar la ventana
    
    Returns:
        True si la ventana estaba presente y se cerró, False si no estaba presente
    
    Raises:
        DhxBlockerNotDismissed: Si la ventana está presente pero no se puede cerrar
    """
    start_time = time.time()
    
    # Patrón para detectar el título
    title_pattern = r"Avisos,\s*comunicados\s+y\s+noticias\s+sin\s+leer"
    
    # Detectar si la ventana está presente
    window_detected = False
    try:
        # Buscar ventanas DHTMLX activas
        dhtmlx_windows = page.locator('.dhtmlx_window_active')
        for i in range(dhtmlx_windows.count()):
            try:
                window = dhtmlx_windows.nth(i)
                title_locator = window.locator('.dhtmlx_window_title, .dhx_wins_cont_inner_title, .dhtmlx_title')
                if title_locator.count() > 0:
                    title_text = title_locator.first.text_content() or ""
                    if re.search(title_pattern, title_text, re.IGNORECASE):
                        window_detected = True
                        break
            except Exception:
                continue
        
        # Si no se encontró en ventanas, buscar por texto en toda la página
        if not window_detected:
            title_locator = page.locator(f'text=/{title_pattern}/i')
            if title_locator.count() > 0:
                try:
                    if title_locator.first.is_visible(timeout=1000):
                        window_detected = True
                except Exception:
                    pass
    except Exception as e:
        print(f"[DHX_BLOCKER] Error al detectar ventana de noticias: {e}")
    
    if not window_detected:
        return False
    
    print(f"[DHX_BLOCKER] Ventana 'Avisos, comunicados y noticias sin leer' detectada, cerrando...")
    
    # Screenshot antes de cerrar
    if evidence_dir is not None:
        try:
            screenshot_path = evidence_dir / "dhx_news_notices_before.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"[DHX_BLOCKER] Screenshot antes: {screenshot_path}")
        except Exception as e:
            print(f"[DHX_BLOCKER] Error al guardar screenshot antes: {e}")
    else:
        print(f"[DHX_BLOCKER] evidence_dir None, skip screenshot")
    
    # CAMBIO 1: Intentar activar "No volver a mostrar esta ventana" (best-effort)
    no_show_activated = False
    try:
        # Buscar el texto "No volver a mostrar esta ventana" dentro de la ventana DHTMLX
        dhtmlx_windows = page.locator('.dhtmlx_window_active')
        for i in range(dhtmlx_windows.count()):
            try:
                window = dhtmlx_windows.nth(i)
                title_locator = window.locator('.dhtmlx_window_title, .dhx_wins_cont_inner_title, .dhtmlx_title')
                if title_locator.count() > 0:
                    title_text = title_locator.first.text_content() or ""
                    if re.search(title_pattern, title_text, re.IGNORECASE):
                        # Buscar "No volver a mostrar esta ventana" dentro de esta ventana
                        no_show_locator = window.locator('text=/no volver a mostrar esta ventana/i')
                        if no_show_locator.count() > 0:
                            try:
                                # Intentar encontrar un checkbox cercano
                                checkbox = window.locator('input[type="checkbox"]').first
                                if checkbox.count() > 0:
                                    if not checkbox.is_checked():
                                        checkbox.check(timeout=2000)
                                        no_show_activated = True
                                        print(f"[DHX_BLOCKER] Checkbox 'No volver a mostrar' activado")
                                else:
                                    # Si no hay checkbox, intentar click en el texto/link
                                    no_show_locator.first.click(timeout=2000)
                                    no_show_activated = True
                                    print(f"[DHX_BLOCKER] Link/texto 'No volver a mostrar' clickeado")
                            except Exception as e:
                                print(f"[DHX_BLOCKER] No se pudo activar 'No volver a mostrar': {e}")
                                # Intentar buscar ancestor clickable
                                try:
                                    clickable_ancestor = no_show_locator.first.locator('xpath=ancestor-or-self::*[self::a or self::button or @role="button" or @onclick][1]')
                                    if clickable_ancestor.count() > 0:
                                        clickable_ancestor.first.click(timeout=2000)
                                        no_show_activated = True
                                        print(f"[DHX_BLOCKER] Ancestor clickable de 'No volver a mostrar' clickeado")
                                except Exception:
                                    pass
                        break
            except Exception:
                continue
        
        # Si no se encontró en ventanas, buscar en toda la página
        if not no_show_activated:
            try:
                no_show_locator = page.locator('text=/no volver a mostrar esta ventana/i')
                if no_show_locator.count() > 0:
                    # Buscar checkbox cercano
                    checkbox = page.locator('input[type="checkbox"]').first
                    if checkbox.count() > 0:
                        if not checkbox.is_checked():
                            checkbox.check(timeout=2000)
                            no_show_activated = True
                            print(f"[DHX_BLOCKER] Checkbox 'No volver a mostrar' activado (página)")
                    else:
                        no_show_locator.first.click(timeout=2000)
                        no_show_activated = True
                        print(f"[DHX_BLOCKER] Link/texto 'No volver a mostrar' clickeado (página)")
            except Exception as e:
                print(f"[DHX_BLOCKER] No se pudo activar 'No volver a mostrar' (página): {e}")
        
        if no_show_activated:
            # Screenshot después de activar
            if evidence_dir is not None:
                try:
                    screenshot_path = evidence_dir / "news_notices_no_show_clicked.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"[DHX_BLOCKER] Screenshot 'No volver a mostrar' activado: {screenshot_path}")
                    time.sleep(0.5)  # Dar tiempo para que se procese
                except Exception as e:
                    print(f"[DHX_BLOCKER] Error al guardar screenshot 'No volver a mostrar': {e}")
            else:
                time.sleep(0.5)  # Dar tiempo para que se procese
    except Exception as e:
        print(f"[DHX_BLOCKER] Error inesperado al buscar 'No volver a mostrar': {e}")
        # No lanzar excepción, es best-effort
    
    # Estrategia de cierre: buscar botón X DHTMLX
    closed = False
    
    # a) Localizar botón X típico DHTMLX
    close_selectors = [
        '.dhtmlx_window_active .dhtmlx_button_close_default',
        '.dhtmlx_window_active .dhtmlx_button_close',
        '.dhtmlx_window_active .dhx_button_close',
        '.dhtmlx_window_active [class*="close"]',
        '.dhtmlx_window_active [title*="Cerrar"], .dhtmlx_window_active [title*="cerrar"]',
        '.dhtmlx_window_active [aria-label*="Cerrar"], .dhtmlx_window_active [aria-label*="cerrar"]',
    ]
    
    for selector in close_selectors:
        try:
            close_button = page.locator(selector)
            if close_button.count() > 0:
                try:
                    if close_button.first.is_visible(timeout=1000):
                        close_button.first.click(timeout=3000)
                        print(f"[DHX_BLOCKER] Click en botón X (selector: {selector})")
                        time.sleep(1.0)
                        if _is_dhx_window_closed(page, title_pattern):
                            closed = True
                            break
                except Exception:
                    # b) Si falla, intentar click force
                    try:
                        close_button.first.click(force=True, timeout=3000)
                        print(f"[DHX_BLOCKER] Click force en botón X (selector: {selector})")
                        time.sleep(1.0)
                        if _is_dhx_window_closed(page, title_pattern):
                            closed = True
                            break
                    except Exception:
                        # c) Si falla, click por coordenadas
                        try:
                            bbox = close_button.first.bounding_box()
                            if bbox:
                                center_x = bbox["x"] + bbox["width"] / 2
                                center_y = bbox["y"] + bbox["height"] / 2
                                page.mouse.click(center_x, center_y)
                                print(f"[DHX_BLOCKER] Click por coordenadas en botón X")
                                time.sleep(1.0)
                                if _is_dhx_window_closed(page, title_pattern):
                                    closed = True
                                    break
                        except Exception:
                            pass
        except Exception:
            continue
    
    # Si no se cerró, intentar cierre por JavaScript DHTMLX
    if not closed:
        try:
            dhx_wins = page.evaluate("""
                () => {
                    if (window.dhxWins) return 'dhxWins';
                    if (window.dhtmlXWindows) return 'dhtmlXWindows';
                    return null;
                }
            """)
            if dhx_wins:
                closed_js = page.evaluate(f"""
                    () => {{
                        try {{
                            var wins = window.{dhx_wins};
                            if (wins) {{
                                var allWins = wins.getWindows ? wins.getWindows() : [];
                                for (var i = 0; i < allWins.length; i++) {{
                                    var win = allWins[i];
                                    var title = win.getTitle ? win.getTitle() : '';
                                    if (title && /Avisos,\\s*comunicados\\s+y\\s+noticias\\s+sin\\s+leer/i.test(title)) {{
                                        win.close();
                                        return true;
                                    }}
                                }}
                            }}
                        }} catch(e) {{
                            return false;
                        }}
                        return false;
                    }}
                """)
                if closed_js:
                    print(f"[DHX_BLOCKER] Ventana cerrada por JS DHTMLX")
                    time.sleep(1.0)
                    closed = _is_dhx_window_closed(page, title_pattern)
        except Exception as e:
            print(f"[DHX_BLOCKER] Error al cerrar por JS: {e}")
    
    # Fallback: Escape
    if not closed:
        try:
            page.keyboard.press("Escape")
            time.sleep(1.0)
            print(f"[DHX_BLOCKER] Pulsado Escape")
            closed = _is_dhx_window_closed(page, title_pattern)
        except Exception:
            pass
    
    # Verificar que se cerró
    if not closed:
        # Guardar evidence de fallo
        if evidence_dir is not None:
            try:
                screenshot_path = evidence_dir / "dhx_news_notices_failed.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                
                html_path = evidence_dir / "dhx_news_notices_failed.html"
                html_content = page.content()
                html_path.write_text(html_content, encoding='utf-8')
            except Exception as e:
                print(f"[DHX_BLOCKER] Error al guardar evidence de fallo: {e}")
        
        raise DhxBlockerNotDismissed(
            f"No se pudo cerrar la ventana 'Avisos, comunicados y noticias sin leer' después de {timeout_seconds}s. "
            "Revisar evidence en el directorio de runs."
        )
    
    # Screenshot después de cerrar
    if evidence_dir is not None:
        try:
            screenshot_path = evidence_dir / "dhx_news_notices_closed.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"[DHX_BLOCKER] Ventana cerrada exitosamente. Screenshot: {screenshot_path}")
        except Exception as e:
            print(f"[DHX_BLOCKER] Error al guardar screenshot después: {e}")
    else:
        print(f"[DHX_BLOCKER] evidence_dir None, skip screenshot")
    
    return True


def dismiss_generic_dhx_overlays_if_present(
    page: Page,
    evidence_dir: Path,
    timeout_seconds: int = 10,
) -> bool:
    """
    Detecta y cierra cualquier overlay DHTMLX con títulos que contengan palabras clave específicas.
    
    Este es un "catch-all" para evitar que overlays intermitentes rompan el flujo.
    
    Args:
        page: Página de Playwright
        evidence_dir: Directorio donde guardar screenshots de evidence
        timeout_seconds: Timeout máximo para cerrar cada overlay
    
    Returns:
        True si se cerró al menos un overlay, False si no había ninguno
    
    Raises:
        DhxBlockerNotDismissed: Si un overlay está presente pero no se puede cerrar
    """
    # Palabras clave para detectar overlays bloqueantes
    keywords = ["Avisos", "Comunicados", "Noticias", "Seguridad"]
    
    closed_any = False
    
    for keyword in keywords:
        try:
            # Buscar ventanas DHTMLX activas con el keyword en el título
            dhtmlx_windows = page.locator('.dhtmlx_window_active')
            for i in range(dhtmlx_windows.count()):
                try:
                    window = dhtmlx_windows.nth(i)
                    title_locator = window.locator('.dhtmlx_window_title, .dhx_wins_cont_inner_title, .dhtmlx_title')
                    if title_locator.count() > 0:
                        title_text = title_locator.first.text_content() or ""
                        if keyword.lower() in title_text.lower():
                            print(f"[DHX_BLOCKER] Overlay genérico detectado: '{title_text}' (keyword: {keyword})")
                            
                            # Intentar cerrar con la misma estrategia que dismiss_news_notices_if_present
                            closed = False
                            
                            # Buscar botón X
                            close_selectors = [
                                '.dhtmlx_window_active .dhtmlx_button_close_default',
                                '.dhtmlx_window_active .dhtmlx_button_close',
                                '.dhtmlx_window_active .dhx_button_close',
                            ]
                            
                            for selector in close_selectors:
                                try:
                                    close_button = window.locator(selector)
                                    if close_button.count() > 0:
                                        try:
                                            close_button.first.click(timeout=2000)
                                            time.sleep(0.5)
                                            closed = True
                                            closed_any = True
                                            print(f"[DHX_BLOCKER] Overlay '{title_text}' cerrado")
                                            break
                                        except Exception:
                                            try:
                                                close_button.first.click(force=True, timeout=2000)
                                                time.sleep(0.5)
                                                closed = True
                                                closed_any = True
                                                print(f"[DHX_BLOCKER] Overlay '{title_text}' cerrado (force)")
                                                break
                                            except Exception:
                                                pass
                                except Exception:
                                    continue
                            
                            # Si no se cerró, intentar JS
                            if not closed:
                                try:
                                    dhx_wins = page.evaluate("""
                                        () => {
                                            if (window.dhxWins) return 'dhxWins';
                                            if (window.dhtmlXWindows) return 'dhtmlXWindows';
                                            return null;
                                        }
                                    """)
                                    if dhx_wins:
                                        closed_js = page.evaluate(f"""
                                            () => {{
                                                try {{
                                                    var wins = window.{dhx_wins};
                                                    if (wins) {{
                                                        var allWins = wins.getWindows ? wins.getWindows() : [];
                                                        for (var i = 0; i < allWins.length; i++) {{
                                                            var win = allWins[i];
                                                            var title = win.getTitle ? win.getTitle() : '';
                                                            if (title && title.toLowerCase().indexOf('{keyword.lower()}') >= 0) {{
                                                                win.close();
                                                                return true;
                                                            }}
                                                        }}
                                                    }}
                                                }} catch(e) {{
                                                    return false;
                                                }}
                                                return false;
                                            }}
                                        """)
                                        if closed_js:
                                            time.sleep(0.5)
                                            closed = True
                                            closed_any = True
                                            print(f"[DHX_BLOCKER] Overlay '{title_text}' cerrado por JS")
                                except Exception:
                                    pass
                            
                            # Si aún no se cerró y es crítico, lanzar excepción
                            if not closed:
                                print(f"[DHX_BLOCKER] Advertencia: No se pudo cerrar overlay '{title_text}'")
                except Exception:
                    continue
        except Exception as e:
            print(f"[DHX_BLOCKER] Error al procesar keyword '{keyword}': {e}")
            continue
    
    return closed_any


def dismiss_all_dhx_blockers(
    page: Page,
    evidence_dir: Optional[Path],
    timeout_seconds: int = 30,
) -> None:
    """
    Pipeline que cierra todos los overlays DHTMLX bloqueantes en orden.
    
    Orden de ejecución:
    1. dismiss_priority_comms_if_present (comunicados prioritarios con no-leídos)
    2. dismiss_news_notices_if_present (avisos/comunicados/noticias sin leer)
    3. dismiss_generic_dhx_overlays_if_present (catch-all para otros overlays)
    
    Args:
        page: Página de Playwright
        evidence_dir: Directorio donde guardar screenshots de evidence
        timeout_seconds: Timeout máximo total
    
    Raises:
        PriorityCommsModalNotDismissed: Si no se puede cerrar el modal de comunicados prioritarios
        DhxBlockerNotDismissed: Si no se puede cerrar otro overlay bloqueante
    """
    print(f"[DHX_BLOCKER] Iniciando pipeline de cierre de overlays DHTMLX...")
    
    # 1) Comunicados prioritarios (requiere marcar como leídos)
    try:
        dismiss_priority_comms_if_present(page, evidence_dir, timeout_seconds=timeout_seconds)
    except PriorityCommsModalNotDismissed:
        # Re-lanzar esta excepción específica
        raise
    except Exception as e:
        print(f"[DHX_BLOCKER] Error inesperado en dismiss_priority_comms_if_present: {e}")
        # Continuar con el siguiente paso
    
    # 2) Avisos/comunicados/noticias sin leer (cerrar directamente)
    try:
        dismiss_news_notices_if_present(page, evidence_dir, timeout_seconds=10)
    except DhxBlockerNotDismissed:
        # Re-lanzar esta excepción
        raise
    except Exception as e:
        print(f"[DHX_BLOCKER] Error inesperado en dismiss_news_notices_if_present: {e}")
        # Continuar con el siguiente paso
    
    # 3) Overlays genéricos (catch-all)
    try:
        dismiss_generic_dhx_overlays_if_present(page, evidence_dir, timeout_seconds=10)
    except Exception as e:
        print(f"[DHX_BLOCKER] Error inesperado en dismiss_generic_dhx_overlays_if_present: {e}")
        # No lanzar excepción aquí, es un catch-all
    
    print(f"[DHX_BLOCKER] Pipeline de cierre de overlays DHTMLX completado")
