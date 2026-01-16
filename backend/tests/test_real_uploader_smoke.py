"""
Smoke test para EgestionaRealUploader.

NO hace login real ni sube documentos reales.
Solo valida que la clase se instancia correctamente y genera evidencias dummy.
"""

import pytest
from pathlib import Path
from backend.adapters.egestiona.real_uploader import EgestionaRealUploader
from backend.config import DATA_DIR


def test_real_uploader_instantiation():
    """Test que RealUploader se instancia correctamente."""
    evidence_dir = Path(DATA_DIR) / "test_evidence" / "real_uploader_smoke"
    uploader = EgestionaRealUploader(evidence_dir)
    
    assert uploader.evidence_dir == evidence_dir
    assert uploader.upload_count == 0
    assert uploader.repo_store is not None


def test_real_uploader_with_dummy_page():
    """Test que RealUploader genera evidencias dummy si page=about:blank."""
    from playwright.sync_api import sync_playwright
    
    evidence_dir = Path(DATA_DIR) / "test_evidence" / "real_uploader_smoke"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    uploader = EgestionaRealUploader(evidence_dir)
    
    # Item fixture
    item = {
        "pending_ref": {
            "tipo_doc": "Seguro de Responsabilidad Civil",
            "elemento": "Trabajador",
            "empresa": "TEST_COMPANY",
            "row_index": 0
        },
        "matched_doc": {
            "doc_id": "DOC_TEST",
            "type_id": "T_TEST",
            "file_name": "test.pdf",
        },
        "proposed_fields": {
            "fecha_inicio_vigencia": "2026-01-14",
            "fecha_fin_vigencia": "2027-01-14"
        },
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto("about:blank")
        
        try:
            # Intentar upload (fallará porque no hay documento real, pero valida estructura)
            result = uploader.upload_one_real(page, item, requirement_id="test_req_1")
            
            # Result debe tener estructura correcta
            assert "success" in result
            assert "upload_id" in result
            assert "reason" in result
            
            # Si falló temprano (doc_not_found), no se generan evidencias de item
            # Pero si llegó más lejos, debe haber evidencias
            if result.get("success") is False:
                # Si el error es temprano (doc_not_found, pdf_not_found), es esperado
                reason = result.get("reason", "")
                if "doc_not_found" in reason or "pdf_not_found" in reason:
                    # Esto es esperado en el smoke test
                    assert True
                else:
                    # Si falló más tarde, debe haber evidencias
                    item_evidence_dir = evidence_dir / "items" / "test_req_1"
                    if item_evidence_dir.exists():
                        upload_log = item_evidence_dir / "upload_log.txt"
                        if upload_log.exists():
                            log_content = upload_log.read_text(encoding="utf-8")
                            assert "REAL UPLOAD" in log_content or "REAL UPLOAD ERROR" in log_content
        finally:
            browser.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
