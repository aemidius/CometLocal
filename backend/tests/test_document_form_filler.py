"""
Tests para DocumentFormFiller v4.5.0
"""

import pytest
from datetime import date
from backend.agents.document_form_filler import DocumentFormFiller, format_date_for_form
from backend.shared.models import DocumentAnalysisResult, DocumentFormFillPlan, FormFillInstruction


class TestDocumentFormFiller:
    """Tests para DocumentFormFiller"""
    
    def test_format_date_for_form(self):
        """Test que formatea fechas correctamente"""
        d = date(2025, 3, 1)
        formatted = format_date_for_form(d)
        assert formatted == "2025-03-01"
        
        d2 = date(2024, 12, 31)
        formatted2 = format_date_for_form(d2)
        assert formatted2 == "2024-12-31"
    
    def test_build_plan_from_analysis_complete(self):
        """Test que construye un plan completo cuando el análisis tiene todos los campos"""
        filler = DocumentFormFiller()
        
        analysis = DocumentAnalysisResult(
            doc_type="reconocimiento_medico",
            worker_name="Juan Pérez García",
            issue_date=date(2025, 3, 1),
            expiry_date=date(2026, 3, 1),
            confidence=0.85,
        )
        
        plan = filler.build_plan_from_analysis(analysis)
        
        assert isinstance(plan, DocumentFormFillPlan)
        assert plan.doc_type == "reconocimiento_medico"
        assert plan.worker_name == "Juan Pérez García"
        assert len(plan.fields) == 3
        
        # Verificar campos
        field_dict = {f.semantic_field: f for f in plan.fields}
        assert "issue_date" in field_dict
        assert field_dict["issue_date"].value == "2025-03-01"
        assert field_dict["issue_date"].source == "document_analysis"
        # v4.6.0: Verificar que possible_labels se generan
        assert len(field_dict["issue_date"].possible_labels) > 0
        assert "Fecha de expedición" in field_dict["issue_date"].possible_labels
        
        assert "expiry_date" in field_dict
        assert field_dict["expiry_date"].value == "2026-03-01"
        # v4.6.0: Verificar que possible_labels se generan
        assert len(field_dict["expiry_date"].possible_labels) > 0
        assert "Fecha de caducidad" in field_dict["expiry_date"].possible_labels
        
        assert "worker_name" in field_dict
        assert field_dict["worker_name"].value == "Juan Pérez García"
        # v4.6.0: Verificar que possible_labels se generan
        assert len(field_dict["worker_name"].possible_labels) > 0
        assert "Trabajador" in field_dict["worker_name"].possible_labels
        
        # Confidence debería ser > 0
        assert plan.confidence > 0.0
        assert plan.confidence <= 1.0
    
    def test_build_plan_from_analysis_partial(self):
        """Test que construye un plan parcial cuando faltan campos"""
        filler = DocumentFormFiller()
        
        analysis = DocumentAnalysisResult(
            doc_type="reconocimiento_medico",
            worker_name="Juan Pérez García",
            issue_date=date(2025, 3, 1),
            expiry_date=None,  # Falta expiry_date
            confidence=0.75,
        )
        
        plan = filler.build_plan_from_analysis(analysis)
        
        assert len(plan.fields) == 2  # Solo issue_date y worker_name
        assert any(f.semantic_field == "issue_date" for f in plan.fields)
        assert any(f.semantic_field == "worker_name" for f in plan.fields)
        assert not any(f.semantic_field == "expiry_date" for f in plan.fields)
        
        # Debería tener warnings sobre falta de expiry_date
        assert any("caducidad" in w.lower() for w in plan.warnings)
        
        # Confidence debería ser menor que si tuviera todos los campos
        assert plan.confidence < 0.75  # Menor porque falta un campo
    
    def test_build_plan_from_analysis_empty(self):
        """Test que maneja correctamente un análisis vacío"""
        filler = DocumentFormFiller()
        
        analysis = DocumentAnalysisResult(
            confidence=0.0,
        )
        
        plan = filler.build_plan_from_analysis(analysis)
        
        assert len(plan.fields) == 0
        assert len(plan.warnings) >= 3  # Warnings para issue_date, expiry_date, worker_name
        assert plan.confidence == 0.0
    
    def test_build_instruction_for_cae_upload_form_complete(self):
        """Test que construye una instrucción cuando el plan tiene campos"""
        filler = DocumentFormFiller()
        
        from backend.shared.models import FormFieldValue
        from backend.agents.document_form_filler import SEMANTIC_FIELD_LABELS
        
        plan = DocumentFormFillPlan(
            doc_type="reconocimiento_medico",
            worker_name="Juan Pérez García",
            fields=[
                FormFieldValue(
                    semantic_field="issue_date",
                    value="2025-03-01",
                    source="document_analysis",
                    possible_labels=SEMANTIC_FIELD_LABELS.get("issue_date", []),  # v4.6.0
                ),
                FormFieldValue(
                    semantic_field="expiry_date",
                    value="2026-03-01",
                    source="document_analysis",
                    possible_labels=SEMANTIC_FIELD_LABELS.get("expiry_date", []),  # v4.6.0
                ),
                FormFieldValue(
                    semantic_field="worker_name",
                    value="Juan Pérez García",
                    source="document_analysis",
                    possible_labels=SEMANTIC_FIELD_LABELS.get("worker_name", []),  # v4.6.0
                ),
            ],
            confidence=0.85,
        )
        
        instruction = filler.build_instruction_for_cae_upload_form(plan, form_variant="default")
        
        assert instruction is not None
        assert isinstance(instruction, FormFillInstruction)
        assert len(instruction.field_selectors) == 3
        assert "issue_date" in instruction.field_selectors
        assert "expiry_date" in instruction.field_selectors
        assert "worker_name" in instruction.field_selectors
        # v4.6.0: Verificar que label_hints se generan
        assert len(instruction.label_hints) == 3
        assert "issue_date" in instruction.label_hints
        assert "expiry_date" in instruction.label_hints
        assert "worker_name" in instruction.label_hints
        assert instruction.plan == plan
        assert instruction.form_context == "cae_upload_default"
    
    def test_build_instruction_for_cae_upload_form_empty_plan(self):
        """Test que devuelve None cuando el plan está vacío"""
        filler = DocumentFormFiller()
        
        plan = DocumentFormFillPlan(
            fields=[],
            confidence=0.0,
        )
        
        instruction = filler.build_instruction_for_cae_upload_form(plan)
        
        assert instruction is None
    
    def test_build_instruction_for_cae_upload_form_unknown_variant(self):
        """Test que maneja correctamente un form_variant desconocido"""
        filler = DocumentFormFiller()
        
        from backend.shared.models import FormFieldValue
        
        plan = DocumentFormFillPlan(
            fields=[
                FormFieldValue(
                    semantic_field="issue_date",
                    value="2025-03-01",
                    source="document_analysis",
                ),
            ],
            confidence=0.5,
        )
        
        # Debería usar default aunque el variant sea desconocido
        instruction = filler.build_instruction_for_cae_upload_form(plan, form_variant="unknown")
        
        assert instruction is not None
        assert instruction.form_context == "cae_upload_unknown"

