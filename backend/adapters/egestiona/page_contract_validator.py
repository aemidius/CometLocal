"""
Page Contract Validator: Valida que estamos en la página correcta antes de extraer datos.

Evita falsos "0 pendientes" cuando la navegación falla o hay modales bloqueando.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional
import time


def wait_for_grid_stable(page_or_frame: Any, timeout: float = 25.0) -> Dict[str, Any]:
    """
    Espera a que el grid esté estable (sin overlay de "Loading...").
    
    Args:
        page_or_frame: Page o Frame de Playwright
        timeout: Timeout máximo en segundos (default 25s)
    
    Returns:
        Dict con información de lo detectado:
        - loading_overlay_detected: bool
        - loading_overlay_text: str|None (primeros 80 chars)
        - loading_duration_ms: float (tiempo que duró el loading)
    """
    start_time = time.time()
    loading_detected = False
    loading_text = None
    poll_interval = 0.4  # 400ms entre checks
    
    # Selectores para detectar "Loading..."
    loading_selectors = [
        r'text=/loading\.\.\./i',
        r'text=/cargando\.\.\./i',
        '[class*="loading"]',
        '[id*="loading"]',
        '.loading',
        '#loading',
    ]
    
    # Buscar overlay/modal de loading
    while time.time() - start_time < timeout:
        loading_found = False
        current_text = None
        
        try:
            # Buscar por texto "Loading..." (case-insensitive)
            for selector in loading_selectors:
                try:
                    locator = page_or_frame.locator(selector)
                    count = locator.count()
                    if count > 0:
                        # Verificar que es visible
                        for i in range(min(count, 3)):  # Revisar hasta 3 elementos
                            try:
                                if locator.nth(i).is_visible():
                                    loading_found = True
                                    # Obtener texto del elemento
                                    try:
                                        current_text = locator.nth(i).text_content()[:80] if locator.nth(i).text_content() else None
                                    except Exception:
                                        pass
                                    break
                            except Exception:
                                continue
                        if loading_found:
                            break
                except Exception:
                    continue
            
            # También buscar por texto en el body
            if not loading_found:
                try:
                    body_text = page_or_frame.evaluate("() => document.body.innerText.toLowerCase()")
                    if "loading" in body_text or "cargando" in body_text:
                        # Verificar que no es parte de otro texto (ej: "unloading")
                        loading_keywords = ["loading...", "cargando...", "loading", "cargando"]
                        for keyword in loading_keywords:
                            if keyword in body_text:
                                # Buscar el contexto alrededor
                                idx = body_text.find(keyword)
                                context = body_text[max(0, idx-20):min(len(body_text), idx+100)]
                                if "loading" in context or "cargando" in context:
                                    loading_found = True
                                    current_text = context[:80]
                                    break
                except Exception:
                    pass
            
            if loading_found:
                if not loading_detected:
                    loading_detected = True
                    loading_text = current_text
                # Esperar un poco más
                time.sleep(poll_interval)
            else:
                # Si ya no hay loading, esperar un poco más para estabilizar
                if loading_detected:
                    time.sleep(0.5)  # Espera adicional tras desaparecer loading
                break
                
        except Exception as e:
            # Si hay error al verificar, continuar
            time.sleep(poll_interval)
            continue
    
    loading_duration_ms = (time.time() - start_time) * 1000
    
    return {
        "loading_overlay_detected": loading_detected,
        "loading_overlay_text": loading_text,
        "loading_duration_ms": loading_duration_ms,
    }


class PageContractError(Exception):
    """Excepción para errores de page contract."""
    
    def __init__(
        self,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        evidence_paths: Optional[Dict[str, str]] = None,
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.evidence_paths = evidence_paths or {}
        super().__init__(self.message)


def validate_pending_page_contract(
    page: Any,
    list_frame: Optional[Any],
    evidence_dir: Path,
) -> None:
    """
    Valida el "page contract" antes de extraer pendientes.
    
    Verifica:
    A) Autenticación: selector de sesión iniciada
    B) Vista correcta: frame f3 con URL correcta o breadcrumb/título
    C) Tabla renderizada: table.hdr + table.obj.row20px O empty-state real
    
    Raises:
        PageContractError: Si alguna validación falla, con error_code, message, details y evidence_paths
    """
    
    # A) Validar autenticación
    auth_verified = False
    try:
        # Verificar frame nm_contenido (indica autenticación)
        main_frame = page.frame(name="nm_contenido")
        if main_frame:
            auth_verified = True
    except Exception:
        pass
    
    if not auth_verified:
        # Intentar selectores de logout/usuario
        try:
            logout_selectors = [
                'text=/desconectar|logout|cerrar sesión/i',
                'a[href*="logout"]',
                'a[href*="desconectar"]',
            ]
            for selector in logout_selectors:
                if page.locator(selector).count() > 0:
                    auth_verified = True
                    break
        except Exception:
            pass
    
    if not auth_verified:
        # Verificar URL (si no está en login, probablemente autenticado)
        current_url = page.url
        if "login" not in current_url.lower() and "default_contenido" in current_url.lower():
            auth_verified = True
    
    if not auth_verified:
        screenshot_path = evidence_dir / "not_authenticated.png"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass
        
        # Generar dump
        dump_path = evidence_dir / "not_authenticated_dump.txt"
        page_info = {}
        try:
            page_info = page.evaluate("""() => ({
                url: window.location.href,
                title: document.title,
                bodyText: document.body.innerText.substring(0, 300)
            })""")
            dump_content = f"""Error: No autenticado
URL: {page_info.get('url', 'N/A')}
Title: {page_info.get('title', 'N/A')}
Body (primeros 300 chars): {page_info.get('bodyText', 'N/A')}
"""
            dump_path.write_text(dump_content, encoding="utf-8")
        except Exception:
            pass
        
        # Construir evidence_paths de forma segura
        from backend.shared.path_utils import safe_path_join, as_str
        evidence_base = evidence_dir.parent.parent.parent if evidence_dir else None
        screenshot_rel = None
        dump_rel = None
        if screenshot_path.exists() and evidence_base:
            screenshot_abs = safe_path_join(evidence_base, screenshot_path)
            if screenshot_abs:
                screenshot_rel = as_str(screenshot_path.relative_to(evidence_base))
        if dump_path.exists() and evidence_base:
            dump_abs = safe_path_join(evidence_base, dump_path)
            if dump_abs:
                dump_rel = as_str(dump_path.relative_to(evidence_base))
        
        raise PageContractError(
            error_code="not_authenticated",
            message="No se pudo verificar autenticación. No se detectó sesión iniciada.",
            details={
                "current_url": page_info.get('url', page.url),
                "title": page_info.get('title', 'N/A'),
                "selector_checks": {
                    "nm_contenido_frame": False,
                    "logout_selectors": False,
                    "url_check": False,
                }
            },
            evidence_paths={
                "screenshot": screenshot_rel,
                "dump": dump_rel,
            }
        )
    
    # B) Validar vista correcta de pendientes
    if not list_frame:
        screenshot_path = evidence_dir / "wrong_page.png"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass
        
        dump_path = evidence_dir / "wrong_page_dump.txt"
        page_info = {}
        try:
            page_info = page.evaluate("""() => ({
                url: window.location.href,
                title: document.title,
                bodyText: document.body.innerText.substring(0, 300),
                frames: Array.from(window.frames).map(f => ({ name: f.name, url: f.location.href }))
            })""")
            dump_content = f"""Error: Vista incorrecta (frame de pendientes no encontrado)
URL: {page_info.get('url', 'N/A')}
Title: {page_info.get('title', 'N/A')}
Body (primeros 300 chars): {page_info.get('bodyText', 'N/A')}
Frames: {page_info.get('frames', [])}
"""
            dump_path.write_text(dump_content, encoding="utf-8")
        except Exception:
            pass
        
        raise PageContractError(
            error_code="wrong_page",
            message="No se encontró el frame de lista de pendientes (f3). No estamos en la vista correcta.",
            details={
                "current_url": page_info.get('url', page.url),
                "title": page_info.get('title', 'N/A'),
                "frames_found": page_info.get('frames', []),
                "expected_frame": "f3",
            },
            evidence_paths={
                "screenshot": str(screenshot_path.relative_to(evidence_dir.parent.parent.parent)) if (screenshot_path.exists() and evidence_dir and evidence_dir.parent and evidence_dir.parent.parent and evidence_dir.parent.parent.parent) else None,
                "dump": str(dump_path.relative_to(evidence_dir.parent.parent.parent)) if (dump_path.exists() and evidence_dir and evidence_dir.parent and evidence_dir.parent.parent and evidence_dir.parent.parent.parent) else None,
            }
        )
    
    # Verificar URL del frame
    frame_url = list_frame.url if hasattr(list_frame, 'url') else ""
    if not ("buscador.asp" in frame_url.lower() and "apartado_id=3" in frame_url.lower()):
        screenshot_path = evidence_dir / "wrong_page.png"
        try:
            list_frame.locator("body").screenshot(path=str(screenshot_path))
        except Exception:
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                pass
        
        dump_path = evidence_dir / "wrong_page_dump.txt"
        frame_info = {}
        try:
            frame_info = list_frame.evaluate("""() => ({
                url: window.location.href,
                title: document.title,
                bodyText: document.body.innerText.substring(0, 300)
            })""")
            dump_content = f"""Error: Vista incorrecta (URL del frame no corresponde a pendientes)
Frame URL: {frame_url}
Frame Title: {frame_info.get('title', 'N/A')}
Frame Body (primeros 300 chars): {frame_info.get('bodyText', 'N/A')}
"""
            dump_path.write_text(dump_content, encoding="utf-8")
        except Exception:
            pass
        
        raise PageContractError(
            error_code="wrong_page",
            message=f"El frame de lista no está en la URL correcta de pendientes. URL actual: {frame_url}",
            details={
                "current_url": page.url,
                "frame_url": frame_url,
                "frame_title": frame_info.get('title', 'N/A'),
                "expected_url_pattern": "buscador.asp?Apartado_ID=3",
            },
            evidence_paths={
                "screenshot": str(screenshot_path.relative_to(evidence_dir.parent.parent.parent)) if (screenshot_path.exists() and evidence_dir and evidence_dir.parent and evidence_dir.parent.parent and evidence_dir.parent.parent.parent) else None,
                "dump": str(dump_path.relative_to(evidence_dir.parent.parent.parent)) if (dump_path.exists() and evidence_dir and evidence_dir.parent and evidence_dir.parent.parent and evidence_dir.parent.parent.parent) else None,
            }
        )
    
    # C) Esperar a que el grid esté estable (sin "Loading...")
    loading_info = wait_for_grid_stable(list_frame, timeout=25.0)
    
    # C) Validar que la tabla está renderizada O hay empty-state real
    has_table_headers = False
    has_table_rows = False
    has_empty_state = False
    empty_state_text_sample = None
    
    try:
        # Verificar table.hdr
        hdr_count = list_frame.locator("table.hdr").count()
        has_table_headers = hdr_count > 0
        
        # Verificar table.obj.row20px
        obj_count = list_frame.locator("table.obj.row20px").count()
        has_table_rows = obj_count > 0
        
        # Verificar empty-state robusto (incluyendo "0 Registros", "0 registros", etc.)
        empty_state_patterns = [
            r"0\s+registros?",  # "0 Registros", "0 registros"
            r"0\s+registro\(s\)",  # "0 Registro(s)"
            r"no hay",
            r"sin resultados",
            r"sin datos",
            r"no se encontraron",
            r"lista vacía",
            r"ningún resultado",
            r"sin registros",
        ]
        
        body_text = list_frame.evaluate("() => document.body.innerText")
        body_text_lower = body_text.lower() if body_text else ""
        
        # Buscar patrones de empty-state
        import re
        for pattern in empty_state_patterns:
            matches = re.search(pattern, body_text_lower, re.IGNORECASE)
            if matches:
                # Verificar que realmente no hay tabla con datos
                if not has_table_rows or list_frame.locator("table.obj.row20px tr").count() == 0:
                    has_empty_state = True
                    # Extraer muestra del texto alrededor del match
                    start = max(0, matches.start() - 20)
                    end = min(len(body_text), matches.end() + 60)
                    empty_state_text_sample = body_text[start:end].strip()[:100]
                    break
        
        # También buscar en elementos específicos del grid/paginador
        if not has_empty_state:
            try:
                # Buscar en elementos comunes de empty-state
                empty_selectors = [
                    '.empty-state',
                    '.no-results',
                    '.sin-resultados',
                    '[class*="empty"]',
                    '[class*="no-data"]',
                ]
                for selector in empty_selectors:
                    try:
                        empty_elem = list_frame.locator(selector)
                        if empty_elem.count() > 0 and empty_elem.first().is_visible():
                            has_empty_state = True
                            empty_state_text_sample = empty_elem.first().text_content()[:100] if empty_elem.first().text_content() else None
                            break
                    except Exception:
                        continue
            except Exception:
                pass
                
    except Exception as e:
        # Si hay excepción al verificar, considerar como no renderizado
        pass
    
    # Considerar "tabla cargada" si:
    # A) se detecta table.hdr (headers) Y
    # B) (rows_detected > 0) OR (empty_state_detected == true)
    table_loaded = has_table_headers and (has_table_rows or has_empty_state)
    
    if not table_loaded:
        screenshot_path = evidence_dir / "pending_list_not_loaded.png"
        try:
            list_frame.locator("body").screenshot(path=str(screenshot_path))
        except Exception:
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                pass
        
        dump_path = evidence_dir / "pending_list_not_loaded_dump.txt"
        frame_info = {}
        try:
            frame_info = list_frame.evaluate("""() => ({
                url: window.location.href,
                title: document.title,
                bodyText: document.body.innerText.substring(0, 500),
                hasHdrTable: document.querySelectorAll('table.hdr').length > 0,
                hasObjTable: document.querySelectorAll('table.obj.row20px').length > 0,
                hdrTableCount: document.querySelectorAll('table.hdr').length,
                objTableCount: document.querySelectorAll('table.obj.row20px').length
            })""")
            dump_content = f"""Error: Lista de pendientes no cargada
Frame URL: {frame_url}
Frame Title: {frame_info.get('title', 'N/A')}
Frame Body (primeros 500 chars): {frame_info.get('bodyText', 'N/A')}
Has table.hdr: {frame_info.get('hasHdrTable', False)}
Has table.obj.row20px: {frame_info.get('hasObjTable', False)}
HDR tables count: {frame_info.get('hdrTableCount', 0)}
OBJ tables count: {frame_info.get('objTableCount', 0)}
Loading overlay detected: {loading_info.get('loading_overlay_detected', False)}
Loading overlay text: {loading_info.get('loading_overlay_text', 'N/A')}
Empty state detected: {has_empty_state}
Empty state text sample: {empty_state_text_sample or 'N/A'}
"""
            dump_path.write_text(dump_content, encoding="utf-8")
        except Exception:
            pass
        
        raise PageContractError(
            error_code="pending_list_not_loaded",
            message="La tabla de pendientes no está renderizada. No se encontraron table.hdr ni table.obj.row20px, ni empty-state válido.",
            details={
                "current_url": page.url,
                "frame_url": frame_url,
                "frame_title": frame_info.get('title', 'N/A'),
                "selector_checks": {
                    "has_table_headers": has_table_headers,
                    "has_table_rows": has_table_rows,
                    "has_empty_state": has_empty_state,
                    "hdr_table_count": frame_info.get('hdrTableCount', 0),
                    "obj_table_count": frame_info.get('objTableCount', 0),
                },
                "loading_info": loading_info,
                "empty_state_text_sample": empty_state_text_sample,
            },
            evidence_paths={
                "screenshot": str(screenshot_path.relative_to(evidence_dir.parent.parent.parent)) if (screenshot_path.exists() and evidence_dir and evidence_dir.parent and evidence_dir.parent.parent and evidence_dir.parent.parent.parent) else None,
                "dump": str(dump_path.relative_to(evidence_dir.parent.parent.parent)) if (dump_path.exists() and evidence_dir and evidence_dir.parent and evidence_dir.parent.parent and evidence_dir.parent.parent.parent) else None,
            }
        )
    
    # Todo correcto - no lanzar excepción
