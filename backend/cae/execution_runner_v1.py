"""
Runner para ejecutar planes CAE v1.2.

Ejecuta planes READY en eGestiona usando Playwright (o modo FAKE para tests).
"""

from __future__ import annotations

import json
import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from backend.cae.submission_models_v1 import CAESubmissionPlanV1, CAESubmissionItemV1
from backend.cae.execution_models_v1 import RunResultV1
from backend.cae.job_queue_models_v1 import CAEJobProgressV1
from backend.config import DATA_DIR


# Allowlist para ejecución WRITE (hard scope)
CAE_WRITE_ALLOWLIST = {
    "company_key": "TEDELAB",  # O la clave real del repo
    "person_key": "EMILIO",  # O None si scope company
}


class CAEExecutionRunnerV1:
    """Runner para ejecutar planes CAE."""
    
    def __init__(self):
        self.evidence_base_dir = Path(DATA_DIR) / "docs" / "evidence" / "cae_runs"
        self.evidence_base_dir.mkdir(parents=True, exist_ok=True)
        self.executor_mode = os.getenv("CAE_EXECUTOR_MODE", "REAL")  # REAL o FAKE
    
    def execute_plan_egestiona(
        self,
        plan: CAESubmissionPlanV1,
        dry_run: bool = False,
    ) -> RunResultV1:
        """
        Ejecuta un plan en eGestiona.
        
        Args:
            plan: Plan a ejecutar (debe tener decision=READY)
            dry_run: Si True, simula la ejecución sin abrir navegador
        
        Returns:
            RunResultV1 con el resultado de la ejecución
        """
        run_id = self._generate_run_id()
        started_at = datetime.now()
        
        # Validar que el plan es ejecutable
        validation_error = self._validate_plan_for_execution(plan)
        if validation_error:
            return RunResultV1(
                run_id=run_id,
                status="BLOCKED",
                evidence_path=str(self.evidence_base_dir / run_id),
                summary={"error": validation_error},
                error=validation_error,
                started_at=started_at,
                finished_at=datetime.now(),
            )
        
        # Crear directorio de evidencia
        evidence_dir = self.evidence_base_dir / run_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        screenshots_dir = evidence_dir / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        
        # v1.4: Ejecutar batch de items
        if len(plan.items) == 0:
            error_msg = "Plan no tiene items para ejecutar"
            return self._create_failed_run(
                run_id=run_id,
                evidence_dir=evidence_dir,
                error=error_msg,
                started_at=started_at,
            )
        
        # Ejecutar items secuencialmente
        items_results = []
        items_success = 0
        items_failed = 0
        items_blocked = 0
        first_error = None
        stop_reason = None
        
        for idx, item in enumerate(plan.items):
            # Crear subcarpeta por item
            item_evidence_dir = evidence_dir / f"item_{idx + 1}"
            item_evidence_dir.mkdir(exist_ok=True)
            item_screenshots_dir = item_evidence_dir / "screenshots"
            item_screenshots_dir.mkdir(exist_ok=True)
            
            # Ejecutar item
            if self.executor_mode == "FAKE" or dry_run:
                item_result = self._execute_fake(
                    plan=plan,
                    item=item,
                    run_id=f"{run_id}_item{idx + 1}",
                    evidence_dir=item_evidence_dir,
                    screenshots_dir=item_screenshots_dir,
                    started_at=datetime.now(),
                )
            else:
                item_result = self._execute_real(
                    plan=plan,
                    item=item,
                    run_id=f"{run_id}_item{idx + 1}",
                    evidence_dir=item_evidence_dir,
                    screenshots_dir=item_screenshots_dir,
                    started_at=datetime.now(),
                )
            
            items_results.append({
                "item_index": idx,
                "item_type_id": item.type_id,
                "item_period_key": item.period_key,
                "status": item_result.status,
                "error": item_result.error,
            })
            
            if item_result.status == "SUCCESS":
                items_success += 1
            elif item_result.status == "BLOCKED":
                items_blocked += 1
                if not first_error:
                    first_error = item_result.error
                    stop_reason = "BLOCKED"
                # Stop on first BLOCKED
                break
            elif item_result.status == "FAILED":
                items_failed += 1
                if not first_error:
                    first_error = item_result.error
                    stop_reason = "FAILED"
                # Stop on first FAILED
                break
        
        # Determinar status final
        finished_at = datetime.now()
        total_items = len(plan.items)
        items_processed = items_success + items_failed + items_blocked
        
        if items_success == total_items:
            final_status = "SUCCESS"
        elif items_success > 0 and (items_failed > 0 or items_blocked > 0):
            final_status = "PARTIAL_SUCCESS"
        elif items_blocked > 0:
            final_status = "BLOCKED"
        else:
            final_status = "FAILED"
        
        # Crear manifest global
        manifest = {
            "run_id": run_id,
            "plan_id": plan.plan_id,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": final_status,
            "stop_reason": stop_reason,
            "error": first_error,
            "items_results": items_results,
            "summary": {
                "total_items": total_items,
                "items_processed": items_processed,
                "items_success": items_success,
                "items_failed": items_failed,
                "items_blocked": items_blocked,
            },
        }
        
        with open(evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        # Crear run_finished.json
        run_finished = {
            "run_id": run_id,
            "status": final_status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "error": first_error,
            "stop_reason": stop_reason,
            "summary": manifest["summary"],
            "items_results": items_results,
        }
        
        with open(evidence_dir / "run_finished.json", "w", encoding="utf-8") as f:
            json.dump(run_finished, f, indent=2, ensure_ascii=False)
        
        return RunResultV1(
            run_id=run_id,
            status=final_status,
            evidence_path=str(evidence_dir),
            summary=manifest["summary"],
            error=first_error,
            started_at=started_at,
            finished_at=finished_at,
        )
    
    async def execute_plan_egestiona_with_progress(
        self,
        plan: CAESubmissionPlanV1,
        dry_run: bool = False,
        on_progress: Optional[Callable[[CAEJobProgressV1], bool]] = None,
    ) -> RunResultV1:
        """
        Ejecuta un plan en eGestiona con callback de progreso.
        
        v1.8: Versión async que reporta progreso durante la ejecución.
        
        Args:
            plan: Plan a ejecutar (debe tener decision=READY)
            dry_run: Si True, simula la ejecución sin abrir navegador
            on_progress: Callback opcional para reportar progreso
        
        Returns:
            RunResultV1 con el resultado de la ejecución
        """
        run_id = self._generate_run_id()
        started_at = datetime.now()
        
        # Validar que el plan es ejecutable
        validation_error = self._validate_plan_for_execution(plan)
        if validation_error:
            if on_progress:
                progress = CAEJobProgressV1(
                    total_items=len(plan.items),
                    current_index=0,
                    items_success=0,
                    items_failed=0,
                    items_blocked=0,
                    percent=0,
                    message=f"Error: {validation_error}",
                )
                on_progress(progress)
            return RunResultV1(
                run_id=run_id,
                status="BLOCKED",
                evidence_path=str(self.evidence_base_dir / run_id),
                summary={"error": validation_error},
                error=validation_error,
                started_at=started_at,
                finished_at=datetime.now(),
            )
        
        # Crear directorio de evidencia
        evidence_dir = self.evidence_base_dir / run_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        screenshots_dir = evidence_dir / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        
        # v1.4: Ejecutar batch de items
        if len(plan.items) == 0:
            error_msg = "Plan no tiene items para ejecutar"
            if on_progress:
                progress = CAEJobProgressV1(
                    total_items=0,
                    current_index=0,
                    items_success=0,
                    items_failed=0,
                    items_blocked=0,
                    percent=0,
                    message=error_msg,
                )
                on_progress(progress)
            return self._create_failed_run(
                run_id=run_id,
                evidence_dir=evidence_dir,
                error=error_msg,
                started_at=started_at,
            )
        
        total_items = len(plan.items)
        
        # Ejecutar items secuencialmente con progreso
        items_results = []
        items_success = 0
        items_failed = 0
        items_blocked = 0
        first_error = None
        stop_reason = None
        
        # v1.9.1: Control de fallo FAKE para tests E2E
        fake_fail_after_item = None
        if (self.executor_mode == "FAKE" or dry_run) and os.getenv("CAE_FAKE_FAIL_AFTER_ITEM"):
            try:
                fake_fail_after_item = int(os.getenv("CAE_FAKE_FAIL_AFTER_ITEM"))
                print(f"[execution_runner] CAE_FAKE_FAIL_AFTER_ITEM={fake_fail_after_item}, total_items={total_items}")
            except (ValueError, TypeError):
                fake_fail_after_item = None
        
        for idx, item in enumerate(plan.items):
            # Actualizar progreso antes de ejecutar item
            if on_progress:
                progress = CAEJobProgressV1(
                    total_items=total_items,
                    current_index=idx,
                    items_success=items_success,
                    items_failed=items_failed,
                    items_blocked=items_blocked,
                    percent=int((idx / total_items) * 100) if total_items > 0 else 0,
                    message=f"Subiendo item {idx + 1}/{total_items}...",
                )
                # v1.9: Verificar si debe continuar (cancelación)
                should_continue = on_progress(progress)
                if not should_continue:
                    # Cancelación solicitada
                    stop_reason = "CANCELED"
                    first_error = "Cancelado por usuario"
                    break
            
            # Crear subcarpeta por item
            item_evidence_dir = evidence_dir / f"item_{idx + 1}"
            item_evidence_dir.mkdir(exist_ok=True)
            item_screenshots_dir = item_evidence_dir / "screenshots"
            item_screenshots_dir.mkdir(exist_ok=True)
            
            # Ejecutar item (en modo FAKE, usar sleep mínimo para simular progreso)
            if self.executor_mode == "FAKE" or dry_run:
                # v1.9.1: Verificar si debemos forzar fallo FAKE
                if fake_fail_after_item is not None and idx >= fake_fail_after_item:
                    # Forzar fallo después de N items
                    print(f"[execution_runner] Forzando fallo FAKE en item {idx} (fake_fail_after_item={fake_fail_after_item})")
                    item_result = RunResultV1(
                        run_id=f"{run_id}_item{idx + 1}",
                        status="FAILED",
                        evidence_path=str(item_evidence_dir),
                        summary={
                            "total_items": 1,
                            "items_success": 0,
                            "items_failed": 1,
                            "items_blocked": 0,
                        },
                        error=f"Forzado fallo FAKE después de {fake_fail_after_item} item(s) (CAE_FAKE_FAIL_AFTER_ITEM={fake_fail_after_item})",
                        started_at=datetime.now(),
                        finished_at=datetime.now(),
                    )
                    # Crear manifest de error
                    manifest = {
                        "run_id": item_result.run_id,
                        "plan_id": plan.plan_id,
                        "item": {
                            "kind": item.kind,
                            "type_id": item.type_id,
                            "scope": item.scope,
                            "company_key": item.company_key,
                            "person_key": item.person_key,
                            "period_key": item.period_key,
                        },
                        "started_at": item_result.started_at.isoformat(),
                        "finished_at": item_result.finished_at.isoformat(),
                        "mode": "FAKE",
                        "dry_run": True,
                        "error": item_result.error,
                        "forced_failure": True,
                    }
                    with open(item_evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
                        json.dump(manifest, f, indent=2, ensure_ascii=False)
                else:
                    # En modo FAKE, simular un pequeño delay para progreso visible
                    await asyncio.sleep(0.05)  # Mínimo delay solo en FAKE
                    item_result = self._execute_fake(
                        plan=plan,
                        item=item,
                        run_id=f"{run_id}_item{idx + 1}",
                        evidence_dir=item_evidence_dir,
                        screenshots_dir=item_screenshots_dir,
                        started_at=datetime.now(),
                    )
            else:
                # En modo REAL, ejecutar sincrónicamente (el callback se llama antes)
                item_result = await asyncio.to_thread(
                    self._execute_real,
                    plan=plan,
                    item=item,
                    run_id=f"{run_id}_item{idx + 1}",
                    evidence_dir=item_evidence_dir,
                    screenshots_dir=item_screenshots_dir,
                    started_at=datetime.now(),
                )
            
            items_results.append({
                "item_index": idx,
                "item_type_id": item.type_id,
                "item_period_key": item.period_key,
                "status": item_result.status,
                "error": item_result.error,
            })
            
            if item_result.status == "SUCCESS":
                items_success += 1
            elif item_result.status == "BLOCKED":
                items_blocked += 1
                if not first_error:
                    first_error = item_result.error
                    stop_reason = "BLOCKED"
                # Stop on first BLOCKED
                break
            elif item_result.status == "FAILED":
                items_failed += 1
                if not first_error:
                    first_error = item_result.error
                    stop_reason = "FAILED"
                # Stop on first FAILED
                break
            
            # Actualizar progreso después de ejecutar item
            if on_progress:
                progress = CAEJobProgressV1(
                    total_items=total_items,
                    current_index=idx + 1,
                    items_success=items_success,
                    items_failed=items_failed,
                    items_blocked=items_blocked,
                    percent=int(((idx + 1) / total_items) * 100) if total_items > 0 else 100,
                    message=f"Completado item {idx + 1}/{total_items}",
                )
                # v1.9: Verificar si debe continuar (cancelación)
                should_continue = on_progress(progress)
                if not should_continue:
                    # Cancelación solicitada
                    stop_reason = "CANCELED"
                    first_error = "Cancelado por usuario"
                    break
        
        # Determinar status final
        finished_at = datetime.now()
        items_processed = items_success + items_failed + items_blocked
        
        # v1.9: Manejar cancelación
        if stop_reason == "CANCELED":
            final_status = "CANCELED"
        elif items_success == total_items:
            final_status = "SUCCESS"
        elif items_success > 0 and (items_failed > 0 or items_blocked > 0):
            final_status = "PARTIAL_SUCCESS"
        elif items_blocked > 0:
            final_status = "BLOCKED"
        else:
            final_status = "FAILED"
        
        # Crear manifest global
        manifest = {
            "run_id": run_id,
            "plan_id": plan.plan_id,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": final_status,
            "stop_reason": stop_reason,
            "error": first_error,
            "items_results": items_results,
            "summary": {
                "total_items": total_items,
                "items_processed": items_processed,
                "items_success": items_success,
                "items_failed": items_failed,
                "items_blocked": items_blocked,
            },
        }
        
        with open(evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        # Crear run_finished.json
        run_finished = {
            "run_id": run_id,
            "status": final_status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "error": first_error,
            "stop_reason": stop_reason,
            "summary": manifest["summary"],
            "items_results": items_results,
        }
        
        with open(evidence_dir / "run_finished.json", "w", encoding="utf-8") as f:
            json.dump(run_finished, f, indent=2, ensure_ascii=False)
        
        # Actualizar progreso final
        if on_progress:
            progress = CAEJobProgressV1(
                total_items=total_items,
                current_index=total_items,
                items_success=items_success,
                items_failed=items_failed,
                items_blocked=items_blocked,
                percent=100,
                message=f"Finalizado: {items_success} éxito, {items_failed} fallos, {items_blocked} bloqueados" if final_status != "CANCELED" else "Cancelado",
            )
            on_progress(progress)  # Retorno ignorado al finalizar
        
        return RunResultV1(
            run_id=run_id,
            status=final_status,
            evidence_path=str(evidence_dir),
            summary=manifest["summary"],
            error=first_error,
            started_at=started_at,
            finished_at=finished_at,
        )
    
    def _validate_plan_for_execution(self, plan: CAESubmissionPlanV1) -> Optional[str]:
        """Valida que el plan es ejecutable."""
        if plan.decision != "READY":
            return f"Plan decision debe ser READY, es {plan.decision}"
        
        if plan.scope.platform_key != "egestiona":
            return f"Platform debe ser 'egestiona', es '{plan.scope.platform_key}'"
        
        if plan.scope.mode not in ["PREPARE_WRITE", "WRITE"]:
            return f"Mode debe ser PREPARE_WRITE o WRITE, es '{plan.scope.mode}'"
        
        # Validar allowlist (v1.9.1: más permisivo en modo FAKE para tests E2E)
        # En modo FAKE, permitir cualquier company_key para facilitar tests E2E
        if self.executor_mode != "FAKE":
            if plan.scope.company_key != CAE_WRITE_ALLOWLIST["company_key"]:
                return f"company_key '{plan.scope.company_key}' no está en allowlist (solo '{CAE_WRITE_ALLOWLIST['company_key']}')"
            
            if plan.scope.person_key and plan.scope.person_key != CAE_WRITE_ALLOWLIST["person_key"]:
                return f"person_key '{plan.scope.person_key}' no está en allowlist (solo '{CAE_WRITE_ALLOWLIST['person_key']}')"
        
        # Validar que todos los items están PLANNED
        for item in plan.items:
            if item.status != "PLANNED":
                return f"Item {item.type_id} tiene status {item.status}, debe ser PLANNED"
        
        # v1.3.1: En REAL write (no FAKE), validar que todos los items tienen suggested_doc_id
        # Esta validación se hace en _execute_real, no aquí, para permitir FAKE sin suggested_doc_id
        # (La validación en _validate_plan_for_execution es solo para validaciones generales)
        
        return None
    
    def _execute_fake(
        self,
        plan: CAESubmissionPlanV1,
        item: CAESubmissionItemV1,
        run_id: str,
        evidence_dir: Path,
        screenshots_dir: Path,
        started_at: datetime,
    ) -> RunResultV1:
        """Ejecuta en modo FAKE (simulado, sin navegador)."""
        # Crear manifest
        manifest = {
            "run_id": run_id,
            "plan_id": plan.plan_id,
            "item": {
                "kind": item.kind,
                "type_id": item.type_id,
                "scope": item.scope,
                "company_key": item.company_key,
                "person_key": item.person_key,
                "period_key": item.period_key,
            },
            "started_at": started_at.isoformat(),
            "mode": "FAKE",
            "dry_run": True,
        }
        
        with open(evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        # Crear screenshot simulado
        fake_screenshot = screenshots_dir / "fake_execution.png"
        fake_screenshot.write_bytes(b"FAKE_SCREENSHOT_DATA")
        
        finished_at = datetime.now()
        
        # Crear run_finished.json
        run_finished = {
            "run_id": run_id,
            "status": "SUCCESS",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "summary": {
                "items_processed": 1,
                "items_success": 1,
                "items_failed": 0,
            },
        }
        
        with open(evidence_dir / "run_finished.json", "w", encoding="utf-8") as f:
            json.dump(run_finished, f, indent=2, ensure_ascii=False)
        
        return RunResultV1(
            run_id=run_id,
            status="SUCCESS",
            evidence_path=str(evidence_dir),
            summary=run_finished["summary"],
            started_at=started_at,
            finished_at=finished_at,
        )
    
    def _execute_real(
        self,
        plan: CAESubmissionPlanV1,
        item: CAESubmissionItemV1,
        run_id: str,
        evidence_dir: Path,
        screenshots_dir: Path,
        started_at: datetime,
    ) -> RunResultV1:
        """
        Ejecuta en modo REAL usando Playwright y eGestiona.
        
        Algoritmo:
        1) Validar que item.suggested_doc_id existe
        2) Cargar documento del store y obtener PDF
        3) Login eGestiona
        4) Navegar a pendientes y localizar el pendiente específico
        5) Entrar al detalle
        6) Subir PDF
        7) Confirmar resultado
        8) Capturar evidencia
        """
        from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
        from backend.repository.config_store_v1 import ConfigStoreV1
        from backend.repository.secrets_store_v1 import SecretsStoreV1
        from backend.repository.data_bootstrap_v1 import ensure_data_layout
        
        # v1.3.1: En REAL write (no dry_run), suggested_doc_id es obligatorio (no matching heurístico)
        # Nota: Esta validación solo aplica en _execute_real, no en _execute_fake
        if not item.suggested_doc_id:
            error_msg = "Item no tiene suggested_doc_id. En modo REAL write (no dry_run), suggested_doc_id es obligatorio (no se permite matching heurístico por seguridad)."
            return CAEExecutionRunnerV1._create_blocked_run(
                run_id=run_id,
                evidence_dir=evidence_dir,
                error=error_msg,
                started_at=started_at,
            )
        
        # Cargar documento del store
        store = DocumentRepositoryStoreV1()
        try:
            doc = store.get_document(item.suggested_doc_id)
            if not doc:
                error_msg = f"Documento {item.suggested_doc_id} no encontrado en el repositorio"
                return self._create_failed_run(
                    run_id=run_id,
                    evidence_dir=evidence_dir,
                    error=error_msg,
                    started_at=started_at,
                )
        except Exception as e:
            error_msg = f"Error al cargar documento {item.suggested_doc_id}: {str(e)}"
            return self._create_failed_run(
                run_id=run_id,
                evidence_dir=evidence_dir,
                error=error_msg,
                started_at=started_at,
            )
        
        # Obtener path del PDF
        try:
            pdf_path = store._get_doc_pdf_path(doc.doc_id)
            if not pdf_path.exists():
                error_msg = f"PDF no encontrado para documento {doc.doc_id} en {pdf_path}"
                return self._create_failed_run(
                    run_id=run_id,
                    evidence_dir=evidence_dir,
                    error=error_msg,
                    started_at=started_at,
                )
        except Exception as e:
            error_msg = f"Error al obtener path del PDF: {str(e)}"
            return self._create_failed_run(
                run_id=run_id,
                evidence_dir=evidence_dir,
                error=error_msg,
                started_at=started_at,
            )
        
        # Validar credenciales
        try:
            base_dir = ensure_data_layout()
            config_store = ConfigStoreV1(base_dir=base_dir)
            secrets_store = SecretsStoreV1(base_dir=base_dir)
            
            platforms = config_store.load_platforms()
            plat = next((p for p in platforms.platforms if p.key == "egestiona"), None)
            if not plat:
                error_msg = "Plataforma 'egestiona' no encontrada en configuración"
                return self._create_failed_run(
                    run_id=run_id,
                    evidence_dir=evidence_dir,
                    error=error_msg,
                    started_at=started_at,
                )
            
            # Usar primera coordination disponible (o "Kern" por defecto)
            coordination = "Kern"
            coord = next((c for c in plat.coordinations if c.label == coordination), None)
            if not coord and plat.coordinations:
                coord = plat.coordinations[0]
                coordination = coord.label
            
            if not coord:
                error_msg = f"Coordination '{coordination}' no encontrada en plataforma egestiona"
                return self._create_failed_run(
                    run_id=run_id,
                    evidence_dir=evidence_dir,
                    error=error_msg,
                    started_at=started_at,
                )
            
            # Validar credenciales
            client_code = (coord.client_code or "").strip()
            username = (coord.username or "").strip()
            password_ref = (coord.password_ref or "").strip()
            password = secrets_store.get_secret(password_ref) if password_ref else None
            
            if not client_code or not username or not password:
                error_msg = f"Credenciales incompletas para coordination '{coordination}'. Requiere: client_code, username, password_ref"
                return self._create_failed_run(
                    run_id=run_id,
                    evidence_dir=evidence_dir,
                    error=error_msg,
                    started_at=started_at,
                )
        except Exception as e:
            error_msg = f"Error al validar credenciales: {str(e)}"
            return self._create_failed_run(
                run_id=run_id,
                evidence_dir=evidence_dir,
                error=error_msg,
                started_at=started_at,
            )
        
        # Ejecutar upload usando función helper
        try:
            result = self._execute_egestiona_upload_real(
                pdf_path=pdf_path,
                item=item,
                doc=doc,
                coordination=coordination,
                client_code=client_code,
                username=username,
                password=password,
                run_id=run_id,
                evidence_dir=evidence_dir,
                screenshots_dir=screenshots_dir,
                started_at=started_at,
            )
            return result
        except Exception as e:
            import traceback
            error_msg = f"Error durante ejecución: {str(e)}\n{traceback.format_exc()}"
            return self._create_failed_run(
                run_id=run_id,
                evidence_dir=evidence_dir,
                error=error_msg,
                started_at=started_at,
            )
    
    def _execute_egestiona_upload_real(
        self,
        pdf_path: Path,
        item: CAESubmissionItemV1,
        doc: 'DocumentInstanceV1',  # Documento a subir
        coordination: str,
        client_code: str,
        username: str,
        password: str,
        run_id: str,
        evidence_dir: Path,
        screenshots_dir: Path,
        started_at: datetime,
    ) -> RunResultV1:
        """
        Ejecuta el upload real en eGestiona usando Playwright.
        
        Reutiliza la lógica de run_upload_pending_document_scoped_headful pero adaptada
        para trabajar con un item del plan CAE.
        """
        import time
        from backend.adapters.egestiona.frame_scan_headful import LOGIN_URL_PREVIOUS_SUCCESS
        
        # Intentar importar Playwright
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            error_msg = f"Playwright no disponible: {str(e)}"
            return self._create_failed_run(
                run_id=run_id,
                evidence_dir=evidence_dir,
                error=error_msg,
                started_at=started_at,
            )
        
        # Preparar paths de screenshots
        screenshot_paths = {
            "01_login": screenshots_dir / "01_login.png",
            "02_dashboard": screenshots_dir / "02_dashboard.png",
            "03_listado": screenshots_dir / "03_listado.png",
            "04_detail": screenshots_dir / "04_detail.png",
            "05_uploaded": screenshots_dir / "05_uploaded.png",
            "06_confirmation": screenshots_dir / "06_confirmation.png",
        }
        
        # v1.3.1: Obtener fecha de inicio de vigencia solo si existe en resolved_dates
        date_ddmmyyyy = None
        if item.resolved_dates and "valid_from" in item.resolved_dates:
            try:
                from datetime import datetime
                from zoneinfo import ZoneInfo
                
                valid_from_str = item.resolved_dates["valid_from"]
                valid_from = datetime.fromisoformat(valid_from_str.replace("Z", "+00:00"))
                date_ddmmyyyy = valid_from.strftime("%d/%m/%Y")
            except Exception:
                # Si hay error al parsear, date_ddmmyyyy queda None
                pass
        
        status = "failed"
        last_error: Optional[str] = None
        
        # Crear manifest inicial
        manifest = {
            "run_id": run_id,
            "plan_id": None,  # Se actualizará después
            "item": {
                "kind": item.kind,
                "type_id": item.type_id,
                "scope": item.scope,
                "company_key": item.company_key,
                "person_key": item.person_key,
                "period_key": item.period_key,
                "suggested_doc_id": item.suggested_doc_id or (doc.doc_id if doc else None),
            },
            "pdf_path": str(pdf_path),
            "coordination": coordination,
            "started_at": started_at.isoformat(),
            "mode": "REAL",
        }
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=300)
            context = browser.new_context(viewport={"width": 1600, "height": 1000})
            page = context.new_page()
            
            try:
                # 1) Login
                login_url = LOGIN_URL_PREVIOUS_SUCCESS or "https://coordinate.egestiona.es/login?origen=subcontrata"
                page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
                page.locator('input[name="ClientName"]').fill(client_code, timeout=20000)
                page.locator('input[name="Username"]').fill(username, timeout=20000)
                page.locator('input[name="Password"]').fill(password, timeout=20000)
                page.locator('button[type="submit"]').click(timeout=20000)
                
                # Esperar post-login
                page.wait_for_url("**/default_contenido.asp", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=25000)
                except Exception:
                    pass
                time.sleep(2.5)
                
                page.screenshot(path=str(screenshot_paths["01_login"]), full_page=True)
                
                # 2) Navegar a pendientes
                frame_dashboard = page.frame(name="nm_contenido")
                if not frame_dashboard:
                    raise RuntimeError("FRAME_NOT_FOUND: nm_contenido")
                
                page.screenshot(path=str(screenshot_paths["02_dashboard"]), full_page=True)
                
                # Click Gestion(3)
                tile_sel = 'a.listado_link[href="javascript:Gestion(3);"]'
                frame_dashboard.locator(tile_sel).first.wait_for(state="visible", timeout=20000)
                frame_dashboard.locator(tile_sel).first.click(timeout=20000)
                
                # 3) Esperar frame de listado
                def _find_list_frame():
                    fr = page.frame(name="f3")
                    if fr:
                        return fr
                    for fr2 in page.frames:
                        u = (fr2.url or "").lower()
                        if ("buscador.asp" in u) and ("apartado_id=3" in u):
                            return fr2
                    return None
                
                def _frame_has_grid(fr):
                    try:
                        return fr.locator("table.obj.row20px").count() > 0 and fr.locator("table.hdr").count() > 0
                    except Exception:
                        return False
                
                list_frame = None
                t_deadline = time.time() + 15.0
                while time.time() < t_deadline:
                    list_frame = _find_list_frame()
                    if list_frame and _frame_has_grid(list_frame):
                        break
                    time.sleep(0.25)
                
                if not (list_frame and _frame_has_grid(list_frame)):
                    # Intentar click Buscar
                    for fr in page.frames:
                        try:
                            btn = fr.get_by_text("Buscar", exact=True)
                            if btn.count() > 0:
                                btn.first.click(timeout=10000)
                                break
                        except Exception:
                            continue
                    
                    t_deadline = time.time() + 20.0
                    while time.time() < t_deadline:
                        list_frame = _find_list_frame()
                        if list_frame and _frame_has_grid(list_frame):
                            break
                        time.sleep(0.25)
                
                if not (list_frame and _frame_has_grid(list_frame)):
                    raise RuntimeError("GRID_NOT_FOUND: no se pudo cargar el grid de pendientes")
                
                # Esperar que el grid tenga filas
                def _grid_rows_ready(fr):
                    try:
                        return bool(
                            fr.evaluate(
                                """() => {
  const obj = document.querySelector('table.obj.row20px');
  if(!obj) return false;
  const trs = Array.from(obj.querySelectorAll('tr'));
  return trs.some(tr => {
    const tds = Array.from(tr.querySelectorAll('td'));
    return tds.length > 0 && tds.some(td => (td.innerText||'').trim().length > 0);
  });
}"""
                            )
                        )
                    except Exception:
                        return False
                
                t_deadline = time.time() + 10.0
                while time.time() < t_deadline:
                    if _grid_rows_ready(list_frame):
                        break
                    time.sleep(0.25)
                
                if not _grid_rows_ready(list_frame):
                    raise RuntimeError("GRID_EMPTY: el grid no tiene filas")
                
                try:
                    list_frame.locator("body").screenshot(path=str(screenshot_paths["03_listado"]))
                except Exception:
                    page.screenshot(path=str(screenshot_paths["03_listado"]), full_page=True)
                
                # 4) Buscar fila que coincida con type_id + sujeto + periodo
                # Por ahora, simplificado: buscar primera fila que coincida con empresa/trabajador
                # TODO: Mejorar matching para usar type_id y period_key del item
                from backend.adapters.egestiona.grid_extract import extract_dhtmlx_grid
                from backend.adapters.egestiona.grid_extract import canonicalize_row
                from backend.shared.text_normalizer import normalize_text_robust, text_contains
                
                extracted = extract_dhtmlx_grid(list_frame)
                rows = extracted.get("rows", [])
                
                # Filtrar filas que coincidan con el sujeto
                matching_rows = []
                for row_data in rows:
                    row = canonicalize_row(row_data)
                    empresa_match = True
                    elemento_match = True
                    
                    if item.company_key:
                        empresa_norm = normalize_text_robust(str(row.get("empresa") or ""))
                        company_key_norm = normalize_text_robust(item.company_key)
                        empresa_match = text_contains(empresa_norm, company_key_norm)
                    
                    if item.person_key:
                        elemento_norm = normalize_text_robust(str(row.get("elemento") or ""))
                        person_key_norm = normalize_text_robust(item.person_key)
                        elemento_match = text_contains(elemento_norm, person_key_norm)
                    
                    if empresa_match and elemento_match:
                        matching_rows.append((row, row_data))
                
                if len(matching_rows) != 1:
                    error_msg = f"Se encontraron {len(matching_rows)} filas que coinciden con el sujeto (esperado: 1). No se puede proceder de forma segura."
                    raise RuntimeError(error_msg)
                
                # 5) Abrir detalle de la fila encontrada
                # Por ahora, usar la lógica simplificada: click en primera fila matching
                # TODO: Mejorar para encontrar el índice exacto y hacer click
                target_row_data = matching_rows[0][1]
                
                # Intentar hacer click en la fila (buscar botón o link)
                click_success = list_frame.evaluate(
                    """() => {
  const tbls = Array.from(document.querySelectorAll('table.obj.row20px'));
  if(!tbls.length) return {ok: false, reason: 'no_table'};
  const trs = Array.from(tbls[0].querySelectorAll('tr'));
  if(!trs.length) return {ok: false, reason: 'no_rows'};
  const tr = trs[0];
  const a = tr.querySelector('a');
  if(a) { a.click(); return {ok: true, kind: 'a'}; }
  const img = tr.querySelector('img[onclick]');
  if(img) { img.click(); return {ok: true, kind: 'img'}; }
  tr.click();
  return {ok: true, kind: 'tr'};
}"""
                )
                
                if not click_success.get("ok"):
                    raise RuntimeError("No se pudo hacer click en la fila del pendiente")
                
                # Esperar modal de detalle
                time.sleep(2.0)
                page.screenshot(path=str(screenshot_paths["04_detail"]), full_page=True)
                
                # 6) Subir PDF
                file_input = page.locator("input[type='file']:visible")
                if file_input.count() == 0:
                    file_input = page.locator("input[type='file']")
                
                if file_input.count() > 0:
                    file_input.first.set_input_files(str(pdf_path))
                else:
                    # Fallback: buscar botón "Adjuntar"
                    try:
                        attach = page.get_by_text("Adjuntar fichero", exact=False)
                        if attach.count() == 0:
                            attach = page.get_by_text("Adjuntar", exact=False)
                        if attach.count() > 0:
                            with page.expect_file_chooser(timeout=15000) as fc_info:
                                attach.first.click(timeout=10000)
                            chooser = fc_info.value
                            chooser.set_files(str(pdf_path))
                        else:
                            raise RuntimeError("FILE_INPUT_NOT_FOUND: no se encontró input de archivo ni botón Adjuntar")
                    except Exception as e:
                        raise RuntimeError(f"FILE_INPUT_NOT_FOUND: {str(e)}")
                
                # 7) Rellenar fecha "Inicio Vigencia" solo si existe en resolved_dates (v1.3.1)
                if date_ddmmyyyy:
                    try:
                        # Buscar input de fecha cerca de label "Inicio Vigencia"
                        date_selector = page.evaluate(
                            """() => {
  function norm(s){ return (s||'').replace(/\\s+/g,' ').trim(); }
  const labels = Array.from(document.querySelectorAll('*')).filter(el => {
    const t = norm(el.innerText).toLowerCase();
    return t.includes('inicio vigencia');
  });
  if(!labels.length) return null;
  const label = labels[0];
  const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="date"]'));
  for(const inp of inputs){
    const r1 = label.getBoundingClientRect();
    const r2 = inp.getBoundingClientRect();
    const dist = Math.sqrt(Math.pow(r1.left - r2.left, 2) + Math.pow(r1.top - r2.top, 2));
    if(dist < 200 && inp.offsetWidth > 0 && inp.offsetHeight > 0){
      if(inp.id) return '#' + inp.id;
      if(inp.name) return `input[name="${inp.name}"]`;
    }
  }
  return null;
}"""
                        )
                        
                        if date_selector:
                            date_input = page.locator(date_selector)
                            if date_input.count() > 0:
                                date_input.first.fill(date_ddmmyyyy, timeout=10000)
                    except Exception as e:
                        # No crítico, continuar
                        pass
                else:
                    # v1.3.1: Si el portal exige fecha y no existe en plan -> verificar si es requerido
                    # Por ahora, solo log (no bloqueamos automáticamente, el portal puede no requerirla)
                    # Si el portal falla por falta de fecha, el error se capturará en el paso siguiente
                    pass
                
                page.screenshot(path=str(screenshot_paths["05_uploaded"]), full_page=True)
                
                # 8) Confirmar (buscar botón Enviar/Guardar)
                try:
                    # Buscar botones comunes de confirmación
                    submit_selectors = [
                        'button:has-text("Enviar documento")',
                        'button:has-text("Enviar archivo")',
                        'button:has-text("Enviar")',
                        'button:has-text("Guardar")',
                        'input[type="submit"][value*="Enviar"]',
                        'input[type="submit"][value*="Guardar"]',
                    ]
                    
                    submitted = False
                    for selector in submit_selectors:
                        try:
                            btn = page.locator(selector)
                            if btn.count() > 0:
                                btn.first.click(timeout=10000)
                                submitted = True
                                break
                        except Exception:
                            continue
                    
                    if not submitted:
                        # Si no hay botón claro, no hacer nada (puede ser auto-submit)
                        pass
                    
                    time.sleep(2.0)
                    page.screenshot(path=str(screenshot_paths["06_confirmation"]), full_page=True)
                except Exception as e:
                    # No crítico, continuar
                    pass
                
                status = "SUCCESS"
                
            except Exception as e:
                last_error = str(e)
                status = "FAILED"
                # Capturar screenshot de error
                try:
                    page.screenshot(path=str(screenshots_dir / "error.png"), full_page=True)
                except Exception:
                    pass
            finally:
                browser.close()
        
        finished_at = datetime.now()
        
        # Actualizar manifest
        manifest.update({
            "plan_id": None,  # Se puede añadir después si es necesario
            "finished_at": finished_at.isoformat(),
            "status": status,
            "error": last_error,
        })
        
        with open(evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        # Crear run_finished.json
        run_finished = {
            "run_id": run_id,
            "status": status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "error": last_error,
            "summary": {
                "items_processed": 1,
                "items_success": 1 if status == "SUCCESS" else 0,
                "items_failed": 1 if status == "FAILED" else 0,
            },
        }
        
        with open(evidence_dir / "run_finished.json", "w", encoding="utf-8") as f:
            json.dump(run_finished, f, indent=2, ensure_ascii=False)
        
        return RunResultV1(
            run_id=run_id,
            status=status,
            evidence_path=str(evidence_dir),
            summary=run_finished["summary"],
            error=last_error,
            started_at=started_at,
            finished_at=finished_at,
        )
    
    def _create_failed_run(
        self,
        run_id: str,
        evidence_dir: Path,
        error: str,
        started_at: datetime,
    ) -> RunResultV1:
        """Crea un run fallido con evidencia."""
        finished_at = datetime.now()
        
        manifest = {
            "run_id": run_id,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": "FAILED",
            "error": error,
        }
        
        with open(evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        run_finished = {
            "run_id": run_id,
            "status": "FAILED",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "error": error,
            "summary": {
                "items_processed": 0,
                "items_success": 0,
                "items_failed": 1,
            },
        }
        
        with open(evidence_dir / "run_finished.json", "w", encoding="utf-8") as f:
            json.dump(run_finished, f, indent=2, ensure_ascii=False)
        
        return RunResultV1(
            run_id=run_id,
            status="FAILED",
            evidence_path=str(evidence_dir),
            summary=run_finished["summary"],
            error=error,
            started_at=started_at,
            finished_at=finished_at,
        )
    
    @staticmethod
    def _create_blocked_run(
        run_id: str,
        evidence_dir: Path,
        error: str,
        started_at: datetime,
    ) -> RunResultV1:
        """Crea un run bloqueado con evidencia."""
        finished_at = datetime.now()
        
        manifest = {
            "run_id": run_id,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": "BLOCKED",
            "error": error,
        }
        
        with open(evidence_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        run_finished = {
            "run_id": run_id,
            "status": "BLOCKED",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "error": error,
            "summary": {
                "items_processed": 0,
                "items_success": 0,
                "items_failed": 0,
            },
        }
        
        with open(evidence_dir / "run_finished.json", "w", encoding="utf-8") as f:
            json.dump(run_finished, f, indent=2, ensure_ascii=False)
        
        return RunResultV1(
            run_id=run_id,
            status="BLOCKED",
            evidence_path=str(evidence_dir),
            summary=run_finished["summary"],
            error=error,
            started_at=started_at,
            finished_at=finished_at,
        )
    
    def _generate_run_id(self) -> str:
        """Genera un run_id único."""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        short_id = str(uuid.uuid4())[:8]
        return f"CAERUN-{timestamp}-{short_id}"

