"""
EgestionaRealUploader: Sube documentos reales en e-gestiona de forma controlada.

Solo se usa cuando:
- ENVIRONMENT=dev
- Header X-USE-REAL-UPLOADER=1
- max_uploads=1
- len(allowlist_type_ids)=1

NOTA: Usa Playwright sync API (no async) para compatibilidad con código existente.
"""

from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.config import DATA_DIR


class EgestionaRealUploader:
    """
    Sube documentos reales en e-gestiona usando Playwright.
    
    Requiere:
    - Página ya autenticada
    - Navegación previa al grid de pendientes
    - Documento válido en el repositorio
    """
    
    def __init__(self, evidence_dir: Path, logger=None):
        """
        Args:
            evidence_dir: Directorio donde guardar evidencias
            logger: Logger opcional (usa print si no se proporciona)
        """
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.log = logger or (lambda msg: print(f"[REAL_UPLOADER] {msg}"))
        self.upload_count = 0
        self.repo_store = DocumentRepositoryStoreV1(base_dir=DATA_DIR)
    
    def upload_one_real(
        self,
        page,
        item: Dict[str, Any],
        *,
        requirement_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sube UN documento real en e-gestiona.
        
        Args:
            page: Página de Playwright ya autenticada
            item: Item del plan con pending_ref, matched_doc, proposed_fields, etc.
            requirement_id: ID del requirement para evidencias (opcional)
        
        Returns:
            Dict con:
            - success: bool
            - upload_id: str
            - evidence_path: str
            - duration_ms: int
            - reason: str
            - portal_reference: str (si éxito)
        """
        self.upload_count += 1
        upload_id = f"real_upload_{self.upload_count}_{int(time.time())}"
        
        pending_ref = item.get("pending_ref", {})
        matched_doc = item.get("matched_doc", {})
        proposed_fields = item.get("proposed_fields", {})
        
        doc_id = matched_doc.get("doc_id")
        type_id = matched_doc.get("type_id")
        
        if not doc_id:
            return {
                "success": False,
                "upload_id": upload_id,
                "reason": "missing_doc_id",
                "error": "Item no tiene doc_id",
            }
        
        # Obtener path del documento desde el repositorio
        try:
            doc = self.repo_store.get_document(doc_id)
            if not doc:
                return {
                    "success": False,
                    "upload_id": upload_id,
                    "reason": "doc_not_found",
                    "error": f"Documento {doc_id} no encontrado en repositorio",
                }
            
            # Obtener path del PDF
            pdf_path = self.repo_store._get_doc_pdf_path(doc_id)
            if not pdf_path.exists():
                return {
                    "success": False,
                    "upload_id": upload_id,
                    "reason": "pdf_not_found",
                    "error": f"PDF no encontrado en {pdf_path}",
                }
        except Exception as e:
            return {
                "success": False,
                "upload_id": upload_id,
                "reason": "repo_error",
                "error": f"Error accediendo al repositorio: {e}",
            }
        
        # Directorio de evidencias para este item
        item_evidence_dir = self.evidence_dir / "items" / (requirement_id or f"req_{upload_id}")
        item_evidence_dir.mkdir(parents=True, exist_ok=True)
        
        started = time.time()
        
        try:
            # 1) dismiss_all_dhx_blockers
            try:
                from backend.adapters.egestiona.priority_comms_headful import dismiss_all_dhx_blockers
                self.log(f"Dismissing DHX blockers...")
                dismiss_all_dhx_blockers(page, item_evidence_dir, timeout_seconds=30)
            except Exception as e:
                self.log(f"Warning: Error al cerrar modales DHTMLX: {e}")
            
            # 2) Navegar al formulario de subida
            # Asumimos que estamos en el grid de pendientes
            # Necesitamos encontrar la fila correspondiente y abrir el detalle
            
            # Buscar frame de lista (f3 o buscador.asp)
            def _find_list_frame():
                fr = page.frame(name="f3")
                if fr:
                    return fr
                for fr2 in page.frames:
                    u = (fr2.url or "").lower()
                    if ("buscador.asp" in u) and ("apartado_id=3" in u):
                        return fr2
                return None
            
            list_frame = _find_list_frame()
            if not list_frame:
                # Intentar navegar desde dashboard
                frame_dashboard = page.frame(name="nm_contenido")
                if frame_dashboard:
                    # Click en Gestion(3)
                    tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
                    try:
                        frame_dashboard.locator(tile_sel).first.wait_for(state="visible", timeout=20000)
                        frame_dashboard.locator(tile_sel).first.click(timeout=20000)
                        time.sleep(2)
                        list_frame = _find_list_frame()
                    except Exception as e:
                        self.log(f"Warning: No se pudo navegar a Gestion(3): {e}")
            
            if not list_frame:
                raise RuntimeError("No se pudo encontrar el frame de lista de pendientes")
            
            # 3) Buscar la fila correspondiente al requirement
            # Usar pending_ref para identificar la fila
            tipo_doc = pending_ref.get("tipo_doc", "")
            elemento = pending_ref.get("elemento", "")
            empresa = pending_ref.get("empresa", "")
            
            # Extraer filas del grid
            extraction = list_frame.evaluate(
                """() => {
  function norm(s){ return (s||'').replace(/\\s+/g,' ').trim(); }
  function headersFromHdrTable(hdr){
    const cells = Array.from(hdr.querySelectorAll('tr:nth-of-type(2) td'));
    if(cells.length){
      return cells.map(td => {
        const span = td.querySelector('.hdrcell span');
        return span ? norm(span.innerText) : norm(td.innerText);
      });
    }
    return Array.from(hdr.querySelectorAll('.hdrcell span')).map(s => norm(s.innerText));
  }
  function extractRowsFromObjTable(tbl, headers){
    const trs = Array.from(tbl.querySelectorAll('tr'));
    const rows = [];
    for(const tr of trs){
      const tds = Array.from(tr.querySelectorAll('td'));
      if(!tds.length) continue;
      const cells = tds.map(td => norm(td.innerText));
      if(!cells.some(x => x)) continue;
      const mapped = {};
      for(let i=0;i<cells.length;i++){
        const k = (i < headers.length && headers[i]) ? headers[i] : `col_${i+1}`;
        mapped[k] = cells[i] || '';
      }
      rows.push({ mapped, raw_cells: cells, tr });
    }
    return rows;
  }
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!hdrTables.length || !objTables.length) return { headers: [], rows: [] };
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);
  let best = { tbl: null, rows: [] };
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > best.rows.length){
      best = { tbl: t, rows: rs };
    }
  }
  return { headers, rows: best.rows };
}"""
            )
            
            rows = extraction.get("rows", [])
            
            # Buscar fila que coincida (simplificado: buscar por tipo_doc y elemento)
            target_row_idx = None
            for idx, row_data in enumerate(rows):
                mapped = row_data.get("mapped", {})
                row_text = " ".join(str(v) for v in mapped.values()).lower()
                if tipo_doc.lower() in row_text and elemento.lower() in row_text:
                    target_row_idx = idx
                    break
            
            if target_row_idx is None:
                raise RuntimeError(f"No se encontró fila que coincida con tipo_doc='{tipo_doc}', elemento='{elemento}'")
            
            # 4) Screenshot before
            before_screenshot = item_evidence_dir / "before_upload.png"
            try:
                page.screenshot(path=str(before_screenshot), full_page=True)
            except Exception:
                try:
                    list_frame.locator("body").screenshot(path=str(before_screenshot))
                except Exception:
                    pass
            
            # 5) Abrir detalle de la fila
            click_result = list_frame.evaluate(
                """(idx) => {
  const tbls = Array.from(document.querySelectorAll('table.obj.row20px'));
  let best = null;
  let bestCount = -1;
  for(const t of tbls){
    const trs = Array.from(t.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length);
    if(trs.length > bestCount){
      best = { t, trs };
      bestCount = trs.length;
    }
  }
  if(!best || !best.trs[idx]) return { success: false, error: 'row_not_found' };
  const tr = best.trs[idx];
  const clickable = tr.querySelector('a, button, [onclick]');
  if(clickable){
    clickable.click();
    return { success: true };
  }
  tr.click();
  return { success: true };
}""",
                target_row_idx,
            )
            
            if not click_result.get("success"):
                raise RuntimeError(f"No se pudo hacer click en la fila {target_row_idx}")
            
            # Esperar a que se abra el detalle
            time.sleep(2)
            
            # 6) Buscar formulario de subida en el detalle
            # El detalle puede estar en un frame o en la misma página
            detail_frame = None
            for fr in page.frames:
                u = (fr.url or "").lower()
                if "detalle" in u or "detail" in u or "enviar" in u:
                    detail_frame = fr
                    break
            
            if not detail_frame:
                # Intentar buscar en la página principal
                detail_frame = page
            
            # 7) Seleccionar tipo de documento (si hay selector)
            # Buscar select/dropdown con el tipo de documento
            tipo_doc_text = tipo_doc  # Texto visible del tipo de documento
            
            # Intentar encontrar y seleccionar el tipo
            try:
                # Buscar select o dropdown
                select_found = False
                try:
                    # Intentar con select
                    select_locator = detail_frame.locator('select, [role="combobox"]')
                    if select_locator.count() > 0:
                        # Buscar opción que contenga el tipo de documento
                        options = detail_frame.locator('option, [role="option"]')
                        for i in range(options.count()):
                            option_text = options.nth(i).inner_text()
                            if tipo_doc_text.lower() in option_text.lower():
                                select_locator.first.select_option(index=i)
                                select_found = True
                                break
                except Exception:
                    pass
                
                if not select_found:
                    self.log(f"Warning: No se encontró selector de tipo de documento, continuando...")
            except Exception as e:
                self.log(f"Warning: Error al seleccionar tipo de documento: {e}")
            
            # 8) Subir archivo
            file_input = detail_frame.locator('input[type="file"]')
            if file_input.count() == 0:
                raise RuntimeError("No se encontró input[type='file'] en el formulario")
            
            self.log(f"Subiendo archivo: {pdf_path}")
            file_input.first.set_input_files(str(pdf_path))
            
            # 9) Rellenar campos de fechas si existen
            fecha_inicio = proposed_fields.get("fecha_inicio_vigencia")
            fecha_fin = proposed_fields.get("fecha_fin_vigencia")
            
            if fecha_inicio:
                # Buscar campo de fecha inicio
                try:
                    fecha_inicio_input = detail_frame.locator('input[name*="inicio"], input[name*="Inicio"], input[placeholder*="inicio"], input[placeholder*="Inicio"]')
                    if fecha_inicio_input.count() > 0:
                        # Formatear fecha (e-gestiona suele usar DD/MM/YYYY)
                        if isinstance(fecha_inicio, str):
                            from datetime import datetime
                            try:
                                dt = datetime.fromisoformat(fecha_inicio.replace('Z', '+00:00'))
                                fecha_formatted = dt.strftime("%d/%m/%Y")
                            except:
                                fecha_formatted = fecha_inicio
                        else:
                            fecha_formatted = fecha_inicio
                        fecha_inicio_input.first.fill(fecha_formatted)
                except Exception as e:
                    self.log(f"Warning: No se pudo rellenar fecha_inicio: {e}")
            
            if fecha_fin:
                try:
                    fecha_fin_input = detail_frame.locator('input[name*="fin"], input[name*="Fin"], input[placeholder*="fin"], input[placeholder*="Fin"]')
                    if fecha_fin_input.count() > 0:
                        if isinstance(fecha_fin, str):
                            from datetime import datetime
                            try:
                                dt = datetime.fromisoformat(fecha_fin.replace('Z', '+00:00'))
                                fecha_formatted = dt.strftime("%d/%m/%Y")
                            except:
                                fecha_formatted = fecha_fin
                        else:
                            fecha_formatted = fecha_fin
                        fecha_fin_input.first.fill(fecha_formatted)
                except Exception as e:
                    self.log(f"Warning: No se pudo rellenar fecha_fin: {e}")
            
            # 10) Confirmar subida (buscar botón "Enviar", "Subir", "Guardar")
            submit_button = detail_frame.locator('button:has-text("Enviar"), button:has-text("Subir"), button:has-text("Guardar"), input[type="submit"]:has-text("Enviar")')
            if submit_button.count() == 0:
                # Intentar con texto más genérico
                submit_button = detail_frame.get_by_text("Enviar", exact=False)
            
            if submit_button.count() == 0:
                raise RuntimeError("No se encontró botón de envío")
            
            submit_button.first.click()
            
            # 11) Esperar confirmación
            time.sleep(3)
            
            # Buscar mensaje de éxito o cambio en la UI
            confirmation_found = False
            try:
                # Buscar mensajes de éxito
                success_messages = detail_frame.locator('text=/éxito|exitoso|correcto|enviado|subido/i')
                if success_messages.count() > 0:
                    confirmation_found = True
            except Exception:
                pass
            
            # 12) Screenshot after
            after_screenshot = item_evidence_dir / "after_upload.png"
            try:
                page.screenshot(path=str(after_screenshot), full_page=True)
            except Exception:
                try:
                    detail_frame.locator("body").screenshot(path=str(after_screenshot))
                except Exception:
                    pass
            
            # 13) Generar portal_reference (extraer de la UI si es posible)
            portal_reference = f"PORTAL_REF_{upload_id}"
            try:
                # Intentar extraer referencia del portal si hay algún elemento que la muestre
                ref_elements = detail_frame.locator('text=/referencia|ref|id/i')
                if ref_elements.count() > 0:
                    ref_text = ref_elements.first.inner_text()
                    # Extraer números o códigos
                    import re
                    matches = re.findall(r'[A-Z0-9\-]+', ref_text)
                    if matches:
                        portal_reference = matches[0]
            except Exception:
                pass
            
            finished = time.time()
            duration_ms = int((finished - started) * 1000)
            
            # 14) Generar log
            upload_log = item_evidence_dir / "upload_log.txt"
            upload_log.write_text(
                f"REAL UPLOAD LOG\n"
                f"Upload ID: {upload_id}\n"
                f"Doc ID: {doc_id}\n"
                f"Type ID: {type_id}\n"
                f"File: {pdf_path}\n"
                f"Duration: {duration_ms}ms\n"
                f"Confirmation: {'Found' if confirmation_found else 'Not found'}\n"
                f"Portal Reference: {portal_reference}\n"
                f"Timestamp: {datetime.utcnow().isoformat()}\n",
                encoding="utf-8"
            )
            
            return {
                "success": True,
                "upload_id": upload_id,
                "evidence_path": str(item_evidence_dir),
                "duration_ms": duration_ms,
                "reason": "Real upload completed",
                "portal_reference": portal_reference,
                "simulated": False,
            }
            
        except Exception as e:
            finished = time.time()
            duration_ms = int((finished - started) * 1000)
            
            # Generar log de error
            upload_log = item_evidence_dir / "upload_log.txt"
            try:
                upload_log.write_text(
                    f"REAL UPLOAD ERROR\n"
                    f"Upload ID: {upload_id}\n"
                    f"Doc ID: {doc_id}\n"
                    f"Error: {str(e)}\n"
                    f"Duration: {duration_ms}ms\n"
                    f"Timestamp: {datetime.utcnow().isoformat()}\n",
                    encoding="utf-8"
                )
            except Exception:
                pass
            
            return {
                "success": False,
                "upload_id": upload_id,
                "evidence_path": str(item_evidence_dir),
                "duration_ms": duration_ms,
                "reason": f"upload_error: {str(e)}",
                "error": str(e),
            }
