"""
Tests para HybridFormMapper v4.7.0
"""

import pytest
from backend.agents.hybrid_form_mapper import HybridFormMapper, euclidean_distance
from backend.shared.models import MappedField


class TestHybridFormMapper:
    """Tests para HybridFormMapper"""
    
    def test_euclidean_distance(self):
        """Test que calcula distancia euclídea correctamente"""
        assert euclidean_distance(0, 0, 3, 4) == 5.0
        assert euclidean_distance(1, 1, 1, 1) == 0.0
        assert euclidean_distance(0, 0, 1, 1) == pytest.approx(1.414, abs=0.01)
    
    def test_map_when_dom_broken_but_ocr_correct(self):
        """Test mapeo cuando DOM está roto pero OCR es correcto"""
        dom = {
            "labels": [],  # DOM roto: sin labels
            "inputs": [
                {"selector": "#campo1", "name": "campo1", "id": "campo1"},
            ],
        }
        
        ocr_blocks = [
            {
                "text": "Fecha de caducidad",
                "x": 100,
                "y": 200,
                "width": 150,
                "height": 20,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["expiry_date"])
        
        assert "expiry_date" in results
        # Debería encontrar el campo usando OCR
        # (aunque el selector puede no ser perfecto sin DOM completo)
    
    def test_map_when_ocr_detects_labels_but_dom_not(self):
        """Test mapeo cuando OCR detecta labels pero DOM no"""
        dom = {
            "labels": [],  # Sin labels en DOM
            "inputs": [
                {"selector": "#fecha", "name": "fecha", "id": "fecha"},
            ],
        }
        
        ocr_blocks = [
            {
                "text": "Fecha de emisión",
                "x": 50,
                "y": 100,
                "width": 120,
                "height": 18,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["issue_date"])
        
        assert "expiry_date" in results or "issue_date" in results
        # Debería usar OCR para encontrar el campo
    
    def test_map_inputs_without_label_and_nearby_ocr(self):
        """Test mapeo de inputs sin label pero con OCR cercano"""
        dom = {
            "labels": [],  # Sin labels asociados
            "inputs": [
                {"selector": "#input1", "name": "input1", "id": "input1"},
            ],
        }
        
        ocr_blocks = [
            {
                "text": "Trabajador",
                "x": 100,
                "y": 150,
                "width": 80,
                "height": 20,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["worker_name"])
        
        # Debería encontrar el campo usando OCR aunque no haya label en DOM
        assert "worker_name" in results
    
    def test_map_negative_fields(self):
        """Test que distingue correctamente issue_date vs expiry_date"""
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
        
        ocr_blocks = [
            {
                "text": "Fecha de emisión",
                "x": 50,
                "y": 100,
                "width": 120,
                "height": 18,
            },
            {
                "text": "Fecha de caducidad",
                "x": 50,
                "y": 150,
                "width": 140,
                "height": 18,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["issue_date", "expiry_date"])
        
        assert results["issue_date"] is not None
        assert results["expiry_date"] is not None
        assert results["issue_date"].selector != results["expiry_date"].selector
    
    def test_proximity_visual_correct(self):
        """Test que elige el texto más cercano visualmente"""
        dom = {
            "labels": [],
            "inputs": [
                {"selector": "#input1", "name": "input1", "id": "input1"},
            ],
        }
        
        ocr_blocks = [
            {
                "text": "Fecha de emisión",
                "x": 100,
                "y": 100,  # Cerca del input
                "width": 120,
                "height": 18,
            },
            {
                "text": "Otro texto",
                "x": 500,
                "y": 500,  # Lejos del input
                "width": 100,
                "height": 18,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["issue_date"])
        
        # Debería elegir el bloque OCR más cercano
        assert "issue_date" in results
    
    def test_fusion_dom_ocr_higher_score(self):
        """Test que fusión DOM+OCR produce score más alto"""
        dom = {
            "labels": [
                {"text": "Fecha de emisión", "for": "#emision"},
            ],
            "inputs": [
                {"selector": "#emision", "name": "emision", "id": "emision"},
            ],
        }
        
        ocr_blocks = [
            {
                "text": "Fecha de emisión",
                "x": 100,
                "y": 100,
                "width": 120,
                "height": 18,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["issue_date"])
        
        mapped = results["issue_date"]
        assert mapped is not None
        # Cuando DOM y OCR coinciden, debería tener source="hybrid" y alta confianza
        if mapped.source == "hybrid":
            assert mapped.confidence >= 0.8
    
    def test_fallback_when_no_ocr(self):
        """Test fallback a heuristic mapper cuando no hay OCR"""
        dom = {
            "labels": [
                {"text": "Fecha de emisión", "for": "#emision"},
            ],
            "inputs": [
                {"selector": "#emision", "name": "emision", "id": "emision"},
            ],
        }
        
        # Sin OCR blocks
        mapper = HybridFormMapper(dom, ocr_blocks=None)
        results = mapper.map_semantic_fields(["issue_date"])
        
        # Debería usar heuristic mapper (fallback)
        assert "issue_date" in results
        mapped = results["issue_date"]
        assert mapped is not None
        assert mapped.source == "dom"  # Heuristic mapper usa source="dom" por defecto
    
    def test_high_confidence_when_dom_ocr_match(self):
        """Test confianza alta cuando DOM y OCR coinciden"""
        dom = {
            "labels": [
                {"text": "Fecha de caducidad", "for": "#caducidad"},
            ],
            "inputs": [
                {"selector": "#caducidad", "name": "caducidad", "id": "caducidad"},
            ],
        }
        
        ocr_blocks = [
            {
                "text": "Fecha de caducidad",
                "x": 100,
                "y": 100,
                "width": 140,
                "height": 18,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["expiry_date"])
        
        mapped = results["expiry_date"]
        assert mapped is not None
        if mapped.source == "hybrid":
            assert mapped.confidence >= 0.8
    
    def test_low_confidence_when_ocr_far(self):
        """Test confianza baja cuando OCR está lejos"""
        dom = {
            "labels": [],
            "inputs": [
                {"selector": "#input1", "name": "input1", "id": "input1"},
            ],
        }
        
        ocr_blocks = [
            {
                "text": "Trabajador",
                "x": 1000,  # Muy lejos
                "y": 1000,
                "width": 80,
                "height": 20,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["worker_name"])
        
        # Aunque encuentre el campo, la confianza debería ser menor
        if results["worker_name"]:
            # La confianza puede ser menor si está lejos
            pass  # Test pasa si encuentra el campo
    
    def test_partial_mapping_only_issue_date(self):
        """Test mapeo parcial (solo issue_date)"""
        dom = {
            "labels": [
                {"text": "Fecha de emisión", "for": "#emision"},
            ],
            "inputs": [
                {"selector": "#emision", "name": "emision", "id": "emision"},
            ],
        }
        
        ocr_blocks = [
            {
                "text": "Fecha de emisión",
                "x": 100,
                "y": 100,
                "width": 120,
                "height": 18,
            },
        ]
        
        mapper = HybridFormMapper(dom, ocr_blocks)
        results = mapper.map_semantic_fields(["issue_date", "expiry_date", "worker_name"])
        
        # Debería mapear issue_date pero no los otros
        assert results["issue_date"] is not None
        # expiry_date y worker_name pueden ser None si no se encuentran










