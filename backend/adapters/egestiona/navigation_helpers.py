"""
Helpers para navegación robusta en eGestiona después del login.

Garantiza que el agente llegue correctamente a la pantalla de "Enviar documentación pendiente"
y valida que el grid de pendientes está realmente cargado.
"""

from __future__ import annotations

import time
import re
from pathlib import Path
from typing import Optional, Any
from playwright.sync_api import Page, Frame, TimeoutError as PlaywrightTimeoutError


class PendingEntryPointNotReached(Exception):
    """Excepción cuando no se puede llegar a la pantalla de pendientes después de reintentos."""
    pass


def ensure_pending_upload_dashboard(
    page: Page,
    evidence_dir: Path,
    max_retries: int = 2,
    timeout_seconds: int = 15,
) -> Frame:
    """
    Garantiza que estamos en el lugar correcto para extraer pendientes.
    
    Estrategia en cascada:
    1) Intentar click en el tile/icono del dashboard "Enviar documentación pendiente"
    2) Si falla, ir por menú lateral "Coordinación" -> subitem relacionado
    3) Si sigue fallando, reintentar (máx max_retries)
    
    Args:
        page: Página de Playwright
        evidence_dir: Directorio donde guardar evidence
        max_retries: Máximo número de reintentos
        timeout_seconds: Timeout para cada intento
    
    Returns:
        Frame del grid de pendientes (f3 o buscador.asp?Apartado_ID=3)
    
    Raises:
        PendingEntryPointNotReached: Si no se puede llegar después de reintentos
    """
    for attempt in range(max_retries + 1):
        print(f"[NAVIGATION] Intento {attempt + 1}/{max_retries + 1} de navegación a pendientes...")
        
        try:
            # Esperar frame nm_contenido
            t_deadline = time.time() + 25.0
            frame_dashboard = None
            while time.time() < t_deadline:
                frame_dashboard = page.frame(name="nm_contenido")
                if frame_dashboard and frame_dashboard.url:
                    break
                time.sleep(0.25)
            
            if not frame_dashboard:
                page.screenshot(path=str(evidence_dir / f"nav_error_no_frame_attempt_{attempt + 1}.png"), full_page=True)
                if attempt < max_retries:
                    print(f"[NAVIGATION] Frame nm_contenido no encontrado, reintentando...")
                    time.sleep(2.0)
                    continue
                raise PendingEntryPointNotReached("Frame nm_contenido no encontrado después de reintentos")
            
            # ESTRATEGIA 1: Intentar click en tile del dashboard
            tile_clicked = False
            try:
                # Selector actual conocido
                tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
                tile = frame_dashboard.locator(tile_sel)
                if tile.count() > 0:
                    tile.first.wait_for(state="visible", timeout=10000)
                    tile.first.click(timeout=10000)
                    tile_clicked = True
                    print(f"[NAVIGATION] Tile clickeado (selector: {tile_sel})")
            except Exception as e:
                print(f"[NAVIGATION] Tile no encontrado o no clickeable: {e}")
                # Intentar por texto
                try:
                    tile_by_text = frame_dashboard.get_by_role("link", name=re.compile(r"enviar.*pendiente|documentaci[oó]n.*pendiente|gesti[oó]n documental", re.IGNORECASE))
                    if tile_by_text.count() > 0:
                        tile_by_text.first.wait_for(state="visible", timeout=10000)
                        tile_by_text.first.click(timeout=10000)
                        tile_clicked = True
                        print(f"[NAVIGATION] Tile clickeado (por texto)")
                except Exception as e2:
                    print(f"[NAVIGATION] Tile por texto no encontrado: {e2}")
            
            # Si no se pudo clickear el tile, intentar ESTRATEGIA 2: Menú lateral
            if not tile_clicked:
                try:
                    # Buscar menú "Coordinación"
                    coord_menu = page.get_by_text("Coordinación", exact=True)
                    if coord_menu.count() > 0:
                        coord_menu.first.click(timeout=5000)
                        time.sleep(1.0)
                        # Buscar subitem relacionado
                        subitems = [
                            "Gestión documental",
                            "Documentación",
                            "Pendiente",
                            "Enviar documentación pendiente",
                        ]
                        for subitem_text in subitems:
                            try:
                                subitem = page.get_by_text(subitem_text, exact=False)
                                if subitem.count() > 0:
                                    subitem.first.click(timeout=5000)
                                    print(f"[NAVIGATION] Subitem '{subitem_text}' clickeado")
                                    tile_clicked = True
                                    break
                            except Exception:
                                continue
                except Exception as e:
                    print(f"[NAVIGATION] Error al navegar por menú lateral: {e}")
            
            if not tile_clicked:
                if attempt < max_retries:
                    print(f"[NAVIGATION] No se pudo clickear tile/menú, reintentando...")
                    time.sleep(2.0)
                    continue
                raise PendingEntryPointNotReached("No se pudo navegar al área de pendientes después de reintentos")
            
            # Esperar grid de pendientes
            time.sleep(1.0)  # Dar tiempo para que cargue
            
            def _find_list_frame() -> Optional[Frame]:
                fr = page.frame(name="f3")
                if fr:
                    return fr
                for fr2 in page.frames:
                    u = (fr2.url or "").lower()
                    if ("buscador.asp" in u) and ("apartado_id=3" in u):
                        return fr2
                return None
            
            def _frame_has_grid(fr: Frame) -> bool:
                try:
                    return fr.locator("table.obj.row20px").count() > 0
                except Exception:
                    return False
            
            # Verificar que el grid está cargado
            list_frame = None
            t_deadline = time.time() + timeout_seconds
            while time.time() < t_deadline:
                list_frame = _find_list_frame()
                if list_frame and _frame_has_grid(list_frame):
                    break
                time.sleep(0.25)
            
            # Si no hay grid, intentar click "Buscar"
            if not (list_frame and _frame_has_grid(list_frame)):
                try:
                    btn_buscar = frame_dashboard.get_by_text("Buscar", exact=True)
                    if btn_buscar.count() > 0:
                        btn_buscar.first.click(timeout=10000)
                        time.sleep(1.0)
                        # Reintentar encontrar grid
                        t_deadline = time.time() + timeout_seconds
                        while time.time() < t_deadline:
                            list_frame = _find_list_frame()
                            if list_frame and _frame_has_grid(list_frame):
                                break
                            time.sleep(0.25)
                except Exception:
                    pass
            
            # Validar que estamos en la pantalla correcta
            if list_frame and _frame_has_grid(list_frame):
                print(f"[NAVIGATION] Grid de pendientes encontrado y cargado")
                # Screenshot de éxito
                try:
                    page.screenshot(path=str(evidence_dir / f"nav_success_attempt_{attempt + 1}.png"), full_page=True)
                except Exception:
                    pass
                return list_frame
            else:
                # Validar que al menos estamos en una pantalla relacionada
                # (hay grid container / títulos / breadcrumbs)
                is_valid_page = False
                validation_details = []
                try:
                    # Buscar indicadores en el frame del grid (no en frame_dashboard)
                    if list_frame:
                        # Indicadores en el frame del grid
                        indicators = [
                            ('text documentacion pendiente', list_frame.locator('text=/documentaci[oó]n.*pendiente/i')),
                            ('text gestion documental', list_frame.locator('text=/gesti[oó]n.*documental/i')),
                            ('table.obj', list_frame.locator('table.obj')),
                            ('table.hdr', list_frame.locator('table.hdr')),
                            ('.listado_link', list_frame.locator('.listado_link')),
                        ]
                        for name, indicator in indicators:
                            try:
                                count = indicator.count()
                                if count > 0:
                                    is_valid_page = True
                                    validation_details.append(f"{name}: {count}")
                                    print(f"[NAVIGATION] Indicador encontrado: {name} (count={count})")
                                    break
                            except Exception as e:
                                validation_details.append(f"{name}: error={e}")
                    else:
                        # Si no hay list_frame, buscar en frame_dashboard
                        indicators = [
                            ('text documentacion pendiente', frame_dashboard.locator('text=/documentaci[oó]n.*pendiente/i')),
                            ('text gestion documental', frame_dashboard.locator('text=/gesti[oó]n.*documental/i')),
                            ('table.obj', frame_dashboard.locator('table.obj')),
                            ('.listado_link', frame_dashboard.locator('.listado_link')),
                        ]
                        for name, indicator in indicators:
                            try:
                                count = indicator.count()
                                if count > 0:
                                    is_valid_page = True
                                    validation_details.append(f"{name}: {count}")
                                    print(f"[NAVIGATION] Indicador encontrado en dashboard: {name} (count={count})")
                                    break
                            except Exception as e:
                                validation_details.append(f"{name}: error={e}")
                except Exception as e:
                    validation_details.append(f"validation_error: {e}")
                
                print(f"[NAVIGATION] Validación de pantalla: is_valid={is_valid_page}, details={validation_details}")
                
                if not is_valid_page:
                    page.screenshot(path=str(evidence_dir / f"nav_invalid_page_attempt_{attempt + 1}.png"), full_page=True)
                    # Guardar más información de diagnóstico
                    try:
                        if list_frame:
                            list_frame.locator("body").screenshot(path=str(evidence_dir / f"nav_invalid_frame_attempt_{attempt + 1}.png"))
                    except Exception:
                        pass
                    if attempt < max_retries:
                        print(f"[NAVIGATION] Pantalla no válida, reintentando...")
                        time.sleep(2.0)
                        continue
                    raise PendingEntryPointNotReached(f"No se encontró grid de pendientes y la pantalla no es válida. Details: {validation_details}")
                else:
                    # Estamos en una pantalla relacionada pero sin grid cargado
                    print(f"[NAVIGATION] Pantalla válida pero grid no cargado, esperando más tiempo...")
                    # Esperar más tiempo antes de reintentar
                    time.sleep(3.0)
                    # Reintentar encontrar grid
                    t_deadline = time.time() + timeout_seconds
                    while time.time() < t_deadline:
                        list_frame = _find_list_frame()
                        if list_frame and _frame_has_grid(list_frame):
                            print(f"[NAVIGATION] Grid encontrado después de espera adicional")
                            return list_frame
                        time.sleep(0.5)
                    if attempt < max_retries:
                        print(f"[NAVIGATION] Grid no apareció después de espera, reintentando...")
                        time.sleep(2.0)
                        continue
                    raise PendingEntryPointNotReached("Grid de pendientes no cargado después de reintentos")
        
        except PendingEntryPointNotReached:
            if attempt < max_retries:
                print(f"[NAVIGATION] Error en intento {attempt + 1}, reintentando...")
                time.sleep(2.0)
                continue
            raise
        except Exception as e:
            page.screenshot(path=str(evidence_dir / f"nav_error_attempt_{attempt + 1}.png"), full_page=True)
            if attempt < max_retries:
                print(f"[NAVIGATION] Error inesperado en intento {attempt + 1}: {e}, reintentando...")
                time.sleep(2.0)
                continue
            raise PendingEntryPointNotReached(f"Error inesperado después de reintentos: {e}") from e
    
    raise PendingEntryPointNotReached("No se pudo llegar a la pantalla de pendientes después de todos los reintentos")


def pick_pending_grid_frame(page: Page) -> Optional[Frame]:
    """
    Selecciona determinísticamente el frame correcto del grid de pendientes.
    
    Prioridad:
    1. Frame con name="f3" (más estable)
    2. Frame con URL que contiene "buscador.asp" y "apartado_id=3"
    3. Frame con URL que contiene "subcontratas" o "documento" o "gestion_documental"
    4. Frame que contiene selector header único del grid (table.hdr)
    
    Args:
        page: Página de Playwright
    
    Returns:
        Frame del grid de pendientes o None si no se encuentra
    """
    # Prioridad 1: Frame f3
    frame_f3 = page.frame(name="f3")
    if frame_f3:
        try:
            if frame_f3.locator("table.hdr").count() > 0:
                print(f"[PICK_FRAME] Frame f3 seleccionado (por name)")
                return frame_f3
        except Exception:
            pass
    
    # Prioridad 2: Frame con URL buscador.asp?Apartado_ID=3
    for frame in page.frames:
        u = (frame.url or "").lower()
        if ("buscador.asp" in u) and ("apartado_id=3" in u):
            try:
                if frame.locator("table.hdr").count() > 0:
                    print(f"[PICK_FRAME] Frame seleccionado por URL pattern (buscador.asp?Apartado_ID=3)")
                    return frame
            except Exception:
                pass
    
    # Prioridad 3: Frame con URL que contiene keywords
    keywords = ["subcontratas", "documento", "gestion_documental", "pendiente"]
    for keyword in keywords:
        for frame in page.frames:
            u = (frame.url or "").lower()
            if keyword in u:
                try:
                    if frame.locator("table.hdr").count() > 0 or frame.locator("table.obj.row20px").count() > 0:
                        print(f"[PICK_FRAME] Frame seleccionado por URL keyword: {keyword}")
                        return frame
                except Exception:
                    pass
    
    # Prioridad 4: Frame que contiene selector header único
    for frame in page.frames:
        try:
            if frame.locator("table.hdr").count() > 0:
                # Verificar que también tiene grid
                if frame.locator("table.obj.row20px").count() > 0:
                    print(f"[PICK_FRAME] Frame seleccionado por selector header único")
                    return frame
        except Exception:
            continue
    
    return None


def validate_pending_grid_loaded(
    frame: Frame,
    evidence_dir: Path,
) -> bool:
    """
    Valida que el grid de pendientes está realmente cargado (no spinner, hay filas o encabezados).
    
    Args:
        frame: Frame donde debería estar el grid
        evidence_dir: Directorio donde guardar evidence si falla
    
    Returns:
        True si el grid está cargado, False si no
    """
    try:
        # Verificar que hay un grid
        grid = frame.locator("table.obj.row20px")
        if grid.count() == 0:
            return False
        
        # Verificar que no hay spinner/loading
        try:
            spinner = frame.locator('.loading, .spinner, [class*="loading"], [class*="spinner"]')
            if spinner.count() > 0 and spinner.first.is_visible(timeout=500):
                return False
        except Exception:
            pass
        
        # Verificar que hay al menos encabezados o filas
        try:
            rows = frame.locator("table.obj.row20px tr")
            if rows.count() > 0:
                return True
        except Exception:
            pass
        
        # Verificar encabezados
        try:
            headers = frame.locator("table.obj.row20px th, table.obj.row20px thead tr")
            if headers.count() > 0:
                return True
        except Exception:
            pass
        
        return False
    except Exception as e:
        print(f"[NAVIGATION] Error al validar grid: {e}")
        return False

