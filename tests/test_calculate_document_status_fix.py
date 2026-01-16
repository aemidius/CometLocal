"""
Test para verificar el fix del cálculo de validez usando validity_start_date correctamente.
"""
import pytest
from datetime import date, timedelta
from backend.shared.document_repository_v1 import (
    DocumentInstanceV1,
    DocumentTypeV1,
    DocumentScopeV1,
    ExtractedMetadataV1,
    ValidityPolicyV1,
    ValidityModeV1,
    ValidityBasisV1,
    MonthlyValidityConfigV1,
    NMonthsValidityConfigV1,
    PeriodKindV1,
    DocumentStatusV1
)
from backend.repository.document_status_calculator_v1 import calculate_document_status, DocumentValidityStatus


def test_rc_certificate_with_validity_start_date_future():
    """
    Test: RC certificado con validity_start_date futura y periodicidad 12 meses.
    
    Escenario:
    - Fecha de emisión: 2025-08-01
    - Mes/Año: 2025-08
    - Fecha inicio de vigencia: 2026-05-30 (futura)
    - Periodicidad: cada 12 meses (n_months.n = 12)
    - validity_start_mode = "manual"
    
    Resultado esperado:
    - base_date = 2026-05-30 (validity_start_date)
    - validity_end_date = 2027-05-30 (base_date + 12 meses)
    - status = VALID (no EXPIRED)
    - days_until_expiry debe ser positivo (futuro)
    """
    # Crear tipo RC con periodicidad 12 meses
    rc_type = DocumentTypeV1(
        type_id="T8447_RC_CERTIFICADO",
        name="RC Certificado",
        scope=DocumentScopeV1.company,
        validity_start_mode="manual",
        validity_policy=ValidityPolicyV1(
            mode=ValidityModeV1.monthly,  # mode puede ser monthly pero con n_months override
            basis=ValidityBasisV1.manual,
            monthly=MonthlyValidityConfigV1(),
            n_months=NMonthsValidityConfigV1(n=12)  # Cada 12 meses
        )
    )
    
    # Crear documento con validity_start_date futura
    doc = DocumentInstanceV1(
        doc_id="test-rc-doc",
        file_name_original="test.pdf",
        stored_path="test.pdf",
        sha256="test",
        type_id="T8447_RC_CERTIFICADO",
        scope=DocumentScopeV1.company,
        company_key="F63161988",
        extracted=ExtractedMetadataV1(
            issue_date=date(2025, 8, 1),
            validity_start_date=date(2026, 5, 30)  # FUTURA
        ),
        period_key="2025-08",
        period_kind=PeriodKindV1.MONTH,
        status=DocumentStatusV1.draft
    )
    
    # Calcular estado
    status, validity_end_date, days_until_expiry, base_date, base_reason = calculate_document_status(
        doc, doc_type=rc_type
    )
    
    # Verificaciones
    assert base_reason == "validity_start_date", f"base_reason debe ser 'validity_start_date', got '{base_reason}'"
    assert base_date == date(2026, 5, 30), f"base_date debe ser 2026-05-30, got {base_date}"
    
    # validity_end_date debe ser base_date + 12 meses = 2027-05-30
    expected_end_date = date(2027, 5, 30)
    assert validity_end_date == expected_end_date, f"validity_end_date debe ser {expected_end_date}, got {validity_end_date}"
    
    # status NO debe ser EXPIRED (es futuro)
    assert status != DocumentValidityStatus.EXPIRED, f"status no debe ser EXPIRED, got {status}"
    assert status == DocumentValidityStatus.VALID, f"status debe ser VALID (futuro), got {status}"
    
    # days_until_expiry debe ser positivo (futuro)
    today = date.today()
    expected_days = (expected_end_date - today).days
    assert days_until_expiry == expected_days, f"days_until_expiry debe ser {expected_days}, got {days_until_expiry}"
    assert days_until_expiry > 0, f"days_until_expiry debe ser positivo (futuro), got {days_until_expiry}"


def test_rc_certificate_with_validity_start_date_past():
    """
    Test: RC certificado con validity_start_date pasada y periodicidad 12 meses.
    
    Escenario:
    - Fecha de emisión: 2024-01-01
    - Fecha inicio de vigencia: 2024-01-01 (pasada)
    - Periodicidad: cada 12 meses
    
    Resultado esperado:
    - base_date = 2024-01-01 (validity_start_date)
    - validity_end_date = 2025-01-01 (base_date + 12 meses)
    - status = EXPIRED (si hoy > 2025-01-01)
    """
    rc_type = DocumentTypeV1(
        type_id="T8447_RC_CERTIFICADO",
        name="RC Certificado",
        scope=DocumentScopeV1.company,
        validity_start_mode="manual",
        validity_policy=ValidityPolicyV1(
            mode=ValidityModeV1.monthly,
            basis=ValidityBasisV1.manual,
            monthly=MonthlyValidityConfigV1(),
            n_months=NMonthsValidityConfigV1(n=12)
        )
    )
    
    doc = DocumentInstanceV1(
        doc_id="test-rc-doc-past",
        file_name_original="test.pdf",
        stored_path="test.pdf",
        sha256="test",
        type_id="T8447_RC_CERTIFICADO",
        scope=DocumentScopeV1.company,
        company_key="F63161988",
        extracted=ExtractedMetadataV1(
            issue_date=date(2024, 1, 1),
            validity_start_date=date(2024, 1, 1)  # PASADA
        ),
        period_key="2024-01",
        period_kind=PeriodKindV1.MONTH,
        status=DocumentStatusV1.draft
    )
    
    status, validity_end_date, days_until_expiry, base_date, base_reason = calculate_document_status(
        doc, doc_type=rc_type
    )
    
    assert base_reason == "validity_start_date"
    assert base_date == date(2024, 1, 1)
    assert validity_end_date == date(2025, 1, 1)
    
    # Si hoy es después de 2025-01-01, debe estar expirado
    today = date.today()
    if today > date(2025, 1, 1):
        assert status == DocumentValidityStatus.EXPIRED
        assert days_until_expiry < 0


def test_manual_mode_missing_validity_start_date():
    """
    Test: Tipo con validity_start_mode="manual" pero sin validity_start_date debe retornar UNKNOWN.
    """
    rc_type = DocumentTypeV1(
        type_id="T8447_RC_CERTIFICADO",
        name="RC Certificado",
        scope=DocumentScopeV1.company,
        validity_start_mode="manual",
        validity_policy=ValidityPolicyV1(
            mode=ValidityModeV1.monthly,
            basis=ValidityBasisV1.manual,
            monthly=MonthlyValidityConfigV1(),
            n_months=NMonthsValidityConfigV1(n=12)
        )
    )
    
    doc = DocumentInstanceV1(
        doc_id="test-rc-doc-missing",
        file_name_original="test.pdf",
        stored_path="test.pdf",
        sha256="test",
        type_id="T8447_RC_CERTIFICADO",
        scope=DocumentScopeV1.company,
        company_key="F63161988",
        extracted=ExtractedMetadataV1(
            issue_date=date(2025, 8, 1),
            # NO hay validity_start_date
        ),
        period_key="2025-08",
        period_kind=PeriodKindV1.MONTH,
        status=DocumentStatusV1.draft
    )
    
    status, validity_end_date, days_until_expiry, base_date, base_reason = calculate_document_status(
        doc, doc_type=rc_type
    )
    
    assert status == DocumentValidityStatus.UNKNOWN
    assert base_reason == "missing_validity_start_date_for_manual_mode"
    assert validity_end_date is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])







