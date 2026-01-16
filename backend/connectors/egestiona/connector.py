"""
Conector para e-gestiona (IMPLEMENTACIÓN REAL).

Sprint C2.12.2: Implementación end-to-end real con dry-run.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import date, datetime
from playwright.async_api import Page, Frame

from backend.connectors.base import BaseConnector
from backend.connectors.models import (
    RunContext,
    PendingRequirement,
    UploadResult,
)
from backend.connectors.egestiona.config_helpers import (
    get_platform_config,
    get_coordination,
    resolve_secret,
)
from backend.connectors.egestiona.selectors import (
    LOGIN_SELECTORS,
    POST_LOGIN_MARKER,
    PENDING_NAVIGATION,
    PENDING_GRID,
)
from backend.adapters.egestiona.grid_extract import (
    extract_dhtmlx_grid,
    canonicalize_row,
)
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.document_matcher_v1 import (
    DocumentMatcherV1,
    PendingItemV1,
)
from backend.config import DATA_DIR
from backend.shared.platforms_v1 import SelectorSpecV1


class EgestionaConnector(BaseConnector):
    """
    Conector para e-gestiona.
    
    Sprint C2.12.2: Implementación real con login, navegación, extracción y matching.
    """
    
    platform_id = "egestiona"
    
    def __init__(self, ctx: RunContext):
        super().__init__(ctx)
        # Cargar configuración de plataforma y coordination
        self.platform_config = None
        self.coordination = None
        self.credentials = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """Carga configuración de plataforma y coordination."""
        # Cargar platform config
        self.platform_config = get_platform_config(self.platform_id)
        if not self.platform_config:
            raise ValueError(f"Platform '{self.platform_id}' not found in configuration")
        
        # Cargar coordination (tenant_id es el label)
        if self.ctx.tenant_id:
            self.coordination = get_coordination(self.platform_config, self.ctx.tenant_id)
            if not self.coordination:
                raise ValueError(f"Coordination '{self.ctx.tenant_id}' not found in platform '{self.platform_id}'")
        else:
            # Usar primera coordination disponible
            if not self.platform_config.coordinations:
                raise ValueError(f"No coordinations found for platform '{self.platform_id}'")
            self.coordination = self.platform_config.coordinations[0]
        
        # Resolver credenciales
        client_code = (self.coordination.client_code or "").strip()
        username = (self.coordination.username or "").strip()
        password_ref = (self.coordination.password_ref or "").strip()
        
        if not password_ref:
            raise ValueError(f"password_ref not set for coordination '{self.coordination.label}'")
        
        password = resolve_secret(password_ref)
        if not password:
            raise ValueError(f"Secret '{password_ref}' not found in secrets store")
        
        self.credentials = {
            "client_code": client_code,
            "username": username,
            "password": password,
        }
        
        # Determinar URL de login
        if self.platform_config.login_url:
            self.login_url = self.platform_config.login_url
        elif self.coordination.url_override:
            self.login_url = self.coordination.url_override
        elif self.platform_config.base_url:
            self.login_url = self.platform_config.base_url
        else:
            raise ValueError(f"No login URL configured for platform '{self.platform_id}'")
    
    async def login(self, page: Page) -> None:
        """
        Login real usando Config → Platforms y Config → Secrets.
        
        PASO 2: Implementación real de login.
        """
        evidence_dir = Path(self.ctx.evidence_dir) if self.ctx.evidence_dir else Path(".")
        
        # Screenshot inicial
        await page.goto(self.login_url, wait_until="domcontentloaded", timeout=self.ctx.timeouts.get("navigation", 30000))
        await page.screenshot(path=str(evidence_dir / "01_login_page.png"), full_page=True)
        
        # Obtener selectores desde platform config
        login_fields = self.platform_config.login_fields
        client_sel = login_fields.client_code_selector
        username_sel = login_fields.username_selector
        password_sel = login_fields.password_selector
        submit_sel = login_fields.submit_selector
        
        if not all([client_sel, username_sel, password_sel, submit_sel]):
            raise ValueError("Login selectors not configured in platform config")
        
        # Rellenar formulario
        if login_fields.requires_client and self.credentials["client_code"]:
            # Resolver selector de client
            if client_sel.kind == "css":
                await page.locator(client_sel.value).fill(self.credentials["client_code"], timeout=self.ctx.timeouts.get("action", 10000))
            elif client_sel.kind == "xpath":
                await page.locator(f"xpath={client_sel.value}").fill(self.credentials["client_code"], timeout=self.ctx.timeouts.get("action", 10000))
        
        # Username
        if username_sel.kind == "css":
            await page.locator(username_sel.value).fill(self.credentials["username"], timeout=self.ctx.timeouts.get("action", 10000))
        elif username_sel.kind == "xpath":
            await page.locator(f"xpath={username_sel.value}").fill(self.credentials["username"], timeout=self.ctx.timeouts.get("action", 10000))
        
        # Password
        if password_sel.kind == "css":
            await page.locator(password_sel.value).fill(self.credentials["password"], timeout=self.ctx.timeouts.get("action", 10000))
        elif password_sel.kind == "xpath":
            await page.locator(f"xpath={password_sel.value}").fill(self.credentials["password"], timeout=self.ctx.timeouts.get("action", 10000))
        
        # Submit
        if submit_sel.kind == "css":
            await page.locator(submit_sel.value).click(timeout=self.ctx.timeouts.get("action", 10000))
        elif submit_sel.kind == "xpath":
            await page.locator(f"xpath={submit_sel.value}").click(timeout=self.ctx.timeouts.get("action", 10000))
        
        # Esperar post-login marker
        post_login_sel = self.coordination.post_login_selector
        if post_login_sel:
            if post_login_sel.kind == "css":
                await page.locator(post_login_sel.value).wait_for(state="visible", timeout=self.ctx.timeouts.get("navigation", 30000))
            elif post_login_sel.kind == "xpath":
                await page.locator(f"xpath={post_login_sel.value}").wait_for(state="visible", timeout=self.ctx.timeouts.get("navigation", 30000))
        else:
            # Fallback: esperar cambio de URL o network idle
            await page.wait_for_load_state("networkidle", timeout=self.ctx.timeouts.get("network_idle", 5000))
        
        # Screenshot post-login
        await page.screenshot(path=str(evidence_dir / "02_logged_in.png"), full_page=True)
        
        print(f"[egestiona] Login successful for coordination '{self.coordination.label}'")
        
        # Cerrar modales DHTMLX bloqueantes (comunicados prioritarios)
        try:
            from backend.connectors.egestiona.dhx_blockers import dismiss_all_dhx_blockers
            await page.wait_for_timeout(2000)  # Esperar a que aparezcan modales
            result = await dismiss_all_dhx_blockers(
                page,
                max_rounds=5,
                evidence_dir=evidence_dir,
            )
            if result["had_blocker"]:
                print(f"[egestiona] DHX blocker dismissed: {result['success']}, rounds: {result['rounds']}")
            else:
                print(f"[egestiona] No DHX blocker detected")
        except Exception as e:
            print(f"[egestiona] Warning: Error al cerrar modales DHTMLX: {e}")
            # Continuar de todas formas
    
    async def navigate_to_pending(self, page: Page) -> None:
        """
        Navegar a pendientes con manejo de frames/overlays.
        
        PASO 3: Implementación real de navegación.
        """
        evidence_dir = Path(self.ctx.evidence_dir) if self.ctx.evidence_dir else Path(".")
        
        # Cerrar modales DHTMLX bloqueantes si aparecen (best-effort)
        # Nota: Ya se cerraron después del login, pero por si acaso vuelven a aparecer
        try:
            from backend.connectors.egestiona.dhx_blockers import dismiss_all_dhx_blockers
            await page.wait_for_timeout(1000)
            result = await dismiss_all_dhx_blockers(
                page,
                max_rounds=3,  # Menos rounds aquí, ya se hizo después del login
                evidence_dir=evidence_dir,
            )
            if result["had_blocker"]:
                print(f"[egestiona] DHX blocker dismissed before navigation: {result['success']}")
        except Exception as e:
            print(f"[egestiona] Warning: Error al cerrar modales antes de navegar: {e}")
            # Continuar de todas formas
        
        # Navegar a pendientes usando helpers existentes
        # Nota: Los helpers existentes son sync, pero podemos adaptarlos
        # Por ahora, implementar navegación directa async
        
        # Esperar frame nm_contenido
        frame_dashboard = None
        for _ in range(100):  # 25 segundos máximo
            frame_dashboard = page.frame(name="nm_contenido")
            if frame_dashboard and frame_dashboard.url:
                break
            await page.wait_for_timeout(250)
        
        if not frame_dashboard:
            await page.screenshot(path=str(evidence_dir / "03_pending_error_no_frame.png"), full_page=True)
            raise RuntimeError("Frame nm_contenido not found")
        
        # Click en tile de pendientes
        # Estrategia: Intentar click normal, luego force, luego JavaScript directo
        tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
        tile = frame_dashboard.locator(tile_sel)
        tile_clicked = False
        
        if await tile.count() > 0:
            await tile.first.wait_for(state="visible", timeout=20000)
            try:
                await tile.first.click(timeout=20000)
                tile_clicked = True
                print(f"[egestiona] Click normal exitoso")
            except Exception:
                try:
                    # Si falla por overlay, intentar con force
                    print(f"[egestiona] Click normal falló, intentando con force=True")
                    await tile.first.click(timeout=20000, force=True)
                    tile_clicked = True
                except Exception:
                    # Si falla, ejecutar JavaScript directamente
                    print(f"[egestiona] Click falló, ejecutando Gestion(3) directamente")
                    try:
                        await frame_dashboard.evaluate("Gestion(3)")
                        tile_clicked = True
                    except Exception as e:
                        print(f"[egestiona] Error ejecutando Gestion(3): {e}")
        else:
            # Intentar por texto usando regex
            import re
            tile_by_text = frame_dashboard.locator('a.listado_link').filter(has_text=re.compile(r'pendiente|documentaci[oó]n', re.IGNORECASE))
            if await tile_by_text.count() > 0:
                try:
                    await tile_by_text.first.click(timeout=20000)
                    tile_clicked = True
                except Exception:
                    try:
                        print(f"[egestiona] Click normal falló, intentando con force=True")
                        await tile_by_text.first.click(timeout=20000, force=True)
                        tile_clicked = True
                    except Exception:
                        # Intentar JavaScript
                        try:
                            await frame_dashboard.evaluate("Gestion(3)")
                            tile_clicked = True
                        except Exception:
                            pass
        
        if not tile_clicked:
            raise RuntimeError("No se pudo hacer click en el tile de pendientes")
        
        # Esperar grid de pendientes - dar tiempo suficiente para que se cargue
        print(f"[egestiona] Esperando a que se cargue el grid de pendientes...")
        await page.wait_for_timeout(3000)  # Dar más tiempo para que cargue
        
        # Intentar click "Buscar" si existe (a veces es necesario)
        try:
            btn_buscar = frame_dashboard.get_by_text("Buscar", exact=True)
            if await btn_buscar.count() > 0:
                print(f"[egestiona] Click en botón Buscar")
                await btn_buscar.first.click(timeout=10000)
                await page.wait_for_timeout(2000)
        except Exception:
            pass
        
        # Buscar frame del grid con múltiples estrategias
        list_frame = None
        
        # Estrategia 1: Buscar frame f3
        for _ in range(80):  # 20 segundos máximo
            try:
                list_frame = page.frame(name="f3")
                if list_frame:
                    # Verificar que tiene grid
                    try:
                        grid_count = await list_frame.locator("table.obj.row20px").count()
                        if grid_count > 0:
                            print(f"[egestiona] Grid encontrado en frame f3 con {grid_count} tablas")
                            break
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Estrategia 2: Buscar por URL
            try:
                for fr in page.frames:
                    url = (fr.url or "").lower()
                    if ("buscador.asp" in url or "buscador.aspx" in url) and ("apartado_id=3" in url or "apartado=3" in url):
                        try:
                            grid_count = await fr.locator("table.obj.row20px").count()
                            if grid_count > 0:
                                list_frame = fr
                                print(f"[egestiona] Grid encontrado en frame por URL: {url}")
                                break
                        except Exception:
                            pass
                if list_frame:
                    break
            except Exception:
                pass
            
            # Estrategia 3: Buscar cualquier frame que tenga el grid
            try:
                for fr in page.frames:
                    if fr.name and fr.name.startswith("f"):
                        try:
                            grid_count = await fr.locator("table.obj.row20px").count()
                            if grid_count > 0:
                                list_frame = fr
                                print(f"[egestiona] Grid encontrado en frame {fr.name}")
                                break
                        except Exception:
                            pass
                if list_frame:
                    break
            except Exception:
                pass
            
            await page.wait_for_timeout(250)
        
        if not list_frame:
            # Intentar click "Buscar" si existe
            try:
                btn_buscar = frame_dashboard.get_by_text("Buscar", exact=True)
                if await btn_buscar.count() > 0:
                    print(f"[egestiona] Click en botón Buscar")
                    await btn_buscar.first.click(timeout=10000)
                    await page.wait_for_timeout(2000)
                    # Reintentar encontrar grid
                    for _ in range(80):
                        try:
                            list_frame = page.frame(name="f3")
                            if list_frame:
                                try:
                                    grid_count = await list_frame.locator("table.obj.row20px").count()
                                    if grid_count > 0:
                                        break
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        await page.wait_for_timeout(250)
            except Exception as e:
                print(f"[egestiona] No se pudo clickear Buscar: {e}")
        
        if not list_frame:
            await page.screenshot(path=str(evidence_dir / "03_pending_error_no_grid.png"), full_page=True)
            # Listar todos los frames disponibles para debug
            frames_info = []
            for fr in page.frames:
                frames_info.append(f"  - {fr.name or 'unnamed'}: {fr.url}")
            print(f"[egestiona] Frames disponibles:\n" + "\n".join(frames_info))
            raise RuntimeError("Grid frame not found")
        
        # Esperar a que el grid esté completamente cargado
        await list_frame.locator("table.hdr").first.wait_for(state="attached", timeout=15000)
        await list_frame.locator("table.obj.row20px").first.wait_for(state="attached", timeout=15000)
        
        # Screenshot de pendientes
        try:
            await list_frame.locator("body").screenshot(path=str(evidence_dir / "03_pending_view.png"))
        except Exception:
            await page.screenshot(path=str(evidence_dir / "03_pending_view.png"), full_page=True)
        
        print(f"[egestiona] Navigated to pending documents")
    
    async def extract_pending(self, page: Page) -> List[PendingRequirement]:
        """
        Extraer pendientes reales (máx 20) → PendingRequirement.
        
        PASO 4: Implementación real de extracción.
        """
        evidence_dir = Path(self.ctx.evidence_dir) if self.ctx.evidence_dir else Path(".")
        
        # Buscar frame del grid
        list_frame = None
        for fr in page.frames:
            if fr.name == "f3":
                list_frame = fr
                break
            url = (fr.url or "").lower()
            if "buscador.asp" in url and "apartado_id=3" in url:
                list_frame = fr
                break
        
        if not list_frame:
            raise RuntimeError("Grid frame not found for extraction")
        
        # Extraer grid usando función existente
        extracted = await list_frame.evaluate("""() => {
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
  function extractRowsFromObjTable(obj, headers){
    const rows = Array.from(obj.querySelectorAll('tbody tr'));
    return rows.map(tr => {
      const cells = Array.from(tr.querySelectorAll('td'));
      const row = {};
      headers.forEach((h, i) => {
        if(cells[i]) row[h] = norm(cells[i].innerText);
      });
      return row;
    });
  }
  const hdrTables = Array.from(document.querySelectorAll('table.hdr'));
  const objTables = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!hdrTables.length || !objTables.length) return {headers:[], rows:[]};
  const bestHdr = hdrTables[0];
  const headers = headersFromHdrTable(bestHdr);
  let bestObj = null;
  let bestRows = [];
  for(const t of objTables){
    const rs = extractRowsFromObjTable(t, headers);
    if(rs.length > bestRows.length){
      bestObj = t;
      bestRows = rs;
    }
  }
  return {headers, rows: bestRows};
}""")
        
        raw_rows = extracted.get("rows", [])
        
        # Limitar a máximo 20
        raw_rows = raw_rows[:20]
        
        # Convertir a PendingRequirement
        requirements = []
        
        def _parse_date(date_str: str) -> Optional[str]:
            """Intenta parsear una fecha."""
            if not date_str or date_str.strip() == "-":
                return None
            # Intentar formatos comunes
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return None
        
        for idx, row in enumerate(raw_rows):
            # Canonicalizar fila
            canon = canonicalize_row(row)
            
            tipo_doc = canon.get("tipo_doc") or ""
            elemento = canon.get("elemento") or ""
            empresa = canon.get("empresa") or ""
            estado_raw = canon.get("estado") or ""
            inicio = canon.get("inicio")
            fin = canon.get("fin")
            
            # Determinar subject_type
            # Si hay elemento (trabajador), es trabajador; si no, empresa
            subject_type = "trabajador" if elemento else "empresa"
            subject_id = elemento if elemento else empresa
            
            # Determinar status
            estado_lower = estado_raw.lower() if estado_raw else ""
            if "vencido" in estado_lower or "expired" in estado_lower:
                status = "expired"
            elif "venciéndose" in estado_lower or "expiring" in estado_lower:
                status = "expiring"
            elif "solicitado" in estado_lower or "requested" in estado_lower:
                status = "requested"
            else:
                status = "missing"
            
            # Extraer periodo si hay fechas
            period = None
            if inicio:
                try:
                    # Intentar parsear inicio para extraer YYYY-MM
                    dt = datetime.strptime(inicio.strip(), "%d/%m/%Y")
                    period = dt.strftime("%Y-%m")
                except Exception:
                    pass
            
            # Due date (usar fin si existe)
            due_date = _parse_date(fin) if fin else None
            
            # Crear ID determinista
            req_id = PendingRequirement.create_id(
                platform_id=self.platform_id,
                subject_type=subject_type,
                doc_type_hint=tipo_doc,
                subject_id=subject_id,
                period=period,
            )
            
            # Portal meta
            portal_meta = {
                "row_index": idx,
                "tipo_doc": tipo_doc,
                "elemento": elemento,
                "empresa": empresa,
                "estado": estado_raw,
                "inicio": inicio,
                "fin": fin,
                "raw_row": row,
            }
            
            req = PendingRequirement(
                id=req_id,
                subject_type=subject_type,
                doc_type_hint=tipo_doc,
                subject_id=subject_id,
                period=period,
                due_date=due_date,
                status=status,
                portal_meta=portal_meta,
            )
            
            requirements.append(req)
        
        # Guardar evidence
        reqs_data = [
            {
                "id": req.id,
                "subject_type": req.subject_type,
                "subject_id": req.subject_id,
                "doc_type_hint": req.doc_type_hint,
                "period": req.period,
                "due_date": req.due_date,
                "status": req.status,
                "portal_meta": req.portal_meta,
            }
            for req in requirements
        ]
        
        if requirements:
            with open(evidence_dir / "pending_extracted.json", "w", encoding="utf-8") as f:
                json.dump(reqs_data, f, indent=2, ensure_ascii=False)
            await page.screenshot(path=str(evidence_dir / "04_pending_extracted.png"), full_page=True)
        else:
            with open(evidence_dir / "pending_empty.json", "w", encoding="utf-8") as f:
                json.dump({"message": "No pending requirements found"}, f, indent=2)
            await page.screenshot(path=str(evidence_dir / "04_pending_empty.png"), full_page=True)
        
        print(f"[egestiona] Extracted {len(requirements)} pending requirements")
        return requirements
    
    async def match_repository(
        self,
        reqs: List[PendingRequirement]
    ) -> Dict[str, Dict]:
        """
        Match con repositorio usando DocumentMatcherV1 completo.
        
        PASO 5: Implementación real de matching.
        
        Returns:
            Dict mapping requirement_id -> {
                "requirement": {...},
                "matched_type_id": "...|null",
                "candidate_docs": [...],
                "decision": "match|no_match",
                "chosen_doc_id": "...|null",
                "decision_reason": "..."
            }
        """
        if not reqs:
            return {}
        
        evidence_dir = Path(self.ctx.evidence_dir) if self.ctx.evidence_dir else Path(".")
        
        # Inicializar matcher
        store = DocumentRepositoryStoreV1(base_dir=DATA_DIR)
        matcher = DocumentMatcherV1(store, base_dir=DATA_DIR)
        
        match_results = {}
        
        for req in reqs:
            # Convertir PendingRequirement a PendingItemV1
            # Parsear fechas si existen
            fecha_inicio = None
            fecha_fin = None
            if req.period:
                try:
                    year, month = req.period.split("-")
                    fecha_inicio = date(int(year), int(month), 1)
                except Exception:
                    pass
            if req.due_date:
                try:
                    fecha_fin = datetime.strptime(req.due_date, "%Y-%m-%d").date()
                except Exception:
                    pass
            
            pending_item = PendingItemV1(
                tipo_doc=req.doc_type_hint,
                elemento=req.subject_id if req.subject_type == "trabajador" else None,
                empresa=req.subject_id if req.subject_type == "empresa" else None,
                trabajador=req.subject_id if req.subject_type == "trabajador" else None,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                raw_data=req.portal_meta,
            )
            
            # Hacer matching
            # Necesitamos company_key y person_key para el matcher
            # Intentar extraer desde subject_id o usar valores por defecto
            company_key = None
            person_key = None
            
            if req.subject_type == "empresa":
                company_key = req.subject_id
            elif req.subject_type == "trabajador":
                person_key = req.subject_id
                # Intentar extraer empresa desde portal_meta
                empresa = req.portal_meta.get("empresa")
                if empresa:
                    company_key = empresa
            
            match_result = matcher.match_pending_item(
                pending=pending_item,
                company_key=company_key or "",
                person_key=person_key,
                platform_key=self.platform_id,
                coord_label=self.coordination.label if self.coordination else None,
                evidence_dir=evidence_dir,
            )
            
            # Procesar resultado
            best_doc = match_result.get("best_doc")
            matched_type_id = None
            chosen_doc_id = None
            decision = "no_match"
            decision_reason = ""
            candidate_docs = []
            
            if best_doc:
                matched_type_id = best_doc.get("type_id")
                chosen_doc_id = best_doc.get("doc_id")
                decision = "match"
                decision_reason = f"Matched with confidence {best_doc.get('score', 0):.2f}. Reasons: {', '.join(best_doc.get('reasons', []))}"
            else:
                decision_reason = match_result.get("reasons", ["No matching document found"])
                if isinstance(decision_reason, list):
                    decision_reason = "; ".join(decision_reason)
            
            # Añadir alternativas como candidatos
            alternatives = match_result.get("alternatives", [])
            for alt in alternatives:
                candidate_docs.append({
                    "doc_id": alt.get("doc_id"),
                    "score": alt.get("score", 0),
                    "reason": ", ".join(alt.get("reasons", [])),
                })
            
            match_results[req.id] = {
                "requirement": {
                    "id": req.id,
                    "subject_type": req.subject_type,
                    "subject_id": req.subject_id,
                    "doc_type_hint": req.doc_type_hint,
                    "period": req.period,
                    "due_date": req.due_date,
                    "status": req.status,
                },
                "matched_type_id": matched_type_id,
                "candidate_docs": candidate_docs,
                "decision": decision,
                "chosen_doc_id": chosen_doc_id,
                "decision_reason": decision_reason,
            }
        
        # Guardar evidence
        with open(evidence_dir / "match_results.json", "w", encoding="utf-8") as f:
            json.dump(match_results, f, indent=2, ensure_ascii=False)
        
        print(f"[egestiona] Matched {len([r for r in match_results.values() if r['decision'] == 'match'])}/{len(reqs)} requirements")
        return match_results
    
    async def upload_one(
        self,
        page: Page,
        req: PendingRequirement,
        doc_id: str
    ) -> UploadResult:
        """
        Upload stub: en dry-run no se sube nada.
        
        PASO 6: En dry-run, este método no debe ser llamado.
        """
        evidence_dir = Path(self.ctx.evidence_dir) if self.ctx.evidence_dir else Path(".")
        
        # Screenshot antes de "subir"
        screenshot_path = evidence_dir / f"upload_stub_{req.id[:8]}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        
        print(f"[egestiona] upload_one called (dry_run={self.ctx.dry_run}) - req={req.id}, doc={doc_id}")
        
        return UploadResult(
            success=False,
            requirement_id=req.id,
            uploaded_doc_id=doc_id,
            error="upload not implemented in dry-run mode",
            evidence={"screenshot": str(screenshot_path)},
        )
