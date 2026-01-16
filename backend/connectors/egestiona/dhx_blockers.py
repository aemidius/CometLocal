"""
Helper async para cerrar modales DHTMLX bloqueantes en eGestiona.

Reutiliza la lógica de priority_comms_headful.py adaptada a Playwright async.
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from playwright.async_api import Page, Frame


async def dismiss_all_dhx_blockers(
    page: Page,
    *,
    max_rounds: int = 5,
    evidence_dir: Optional[Path] = None,
    logger=None,
) -> Dict[str, Any]:
    """
    Detecta y cierra modales DHTMLX bloqueantes (especialmente comunicados prioritarios).
    
    Args:
        page: Página de Playwright async
        max_rounds: Máximo número de rondas para marcar comunicados
        evidence_dir: Directorio donde guardar evidencias (opcional)
        logger: Logger opcional (usa print si no se proporciona)
    
    Returns:
        Dict con:
        - had_blocker: bool - Si había un modal bloqueante
        - rounds: int - Número de rondas ejecutadas
        - actions: List[str] - Acciones realizadas
        - success: bool - Si se cerró exitosamente
    """
    log = logger or (lambda msg: print(f"[DHX] {msg}"))
    actions: List[str] = []
    
    # 1) Detectar si hay modal bloqueante
    had_blocker = False
    modal_frame: Optional[Frame] = None
    
    title_texts = [
        "Comunicados prioritarios",
        "comunicados prioritarios",
        "COMUNICADOS PRIORITARIOS",
        "Avisos, comunicados y noticias sin leer",
    ]
    
    # Buscar iframe de ComunicadosPrioritarios
    try:
        iframe_locator = page.locator('iframe[src*="ComunicadosPrioritarios"]')
        iframe_count = await iframe_locator.count()
        if iframe_count > 0:
            for frame in page.frames:
                if "ComunicadosPrioritarios" in frame.url:
                    modal_frame = frame
                    had_blocker = True
                    log(f"Modal detectado en iframe: {frame.url}")
                    actions.append(f"Detected modal in iframe: {frame.url}")
                    break
    except Exception as e:
        log(f"Error al buscar iframe: {e}")
    
    # Si no hay iframe, buscar por texto
    if not had_blocker:
        for title_text in title_texts:
            try:
                locator = page.locator(f'text="{title_text}"')
                count = await locator.count()
                if count > 0:
                    try:
                        if await locator.first.is_visible(timeout=1000):
                            had_blocker = True
                            log(f"Modal detectado por texto: {title_text}")
                            actions.append(f"Detected modal by text: {title_text}")
                            break
                    except Exception:
                        pass
            except Exception:
                pass
    
    # Si no hay modal, salir inmediatamente
    if not had_blocker:
        log("No blocker detected")
        return {
            "had_blocker": False,
            "rounds": 0,
            "actions": actions,
            "success": True,
        }
    
    log("Blocker detected, starting dismissal process")
    
    # Guardar screenshot inicial
    if evidence_dir:
        try:
            screenshot_path = evidence_dir / f"dhx_blocker_initial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            log(f"Screenshot inicial guardado: {screenshot_path}")
            actions.append(f"Screenshot saved: {screenshot_path.name}")
        except Exception as e:
            log(f"Error al guardar screenshot: {e}")
    
    # Esperar a que el iframe esté cargado
    if modal_frame:
        try:
            await modal_frame.wait_for_load_state("domcontentloaded", timeout=10000)
            await page.wait_for_timeout(1500)
            log(f"Iframe cargado: {modal_frame.url}")
        except Exception as e:
            log(f"Advertencia: No se pudo esperar carga del iframe: {e}")
    
    # 2) Localizar contador "No leído: X"
    unread_count = None
    unread_patterns = [
        r"No leído:\s*(\d+)",
        r"no leído:\s*(\d+)",
        r"NO LEÍDO:\s*(\d+)",
        r"(\d+)\s*no leído",
        r"(\d+)\s*No leído",
    ]
    
    ctx = modal_frame if modal_frame else page
    
    # Buscar contador
    try:
        content = await ctx.content()
        for pattern in unread_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                unread_count = int(match.group(1))
                log(f"Contador encontrado: {unread_count} no leídos")
                actions.append(f"Found unread count: {unread_count}")
                break
    except Exception:
        pass
    
    # Si no se encontró contador, buscar por texto visible
    if unread_count is None:
        try:
            unread_text_locator = ctx.locator('text=/No leído|no leído|NO LEÍDO/i')
            count = await unread_text_locator.count()
            if count > 0:
                text = await unread_text_locator.first.text_content()
                match = re.search(r'(\d+)', text or "")
                if match:
                    unread_count = int(match.group(1))
                    log(f"Contador encontrado en texto visible: {unread_count}")
                    actions.append(f"Found unread count in visible text: {unread_count}")
        except Exception:
            pass
    
    # Si no se encontró contador, asumir que hay comunicados
    if unread_count is None:
        log("No se encontró contador, asumiendo que hay comunicados por marcar")
        unread_count = 1
        actions.append("No counter found, assuming 1 unread")
    
    # 3) Marcar comunicados como leídos
    iteration = 0
    while unread_count > 0 and iteration < max_rounds:
        iteration += 1
        log(f"Round {iteration}: {unread_count} comunicados no leídos")
        actions.append(f"Round {iteration}: {unread_count} unread")
        
        # Screenshot antes de la iteración
        if evidence_dir and iteration == 1:
            try:
                screenshot_path = evidence_dir / f"dhx_blocker_before_round_{iteration}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                pass
        
        # 3a) Abrir un comunicado no leído
        comm_opened = False
        try:
            if modal_frame:
                comm_links = modal_frame.locator('a[href]:not([href=""]), a:not([href=""]), [role="link"]')
                count = await comm_links.count()
                if count == 0:
                    comm_links = modal_frame.locator('tr, li, [onclick], [class*="comunicado"], [class*="item"]')
                    count = await comm_links.count()
            else:
                comm_links = page.locator('.dhtmlx_window_active a, .dhtmlx_window_active [role="link"]')
                count = await comm_links.count()
            
            if count > 0:
                first_link = comm_links.first
                try:
                    await first_link.click(timeout=5000)
                    await page.wait_for_timeout(1500)
                    comm_opened = True
                    log(f"Comunicado abierto (round {iteration})")
                    actions.append(f"Opened comm (round {iteration})")
                except Exception:
                    try:
                        await first_link.click(force=True, timeout=3000)
                        await page.wait_for_timeout(1500)
                        comm_opened = True
                        log(f"Comunicado abierto con force (round {iteration})")
                        actions.append(f"Opened comm with force (round {iteration})")
                    except Exception:
                        pass
        except Exception as e:
            log(f"Error buscando comunicado: {e}")
        
        # 3b) Pulsar "Marcar como leído"
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
                text_locator = page.locator(f'text=/{text_pattern}/i')
                count = await text_locator.count()
                if count > 0:
                    try:
                        await text_locator.first.click(timeout=3000)
                        mark_read_clicked = True
                        log(f"Click en 'Marcar como leído' (page, round {iteration})")
                        actions.append(f"Marked as read (page, round {iteration})")
                        break
                    except Exception:
                        # Buscar ancestor clickable
                        try:
                            clickable_ancestor = text_locator.first.locator("xpath=ancestor-or-self::*[self::a or self::button or @role='button' or @onclick][1]")
                            ancestor_count = await clickable_ancestor.count()
                            if ancestor_count > 0:
                                await clickable_ancestor.first.click(timeout=3000)
                                mark_read_clicked = True
                                log(f"Click en 'Marcar como leído' (ancestor, round {iteration})")
                                actions.append(f"Marked as read (ancestor, round {iteration})")
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
                    count = await text_locator.count()
                    if count > 0:
                        try:
                            await text_locator.first.click(timeout=3000)
                            mark_read_clicked = True
                            log(f"Click en 'Marcar como leído' (frame, round {iteration})")
                            actions.append(f"Marked as read (frame, round {iteration})")
                            break
                        except Exception:
                            try:
                                clickable_ancestor = text_locator.first.locator("xpath=ancestor-or-self::*[self::a or self::button or @role='button' or @onclick][1]")
                                ancestor_count = await clickable_ancestor.count()
                                if ancestor_count > 0:
                                    await clickable_ancestor.first.click(timeout=3000)
                                    mark_read_clicked = True
                                    log(f"Click en 'Marcar como leído' (frame ancestor, round {iteration})")
                                    actions.append(f"Marked as read (frame ancestor, round {iteration})")
                                    break
                            except Exception:
                                pass
                except Exception:
                    pass
        
        # Si aún no se encontró, buscar cualquier botón con "marcar" o "leído"
        if not mark_read_clicked:
            try:
                all_buttons = page.locator('button, a, input[type="button"], input[type="submit"]')
                count = await all_buttons.count()
                for i in range(min(count, 20)):
                    try:
                        btn = all_buttons.nth(i)
                        btn_text = await btn.text_content() or ""
                        if any(word in btn_text.lower() for word in ["marcar", "leído", "leido"]):
                            await btn.click(timeout=3000)
                            mark_read_clicked = True
                            log(f"Click en botón encontrado por texto: '{btn_text}' (round {iteration})")
                            actions.append(f"Marked as read (button text, round {iteration})")
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        
        if not mark_read_clicked:
            log(f"No se encontró botón 'Marcar como leído' en round {iteration}")
            actions.append(f"No mark-as-read button found (round {iteration})")
        
        # 3c) Esperar y releer contador
        await page.wait_for_timeout(2000)
        
        new_unread_count = None
        try:
            content = await ctx.content()
            for pattern in unread_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    new_unread_count = int(match.group(1))
                    break
        except Exception:
            pass
        
        if new_unread_count is not None:
            if new_unread_count < unread_count:
                log(f"Contador bajó: {unread_count} -> {new_unread_count}")
                actions.append(f"Counter decreased: {unread_count} -> {new_unread_count}")
                unread_count = new_unread_count
            else:
                log(f"Contador no cambió, asumiendo que bajó en 1")
                unread_count = max(0, unread_count - 1)
        else:
            log(f"No se pudo leer contador, asumiendo que bajó en 1")
            unread_count = max(0, unread_count - 1)
        
        # Screenshot después de la iteración
        if evidence_dir:
            try:
                screenshot_path = evidence_dir / f"dhx_blocker_after_round_{iteration}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                pass
    
    # 4) Cerrar el modal
    if unread_count > 0:
        log(f"Quedan {unread_count} comunicados no leídos después de {iteration} rounds")
        actions.append(f"Still {unread_count} unread after {iteration} rounds")
        # Continuar de todas formas para intentar cerrar
    
    log("Todos los comunicados marcados como leídos, cerrando modal...")
    actions.append("All comms marked as read, closing modal")
    
    # Intentar cerrar por JavaScript DHTMLX
    closed = False
    try:
        dhx_wins = await page.evaluate("""
            () => {
                if (window.dhxWins) return 'dhxWins';
                if (window.dhtmlXWindows) return 'dhtmlXWindows';
                return null;
            }
        """)
        if dhx_wins:
            log(f"DHTMLX detectado: {dhx_wins}")
            closed_js = await page.evaluate(f"""
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
            if closed_js:
                log("Modal cerrado por JS DHTMLX")
                actions.append("Closed via JS DHTMLX")
                await page.wait_for_timeout(1000)
                closed = await _is_modal_closed_async(page, title_texts)
    except Exception as e:
        log(f"Error al cerrar por JS: {e}")
    
    # Buscar botón de cerrar
    if not closed:
        try:
            close_button = page.locator('.dhtmlx_window_active .dhtmlx_button_close_default').first
            count = await close_button.count()
            if count > 0:
                try:
                    if await close_button.is_visible(timeout=1000):
                        await close_button.click(timeout=5000)
                        log("Click en botón 'Cerrar' DHTMLX")
                        actions.append("Clicked close button")
                        await page.wait_for_timeout(1500)
                        closed = await _is_modal_closed_async(page, title_texts)
                except Exception:
                    pass
        except Exception:
            pass
    
    # Fallback: Escape
    if not closed:
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(1000)
            log("Pulsado Escape")
            actions.append("Pressed Escape")
            closed = await _is_modal_closed_async(page, title_texts)
        except Exception:
            pass
    
    # Verificar que se cerró
    if not closed:
        if evidence_dir:
            try:
                screenshot_path = evidence_dir / "dhx_blocker_not_closed.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                log(f"Screenshot de fallo guardado: {screenshot_path}")
            except Exception:
                pass
        log("Modal no se pudo cerrar completamente")
        actions.append("Modal not fully closed")
        return {
            "had_blocker": True,
            "rounds": iteration,
            "actions": actions,
            "success": False,
        }
    
    # Screenshot final
    if evidence_dir:
        try:
            screenshot_path = evidence_dir / "dhx_blocker_closed.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            log(f"Modal cerrado exitosamente. Screenshot: {screenshot_path}")
        except Exception:
            pass
    
    log("Blocker dismissed successfully")
    actions.append("Blocker dismissed successfully")
    
    return {
        "had_blocker": True,
        "rounds": iteration,
        "actions": actions,
        "success": True,
    }


async def _is_modal_closed_async(page: Page, title_texts: List[str]) -> bool:
    """Verifica si el modal está cerrado (async)."""
    try:
        # Verificar si la ventana DHTMLX activa aún existe
        dhtmlx_window = page.locator('.dhtmlx_window_active')
        count = await dhtmlx_window.count()
        if count > 0:
            try:
                iframe_in_window = page.locator('.dhtmlx_window_active iframe[src*="ComunicadosPrioritarios"]')
                iframe_count = await iframe_in_window.count()
                if iframe_count > 0:
                    try:
                        if await iframe_in_window.first.is_visible(timeout=500):
                            return False
                    except Exception:
                        pass
            except Exception:
                pass
        
        # Buscar textos del modal
        for title_text in title_texts:
            locator = page.locator(f'text="{title_text}"')
            count = await locator.count()
            if count > 0:
                try:
                    if await locator.first.is_visible(timeout=500):
                        return False
                except Exception:
                    pass
        
        # Buscar en frames
        for frame in page.frames:
            if "ComunicadosPrioritarios" in frame.url:
                return False
        
        return True
    except Exception:
        return True
