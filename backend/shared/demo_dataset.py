"""
SPRINT C2.31: Dataset demo para onboarding rápido.

Crea un dataset controlado para que usuarios nuevos prueben CometLocal
en ≤5 minutos sin configurar datos reales.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from backend.config import DATA_DIR
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.shared.schedule_models import ScheduleV1, ScheduleStore
from backend.shared.tenant_paths import tenant_root
from backend.shared.tenant_context import compute_tenant_from_coordination_context


DEMO_OWN_COMPANY_KEY = "DEMO_COMPANY"
DEMO_PLATFORM_KEY = "demo_platform"
DEMO_COORDINATED_COMPANY_KEY = "DEMO_CLIENT"


def ensure_demo_dataset() -> dict:
    """
    Asegura que el dataset demo existe y está completo.
    
    Returns:
        Dict con información del dataset demo creado
    """
    demo_dir = DATA_DIR / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    
    # Calcular tenant_id para demo
    tenant_id = compute_tenant_from_coordination_context(
        own_company_key=DEMO_OWN_COMPANY_KEY,
        platform_key=DEMO_PLATFORM_KEY,
        coordinated_company_key=DEMO_COORDINATED_COMPANY_KEY,
    )
    
    results = {
        "tenant_id": tenant_id,
        "own_company_key": DEMO_OWN_COMPANY_KEY,
        "platform_key": DEMO_PLATFORM_KEY,
        "coordinated_company_key": DEMO_COORDINATED_COMPANY_KEY,
        "created": False,
        "org_created": False,
        "platform_created": False,
        "types_created": False,
        "docs_created": False,
        "plan_created": False,
        "schedule_created": False,
    }
    
    # 1. Crear org.json con empresa demo
    store = ConfigStoreV1(base_dir=DATA_DIR)
    org = store.load_org()
    
    # Si no existe o no tiene la empresa demo, crearla
    if not org or org.tax_id != DEMO_OWN_COMPANY_KEY:
        from backend.repository.config_store_v1 import OrgConfigV1
        demo_org = OrgConfigV1(
            tax_id=DEMO_OWN_COMPANY_KEY,
            legal_name="Empresa Demo SL",
            vat_id=DEMO_OWN_COMPANY_KEY,
        )
        store.save_org(demo_org)
        results["org_created"] = True
    
    # 2. Crear platforms.json con plataforma demo
    platforms_data = store.load_platforms()
    demo_platform_exists = any(p.key == DEMO_PLATFORM_KEY for p in platforms_data.platforms)
    
    if not demo_platform_exists:
        from backend.repository.config_store_v1 import PlatformConfigV1, CoordinationConfigV1
        
        demo_coordination = CoordinationConfigV1(
            client_code=DEMO_COORDINATED_COMPANY_KEY,
            label="Cliente Demo SA",
            vat_id=DEMO_COORDINATED_COMPANY_KEY,
        )
        
        demo_platform = PlatformConfigV1(
            key=DEMO_PLATFORM_KEY,
            name="Plataforma Demo",
            coordinations=[demo_coordination],
        )
        
        platforms_data.platforms.append(demo_platform)
        store.save_platforms(platforms_data)
        results["platform_created"] = True
    
    # 3. Crear tipos de documentos demo
    repo_store = DocumentRepositoryStoreV1(base_dir=DATA_DIR)
    types = repo_store.list_types()
    
    demo_types = [
        {
            "type_id": "demo_ss_receipt",
            "name": "Recibo Seguridad Social (Demo)",
            "category": "worker",
            "frequency": "monthly",
            "subject": "worker",
        },
        {
            "type_id": "demo_contract",
            "name": "Contrato (Demo)",
            "category": "worker",
            "frequency": "on_demand",
            "subject": "worker",
        },
        {
            "type_id": "demo_insurance",
            "name": "Seguro (Demo)",
            "category": "company",
            "frequency": "yearly",
            "subject": "company",
        },
    ]
    
    existing_type_ids = {t.type_id for t in types}
    created_types = []
    
    for demo_type in demo_types:
        if demo_type["type_id"] not in existing_type_ids:
            from backend.repository.document_repository_store_v1 import DocumentTypeV1
            
            from backend.shared.document_repository_v1 import ValidityPolicyV1, MonthlyValidityConfigV1
            
            type_obj = DocumentTypeV1(
                type_id=demo_type["type_id"],
                name=demo_type["name"],
                description=f"Tipo demo: {demo_type['name']}",
                scope=demo_type["subject"],
                validity_policy=ValidityPolicyV1(
                    mode="monthly" if demo_type["frequency"] == "monthly" else "on_demand",
                    basis="name_date",
                    monthly=MonthlyValidityConfigV1(
                        month_source="name_date",
                        valid_from="period_start",
                        valid_to="period_end",
                        grace_days=0
                    ) if demo_type["frequency"] == "monthly" else None
                ),
                required_fields=[],
                platform_aliases=[],
                active=True
            )
            repo_store.create_type(type_obj)
            created_types.append(demo_type["type_id"])
    
    if created_types:
        results["types_created"] = True
        results["type_ids"] = created_types
    
    # 4. Crear documentos demo (sin PDFs reales, solo metadata)
    docs = repo_store.list_documents()
    existing_doc_ids = {d.doc_id for d in docs}
    
    demo_docs = [
        {
            "doc_id": "demo_doc_ss_001",
            "type_id": "demo_ss_receipt",
            "period": date.today().strftime("%Y-%m"),
            "subject_id": "demo_worker_001",
        },
        {
            "doc_id": "demo_doc_contract_001",
            "type_id": "demo_contract",
            "period": None,
            "subject_id": "demo_worker_001",
        },
        {
            "doc_id": "demo_doc_insurance_001",
            "type_id": "demo_insurance",
            "period": date.today().strftime("%Y"),
            "subject_id": "company",
        },
    ]
    
    created_docs = []
    for demo_doc in demo_docs:
        if demo_doc["doc_id"] not in existing_doc_ids:
            from backend.repository.document_repository_store_v1 import DocumentInstanceV1
            
            from backend.shared.document_repository_v1 import DocumentScopeV1
            
            doc_obj = DocumentInstanceV1(
                doc_id=demo_doc["doc_id"],
                type_id=demo_doc["type_id"],
                scope=DocumentScopeV1(
                    subject_id=demo_doc["subject_id"],
                    period=demo_doc["period"]
                ),
                status="pending",
                created_at=datetime.now(),
            )
            repo_store.save_document(doc_obj)
            created_docs.append(demo_doc["doc_id"])
    
    if created_docs:
        results["docs_created"] = True
        results["doc_ids"] = created_docs
    
    # 5. Crear plan CAE demo (fake, solo metadata)
    tenant_dir = tenant_root(DATA_DIR, tenant_id)
    runs_dir = tenant_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    
    demo_plan_id = "demo_plan_001"
    plan_dir = runs_dir / demo_plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)
    
    plan_data = {
        "plan_id": demo_plan_id,
        "created_at": datetime.now().isoformat(),
        "status": "ready",
        "items": [
            {
                "item_id": "demo_item_001",
                "type_id": "demo_ss_receipt",
                "action": "AUTO_UPLOAD",
                "status": "pending",
            }
        ],
        "metadata": {
            "demo": True,
            "description": "Plan demo para onboarding",
        },
    }
    
    plan_file = plan_dir / "plan_response.json"
    if not plan_file.exists():
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, indent=2, ensure_ascii=False)
        results["plan_created"] = True
        results["plan_id"] = demo_plan_id
    
    # 6. Crear schedule demo (disabled por defecto)
    schedule_store = ScheduleStore(DATA_DIR, tenant_id)
    schedules = schedule_store.list_schedules()
    
    demo_schedule_id = "demo_schedule_001"
    demo_schedule_exists = any(s.schedule_id == demo_schedule_id for s in schedules)
    
    if not demo_schedule_exists:
        demo_schedule = ScheduleV1(
            schedule_id=demo_schedule_id,
            enabled=False,  # Disabled por defecto
            plan_id=demo_plan_id,
            dry_run=True,
            cadence="daily",
            at_time="09:00",
            weekday=None,
            own_company_key=DEMO_OWN_COMPANY_KEY,
            platform_key=DEMO_PLATFORM_KEY,
            coordinated_company_key=DEMO_COORDINATED_COMPANY_KEY,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        schedule_store.save_schedule(demo_schedule)
        results["schedule_created"] = True
        results["schedule_id"] = demo_schedule_id
    
    results["created"] = any([
        results["org_created"],
        results["platform_created"],
        results["types_created"],
        results["docs_created"],
        results["plan_created"],
        results["schedule_created"],
    ])
    
    return results


def is_demo_mode() -> bool:
    """Verifica si estamos en modo demo."""
    return os.getenv("ENVIRONMENT", "").lower() == "demo"


def get_demo_context() -> dict:
    """Retorna el contexto demo para auto-selección."""
    return {
        "own_company_key": DEMO_OWN_COMPANY_KEY,
        "platform_key": DEMO_PLATFORM_KEY,
        "coordinated_company_key": DEMO_COORDINATED_COMPANY_KEY,
    }
