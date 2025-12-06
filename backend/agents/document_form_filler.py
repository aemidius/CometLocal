"""
DocumentFormFiller para rellenar formularios CAE usando DocumentAnalysisResult.

v4.5.0: Fase 2 - Uso del análisis de documentos para rellenar campos de formulario.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import date

from backend.shared.models import (
    DocumentAnalysisResult,
    DocumentFormFillPlan,
    FormFieldValue,
    FormFillInstruction,
)

logger = logging.getLogger(__name__)

# v4.5.0: Formato estándar para fechas en formularios (configurable)
DATE_FORMAT = "YYYY-MM-DD"  # Formato ISO estándar para inputs de tipo date

# v4.6.0: Mapeo de campos semánticos a posibles textos de etiqueta (heurístico, extensible)
SEMANTIC_FIELD_LABELS = {
    "issue_date": [
        "Fecha de expedición",
        "Data d'expedició",
        "Fecha emisión",
        "Fecha de emisión",
        "Fecha de realización",
        "Fecha de reconocimiento",
        "Fecha",
    ],
    "expiry_date": [
        "Fecha de caducidad",
        "Data de caducitat",
        "Válido hasta",
        "Validez hasta",
        "Caduca el",
        "Válido hasta el",
        "Fecha de vencimiento",
    ],
    "worker_name": [
        "Trabajador",
        "Treballador",
        "Nombre del trabajador",
        "Nom del treballador",
        "Nombre",
        "Nom",
        "Trabajador/a",
    ],
}


def format_date_for_form(d: date, format_str: str = DATE_FORMAT) -> str:
    """
    Formatea una fecha para usar en un campo de formulario.
    
    Args:
        d: Fecha a formatear
        format_str: Formato deseado (por ahora solo "YYYY-MM-DD")
        
    Returns:
        Fecha formateada como string (ej. "2025-03-01")
    """
    if format_str == "YYYY-MM-DD":
        return d.strftime("%Y-%m-%d")
    else:
        # Fallback a ISO format
        return d.isoformat()


class DocumentFormFiller:
    """
    Constructor de planes e instrucciones para rellenar formularios CAE.
    
    v4.5.0: Convierte DocumentAnalysisResult en instrucciones ejecutables.
    """
    
    def build_plan_from_analysis(
        self,
        analysis: DocumentAnalysisResult,
        expected_doc_type: Optional[str] = None,
    ) -> DocumentFormFillPlan:
        """
        Construye un plan de rellenado a partir del análisis de un documento.
        
        Args:
            analysis: Resultado del análisis del documento
            expected_doc_type: Tipo de documento esperado (opcional, para validación)
            
        Returns:
            DocumentFormFillPlan con los campos a rellenar
        """
        plan = DocumentFormFillPlan(
            doc_type=analysis.doc_type or expected_doc_type,
            worker_name=analysis.worker_name,
            fields=[],
            warnings=[],
            confidence=0.0,
        )
        
        # Arrastrar warnings del análisis
        plan.warnings.extend(analysis.warnings)
        
        # Construir campos a rellenar
        fields_added = 0
        target_fields = 3  # issue_date, expiry_date, worker_name
        
        # issue_date
        if analysis.issue_date:
            issue_value = format_date_for_form(analysis.issue_date)
            # v4.6.0: Añadir possible_labels para rellenado por etiquetas
            possible_labels = SEMANTIC_FIELD_LABELS.get("issue_date", [])
            plan.fields.append(FormFieldValue(
                semantic_field="issue_date",
                value=issue_value,
                source="document_analysis",
                confidence=analysis.confidence,
                possible_labels=possible_labels,
            ))
            fields_added += 1
        else:
            plan.warnings.append("No se encontró fecha de emisión en el documento")
        
        # expiry_date
        if analysis.expiry_date:
            expiry_value = format_date_for_form(analysis.expiry_date)
            # v4.6.0: Añadir possible_labels para rellenado por etiquetas
            possible_labels = SEMANTIC_FIELD_LABELS.get("expiry_date", [])
            plan.fields.append(FormFieldValue(
                semantic_field="expiry_date",
                value=expiry_value,
                source="document_analysis",
                confidence=analysis.confidence,
                possible_labels=possible_labels,
            ))
            fields_added += 1
        else:
            plan.warnings.append("No se encontró fecha de caducidad en el documento")
        
        # worker_name
        if analysis.worker_name:
            # v4.6.0: Añadir possible_labels para rellenado por etiquetas
            possible_labels = SEMANTIC_FIELD_LABELS.get("worker_name", [])
            plan.fields.append(FormFieldValue(
                semantic_field="worker_name",
                value=analysis.worker_name,
                source="document_analysis",
                confidence=analysis.confidence,
                possible_labels=possible_labels,
            ))
            fields_added += 1
        else:
            plan.warnings.append("No se encontró nombre del trabajador en el documento")
        
        # Calcular confidence del plan
        # Basado en la confidence del análisis y la proporción de campos rellenos
        if target_fields > 0:
            fields_ratio = fields_added / target_fields
            plan.confidence = analysis.confidence * fields_ratio
        else:
            plan.confidence = 0.0
        
        logger.debug(
            f"[form-filler] Plan construido: {fields_added}/{target_fields} campos, "
            f"confidence={plan.confidence:.2f}"
        )
        
        return plan
    
    def build_instruction_via_mapper(
        self,
        plan: DocumentFormFillPlan,
        mapped_fields: Dict[str, "MappedField"],
    ) -> Optional[FormFillInstruction]:
        """
        Construye una FormFillInstruction usando campos mapeados heurísticamente.
        
        v4.6.0: Crea instrucción desde mapeo automático sin LLM.
        
        Args:
            plan: Plan de rellenado con campos semánticos
            mapped_fields: Diccionario de semantic_field -> MappedField
            
        Returns:
            FormFillInstruction o None si no hay campos mapeados
        """
        field_selectors: Dict[str, str] = {}
        label_hints: Dict[str, List[str]] = {}
        
        for field in plan.fields:
            semantic_field = field.semantic_field
            mapped = mapped_fields.get(semantic_field)
            
            if mapped and mapped.selector:
                field_selectors[semantic_field] = mapped.selector
                if mapped.label_text:
                    # Añadir el label encontrado como hint
                    label_hints[semantic_field] = [mapped.label_text]
        
        if not field_selectors:
            logger.debug("[form-filler] No se encontraron campos mapeados")
            return None
        
        instruction = FormFillInstruction(
            field_selectors=field_selectors,
            plan=plan,
            form_context="cae_upload_auto",  # v4.6.0: Mapeo automático
            label_hints=label_hints,
        )
        
        logger.info(f"[form-filler] Instruction built via mapper: {len(field_selectors)} fields")
        return instruction
    
    def build_instruction_for_cae_upload_form(
        self,
        plan: DocumentFormFillPlan,
        form_variant: str = "default",
        dom_structure: Optional[Dict[str, Any]] = None,  # v4.6.0
    ) -> Optional[FormFillInstruction]:
        """
        Construye una instrucción ejecutable para un formulario CAE de subida.
        
        Args:
            plan: Plan de rellenado con los campos y valores
            form_variant: Variante del formulario (por ahora solo "default")
            
        Returns:
            FormFillInstruction si hay campos a rellenar, None en caso contrario
        """
        if not plan.fields:
            logger.debug("[form-filler] Plan vacío, no se genera instrucción")
            return None
        
        # v4.5.0: Mapeo fijo para formulario CAE genérico de ejemplo
        # Más adelante podremos leer esto desde configuración o detectarlo dinámicamente
        field_selectors: Dict[str, str] = {}
        
        if form_variant == "default":
            # Mapeo genérico para formulario CAE de ejemplo
            # En producción, esto podría venir de configuración o detección automática
            field_selectors = {
                "issue_date": 'input[name="issue_date"], input[id="issue_date"], #issue_date',
                "expiry_date": 'input[name="expiry_date"], input[id="expiry_date"], #expiry_date',
                "worker_name": 'input[name="worker_name"], input[id="worker_name"], #worker_name',
            }
        else:
            logger.warning(f"[form-filler] Form variant '{form_variant}' no reconocido, usando default")
            field_selectors = {
                "issue_date": 'input[name="issue_date"], input[id="issue_date"], #issue_date',
                "expiry_date": 'input[name="expiry_date"], input[id="expiry_date"], #expiry_date',
                "worker_name": 'input[name="worker_name"], input[id="worker_name"], #worker_name',
            }
        
        # Filtrar solo los campos que están en el plan y tienen selector
        available_selectors: Dict[str, str] = {}
        for field in plan.fields:
            semantic_field = field.semantic_field
            if semantic_field in field_selectors:
                # Para v4.5.0, usamos el primer selector de la lista (separados por coma)
                # Más adelante podríamos intentar varios selectores
                selector = field_selectors[semantic_field].split(',')[0].strip()
                available_selectors[semantic_field] = selector
        
        # v4.6.0: Construir label_hints desde possible_labels de los campos
        label_hints: Dict[str, List[str]] = {}
        for field in plan.fields:
            if field.possible_labels:
                label_hints[field.semantic_field] = field.possible_labels
        
        if not available_selectors and not label_hints:
            logger.debug("[form-filler] No hay selectores ni labels disponibles para los campos del plan")
            return None
        
        instruction = FormFillInstruction(
            field_selectors=available_selectors,
            plan=plan,
            form_context=f"cae_upload_{form_variant}",
            label_hints=label_hints,  # v4.6.0
        )
        
        logger.info(
            f"[form-filler] Instrucción generada para {len(available_selectors)} campos "
            f"(form_variant={form_variant})"
        )
        
        return instruction

