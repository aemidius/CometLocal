"""
Tests para FormFieldMapper v4.6.0
"""

import pytest
from backend.agents.form_field_mapper import FormFieldMapper, normalize_text, calculate_score
from backend.shared.models import MappedField


class TestFormFieldMapper:
    """Tests para FormFieldMapper"""
    
    def test_normalize_text(self):
        """Test que normaliza texto correctamente"""
        assert normalize_text("Fecha de Emisión") == "fecha de emision"
        assert normalize_text("Trabajador/a") == "trabajador/a"
        assert normalize_text("Válido hasta") == "valido hasta"
    
    def test_calculate_score_positive(self):
        """Test que calcula score positivo para keywords positivas"""
        score = calculate_score(
            "Fecha de emisión del documento",
            ["emisión", "expedición"],
            ["caducidad"]
        )
        assert score > 0
    
    def test_calculate_score_negative(self):
        """Test que calcula score negativo si hay más keywords negativas"""
        score = calculate_score(
            "Fecha de caducidad del documento",
            ["emisión"],
            ["caducidad", "vencimiento"]
        )
        assert score < 0
    
    def test_map_issue_date_variant_a(self):
        """Test que mapea issue_date en Variante A"""
        dom = {
            "labels": [
                {"text": "Fecha de emisión del documento", "for": "#emision_doc"},
                {"text": "Fecha de caducidad", "for": "#caducidad"},
                {"text": "Trabajador/a", "for": "#nombre_trabajador"},
            ],
            "inputs": [
                {"selector": "#emision_doc", "name": "emision_doc", "id": "emision_doc"},
                {"selector": "#caducidad", "name": "caducidad", "id": "caducidad"},
                {"selector": "#nombre_trabajador", "name": "nombre_trabajador", "id": "nombre_trabajador"},
            ],
        }
        
        mapper = FormFieldMapper(dom)
        results = mapper.map_semantic_fields(["issue_date"])
        
        assert "issue_date" in results
        mapped = results["issue_date"]
        assert mapped is not None
        assert mapped.semantic_field == "issue_date"
        assert mapped.selector == "#emision_doc"
        assert "emisión" in mapped.label_text.lower()
        assert mapped.score > 0
        assert mapped.confidence > 0
    
    def test_map_expiry_date_variant_b(self):
        """Test que mapea expiry_date en Variante B"""
        dom = {
            "labels": [
                {"text": "Fecha reconocimiento médico", "for": "#fecha_rm"},
                {"text": "Válido hasta", "for": "#valido_hasta"},
                {"text": "Empleado", "for": "#empleado"},
            ],
            "inputs": [
                {"selector": "#fecha_rm", "name": "fecha_rm", "id": "fecha_rm"},
                {"selector": "#valido_hasta", "name": "valido_hasta", "id": "valido_hasta"},
                {"selector": "#empleado", "name": "empleado", "id": "empleado"},
            ],
        }
        
        mapper = FormFieldMapper(dom)
        results = mapper.map_semantic_fields(["expiry_date"])
        
        assert "expiry_date" in results
        mapped = results["expiry_date"]
        assert mapped is not None
        assert mapped.semantic_field == "expiry_date"
        assert mapped.selector == "#valido_hasta"
        assert "válido" in mapped.label_text.lower() or "valido" in mapped.label_text.lower()
        assert mapped.score > 0
    
    def test_map_worker_name_variant_c(self):
        """Test que mapea worker_name en Variante C"""
        dom = {
            "labels": [
                {"text": "Fecha expedición", "for": "#expedicion"},
                {"text": "Expira el", "for": "#expira_el"},
                {"text": "Nombre completo", "for": "#nombre_completo"},
            ],
            "inputs": [
                {"selector": "#expedicion", "name": "expedicion", "id": "expedicion"},
                {"selector": "#expira_el", "name": "expira_el", "id": "expira_el"},
                {"selector": "#nombre_completo", "name": "nombre_completo", "id": "nombre_completo"},
            ],
        }
        
        mapper = FormFieldMapper(dom)
        results = mapper.map_semantic_fields(["worker_name"])
        
        assert "worker_name" in results
        mapped = results["worker_name"]
        assert mapped is not None
        assert mapped.semantic_field == "worker_name"
        assert mapped.selector == "#nombre_completo"
        assert "nombre" in mapped.label_text.lower()
        assert mapped.score > 0
    
    def test_map_ambiguity_multiple_dates(self):
        """Test que maneja ambigüedad con múltiples campos de fecha"""
        dom = {
            "labels": [
                {"text": "Fecha de emisión", "for": "#emision"},
                {"text": "Fecha de caducidad", "for": "#caducidad"},
            ],
            "inputs": [
                {"selector": "#emision", "name": "emision", "id": "emision"},
                {"selector": "#caducidad", "name": "caducidad", "id": "caducidad"},
            ],
        }
        
        mapper = FormFieldMapper(dom)
        results = mapper.map_semantic_fields(["issue_date", "expiry_date"])
        
        assert results["issue_date"] is not None
        assert results["issue_date"].selector == "#emision"
        assert results["expiry_date"] is not None
        assert results["expiry_date"].selector == "#caducidad"
    
    def test_map_no_matches(self):
        """Test que devuelve None cuando no hay coincidencias"""
        dom = {
            "labels": [
                {"text": "Campo desconocido", "for": "#campo1"},
            ],
            "inputs": [
                {"selector": "#campo1", "name": "campo1", "id": "campo1"},
            ],
        }
        
        mapper = FormFieldMapper(dom)
        results = mapper.map_semantic_fields(["issue_date", "expiry_date", "worker_name"])
        
        assert results["issue_date"] is None
        assert results["expiry_date"] is None
        assert results["worker_name"] is None
    
    def test_integration_with_document_form_filler(self):
        """Test de integración con DocumentFormFiller (mock)"""
        from backend.agents.document_form_filler import DocumentFormFiller
        from backend.shared.models import DocumentFormFillPlan, FormFieldValue
        from datetime import date
        
        # Crear plan
        plan = DocumentFormFillPlan(
            doc_type="reconocimiento_medico",
            worker_name="Juan Pérez",
            fields=[
                FormFieldValue(
                    semantic_field="issue_date",
                    value="2025-03-01",
                    source="document_analysis",
                ),
                FormFieldValue(
                    semantic_field="expiry_date",
                    value="2026-03-01",
                    source="document_analysis",
                ),
                FormFieldValue(
                    semantic_field="worker_name",
                    value="Juan Pérez",
                    source="document_analysis",
                ),
            ],
            confidence=0.8,
        )
        
        # Crear DOM de Variante A
        dom = {
            "labels": [
                {"text": "Fecha de emisión del documento", "for": "#emision_doc"},
                {"text": "Fecha de caducidad", "for": "#caducidad"},
                {"text": "Trabajador/a", "for": "#nombre_trabajador"},
            ],
            "inputs": [
                {"selector": "#emision_doc", "name": "emision_doc", "id": "emision_doc"},
                {"selector": "#caducidad", "name": "caducidad", "id": "caducidad"},
                {"selector": "#nombre_trabajador", "name": "nombre_trabajador", "id": "nombre_trabajador"},
            ],
        }
        
        # Mapear campos
        mapper = FormFieldMapper(dom)
        semantic_fields = [f.semantic_field for f in plan.fields]
        mapped_fields = mapper.map_semantic_fields(semantic_fields)
        
        # Construir instrucción usando mapper
        form_filler = DocumentFormFiller()
        instruction = form_filler.build_instruction_via_mapper(plan, mapped_fields)
        
        assert instruction is not None
        assert len(instruction.field_selectors) == 3
        assert "issue_date" in instruction.field_selectors
        assert "expiry_date" in instruction.field_selectors
        assert "worker_name" in instruction.field_selectors
        assert instruction.form_context == "cae_upload_auto"

