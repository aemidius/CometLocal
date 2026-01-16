"""
Helper para auto-disparar búsqueda y esperar grid estable en eGestión.

SPRINT C2.13.0: Evita falsos "0 Registros" haciendo click en "Buscar" automáticamente
y esperando a que el grid se rellene.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
import time
import re


def ensure_results_loaded(
    list_frame: Any,
    evidence_dir: Optional[Any] = None,
    timeout_seconds: float = 60.0,
    max_retries: int = 1,
    page: Optional[Any] = None,  # HOTFIX C2.13.9: Para validar pestaña correcta
) -> Dict[str, Any]:
    """
    SPRINT C2.13.0: Asegura que el grid tiene resultados cargados.
    
    Si detecta "0 Registros" y el botón "Buscar" está disponible, hace click
    y espera a que el grid se rellene.
    
    Args:
        list_frame: Frame de Playwright que contiene el grid (buscador.asp)
        evidence_dir: Directorio para guardar evidencias (opcional)
        timeout_seconds: Timeout máximo para esperar resultados (default 60s)
        max_retries: Número máximo de reintentos (default 1)
    
    Returns:
        Dict con información del proceso:
        - search_clicked: bool - Si se hizo click en "Buscar"
        - rows_before: int - Filas antes de buscar
        - rows_after: int - Filas después de buscar
        - counter_text_before: str - Texto del contador antes
        - counter_text_after: str - Texto del contador después
        - frame_url: str - URL del frame
        - diagnostics: Dict - Información adicional
    """
    result = {
        "search_clicked": False,
        "rows_before": 0,
        "rows_after": 0,
        "counter_text_before": None,
        "counter_text_after": None,
        "frame_url": list_frame.url if hasattr(list_frame, 'url') else None,
        "diagnostics": {},
    }
    
    # HOTFIX C2.13.9: Definir counter_patterns al inicio para reutilizar en fallbacks
    counter_patterns = [
        r'(\d+)\s+registros?',
        r'(\d+)\s+registro\(s\)',
        r'registros?:\s*(\d+)',
        r'total:\s*(\d+)',
    ]
    
    try:
        # HOTFIX C2.13.9: TAREA A - Validar que estamos en la pestaña correcta "Pendientes" y modo "Pendiente enviar"
        if page:
            try:
                # Verificar URL del frame
                frame_url = list_frame.url if hasattr(list_frame, 'url') else None
                if frame_url:
                    result["diagnostics"]["frame_url"] = frame_url
                    # Validar que estamos en buscador.asp?Apartado_ID=3
                    if not ("buscador.asp" in frame_url.lower() and "apartado_id=3" in frame_url.lower()):
                        result["diagnostics"]["wrong_tab_warning"] = f"Frame URL no corresponde a pendientes: {frame_url}"
                        print(f"[grid_search] ⚠️ Advertencia: Frame URL no corresponde a pendientes: {frame_url}")
            except Exception as e:
                result["diagnostics"]["tab_validation_error"] = str(e)
        
        # 1) Detectar contador de registros y filas antes
        counter_text_before = None
        rows_before = 0
        
        try:
            # Intentar leer texto del frame para encontrar contador
            body_text = list_frame.evaluate("() => document.body.innerText")
            body_text_lower = body_text.lower() if body_text else ""
            
            # Buscar patrón "0 Registros" o "0 Registro(s)" usando counter_patterns definido arriba
            
            for pattern in counter_patterns:
                match = re.search(pattern, body_text_lower, re.IGNORECASE)
                if match:
                    counter_text_before = match.group(0)
                    count = int(match.group(1))
                    result["counter_text_before"] = counter_text_before
                    result["rows_before"] = count
                    rows_before = count
                    break
        except Exception as e:
            result["diagnostics"]["counter_detection_error"] = str(e)
        
        # HOTFIX C2.13.9: Contar filas de datos reales (no tablas, sino filas tr dentro de tbody)
        try:
            # Contar filas de datos en el grid (tr dentro de tbody, excluyendo header)
            rows_count = list_frame.locator("table.obj.row20px tbody tr").count()
            if rows_count > 0:
                result["rows_before"] = rows_count
                rows_before = rows_count
                result["diagnostics"]["rows_count_method"] = "tbody_tr"
            else:
                # Fallback: contar tablas (menos preciso pero mejor que nada)
                tables_count = list_frame.locator("table.obj.row20px").count()
                if tables_count > 0:
                    result["rows_before"] = tables_count
                    rows_before = tables_count
                    result["diagnostics"]["rows_count_method"] = "table_count_fallback"
        except Exception as e:
            result["diagnostics"]["rows_count_error"] = str(e)
        
        # 2) Detectar si hay "0 Registros" y botón "Buscar" disponible
        has_zero_registros = (
            (counter_text_before and "0" in counter_text_before and "registro" in counter_text_before.lower()) or
            rows_before == 0
        )
        
        btn_buscar = None
        btn_buscar_visible = False
        btn_buscar_enabled = False
        btn_buscar_selector_used = None
        
        try:
            # HOTFIX C2.13.9: Buscar botón "Buscar" con múltiples selectores robustos
            buscar_selectors = [
                # Selectores por texto
                'button:has-text("Buscar")',
                'input[type="button"][value*="Buscar"]',
                'input[type="submit"][value*="Buscar"]',
                'a:has-text("Buscar")',
                # Selectores por atributos
                '[aria-label*="Buscar" i]',
                '[title*="Buscar" i]',
                '[alt*="Buscar" i]',
                # Selectores por onclick
                '[onclick*="buscar" i]',
                '[onclick*="Buscar"]',
                # Selectores por clase/ID comunes
                '[id*="buscar" i]',
                '[class*="buscar" i]',
                '[id*="btnBuscar" i]',
                '[id*="btn_buscar" i]',
                # Selectores por icono/lupa
                'button[class*="search" i]',
                'button[class*="lupa" i]',
                'a[class*="search" i]',
                'a[class*="lupa" i]',
            ]
            
            for selector in buscar_selectors:
                try:
                    btn = list_frame.locator(selector)
                    if btn.count() > 0:
                        btn_buscar = btn.first()
                        btn_buscar_visible = btn_buscar.is_visible()
                        btn_buscar_enabled = btn_buscar.is_enabled() if hasattr(btn_buscar, 'is_enabled') else True
                        if btn_buscar_visible:
                            btn_buscar_selector_used = selector
                            result["diagnostics"]["buscar_selector_used"] = selector
                            break
                except Exception:
                    continue
        except Exception as e:
            result["diagnostics"]["buscar_button_detection_error"] = str(e)
        
        # HOTFIX C2.13.9: Si no se encontró "Buscar", intentar fallbacks
        fallback_attempted = False
        fallback_success = False
        
        if has_zero_registros and not btn_buscar:
            # TAREA B: Fallbacks cuando no se encuentra "Buscar"
            print(f"[grid_search] Botón 'Buscar' no encontrado, intentando fallbacks...")
            
            # Fallback 1: Click en "Resultados" si existe
            try:
                resultados_selectors = [
                    'button:has-text("Resultados")',
                    'a:has-text("Resultados")',
                    'input[type="button"][value*="Resultados"]',
                    '[aria-label*="Resultados" i]',
                ]
                for selector in resultados_selectors:
                    try:
                        btn_resultados = list_frame.locator(selector)
                        if btn_resultados.count() > 0 and btn_resultados.first().is_visible():
                            print(f"[grid_search] Fallback 1: Click en 'Resultados' (selector: {selector})")
                            btn_resultados.first().click(timeout=5000)
                            fallback_attempted = True
                            fallback_success = True
                            result["search_clicked"] = True
                            result["diagnostics"]["fallback_used"] = "resultados_button"
                            result["diagnostics"]["fallback_selector"] = selector
                            break
                    except Exception:
                        continue
            except Exception as e:
                result["diagnostics"]["fallback_1_error"] = str(e)
            
            # Fallback 2: Enfocar input del filtro y enviar Enter
            if not fallback_success:
                try:
                    input_selectors = [
                        'input[type="text"]',
                        'input[name*="filtro" i]',
                        'input[name*="buscar" i]',
                        'input[id*="filtro" i]',
                        'input[id*="buscar" i]',
                    ]
                    for selector in input_selectors:
                        try:
                            input_elem = list_frame.locator(selector).first()
                            if input_elem.count() > 0 and input_elem.is_visible():
                                print(f"[grid_search] Fallback 2: Enfocar input y enviar Enter (selector: {selector})")
                                input_elem.focus()
                                input_elem.press("Enter")
                                time.sleep(1.0)  # Esperar a que se procese
                                fallback_attempted = True
                                fallback_success = True
                                result["search_clicked"] = True
                                result["diagnostics"]["fallback_used"] = "input_enter"
                                result["diagnostics"]["fallback_selector"] = selector
                                break
                        except Exception:
                            continue
                except Exception as e:
                    result["diagnostics"]["fallback_2_error"] = str(e)
            
            # Fallback 3: Click en icono refresh del grid (si hay)
            if not fallback_success:
                try:
                    refresh_selectors = [
                        'button[class*="refresh" i]',
                        'a[class*="refresh" i]',
                        'button[title*="Actualizar" i]',
                        'button[title*="Refresh" i]',
                        '[aria-label*="Actualizar" i]',
                        '[aria-label*="Refresh" i]',
                        'button:has-text("Actualizar")',
                    ]
                    for selector in refresh_selectors:
                        try:
                            btn_refresh = list_frame.locator(selector)
                            if btn_refresh.count() > 0 and btn_refresh.first().is_visible():
                                print(f"[grid_search] Fallback 3: Click en refresh (selector: {selector})")
                                btn_refresh.first().click(timeout=5000)
                                fallback_attempted = True
                                fallback_success = True
                                result["search_clicked"] = True
                                result["diagnostics"]["fallback_used"] = "refresh_button"
                                result["diagnostics"]["fallback_selector"] = selector
                                break
                        except Exception:
                            continue
                except Exception as e:
                    result["diagnostics"]["fallback_3_error"] = str(e)
            
            # HOTFIX C2.13.9: Si se usó un fallback exitoso, esperar a que el grid se rellene
            if fallback_success:
                print(f"[grid_search] Fallback exitoso usado, esperando a que el grid se rellene...")
                # Reutilizar la misma lógica de espera que para "Buscar"
                start_wait = time.time()
                rows_after = rows_before
                counter_text_after = counter_text_before
                
                # Esperar un poco después del fallback
                time.sleep(1.0)
                
                # Esperar indicadores de que el grid se está cargando/rellenando
                loading_detected = False
                while time.time() - start_wait < timeout_seconds:
                    try:
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
                                if list_frame.locator(selector).count() > 0:
                                    has_loading = True
                                    loading_detected = True
                                    break
                            except Exception:
                                continue
                        
                        # Si hay loading, esperar a que desaparezca
                        if has_loading:
                            time.sleep(0.5)
                            continue
                        
                        # Si ya no hay loading (o nunca hubo), verificar filas
                        if not has_loading or (loading_detected and not has_loading):
                            # Contar filas actuales
                            try:
                                rows_count = list_frame.locator("table.obj.row20px tbody tr").count()
                                if rows_count == 0:
                                    # Fallback: contar tablas
                                    rows_count = list_frame.locator("table.obj.row20px").count()
                                
                                if rows_count > rows_before:
                                    rows_after = rows_count
                                    result["rows_after"] = rows_after
                                    print(f"[grid_search] Grid rellenado después de fallback: {rows_after} filas detectadas")
                                    break
                            except Exception as e:
                                result["diagnostics"]["rows_count_after_fallback_error"] = str(e)
                                pass
                            
                            # Verificar contador de registros
                            try:
                                body_text = list_frame.evaluate("() => document.body.innerText")
                                body_text_lower = body_text.lower() if body_text else ""
                                
                                for pattern in counter_patterns:
                                    match = re.search(pattern, body_text_lower, re.IGNORECASE)
                                    if match:
                                        counter_text_after = match.group(0)
                                        count = int(match.group(1))
                                        if count > rows_before:
                                            result["counter_text_after"] = counter_text_after
                                            result["rows_after"] = count
                                            rows_after = count
                                            print(f"[grid_search] Contador actualizado después de fallback: {counter_text_after}")
                                            break
                            except Exception:
                                pass
                            
                            # Si ya pasó suficiente tiempo sin loading y hay filas, considerar listo
                            if time.time() - start_wait > 3.0:
                                try:
                                    rows_count = list_frame.locator("table.obj.row20px tbody tr").count()
                                    if rows_count == 0:
                                        # Fallback: contar tablas
                                        rows_count = list_frame.locator("table.obj.row20px").count()
                                    
                                    if rows_count > 0:
                                        rows_after = rows_count
                                        result["rows_after"] = rows_after
                                        break
                                except Exception:
                                    pass
                        
                        time.sleep(0.5)
                    except Exception as e:
                        result["diagnostics"]["wait_error_fallback"] = str(e)
                        time.sleep(0.5)
                
                # Screenshot después (si evidence_dir disponible)
                if evidence_dir:
                    try:
                        list_frame.locator("body").screenshot(path=str(evidence_dir / "04_grid_after_fallback.png"))
                    except Exception:
                        pass
                
                result["counter_text_after"] = counter_text_after
                result["rows_after"] = rows_after
                
                wait_duration = time.time() - start_wait
                result["diagnostics"]["wait_duration_seconds_fallback"] = wait_duration
                result["diagnostics"]["loading_detected_fallback"] = loading_detected
                
                if rows_after > rows_before:
                    print(f"[grid_search] ✅ Grid rellenado exitosamente después de fallback: {rows_before} → {rows_after} filas")
                else:
                    print(f"[grid_search] ⚠️ Grid sigue vacío después de fallback: {rows_after} filas")
            
            if fallback_attempted and not fallback_success:
                result["diagnostics"]["fallback_attempted"] = True
                result["diagnostics"]["fallback_success"] = False
        
        # 3) Si hay "0 Registros" y botón "Buscar" está disponible, hacer click
        if has_zero_registros and btn_buscar and btn_buscar_visible and btn_buscar_enabled:
            print(f"[grid_search] Detectado '0 Registros' con botón Buscar disponible. Haciendo click...")
            result["search_clicked"] = True
            
            # Screenshot antes (si evidence_dir disponible)
            if evidence_dir:
                try:
                    list_frame.locator("body").screenshot(path=str(evidence_dir / "03_grid_before_search.png"))
                except Exception:
                    pass
            
            # Hacer click en "Buscar"
            try:
                btn_buscar.click(timeout=10000)
                print(f"[grid_search] Click en 'Buscar' ejecutado")
            except Exception as e:
                result["diagnostics"]["buscar_click_error"] = str(e)
                print(f"[grid_search] Error al hacer click en 'Buscar': {e}")
                return result
            
            # 4) Esperar a que el grid se rellene
            start_wait = time.time()
            rows_after = rows_before
            counter_text_after = counter_text_before
            
            # HOTFIX C2.13.9: Esperar un poco después del click para que se procese
            time.sleep(1.0)
            
            # Esperar indicadores de que el grid se está cargando/rellenando
            loading_detected = False
            while time.time() - start_wait < timeout_seconds:
                try:
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
                            if list_frame.locator(selector).count() > 0:
                                has_loading = True
                                loading_detected = True
                                break
                        except Exception:
                            continue
                    
                    # Si hay loading, esperar a que desaparezca
                    if has_loading:
                        time.sleep(0.5)
                        continue
                    
                    # Si ya no hay loading (o nunca hubo), verificar filas
                    if not has_loading or (loading_detected and not has_loading):
                        # HOTFIX C2.13.9: Contar filas de datos reales (tr dentro de tbody)
                        try:
                            rows_count = list_frame.locator("table.obj.row20px tbody tr").count()
                            if rows_count == 0:
                                # Fallback: contar tablas
                                rows_count = list_frame.locator("table.obj.row20px").count()
                            
                            if rows_count > rows_before:
                                rows_after = rows_count
                                result["rows_after"] = rows_after
                                print(f"[grid_search] Grid rellenado: {rows_after} filas detectadas")
                                break
                        except Exception as e:
                            result["diagnostics"]["rows_count_after_error"] = str(e)
                            pass
                        
                        # Verificar contador de registros
                        try:
                            body_text = list_frame.evaluate("() => document.body.innerText")
                            body_text_lower = body_text.lower() if body_text else ""
                            
                            for pattern in counter_patterns:
                                match = re.search(pattern, body_text_lower, re.IGNORECASE)
                                if match:
                                    counter_text_after = match.group(0)
                                    count = int(match.group(1))
                                    if count > rows_before:
                                        result["counter_text_after"] = counter_text_after
                                        result["rows_after"] = count
                                        rows_after = count
                                        print(f"[grid_search] Contador actualizado: {counter_text_after}")
                                        break
                        except Exception:
                            pass
                        
                        # Si ya pasó suficiente tiempo sin loading y hay filas, considerar listo
                        if time.time() - start_wait > 3.0:
                            try:
                                rows_count = list_frame.locator("table.obj.row20px tbody tr").count()
                                if rows_count == 0:
                                    # Fallback: contar tablas
                                    rows_count = list_frame.locator("table.obj.row20px").count()
                                
                                if rows_count > 0:
                                    rows_after = rows_count
                                    result["rows_after"] = rows_after
                                    break
                            except Exception:
                                pass
                    
                    time.sleep(0.5)
                except Exception as e:
                    result["diagnostics"]["wait_error"] = str(e)
                    time.sleep(0.5)
            
            # Screenshot después (si evidence_dir disponible)
            if evidence_dir:
                try:
                    list_frame.locator("body").screenshot(path=str(evidence_dir / "04_grid_after_search.png"))
                except Exception:
                    pass
            
            result["counter_text_after"] = counter_text_after
            result["rows_after"] = rows_after
            
            wait_duration = time.time() - start_wait
            result["diagnostics"]["wait_duration_seconds"] = wait_duration
            result["diagnostics"]["loading_detected"] = loading_detected
            
            if rows_after > rows_before:
                print(f"[grid_search] ✅ Grid rellenado exitosamente: {rows_before} → {rows_after} filas")
            else:
                print(f"[grid_search] ⚠️ Grid sigue vacío después de buscar: {rows_after} filas")
        else:
            # No se hizo click (no era necesario o no estaba disponible)
            result["rows_after"] = rows_before
            result["counter_text_after"] = counter_text_before
            if not has_zero_registros:
                print(f"[grid_search] No se requiere búsqueda: {rows_before} filas ya presentes")
            elif not btn_buscar:
                # HOTFIX C2.13.9: TAREA A - Instrumentación fuerte cuando falla Buscar
                print(f"[grid_search] Botón 'Buscar' no encontrado")
                
                # Capturar screenshot
                if evidence_dir:
                    try:
                        screenshot_path = evidence_dir / "01_no_buscar.png"
                        list_frame.locator("body").screenshot(path=str(screenshot_path))
                        print(f"[grid_search] Screenshot guardado: {screenshot_path}")
                        result["diagnostics"]["screenshot_path"] = str(screenshot_path)
                    except Exception as e:
                        result["diagnostics"]["screenshot_error"] = str(e)
                
                # Guardar HTML del toolbar/filtros del grid
                if evidence_dir:
                    try:
                        # Localizar contenedor del grid (toolbar + header)
                        toolbar_selectors = [
                            'div[class*="toolbar" i]',
                            'div[class*="filtro" i]',
                            'div[id*="toolbar" i]',
                            'div[id*="filtro" i]',
                            'table.obj.row20px',
                            'div:has(button, input[type="button"])',
                        ]
                        
                        toolbar_html = None
                        for selector in toolbar_selectors:
                            try:
                                toolbar_elem = list_frame.locator(selector).first()
                                if toolbar_elem.count() > 0:
                                    toolbar_html = toolbar_elem.evaluate("(el) => el.outerHTML")
                                    if toolbar_html and len(toolbar_html) > 100:  # Asegurar que tiene contenido
                                        break
                            except Exception:
                                continue
                        
                        if not toolbar_html:
                            # Fallback: obtener HTML del body completo pero limitado
                            try:
                                body_html = list_frame.evaluate("() => document.body.innerHTML")
                                # Limitar a primeros 50000 caracteres
                                toolbar_html = body_html[:50000] if body_html else None
                            except Exception:
                                pass
                        
                        if toolbar_html:
                            html_path = evidence_dir / "grid_toolbar_outerHTML.html"
                            with open(html_path, "w", encoding="utf-8") as f:
                                f.write(toolbar_html)
                            print(f"[grid_search] HTML del toolbar guardado: {html_path}")
                            result["diagnostics"]["toolbar_html_path"] = str(html_path)
                    except Exception as e:
                        result["diagnostics"]["toolbar_html_error"] = str(e)
                
                # Loguear textos de botones visibles cerca del grid
                try:
                    all_buttons = list_frame.locator("button, input[type='button'], a").all()
                    button_texts = []
                    for btn in all_buttons[:50]:  # Limitar a primeros 50 para no saturar
                        try:
                            text = btn.text_content()
                            if text:
                                text_lower = text.lower().strip()
                                # Filtrar por palabras clave
                                keywords = ["buscar", "resultados", "limpiar", "actualizar", "refresh", "filtrar"]
                                if any(keyword in text_lower for keyword in keywords):
                                    button_texts.append(text.strip())
                        except Exception:
                            continue
                    
                    if button_texts:
                        result["diagnostics"]["visible_button_texts"] = button_texts
                        print(f"[grid_search] Botones visibles encontrados: {button_texts}")
                        
                        # HOTFIX C2.13.9a: TAREA B - Si "Buscar" está en botones visibles, intentar click robusto
                        if any("buscar" in text.lower() for text in button_texts):
                            print(f"[grid_search] 'Buscar' detectado en botones visibles, intentando click robusto...")
                            
                            # Buscar candidatos clicables con texto "Buscar"
                            try:
                                buscar_candidates = []
                                all_clickables = list_frame.locator("button, input[type='button'], a, div[role='button']").all()
                                
                                for idx, candidate in enumerate(all_clickables[:10]):  # Limitar a primeros 10
                                    try:
                                        text = candidate.text_content()
                                        if text and "buscar" in text.lower():
                                            # Capturar información del candidato
                                            try:
                                                tag_name = candidate.evaluate("(el) => el.tagName")
                                                elem_id = candidate.get_attribute("id") or None
                                                elem_class = candidate.get_attribute("class") or None
                                                is_visible = candidate.is_visible()
                                                is_enabled = candidate.is_enabled() if hasattr(candidate, 'is_enabled') else True
                                                
                                                bounding_box = None
                                                try:
                                                    box = candidate.bounding_box()
                                                    if box:
                                                        bounding_box = {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]}
                                                except Exception:
                                                    pass
                                                
                                                buscar_candidates.append({
                                                    "index": idx,
                                                    "tagName": tag_name,
                                                    "id": elem_id,
                                                    "class": elem_class,
                                                    "text": text.strip()[:50],
                                                    "isVisible": is_visible,
                                                    "isEnabled": is_enabled,
                                                    "boundingBox": bounding_box
                                                })
                                            except Exception as e:
                                                print(f"[grid_search] Error al obtener info del candidato {idx}: {e}")
                                                continue
                                    except Exception:
                                        continue
                                
                                result["diagnostics"]["buscar_candidates"] = buscar_candidates
                                print(f"[grid_search] Candidatos 'Buscar' encontrados: {len(buscar_candidates)}")
                                
                                # Elegir el primer candidato visible+enabled con boundingBox
                                clicked_candidate = None
                                for candidate_info in buscar_candidates:
                                    if candidate_info["isVisible"] and candidate_info["isEnabled"] and candidate_info["boundingBox"]:
                                        try:
                                            candidate_elem = all_clickables[candidate_info["index"]]
                                            
                                            # Intentar click normal
                                            try:
                                                candidate_elem.click(timeout=5000)
                                                clicked_candidate = candidate_info
                                                result["search_clicked"] = True
                                                result["diagnostics"]["buscar_click_method"] = "normal_click"
                                                result["diagnostics"]["clicked_buscar_candidate_index"] = candidate_info["index"]
                                                print(f"[grid_search] ✅ Click en 'Buscar' exitoso (candidato {candidate_info['index']}, método: normal_click)")
                                                break
                                            except Exception as click_error:
                                                # Intentar click con position center
                                                try:
                                                    box = candidate_elem.bounding_box()
                                                    if box:
                                                        center_x = box["x"] + box["width"] / 2
                                                        center_y = box["y"] + box["height"] / 2
                                                        list_frame.click(center_x, center_y, timeout=5000)
                                                        clicked_candidate = candidate_info
                                                        result["search_clicked"] = True
                                                        result["diagnostics"]["buscar_click_method"] = "position_click"
                                                        result["diagnostics"]["clicked_buscar_candidate_index"] = candidate_info["index"]
                                                        print(f"[grid_search] ✅ Click en 'Buscar' exitoso (candidato {candidate_info['index']}, método: position_click)")
                                                        break
                                                except Exception as position_error:
                                                    # Último intento: force click SOLO si visible
                                                    if candidate_info["isVisible"]:
                                                        try:
                                                            candidate_elem.click(force=True, timeout=5000)
                                                            clicked_candidate = candidate_info
                                                            result["search_clicked"] = True
                                                            result["diagnostics"]["buscar_click_method"] = "force_click"
                                                            result["diagnostics"]["clicked_buscar_candidate_index"] = candidate_info["index"]
                                                            print(f"[grid_search] ✅ Click en 'Buscar' exitoso (candidato {candidate_info['index']}, método: force_click)")
                                                            break
                                                        except Exception as force_error:
                                                            result["diagnostics"]["buscar_force_click_error"] = str(force_error)
                                                            continue
                                                    continue
                                        except Exception as e:
                                            result["diagnostics"]["buscar_candidate_click_error"] = str(e)
                                            continue
                                
                                # Si se hizo click, esperar a que el grid se rellene
                                if clicked_candidate:
                                    print(f"[grid_search] Esperando a que el grid se rellene después de click en 'Buscar'...")
                                    start_wait = time.time()
                                    rows_after = rows_before
                                    counter_text_after = counter_text_before
                                    
                                    # Esperar un poco después del click
                                    time.sleep(1.0)
                                    
                                    # Esperar indicadores de que el grid se está cargando/rellenando
                                    loading_detected = False
                                    while time.time() - start_wait < timeout_seconds:
                                        try:
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
                                                    if list_frame.locator(selector).count() > 0:
                                                        has_loading = True
                                                        loading_detected = True
                                                        break
                                                except Exception:
                                                    continue
                                            
                                            # Si hay loading, esperar a que desaparezca
                                            if has_loading:
                                                time.sleep(0.5)
                                                continue
                                            
                                            # Si ya no hay loading (o nunca hubo), verificar filas
                                            if not has_loading or (loading_detected and not has_loading):
                                                # Contar filas actuales
                                                try:
                                                    rows_count = list_frame.locator("table.obj.row20px tbody tr").count()
                                                    if rows_count == 0:
                                                        # Fallback: contar tablas
                                                        rows_count = list_frame.locator("table.obj.row20px").count()
                                                    
                                                    if rows_count > rows_before:
                                                        rows_after = rows_count
                                                        result["rows_after"] = rows_after
                                                        print(f"[grid_search] Grid rellenado después de click en 'Buscar': {rows_after} filas detectadas")
                                                        break
                                                except Exception as e:
                                                    result["diagnostics"]["rows_count_after_buscar_error"] = str(e)
                                                    pass
                                                
                                                # Verificar contador de registros (preferible: localizar "X Registros" dentro del contenedor del grid)
                                                try:
                                                    body_text = list_frame.evaluate("() => document.body.innerText")
                                                    body_text_lower = body_text.lower() if body_text else ""
                                                    
                                                    for pattern in counter_patterns:
                                                        match = re.search(pattern, body_text_lower, re.IGNORECASE)
                                                        if match:
                                                            counter_text_after = match.group(0)
                                                            count = int(match.group(1))
                                                            if count > rows_before:
                                                                result["counter_text_after"] = counter_text_after
                                                                result["rows_after"] = count
                                                                rows_after = count
                                                                print(f"[grid_search] Contador actualizado después de click en 'Buscar': {counter_text_after}")
                                                                break
                                                except Exception:
                                                    pass
                                                
                                                # Si ya pasó suficiente tiempo sin loading y hay filas, considerar listo
                                                if time.time() - start_wait > 3.0:
                                                    try:
                                                        rows_count = list_frame.locator("table.obj.row20px tbody tr").count()
                                                        if rows_count == 0:
                                                            # Fallback: contar tablas
                                                            rows_count = list_frame.locator("table.obj.row20px").count()
                                                        
                                                        if rows_count > 0:
                                                            rows_after = rows_count
                                                            result["rows_after"] = rows_after
                                                            break
                                                    except Exception:
                                                        pass
                                            
                                            time.sleep(0.5)
                                        except Exception as e:
                                            result["diagnostics"]["wait_error_buscar"] = str(e)
                                            time.sleep(0.5)
                                    
                                    # Screenshot después (si evidence_dir disponible)
                                    if evidence_dir:
                                        try:
                                            list_frame.locator("body").screenshot(path=str(evidence_dir / "04_grid_after_buscar_click.png"))
                                        except Exception:
                                            pass
                                    
                                    result["counter_text_after"] = counter_text_after
                                    result["rows_after"] = rows_after
                                    
                                    wait_duration = time.time() - start_wait
                                    result["diagnostics"]["wait_duration_seconds_buscar"] = wait_duration
                                    result["diagnostics"]["loading_detected_buscar"] = loading_detected
                                    
                                    if rows_after > rows_before:
                                        print(f"[grid_search] ✅ Grid rellenado exitosamente después de click en 'Buscar': {rows_before} → {rows_after} filas")
                                    else:
                                        print(f"[grid_search] ⚠️ Grid sigue vacío después de click en 'Buscar': {rows_after} filas")
                            except Exception as e:
                                result["diagnostics"]["buscar_candidates_error"] = str(e)
                                print(f"[grid_search] Error al buscar candidatos 'Buscar': {e}")
                except Exception as e:
                    result["diagnostics"]["button_texts_error"] = str(e)
            elif not btn_buscar_visible:
                print(f"[grid_search] Botón 'Buscar' no visible")
            elif not btn_buscar_enabled:
                print(f"[grid_search] Botón 'Buscar' no habilitado")
    
    except Exception as e:
        result["diagnostics"]["error"] = str(e)
        result["diagnostics"]["error_type"] = type(e).__name__
        print(f"[grid_search] Error en ensure_results_loaded: {e}")
    
    return result
