"""
FakeConnectorUploader: Simula subidas de documentos sin tocar el portal real.

Usado en desarrollo y E2E para validar el flujo de ejecución sin riesgo.
"""

from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class FakeConnectorUploader:
    """
    Simula la subida de documentos sin interactuar con el portal real.
    
    Genera evidencias (screenshots, logs) como si fuera real, pero no hace
    clicks ni subidas reales en e-gestiona.
    """
    
    def __init__(self, evidence_dir: Path, logger=None):
        """
        Args:
            evidence_dir: Directorio donde guardar evidencias
            logger: Logger opcional (usa print si no se proporciona)
        """
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.log = logger or (lambda msg: print(f"[FAKE_UPLOADER] {msg}"))
        self.upload_count = 0
    
    def upload_one(
        self,
        item: Dict[str, Any],
        *,
        page=None,  # Opcional, para screenshots si está disponible
    ) -> Dict[str, Any]:
        """
        Simula la subida de un documento.
        
        Args:
            item: Item del plan con pending_ref, matched_doc, proposed_fields, etc.
            page: Página de Playwright (opcional, para screenshots)
        
        Returns:
            Dict con:
            - success: bool
            - upload_id: str (fake)
            - evidence_path: str
            - duration_ms: int
            - reason: str
        """
        self.upload_count += 1
        upload_id = f"fake_upload_{self.upload_count}_{int(time.time())}"
        
        pending_ref = item.get("pending_ref", {})
        matched_doc = item.get("matched_doc", {})
        proposed_fields = item.get("proposed_fields", {})
        
        doc_id = matched_doc.get("doc_id", "unknown")
        type_id = matched_doc.get("type_id", "unknown")
        
        started = time.time()
        
        # Log de lo que se "subiría"
        self.log(f"Simulando subida #{self.upload_count}: doc_id={doc_id}, type_id={type_id}")
        
        # Generar evidencia "before"
        evidence_before = self.evidence_dir / f"{upload_id}_before.json"
        _safe_write_json(evidence_before, {
            "upload_id": upload_id,
            "item": item,
            "timestamp": datetime.utcnow().isoformat(),
            "action": "upload_simulation",
        })
        
        # Generar screenshot dummy (txt con info)
        screenshot_dummy = self.evidence_dir / f"{upload_id}_before.txt"
        screenshot_dummy.write_text(
            f"FAKE UPLOAD BEFORE\n"
            f"Upload ID: {upload_id}\n"
            f"Doc ID: {doc_id}\n"
            f"Type ID: {type_id}\n"
            f"Timestamp: {datetime.utcnow().isoformat()}\n",
            encoding="utf-8"
        )
        
        # Simular delay de subida (100-500ms)
        time.sleep(0.1 + (self.upload_count % 4) * 0.1)
        
        # Generar evidencia "after"
        finished = time.time()
        duration_ms = int((finished - started) * 1000)
        
        # Generar portal_reference fake
        portal_reference = f"PORTAL_REF_{upload_id}"
        
        evidence_after = self.evidence_dir / f"{upload_id}_after.json"
        _safe_write_json(evidence_after, {
            "upload_id": upload_id,
            "success": True,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
            "simulated": True,
            "portal_reference": portal_reference,
        })
        
        # Generar screenshot dummy after
        screenshot_after_dummy = self.evidence_dir / f"{upload_id}_after.txt"
        screenshot_after_dummy.write_text(
            f"FAKE UPLOAD AFTER\n"
            f"Upload ID: {upload_id}\n"
            f"Portal Reference: {portal_reference}\n"
            f"Duration: {duration_ms}ms\n"
            f"Timestamp: {datetime.utcnow().isoformat()}\n",
            encoding="utf-8"
        )
        
        # Si hay página, hacer screenshot (opcional)
        if page:
            try:
                screenshot_path = self.evidence_dir / f"{upload_id}_screenshot.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception as e:
                self.log(f"Warning: No se pudo hacer screenshot: {e}")
        
        return {
            "success": True,
            "upload_id": upload_id,
            "evidence_path": str(self.evidence_dir),
            "duration_ms": duration_ms,
            "reason": "Simulated upload (fake connector)",
            "simulated": True,
            "portal_reference": portal_reference,
        }


def _safe_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Escribe JSON de forma segura."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[FAKE_UPLOADER] Error al escribir {path}: {e}")
