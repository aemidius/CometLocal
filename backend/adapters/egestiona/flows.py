from __future__ import annotations

import json as pyjson  # HOTFIX C2.13.3: Usar alias para evitar shadowing
import re
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from backend.adapters.egestiona.profile import EgestionaProfileV1
from backend.adapters.egestiona.targets import build_targets_from_selectors

# Selector post-login robusto: verificar que salimos de login (no usar texto específico)
POST_LOGIN_SELECTOR_DEFAULT = None  # No usar selector de texto, verificar navegación
from backend.executor.runtime_h4 import ExecutorRuntimeH4
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.secrets_store_v1 import SecretsStoreV1
from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
    ConditionV1,
    ErrorSeverityV1,
    TargetKindV1,
    TargetV1,
)
from backend.shared.platforms_v1 import SelectorSpecV1
from backend.repository.document_repository_v1 import DocumentRepositoryV1
from backend.shared.file_ref_v1 import build_shared_ref
from backend.adapters.egestiona.frame_scan_headful import (
    run_find_enviar_doc_in_all_frames_headful,
    run_frames_screenshots_and_find_tile_headful,
    run_list_pending_documents_readonly_headful,
    run_discovery_pending_table_headful,
    run_open_pending_document_details_readonly_headful,
    run_upload_pending_document_scoped_headful,
)
from backend.adapters.egestiona.match_pending_headful import (
    run_match_pending_documents_readonly_headful,
)
from backend.adapters.egestiona.stability_test_pending import (
    run_stability_test_pending_readonly,
)
from backend.adapters.egestiona.submission_plan_headful import (
    run_build_submission_plan_readonly_headful,
)
# run_execute_submission_plan_scoped_headful se importa desde frame_scan_headful si es necesario
# from backend.adapters.egestiona.execute_plan_headful import (
#     run_execute_submission_plan_scoped_headful,
# )


def run_login_and_snapshot(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    headless: bool = True,
    execution_mode: str = "production",
    fail_fast: bool = False,
) -> str:
    """
    Ejecuta login determinista (sin LLM) usando Config Store + Secrets Store.
    Devuelve run_id.
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if plat is None:
        # backward-compat: aceptar "egestiona_*"
        plat = next((p for p in platforms.platforms if str(p.key or "").lower().startswith(str(platform).lower())), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if coord is None:
        coord = next((c for c in plat.coordinations if str(c.label or "").lower() == str(coordination).lower()), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    def _looks_like_selector(v: str) -> bool:
        vv = (v or "").strip()
        if not vv:
            return False
        # Playwright text selector
        if vv.startswith("text=") or vv.startswith("text=\"") or vv.startswith("text='"):
            return True
        # CSS-ish / xpath-ish cues
        return any(tok in vv for tok in ("[", "]", "#", ".", "=", ":", "//"))

    # Post-login check: usar verificación robusta de que salimos de la página de login
    if not coord.post_login_selector:
        # No usar selector específico, verificar navegación en las postcondiciones
        coord.post_login_selector = None

    # URL: login_url (requerida) > override > platform.base_url > default
    if plat.login_url:
        url = plat.login_url
    elif coord.url_override:
        url = coord.url_override
    elif plat.base_url:
        url = plat.base_url
    else:
        raise ValueError(
            f"No login URL configured for platform '{plat.key}'. "
            "Please set 'login_url' in platforms.json with the actual login URL from your browser. "
            "Example: 'login_url': 'https://your-tenant.egestiona.es/login?origen=subcontrata'"
        )

    # FIX H8.A2+: si faltan selectors, autocompletar defaults estables y (opcional) persistir.
    autofilled = False
    lf = plat.login_fields
    if lf.client_code_selector is None:
        lf.client_code_selector = SelectorSpecV1(kind="css", value='input[name="ClientName"]')
        autofilled = True
    if lf.username_selector is None:
        lf.username_selector = SelectorSpecV1(kind="css", value='input[name="Username"]')
        autofilled = True
    if lf.password_selector is None:
        lf.password_selector = SelectorSpecV1(kind="css", value='input[name="Password"]')
        autofilled = True
    if lf.submit_selector is None:
        lf.submit_selector = SelectorSpecV1(kind="css", value='button[type="submit"]')
        autofilled = True

    if autofilled:
        # write-back para evitar 400 permanente y dejar config estable
        store.save_platforms(platforms)

    targets = build_targets_from_selectors(
        client_code_selector=plat.login_fields.client_code_selector,
        username_selector=plat.login_fields.username_selector,
        password_selector=plat.login_fields.password_selector,
        submit_selector=plat.login_fields.submit_selector,
        post_login_selector=coord.post_login_selector,
    )

    actions: list[ActionSpecV1] = []

    actions.append(
        ActionSpecV1(
            action_id="eg_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    # Resolver credenciales (NO 500; error claro si falta secret requerido)
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    password_val = secrets.get_secret(password_ref)
    if password_val is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="eg_fill_client",
                kind=ActionKindV1.fill,
                target=targets.client_code,
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": targets.client_code.model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="eg_fill_user",
            kind=ActionKindV1.fill,
            target=targets.username,
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.username.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": targets.username.model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    # password: secret_ref (no viaja en claro por config; se resuelve en runtime)
    actions.append(
        ActionSpecV1(
            action_id="eg_fill_pass",
            kind=ActionKindV1.fill,
            target=targets.password,
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.password.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": targets.password.model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="eg_click_submit",
            kind=ActionKindV1.click,
            target=targets.submit,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": targets.submit.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": targets.submit.model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # Último paso (determinista): esperar que el login termine y naveguemos fuera de la página de login.
    # IMPORTANTE: este es el paso final; si se cumple, el runtime termina success y no evalúa policies después.
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_post_login_check",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                # Verificar que salimos de la página de login (postcondición crítica)
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
                # Verificar que el formulario de login desapareció
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.critical, description="Login form must be gone"),
                # Verificar que el botón submit desapareció
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.submit.model_dump()}, severity=ErrorSeverityV1.critical, description="Submit button must be gone"),
            ],
            timeout_ms=30000,  # Más tiempo para esperar la navegación post-login
            criticality="critical",
        )
    )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode=execution_mode,
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=fail_fast, execution_mode="deterministic")
    return run_dir.name


router = APIRouter(tags=["egestiona"])


def run_upload_document_cae(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    file_path: str | Path,
    headless: bool = True,
    execution_mode: str = "production",
    fail_fast: bool = False,
) -> str:
    """
    Ejecuta flujo completo: login + navegación a CAE + upload de documento + validación.
    Devuelve run_id.
    
    Args:
        file_path: Ruta local al archivo a subir (se registrará en el repositorio si no existe)
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)
    
    # Registrar documento si no existe
    repo = DocumentRepositoryV1(project_root=Path(base).parent, data_root="data")
    file_path_obj = Path(file_path).resolve()
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Construir file_ref esperado
    company_id = "demo"
    namespace = "samples"
    name = file_path_obj.stem
    file_ref = f"doc:company:{company_id}:company_docs:{namespace}:{name}"
    
    # Intentar registrar documento (si ya existe, validar que el archivo es el mismo)
    try:
        # Verificar si ya existe
        try:
            entry = repo.validate(file_ref)
            # Si existe y es válido, usar ese file_ref
        except (FileNotFoundError, ValueError):
            # No existe o no es válido, registrar nuevo
            file_ref = repo.register(
                path=file_path_obj,
                metadata={
                    "company_id": company_id,
                    "doc_type": "test_document",
                    "namespace": namespace,
                    "name": name,
                    "tags": ["egestiona_upload_test"],
                },
            )
    except Exception as e:
        raise ValueError(f"Failed to register/validate document: {e}")

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if plat is None:
        plat = next((p for p in platforms.platforms if str(p.key or "").lower().startswith(str(platform).lower())), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if coord is None:
        coord = next((c for c in plat.coordinations if str(c.label or "").lower() == str(coordination).lower()), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    def _looks_like_selector(v: str) -> bool:
        vv = (v or "").strip()
        if not vv:
            return False
        if vv.startswith("text=") or vv.startswith("text=\"") or vv.startswith("text='"):
            return True
        return any(tok in vv for tok in ("[", "]", "#", ".", "=", ":", "//"))

    if (not coord.post_login_selector) or (coord.post_login_selector and not _looks_like_selector(coord.post_login_selector.value)):
        coord.post_login_selector = SelectorSpecV1(kind="css", value=POST_LOGIN_SELECTOR_DEFAULT)
        store.save_platforms(platforms)

    # URL: login_url (requerida) > override > platform.base_url > default
    if plat.login_url:
        url = plat.login_url
    elif coord.url_override:
        url = coord.url_override
    elif plat.base_url:
        url = plat.base_url
    else:
        raise ValueError(
            f"No login URL configured for platform '{plat.key}'. "
            "Please set 'login_url' in platforms.json with the actual login URL from your browser. "
            "Example: 'login_url': 'https://your-tenant.egestiona.es/login?origen=subcontrata'"
        )

    autofilled = False
    lf = plat.login_fields
    if lf.client_code_selector is None:
        lf.client_code_selector = SelectorSpecV1(kind="css", value='input[name="ClientName"]')
        autofilled = True
    if lf.username_selector is None:
        lf.username_selector = SelectorSpecV1(kind="css", value='input[name="Username"]')
        autofilled = True
    if lf.password_selector is None:
        lf.password_selector = SelectorSpecV1(kind="css", value='input[name="Password"]')
        autofilled = True
    if lf.submit_selector is None:
        lf.submit_selector = SelectorSpecV1(kind="css", value='button[type="submit"]')
        autofilled = True

    if autofilled:
        store.save_platforms(platforms)

    targets = build_targets_from_selectors(
        client_code_selector=plat.login_fields.client_code_selector,
        username_selector=plat.login_fields.username_selector,
        password_selector=plat.login_fields.password_selector,
        submit_selector=plat.login_fields.submit_selector,
        post_login_selector=coord.post_login_selector,
    )

    # Resolver credenciales
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    actions: list[ActionSpecV1] = []

    # 1. Navegación inicial
    actions.append(
        ActionSpecV1(
            action_id="eg_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    # 2. Login
    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="eg_fill_client",
                kind=ActionKindV1.fill,
                target=targets.client_code,
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": targets.client_code.model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="eg_fill_user",
            kind=ActionKindV1.fill,
            target=targets.username,
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.username.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": targets.username.model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="eg_fill_pass",
            kind=ActionKindV1.fill,
            target=targets.password,
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.password.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": targets.password.model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="eg_click_submit",
            kind=ActionKindV1.click,
            target=targets.submit,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": targets.submit.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": targets.submit.model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 3. Esperar post-login
    # Nota: Agregamos url_matches como postcondición fuerte para cumplir U5
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_post_login_check",
            kind=ActionKindV1.wait_for,
            target=targets.post_login,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.post_login.model_dump()}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.critical, description="Login form must be gone"),
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="critical",
        )
    )

    # 4. Navegación a CAE - usar selectores robustos basados en texto/roles
    # Estrategia: buscar enlaces o botones que contengan "CAE", "Documentación", "Subir", etc.
    # Usaremos selectores de texto como fallback robusto
    cae_link_target = TargetV1(
        type=TargetKindV1.text,
        text="CAE",
        exact=True,
        normalize_ws=True,
    )
    
    actions.append(
        ActionSpecV1(
            action_id="eg_nav_cae",
            kind=ActionKindV1.click,
            target=cae_link_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": cae_link_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": cae_link_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 5. Esperar a que cargue la página de CAE/upload
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_cae_page",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # 6. Localizar input file - estrategia múltiple: input[type="file"], botones con texto "Subir"/"Seleccionar", etc.
    # Prioridad: input[type="file"] visible > botón con aria-label/role > texto "Subir"/"Seleccionar"
    file_input_target = TargetV1(
        type=TargetKindV1.css,
        selector='input[type="file"]',
    )
    
    actions.append(
        ActionSpecV1(
            action_id="eg_upload_file",
            kind=ActionKindV1.upload,
            target=file_input_target,
            input={"file_ref": file_ref},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": file_input_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": file_input_target.model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.upload_completed, args={}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=30000,
            criticality="critical",
        )
    )

    # 7. Buscar y hacer click en botón "Subir"/"Enviar"/"Guardar" si existe
    # Estrategia: buscar botones con texto que contenga "Subir", "Enviar", "Guardar", "Cargar"
    submit_upload_target = TargetV1(
        type=TargetKindV1.text,
        text="Subir",
        exact=True,
        normalize_ws=True,
    )
    
    actions.append(
        ActionSpecV1(
            action_id="eg_click_submit_upload",
            kind=ActionKindV1.click,
            target=submit_upload_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": submit_upload_target.model_dump()}, severity=ErrorSeverityV1.warning),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": submit_upload_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.warning),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 8. Esperar confirmación - buscar mensajes de éxito, toasts, o cambios en la UI
    # Estrategia: buscar texto que indique éxito: "Cargado", "Correcto", "Éxito", "Documento subido", etc.
    # Nota: Hacemos esta acción menos crítica (normal) porque la confirmación puede variar en la UI real
    confirmation_target = TargetV1(
        type=TargetKindV1.text,
        text="Cargado",
        exact=True,
        normalize_ws=True,
    )
    
    actions.append(
        ActionSpecV1(
            action_id="eg_wait_confirmation",
            kind=ActionKindV1.wait_for,
            target=confirmation_target,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": confirmation_target.model_dump()}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=20000,
            criticality="normal",
        )
    )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode=execution_mode,
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=fail_fast, execution_mode="deterministic")
    return run_dir.name


def run_buscar_frames_dashboard(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    headless: bool = False,  # HEADFUL obligatorio para ver frames
) -> str:
    """
    BÚSQUEDA EN FRAMES: Localizar "Enviar Doc. Pendiente" en todos los frames del dashboard.
    - Login usando URL anterior (coordinate.egestiona.es)
    - Listar todos los frames
    - Buscar texto en cada frame
    - Capturar evidencia cuando se encuentre
    """
    if headless:
        raise ValueError("HEADFUL_REQUIRED: Frame search requires visible browser (headless=False)")

    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # Usar EXACTAMENTE la misma URL del run anterior exitoso
    url = "https://coordinate.egestiona.es/login?origen=subcontrata"
    print(f"[FRAME_SEARCH] Using EXACT URL from previous successful run: {url}")

    # Resolver credenciales
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    actions: list[ActionSpecV1] = []

    # 1. Login completo con URL exacta anterior
    actions.append(
        ActionSpecV1(
            action_id="frame_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="frame_fill_client",
                kind=ActionKindV1.fill,
                target=TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]'),
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="frame_fill_user",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Username"]'),
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="frame_fill_pass",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Password"]'),
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # SUBMIT DEL LOGIN
    actions.append(
        ActionSpecV1(
            action_id="frame_submit_login",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector='button[type="submit"]'),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 2. Esperar dashboard post-login
    actions.append(
        ActionSpecV1(
            action_id="frame_wait_dashboard",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="critical",  # Screenshot dashboard post-login OBLIGATORIA
        )
    )

    # 3. Espera adicional 3s para que cargue todo el contenido dinámico
    actions.append(
        ActionSpecV1(
            action_id="frame_wait_extra",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=3000,
            criticality="normal",  # Screenshot dashboard completo con contenido dinámico
        )
    )

    # 4. Buscar "Enviar Doc. Pendiente" en el frame principal (por si acaso)
    enviar_doc_target = TargetV1(type=TargetKindV1.text, text="Enviar Doc. Pendiente", exact=True, normalize_ws=True)
    actions.append(
        ActionSpecV1(
            action_id="frame_search_main",
            kind=ActionKindV1.wait_for,
            target=enviar_doc_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=3000,  # Timeout corto para búsqueda rápida
            criticality="normal",
        )
    )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode="production",
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=True, execution_mode="deterministic")
    return run_dir.name


def run_smoke_test_tenant_correcto(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    headless: bool = False,  # HEADFUL obligatorio para smoke test
) -> str:
    """
    SMOKE TEST: Verificar tenant correcto y existencia de "Enviar Doc. Pendiente".
    - Login en tenant correcto (grupoindukern.egestiona.com)
    - Verificar hostname post-login
    - Buscar "Enviar Doc. Pendiente" en todos los frames
    - Generar screenshots siempre
    """
    if headless:
        raise ValueError("HEADFUL_REQUIRED: Smoke test requires visible browser (headless=False)")

    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # URL: login_url prioritario (ahora apunta al tenant correcto)
    if plat.login_url:
        url = plat.login_url
    elif coord.url_override:
        url = coord.url_override
    elif plat.base_url and ("login" in plat.base_url.lower() or "egestiona.es" in plat.base_url.lower()):
        # Backward compatibility
        print(f"[MIGRATION] Using base_url as login_url for platform '{plat.key}': {plat.base_url}")
        url = plat.base_url
    else:
        raise ValueError(
            f"No login URL configured for platform '{plat.key}'. "
            "Please set 'login_url' in platforms.json with the actual login URL from your browser. "
            "Example: 'login_url': 'https://your-tenant.egestiona.es/login?origen=subcontrata'"
        )

    # Resolver credenciales
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    actions: list[ActionSpecV1] = []

    # 1. Login completo
    actions.append(
        ActionSpecV1(
            action_id="smoke_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="smoke_fill_client",
                kind=ActionKindV1.fill,
                target=TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]'),
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="smoke_fill_user",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Username"]'),
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="smoke_fill_pass",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Password"]'),
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # SUBMIT DEL LOGIN
    actions.append(
        ActionSpecV1(
            action_id="smoke_submit_login",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector='button[type="submit"]'),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 2. Esperar dashboard post-login (CRITICAL para asegurar screenshot)
    actions.append(
        ActionSpecV1(
            action_id="smoke_wait_dashboard",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="critical",  # Screenshot dashboard post-login OBLIGATORIA
        )
    )

    # 3. Buscar "Enviar Doc. Pendiente" en el dashboard (NORMAL para no fallar si no existe)
    enviar_doc_target = TargetV1(type=TargetKindV1.text, text="Enviar Doc. Pendiente", exact=True, normalize_ws=True)
    actions.append(
        ActionSpecV1(
            action_id="smoke_find_enviar_doc",
            kind=ActionKindV1.wait_for,
            target=enviar_doc_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=5000,  # Timeout corto para búsqueda
            criticality="normal",  # No falla si no encuentra el texto
        )
    )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode="production",
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=True, execution_mode="deterministic")
    return run_dir.name


def run_localizacion_geometrica(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    headless: bool = False,  # HEADFUL obligatorio para diagnóstico visual
) -> str:
    """
    LOCALIZACIÓN GEOMÉTRICA: encontrar elementos clickables por bounding boxes y geometría.
    - Enumerar todos los elementos clickables en zona central
    - Crear overlay visual con índices
    - Usar heurística para seleccionar candidato más probable
    - Click y observar cambios
    """
    if headless:
        raise ValueError("HEADFUL_REQUIRED: Geometry location requires visible browser (headless=False)")

    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # URL: login_url (requerida) > override > platform.base_url > default
    # MIGRACIÓN AUTOMÁTICA: Si login_url es null pero base_url parece URL de login, usar base_url
    if plat.login_url:
        url = plat.login_url
    elif coord.url_override:
        url = coord.url_override
    elif plat.base_url and ("login" in plat.base_url.lower() or "egestiona.es" in plat.base_url.lower()):
        # Backward compatibility: si base_url parece ser una URL de login, usarla como login_url
        print(f"[MIGRATION] Using base_url as login_url for platform '{plat.key}': {plat.base_url}")
        url = plat.base_url
    else:
        raise ValueError(
            f"No login URL configured for platform '{plat.key}'. "
            "Please set 'login_url' in platforms.json with the actual login URL from your browser. "
            "Example: 'login_url': 'https://your-tenant.egestiona.es/login?origen=subcontrata'"
        )

    # Resolver credenciales (solo para login)
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    actions: list[ActionSpecV1] = []

    # 1. Login completo
    actions.append(
        ActionSpecV1(
            action_id="geom_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="geom_fill_client",
                kind=ActionKindV1.fill,
                target=TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]'),
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="geom_fill_user",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Username"]'),
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="geom_fill_pass",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Password"]'),
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # SUBMIT DEL LOGIN
    actions.append(
        ActionSpecV1(
            action_id="geom_submit_login",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector='button[type="submit"]'),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 2. Esperar dashboard completo post-login (3 segundos adicionales)
    actions.append(
        ActionSpecV1(
            action_id="geom_wait_dashboard",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="normal",  # Screenshot dashboard completo + enumeración de clickables
        )
    )

    # 3. Esperar 3 segundos adicionales con dashboard visible
    actions.append(
        ActionSpecV1(
            action_id="geom_wait_extra",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=3000,
            criticality="normal",  # Screenshot dashboard final (01_dashboard.png)
        )
    )

    # 4. Intentar click en elementos del menú lateral (fallback conocido)
    # Como último recurso, intentar click en "Inicio" para verificar que funciona
    actions.append(
        ActionSpecV1(
            action_id="geom_click_menu_inicio",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.text, text="Inicio", exact=True, normalize_ws=True),
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.text, selector=None, role=None, name=None, exact=True, text="Inicio", normalize_ws=True, testid=None, inner_target=None, base_target=None, index=None, url=None).model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": TargetV1(type=TargetKindV1.text, selector=None, role=None, name=None, exact=True, text="Inicio", normalize_ws=True, testid=None, inner_target=None, base_target=None, index=None, url=None).model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=5000,
            criticality="normal",  # Screenshot después del click en "Inicio" del menú
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="geom_wait_final",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=3000,
            criticality="normal",  # Screenshot final después del intento de click
        )
    )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode="production",
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=True, execution_mode="deterministic")
    return run_dir.name


def run_diagnostico_icono_central(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    headless: bool = False,  # HEADFUL obligatorio para diagnóstico visual
) -> str:
    """
    DIAGNÓSTICO DEL ICONO CENTRAL: encontrar y activar el icono "Enviar Doc. Pendiente" del dashboard.
    - Ruta canónica: login -> dashboard -> click icono central
    - Diagnosticar dónde carga el contenido (iframe vs mismo DOM)
    - NO usar menú lateral salvo fallback
    """
    if headless:
        raise ValueError("HEADFUL_REQUIRED: Diagnosis mode requires visible browser (headless=False)")

    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # URL: login_url (requerida) > override > platform.base_url > default
    # MIGRACIÓN AUTOMÁTICA: Si login_url es null pero base_url parece URL de login, usar base_url
    if plat.login_url:
        url = plat.login_url
    elif coord.url_override:
        url = coord.url_override
    elif plat.base_url and ("login" in plat.base_url.lower() or "egestiona.es" in plat.base_url.lower()):
        # Backward compatibility: si base_url parece ser una URL de login, usarla como login_url
        print(f"[MIGRATION] Using base_url as login_url for platform '{plat.key}': {plat.base_url}")
        url = plat.base_url
    else:
        raise ValueError(
            f"No login URL configured for platform '{plat.key}'. "
            "Please set 'login_url' in platforms.json with the actual login URL from your browser. "
            "Example: 'login_url': 'https://your-tenant.egestiona.es/login?origen=subcontrata'"
        )

    # Resolver credenciales (solo para login)
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    actions: list[ActionSpecV1] = []

    # 1. Login completo
    actions.append(
        ActionSpecV1(
            action_id="icon_diag_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="icon_diag_fill_client",
                kind=ActionKindV1.fill,
                target=TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]'),
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="icon_diag_fill_user",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Username"]'),
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="icon_diag_fill_pass",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Password"]'),
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # SUBMIT DEL LOGIN
    actions.append(
        ActionSpecV1(
            action_id="icon_diag_submit_login",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector='button[type="submit"]'),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 2. Esperar dashboard completo post-login
    actions.append(
        ActionSpecV1(
            action_id="icon_diag_wait_dashboard",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="critical",  # Screenshot dashboard completo con iconos centrales
        )
    )

    # 3. Buscar icono central "Enviar Doc. Pendiente" por texto exacto
    enviar_doc_target = TargetV1(type=TargetKindV1.text, text="Enviar Doc. Pendiente", exact=True, normalize_ws=True)
    actions.append(
        ActionSpecV1(
            action_id="icon_diag_find_central_icon",
            kind=ActionKindV1.wait_for,
            target=enviar_doc_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": enviar_doc_target.model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": enviar_doc_target.model_dump()}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=10000,
            criticality="normal",  # Screenshot dashboard con icono localizado
        )
    )

    # 4. Click en el icono central "Enviar Doc. Pendiente"
    actions.append(
        ActionSpecV1(
            action_id="icon_diag_click_central_icon",
            kind=ActionKindV1.click,
            target=enviar_doc_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": enviar_doc_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": enviar_doc_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=10000,
            criticality="normal",  # Screenshot después del click en icono central
        )
    )

    # 5. Esperar que cargue el contenido (5 segundos)
    actions.append(
        ActionSpecV1(
            action_id="icon_diag_wait_content_load",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=5000,
            criticality="normal",  # Screenshot del resultado final
        )
    )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode="production",
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=True, execution_mode="deterministic")
    return run_dir.name


def run_diagnostico_paridad(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    headless: bool = False,  # HEADFUL obligatorio para diagnóstico visual
) -> str:
    """
    DIAGNÓSTICO DE PARIDAD: investigar por qué iframe#id_contenido no carga contenido.
    - Captura información de paridad (URL, title, frames, cookies)
    - Secuencia de clicks "humanos" para intentar activar carga
    - Diagnóstico detallado del iframe y elementos de menú
    """
    if headless:
        raise ValueError("HEADFUL_REQUIRED: Diagnosis mode requires visible browser (headless=False)")

    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # URL: login_url (requerida) > override > platform.base_url > default
    # MIGRACIÓN AUTOMÁTICA: Si login_url es null pero base_url parece URL de login, usar base_url
    if plat.login_url:
        url = plat.login_url
    elif coord.url_override:
        url = coord.url_override
    elif plat.base_url and ("login" in plat.base_url.lower() or "egestiona.es" in plat.base_url.lower()):
        # Backward compatibility: si base_url parece ser una URL de login, usarla como login_url
        print(f"[MIGRATION] Using base_url as login_url for platform '{plat.key}': {plat.base_url}")
        url = plat.base_url
    else:
        raise ValueError(
            f"No login URL configured for platform '{plat.key}'. "
            "Please set 'login_url' in platforms.json with the actual login URL from your browser. "
            "Example: 'login_url': 'https://your-tenant.egestiona.es/login?origen=subcontrata'"
        )

    # Resolver credenciales (solo para login)
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    actions: list[ActionSpecV1] = []

    # 1. Login (solo campos necesarios, NO submit para discovery)
    actions.append(
        ActionSpecV1(
            action_id="diag_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="diag_fill_client",
                kind=ActionKindV1.fill,
                target=TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]'),
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="diag_fill_user",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Username"]'),
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="diag_fill_pass",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Password"]'),
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # SUBMIT DEL LOGIN
    actions.append(
        ActionSpecV1(
            action_id="diag_submit_login",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector='button[type="submit"]'),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 2. Esperar dashboard post-login
    actions.append(
        ActionSpecV1(
            action_id="diag_wait_dashboard",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="critical",  # Screenshot dashboard post-login + diagnóstico de paridad
        )
    )

    # 3. Secuencia de clicks "humanos" para diagnosticar carga iframe
    # Click "Inicio" -> espera 2s
    inicio_target = TargetV1(type=TargetKindV1.text, text="Inicio", exact=True, normalize_ws=True)
    actions.append(
        ActionSpecV1(
            action_id="diag_click_inicio_1",
            kind=ActionKindV1.click,
            target=inicio_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": inicio_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": inicio_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=5000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="diag_wait_after_inicio_1",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=2000,
            criticality="normal",  # Screenshot después de click "Inicio"
        )
    )

    # Click "Coordinación" -> espera 5s
    coordinacion_target = TargetV1(type=TargetKindV1.text, text="Coordinación", exact=True, normalize_ws=True)
    actions.append(
        ActionSpecV1(
            action_id="diag_click_coordinacion_1",
            kind=ActionKindV1.click,
            target=coordinacion_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": coordinacion_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": coordinacion_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=5000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="diag_wait_after_coordinacion_1",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=5000,
            criticality="normal",  # Screenshot después de click "Coordinación" (primera vez)
        )
    )

    # Click "Inicio" -> espera 2s (segunda vez)
    actions.append(
        ActionSpecV1(
            action_id="diag_click_inicio_2",
            kind=ActionKindV1.click,
            target=inicio_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": inicio_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": inicio_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=5000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="diag_wait_after_inicio_2",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=2000,
            criticality="normal",  # Screenshot después del segundo click "Inicio"
        )
    )

    # Click "Coordinación" -> espera 5s (segunda vez)
    actions.append(
        ActionSpecV1(
            action_id="diag_click_coordinacion_2",
            kind=ActionKindV1.click,
            target=coordinacion_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": coordinacion_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": coordinacion_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=5000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="diag_wait_after_coordinacion_2",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=5000,
            criticality="normal",  # Screenshot después del segundo click "Coordinación" + diagnóstico final
        )
    )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode="production",
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=True, execution_mode="deterministic")
    return run_dir.name


def run_discovery_ui_cae(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    headless: bool = False,  # HEADFUL obligatorio para discovery visual
    execution_mode: str = "production",
) -> str:
    """
    DISCOVERY MODE: Navegación visual read-only hasta pantalla "Enviar Doc. Pendiente".
    - Navegador VISIBLE obligatorio (headless=False)
    - NO acciones mutables (no uploads, no submits, no form fills persistentes)
    - Solo navegación, lectura y screenshots
    - Para identificar selectores correctos en UI real de eGestiona
    """
    if headless:
        raise ValueError("HEADFUL_REQUIRED: Discovery mode requires visible browser (headless=False)")

    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # URL: login_url (requerida) > override > platform.base_url > default
    # MIGRACIÓN AUTOMÁTICA: Si login_url es null pero base_url parece URL de login, usar base_url
    if plat.login_url:
        url = plat.login_url
    elif coord.url_override:
        url = coord.url_override
    elif plat.base_url and ("login" in plat.base_url.lower() or "egestiona.es" in plat.base_url.lower()):
        # Backward compatibility: si base_url parece ser una URL de login, usarla como login_url
        print(f"[MIGRATION] Using base_url as login_url for platform '{plat.key}': {plat.base_url}")
        url = plat.base_url
    else:
        raise ValueError(
            f"No login URL configured for platform '{plat.key}'. "
            "Please set 'login_url' in platforms.json with the actual login URL from your browser. "
            "Example: 'login_url': 'https://your-tenant.egestiona.es/login?origen=subcontrata'"
        )

    # Resolver credenciales (solo para login)
    required_missing: list[str] = []
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        required_missing.append("egestiona.client (o coord.client_code)")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        required_missing.append("egestiona.username (o coord.username)")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        required_missing.append(password_ref)
    if required_missing:
        raise ValueError("Missing required secrets: " + ", ".join(required_missing))

    actions: list[ActionSpecV1] = []

    # 1. Login (solo campos necesarios, NO submit para discovery)
    actions.append(
        ActionSpecV1(
            action_id="discovery_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="discovery_fill_client",
                kind=ActionKindV1.fill,
                target=TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]'),
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="ClientName"]').model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="discovery_fill_user",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Username"]'),
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Username"]').model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="discovery_fill_pass",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector='input[name="Password"]'),
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='input[name="Password"]').model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # SUBMIT DEL LOGIN (necesario para discovery)
    actions.append(
        ActionSpecV1(
            action_id="discovery_submit_login",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector='button[type="submit"]'),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": TargetV1(type=TargetKindV1.css, selector='button[type="submit"]').model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 2. Esperar dashboard post-login
    actions.append(
        ActionSpecV1(
            action_id="discovery_wait_dashboard",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=20000,
            criticality="critical",  # Screenshot dashboard
        )
    )

    # 3. Click en "Coordinación" del menú lateral
    coordination_target = TargetV1(
        type=TargetKindV1.text,
        text="Coordinación",
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="discovery_click_coordinacion",
            kind=ActionKindV1.click,
            target=coordination_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": coordination_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": coordination_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": coordination_target.model_dump()}, severity=ErrorSeverityV1.critical, description="Coordinacion menu should stay visible after click"),
            ],
            timeout_ms=15000,
            criticality="normal",  # Screenshot menú lateral abierto
        )
    )

    # 4. Click en "Coordinación" del menú lateral
    coordination_target = TargetV1(
        type=TargetKindV1.text,
        text="Coordinación",
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="discovery_click_coordinacion",
            kind=ActionKindV1.click,
            target=coordination_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": coordination_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": coordination_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=15000,
            criticality="normal",  # Screenshot menú lateral abierto
        )
    )

    # 5. Esperar pantalla de Coordinación General con tiles
    actions.append(
        ActionSpecV1(
            action_id="discovery_wait_coordinacion_general",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=10000,
            criticality="normal",  # Screenshot pantalla de Coordinación General con tiles
        )
    )

    # 6. Buscar dentro del iframe contenido de tiles (patrones específicos)
    search_patterns = ["Enviar Doc", "Doc. Pendiente", "Pendiente", "Gestión documentos", "Consultar Doc. Recibida"]

    for pattern in search_patterns:
        target = TargetV1(type=TargetKindV1.text, text=pattern, exact=True, normalize_ws=True)
        actions.append(
            ActionSpecV1(
                action_id=f"discovery_iframe_{pattern.replace(' ', '_').replace('.', '_').lower()}",
                kind=ActionKindV1.wait_for,
                target=target,
                input={"frame_locator": "iframe#id_contenido"},
                preconditions=[
                    ConditionV1(kind=ConditionKindV1.element_visible, args={"target": TargetV1(type=TargetKindV1.css, selector='iframe#id_contenido').model_dump()}, severity=ErrorSeverityV1.error),
                ],
                postconditions=[
                    ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
                ],
                timeout_ms=5000,  # Timeout más corto para búsqueda exploratoria
                criticality="normal",  # Screenshot contenido iframe con tiles
            )
        )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode=execution_mode,
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=True, execution_mode="deterministic")
    return run_dir.name


def run_send_pending_document_kern(
    *,
    base_dir: str | Path = "data",
    platform: str = "egestiona",
    coordination: str = "Kern",
    company_name: str = "TEDELAB INGENIERIA SCCL",
    worker_name: str = "Emilio Roldán Molina",
    worker_tax_id: str = "37330395",
    headless: bool = True,
    execution_mode: str = "production",
    fail_fast: bool = False,
) -> str:
    """
    Ejecuta flujo específico para enviar documentación pendiente en eGestiona Kern.
    Empresa objetivo: TEDELAB INGENIERIA SCCL
    Trabajador objetivo: Emilio Roldán Molina (DNI 37330395)
    Documento: recibo SS pendiente
    Archivo: el único en data/samples/
    """
    base = ensure_data_layout(base_dir=base_dir)
    store = ConfigStoreV1(base_dir=base)
    secrets = SecretsStoreV1(base_dir=base)

    # Determinar automáticamente el archivo único en data/samples/
    samples_dir = Path(base) / "samples"
    pdf_files = list(samples_dir.glob("*.pdf"))
    if len(pdf_files) != 1:
        raise ValueError(f"Expected exactly 1 PDF file in {samples_dir}, found {len(pdf_files)}")
    file_path_obj = pdf_files[0]

    # Registrar documento automáticamente
    repo = DocumentRepositoryV1(project_root=Path(base).parent, data_root="data")
    company_id = "tedelab"
    namespace = "ss_receipts"
    # Sanitizar nombre para file_ref (solo letras, números, _, -, .)
    name = re.sub(r'[^A-Za-z0-9_\-\.]', '_', file_path_obj.stem)

    file_ref = f"doc:company:{company_id}:company_docs:{namespace}:{name}"
    try:
        # Intentar registrar primero
        file_ref = repo.register(
            path=file_path_obj,
            metadata={
                "company_id": company_id,
                "worker_name": worker_name,
                "worker_tax_id": worker_tax_id,
                "doc_type": "ss_receipt",
                "namespace": namespace,
                "name": name,
                "tags": ["egestiona_upload", "kern", "pending_document", "ss_receipt"],
            },
        )
    except ValueError as e:
        if "already exists" in str(e):
            # El archivo ya existe, validar que sea el mismo
            try:
                existing_entry = repo.validate(file_ref)
                # Si existe y es válido, usar el file_ref existente
                print(f"Using existing document: {file_ref}")
            except (FileNotFoundError, ValueError):
                raise ValueError(f"Document exists but is invalid: {e}")
        else:
            raise ValueError(f"Failed to register document: {e}")

    platforms = store.load_platforms()
    plat = next((p for p in platforms.platforms if p.key == platform), None)
    if not plat:
        raise ValueError(f"platform not found: {platform}")

    coord = next((c for c in plat.coordinations if c.label == coordination), None)
    if not coord:
        raise ValueError(f"coordination not found: {coordination}")

    # URL: login_url (requerida) > override > platform.base_url > default
    # MIGRACIÓN AUTOMÁTICA: Si login_url es null pero base_url parece URL de login, usar base_url
    if plat.login_url:
        url = plat.login_url
    elif coord.url_override:
        url = coord.url_override
    elif plat.base_url and ("login" in plat.base_url.lower() or "egestiona.es" in plat.base_url.lower()):
        # Backward compatibility: si base_url parece ser una URL de login, usarla como login_url
        print(f"[MIGRATION] Using base_url as login_url for platform '{plat.key}': {plat.base_url}")
        url = plat.base_url
    else:
        raise ValueError(
            f"No login URL configured for platform '{plat.key}'. "
            "Please set 'login_url' in platforms.json with the actual login URL from your browser. "
            "Example: 'login_url': 'https://your-tenant.egestiona.es/login?origen=subcontrata'"
        )

    # Autofill selectors si faltan
    autofilled = False
    lf = plat.login_fields
    if lf.client_code_selector is None:
        lf.client_code_selector = SelectorSpecV1(kind="css", value='input[name="ClientName"]')
        autofilled = True
    if lf.username_selector is None:
        lf.username_selector = SelectorSpecV1(kind="css", value='input[name="Username"]')
        autofilled = True
    if lf.password_selector is None:
        lf.password_selector = SelectorSpecV1(kind="css", value='input[name="Password"]')
        autofilled = True
    if lf.submit_selector is None:
        lf.submit_selector = SelectorSpecV1(kind="css", value='button[type="submit"]')
        autofilled = True

    if autofilled:
        store.save_platforms(platforms)

    targets = build_targets_from_selectors(
        client_code_selector=plat.login_fields.client_code_selector,
        username_selector=plat.login_fields.username_selector,
        password_selector=plat.login_fields.password_selector,
        submit_selector=plat.login_fields.submit_selector,
        post_login_selector=coord.post_login_selector,
    )

    # Resolver credenciales
    client_val = coord.client_code.strip() if (coord.client_code or "").strip() else (secrets.get_secret("egestiona.client") or "")
    if plat.login_fields.requires_client and not client_val:
        raise ValueError("Missing required secret: egestiona.client")
    user_val = coord.username.strip() if (coord.username or "").strip() else (secrets.get_secret("egestiona.username") or "")
    if not user_val:
        raise ValueError("Missing required secret: egestiona.username")
    password_ref = (coord.password_ref or "").strip() or "egestiona.password"
    if secrets.get_secret(password_ref) is None:
        raise ValueError(f"Missing required secret: {password_ref}")

    actions: list[ActionSpecV1] = []

    # 1. Login
    actions.append(
        ActionSpecV1(
            action_id="kern_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=url),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=15000,
        )
    )

    if plat.login_fields.requires_client:
        actions.append(
            ActionSpecV1(
                action_id="kern_fill_client",
                kind=ActionKindV1.fill,
                target=targets.client_code,
                input={"text": client_val},
                preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.error)],
                postconditions=[
                    ConditionV1(
                        kind=ConditionKindV1.element_value_equals,
                        args={"target": targets.client_code.model_dump(), "value": client_val},
                        severity=ErrorSeverityV1.warning,
                    )
                ],
                timeout_ms=10000,
            )
        )

    actions.append(
        ActionSpecV1(
            action_id="kern_fill_user",
            kind=ActionKindV1.fill,
            target=targets.username,
            input={"text": user_val},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.username.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": targets.username.model_dump(), "value": user_val}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="kern_fill_pass",
            kind=ActionKindV1.fill,
            target=targets.password,
            input={"secret_ref": password_ref},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": targets.password.model_dump()}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": targets.password.model_dump(), "attr": "type", "value": "password"}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    actions.append(
        ActionSpecV1(
            action_id="kern_click_submit",
            kind=ActionKindV1.click,
            target=targets.submit,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": targets.submit.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_clickable, args={"target": targets.submit.model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 2. Esperar post-login - usar verificación más genérica
    # Primero verificar que ya no estamos en login por URL y elementos desaparecidos
    actions.append(
        ActionSpecV1(
            action_id="kern_wait_post_login",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                # Verificar que salimos de la página de login por URL
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
                # Verificar que el formulario de login desapareció
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.client_code.model_dump()}, severity=ErrorSeverityV1.critical, description="Login form must be gone"),
                ConditionV1(kind=ConditionKindV1.element_not_visible, args={"target": targets.submit.model_dump()}, severity=ErrorSeverityV1.critical, description="Submit button must be gone"),
            ],
            timeout_ms=20000,
            criticality="normal",
        )
    )

    # 3. Navegar a "Coordinación" en el menú lateral
    coordination_target = TargetV1(
        type=TargetKindV1.text,
        text="Coordinación",
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_nav_coordinacion",
            kind=ActionKindV1.click,
            target=coordination_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": coordination_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": coordination_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 4. Esperar a que se expanda el submenú de Coordinación
    actions.append(
        ActionSpecV1(
            action_id="kern_wait_coordinacion_menu",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=5000,
        )
    )

    # 5. Click en "Enviar Doc. Pendiente" (tabs o menú) - intentar con diferentes variaciones
    # Primero intentar con el texto exacto
    pending_docs_target = TargetV1(
        type=TargetKindV1.text,
        text="Enviar Doc. Pendiente",
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_click_pending_docs",
            kind=ActionKindV1.click,
            target=pending_docs_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": pending_docs_target.model_dump()}, severity=ErrorSeverityV1.warning),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": pending_docs_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.warning),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 5. Esperar carga de la tabla de documentos pendientes
    actions.append(
        ActionSpecV1(
            action_id="kern_wait_table_load",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # 6. Filtrar por empresa TEDELAB INGENIERIA SCCL
    # Buscar campo de filtro empresa (desplegable o input)
    company_filter_target = TargetV1(
        type=TargetKindV1.css,
        selector='select[name*="empresa"], select[name*="company"], input[name*="empresa"], input[name*="company"]',
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_filter_company",
            kind=ActionKindV1.fill,
            target=company_filter_target,
            input={"text": company_name},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": company_filter_target.model_dump()}, severity=ErrorSeverityV1.warning),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
            criticality="normal",
        )
    )

    # 7. Click en "Buscar" para aplicar filtros
    search_button_target = TargetV1(
        type=TargetKindV1.text,
        text="Buscar",
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_click_search",
            kind=ActionKindV1.click,
            target=search_button_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": search_button_target.model_dump()}, severity=ErrorSeverityV1.warning),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": search_button_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.warning),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 8. Esperar recarga de tabla con filtros aplicados
    actions.append(
        ActionSpecV1(
            action_id="kern_wait_filtered_table",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # 9. Buscar fila específica: Empresa=TEDELAB INGENIERIA SCCL, Trabajador=Emilio Roldán Molina, Tipo=recibo SS
    # Esta acción requiere JavaScript personalizado para buscar en la tabla
    # Usaremos una acción wait_for con condición que valide la presencia de la fila correcta
    target_row_check = TargetV1(
        type=TargetKindV1.text,
        text=company_name,
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_validate_company_present",
            kind=ActionKindV1.wait_for,
            target=target_row_check,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": target_row_check.model_dump()}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=10000,
            criticality="normal",
        )
    )

    # 10. Hacer click en el icono de "abrir/detalle" de la fila correcta
    # Usaremos JavaScript para encontrar la fila que contiene tanto la empresa como el trabajador
    open_detail_target = TargetV1(
        type=TargetKindV1.css,
        selector='tr:has-text("TEDELAB INGENIERIA SCCL"):has-text("Emilio Roldán Molina") button, tr:has-text("TEDELAB INGENIERIA SCCL"):has-text("37330395") button',
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_open_detail",
            kind=ActionKindV1.click,
            target=open_detail_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": open_detail_target.model_dump()}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": open_detail_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 11. Esperar apertura del modal/detalle de la solicitud
    actions.append(
        ActionSpecV1(
            action_id="kern_wait_detail_modal",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # 12. Validar que estamos en la solicitud correcta (hard stop si no coincide)
    # Buscar texto que confirme empresa y trabajador en el modal
    validate_company_target = TargetV1(
        type=TargetKindV1.text,
        text=company_name,
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_validate_detail_company",
            kind=ActionKindV1.wait_for,
            target=validate_company_target,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": validate_company_target.model_dump()}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=5000,
            criticality="normal",
        )
    )

    validate_worker_target = TargetV1(
        type=TargetKindV1.text,
        text=worker_name,
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_validate_detail_worker",
            kind=ActionKindV1.wait_for,
            target=validate_worker_target,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": validate_worker_target.model_dump()}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=5000,
            criticality="normal",
        )
    )

    # 13. Click en "Enviar documento" en el modal
    send_doc_button_target = TargetV1(
        type=TargetKindV1.text,
        text="Enviar documento",
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_click_send_document",
            kind=ActionKindV1.click,
            target=send_doc_button_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": send_doc_button_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": send_doc_button_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 14. Esperar formulario de subida
    actions.append(
        ActionSpecV1(
            action_id="kern_wait_upload_form",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.url, url=".*"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10000,
        )
    )

    # 15. Adjuntar archivo usando file input
    file_input_target = TargetV1(
        type=TargetKindV1.css,
        selector='input[type="file"]',
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_upload_file",
            kind=ActionKindV1.upload,
            target=file_input_target,
            input={"file_ref": file_ref},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": file_input_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": file_input_target.model_dump()}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.upload_completed, args={}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=30000,
            criticality="critical",
        )
    )

    # 16. Rellenar "Inicio Vigencia" con fecha de hoy (DD/MM/YYYY)
    from datetime import datetime
    today_str = datetime.now().strftime("%d/%m/%Y")
    vigencia_input_target = TargetV1(
        type=TargetKindV1.css,
        selector='input[name*="vigencia"], input[name*="fecha"], input[name*="date"]',
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_fill_vigencia_date",
            kind=ActionKindV1.fill,
            target=vigencia_input_target,
            input={"text": today_str},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": vigencia_input_target.model_dump()}, severity=ErrorSeverityV1.warning),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": vigencia_input_target.model_dump(), "value": today_str}, severity=ErrorSeverityV1.warning)
            ],
            timeout_ms=10000,
            criticality="normal",
        )
    )

    # 17. Pulsar "Enviar documento" final
    final_send_button_target = TargetV1(
        type=TargetKindV1.text,
        text="Enviar documento",
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_final_send",
            kind=ActionKindV1.click,
            target=final_send_button_target,
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": final_send_button_target.model_dump()}, severity=ErrorSeverityV1.error),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": final_send_button_target.model_dump(), "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=15000,
            criticality="normal",
        )
    )

    # 18. Esperar confirmación de envío exitoso
    success_confirmation_target = TargetV1(
        type=TargetKindV1.text,
        text="Enviado",
        exact=True,
        normalize_ws=True,
    )
    actions.append(
        ActionSpecV1(
            action_id="kern_wait_success",
            kind=ActionKindV1.wait_for,
            target=success_confirmation_target,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.warning)],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": success_confirmation_target.model_dump()}, severity=ErrorSeverityV1.warning),
            ],
            timeout_ms=20000,
            criticality="normal",
        )
    )

    rt = ExecutorRuntimeH4(
        runs_root=Path(base) / "runs",
        project_root=Path(base).parent,
        data_root="data",
        execution_mode=execution_mode,
        secrets_store=secrets,
    )
    run_dir = rt.run_actions(url=url, actions=actions, headless=headless, fail_fast=fail_fast, execution_mode="deterministic")
    return run_dir.name


router = APIRouter(tags=["egestiona"])


@router.post("/runs/egestiona/login")
async def egestiona_login(coord: str = "Kern"):
    """
    Ejecuta login determinista a eGestiona usando Config Store (platform=egestiona, coordination=<coord>).
    """
    try:
        run_id = await run_in_threadpool(lambda: run_login_and_snapshot(base_dir="data", platform="egestiona", coordination=coord, headless=True, execution_mode="production"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/upload_document")
async def egestiona_upload_document(coord: str = "Kern", file_path: str = "data/samples/dummy.pdf"):
    """
    Ejecuta flujo completo: login + navegación a CAE + upload de documento + validación.

    Args:
        coord: Coordinación (default: "Kern")
        file_path: Ruta al archivo a subir (default: "data/samples/dummy.pdf")
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_upload_document_cae(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                file_path=file_path,
                headless=True,
                execution_mode="production",
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/send_pending_document")
async def egestiona_send_pending_document(
    coord: str = "Kern",
    company_name: str = "TEDELAB INGENIERIA SCCL",
    worker_name: str = "Emilio Roldán Molina",
    worker_tax_id: str = "37330395"
):
    """
    Ejecuta flujo específico para enviar documentación pendiente en eGestiona Kern.

    Empresa objetivo: TEDELAB INGENIERIA SCCL
    Trabajador objetivo: Emilio Roldán Molina (DNI 37330395)
    Archivo: el único PDF en data/samples/
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_send_pending_document_kern(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                company_name=company_name,
                worker_name=worker_name,
                worker_tax_id=worker_tax_id,
                headless=True,
                execution_mode="production",
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/discovery_ui_cae")
async def egestiona_discovery_ui_cae(coord: str = "Kern"):
    """
    DISCOVERY MODE: Navegación visual read-only hasta pantalla "Enviar Doc. Pendiente".
    - Navegador VISIBLE obligatorio (headless=False)
    - NO acciones mutables
    - Para identificar selectores correctos en UI real de eGestiona
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_discovery_ui_cae(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                headless=False,  # HEADFUL obligatorio
                execution_mode="production",
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/diagnostico_paridad")
async def egestiona_diagnostico_paridad(coord: str = "Kern"):
    """
    DIAGNÓSTICO DE PARIDAD: investigar por qué iframe#id_contenido no carga contenido.
    - Secuencia de clicks "humanos" para activar carga
    - Captura información de paridad completa
    - Diagnóstico detallado del iframe y elementos
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_diagnostico_paridad(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                headless=False,  # HEADFUL obligatorio para diagnóstico
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/diagnostico_icono_central")
async def egestiona_diagnostico_icono_central(coord: str = "Kern"):
    """
    DIAGNÓSTICO DEL ICONO CENTRAL: encontrar y activar el icono "Enviar Doc. Pendiente" del dashboard.
    - Ruta canónica: login -> dashboard -> click icono central
    - Diagnosticar dónde carga el contenido (iframe vs mismo DOM)
    - NO usar menú lateral salvo fallback
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_diagnostico_icono_central(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                headless=False,  # HEADFUL obligatorio para diagnóstico
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/localizacion_geometrica")
async def egestiona_localizacion_geometrica(coord: str = "Kern"):
    """
    LOCALIZACIÓN GEOMÉTRICA: encontrar elementos clickables por bounding boxes y geometría.
    - Enumerar elementos clickables en zona central
    - Usar heurística de posición para seleccionar candidato
    - Click y observar cambios
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_localizacion_geometrica(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                headless=False,  # HEADFUL obligatorio para diagnóstico
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/smoke_test_tenant")
async def egestiona_smoke_test_tenant(coord: str = "Kern"):
    """
    SMOKE TEST: Verificar tenant correcto y existencia de "Enviar Doc. Pendiente".
    - Login en tenant correcto (grupoindukern.egestiona.com)
    - Verificar hostname post-login
    - Buscar "Enviar Doc. Pendiente" en dashboard
    - Generar screenshots obligatorias
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_smoke_test_tenant_correcto(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                headless=False,  # HEADFUL obligatorio para smoke test
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/buscar_frames_dashboard")
async def egestiona_buscar_frames_dashboard(coord: str = "Kern"):
    """
    BÚSQUEDA EN FRAMES: Localizar "Enviar Doc. Pendiente" en todos los frames del dashboard.
    - Login usando EXACTAMENTE la URL anterior correcta
    - Listar todos los frames
    - Buscar texto en cada frame
    - Capturar evidencia
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_buscar_frames_dashboard(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                headless=False,  # HEADFUL obligatorio para ver frames
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/buscar_frames_dashboard_headful")
async def egestiona_buscar_frames_dashboard_headful(coord: str = "Kern"):
    """
    HEADFUL + READ-ONLY:
    - Reutiliza EXACTAMENTE la URL del último run exitoso.
    - Enumera TODOS los frames y busca "Enviar Doc. Pendiente" dentro de cada frame.
    - Evidence PNG SIEMPRE (01_dashboard.png, 02_found_or_not.png, 03_tile_element.png).
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_find_enviar_doc_in_all_frames_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                slow_mo_ms=300,
                wait_after_login_s=2.5,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/frames_screenshots_headful")
async def egestiona_frames_screenshots_headful(coord: str = "Kern"):
    """
    HEADFUL + READ-ONLY:
    - Login con EXACTAMENTE la misma URL del run anterior.
    - Espera 3s con dashboard visible.
    - Enumera frames y genera PNG por frame: evidence/frame_<idx>_<name>.png (SIN omitir).
    - Solo después busca "Enviar Doc. Pendiente" dentro de cada frame.
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_frames_screenshots_and_find_tile_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                slow_mo_ms=300,
                wait_after_login_s=3.0,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/list_pending_documents_readonly")
async def egestiona_list_pending_documents_readonly(coord: str = "Kern"):
    """
    HEADFUL + READ-ONLY:
    - Login
    - Click tile "Enviar Doc. Pendiente" dentro del frame nm_contenido
    - Cargar listado y extraer filas (sin mutar datos)
    - Evidence PNG + JSON en evidence/
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_list_pending_documents_readonly_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.5,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/discovery_pending_table")
async def egestiona_discovery_pending_table(coord: str = "Kern"):
    """
    HEADFUL + READ-ONLY:
    Descubre en qué frame vive la tabla REAL de "Documentación Pendiente" y dumpea:
    - frames_after_gestion3.json
    - screenshots por frame
    - tables_detected.json
    - pending_table_selector.json + pending_table_outerhtml.html
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_discovery_pending_table_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.0,
                wait_after_click_s=10.0,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/open_pending_document_details_readonly")
async def egestiona_open_pending_document_details_readonly(coord: str = "Kern"):
    """
    HEADFUL + READ-ONLY:
    Abre el detalle de EXACTAMENTE 1 documento pendiente filtrado (TEDELAB + Emilio)
    desde el grid DHTMLX (frame f3) y valida scope visible.
    """
    try:
        run_id = await run_in_threadpool(
            lambda: run_open_pending_document_details_readonly_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.5,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/upload_pending_document_scoped")
async def egestiona_upload_pending_document_scoped(coord: str = "Kern"):
    """
    HEADFUL + WRITE (guardrails strict):
    - Encuentra EXACTAMENTE 1 fila (TEDELAB + Emilio), abre detalle, adjunta el ÚNICO PDF en data/samples/,
      rellena Inicio Vigencia (hoy, Europe/Madrid) y pulsa Enviar solo si scope/inputs validan.
    """
    run_id = await run_in_threadpool(
        lambda: run_upload_pending_document_scoped_headful(
            base_dir="data",
            platform="egestiona",
            coordination=coord,
            slow_mo_ms=300,
            viewport={"width": 1600, "height": 1000},
            wait_after_login_s=2.5,
        )
    )
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/match_pending_documents_readonly")
async def egestiona_match_pending_documents_readonly(
    coord: str = "Kern",
    company_key: str = "",
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
):
    """
    HEADFUL / READ-ONLY: Hace matching de pendientes eGestiona con documentos del repositorio.
    - Login -> nm_contenido -> click Gestion(3)
    - Carga grid DHTMLX en frame f3
    - Para cada pendiente (o solo target si only_target=True), propone mejor documento del repo
    - Devuelve: candidato, alternativas, confianza y razones
    - NO sube nada, NO abre modales destructivos
    """
    if not company_key:
        raise HTTPException(status_code=400, detail="company_key is required")
    
    try:
        run_id = await run_in_threadpool(
            lambda: run_match_pending_documents_readonly_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                company_key=company_key,
                person_key=person_key,
                limit=limit,
                only_target=only_target,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.5,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        error_msg = str(e)
        # Verificar si es error de navegación a pendientes
        if "PENDING_ENTRY_POINT_NOT_REACHED" in error_msg:
            error_detail = {
                "error": "pending_entry_point_not_reached",
                "message": error_msg,
                "detail": "No se pudo llegar a la pantalla de pendientes después de reintentos. "
                         "Revisar evidence en el directorio de runs para más detalles.",
            }
            raise HTTPException(status_code=422, detail=error_detail)
        raise HTTPException(status_code=500, detail=str(e))
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


@router.post("/runs/egestiona/stability_test_pending_readonly")
async def egestiona_stability_test_pending_readonly(
    coord: str = "Aigues de Manresa",
    company_key: str = "",
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
    iterations: int = 5,
):
    """
    Stability test: Ejecuta el mismo flujo READ-ONLY N veces y valida consistencia.
    
    Body (JSON):
    {
        "coord": "Aigues de Manresa",
        "company_key": "F63161988",
        "person_key": "optional",
        "limit": 20,
        "only_target": true,
        "iterations": 5
    }
    
    Returns:
        Resumen con resultados de todas las iteraciones y análisis (PASS/FAIL)
    """
    if not company_key:
        raise HTTPException(status_code=400, detail="company_key is required")
    
    if iterations < 1 or iterations > 10:
        raise HTTPException(status_code=400, detail="iterations must be between 1 and 10")
    
    try:
        summary = await run_in_threadpool(
            lambda: run_stability_test_pending_readonly(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                company_key=company_key,
                person_key=person_key,
                limit=limit,
                only_target=only_target,
                iterations=iterations,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.5,
            )
        )
        return summary
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")


@router.post("/runs/egestiona/execute_submission_plan_scoped")
async def egestiona_execute_submission_plan_scoped(
    coord: str = "Kern",
    company_key: str = "",
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
    dry_run: bool = True,
    confirm_execute: bool = False,
    self_test: bool = False,
    self_test_doc_id: Optional[str] = None,
):
    """
    HEADFUL / WRITE (con guardrails fuertes): Ejecuta plan de envío para items AUTO_SUBMIT_OK.
    - Construye submission plan (reutiliza lógica existente)
    - Si dry_run=true: solo genera plan, NO ejecuta
    - Si dry_run=false pero confirm_execute=false: hard stop
    - Si dry_run=false y confirm_execute=true: ejecuta items con AUTO_SUBMIT_OK
    - Usa fechas del plan (proposed_fields), NO "hoy"
    - Evidence completa: execution_results.json, confirmation_text_dump.txt, PNGs
    """
    if not company_key:
        raise HTTPException(status_code=400, detail="company_key is required")
    
    try:
        run_id = await run_in_threadpool(
            lambda: run_execute_submission_plan_scoped_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                company_key=company_key,
                person_key=person_key,
                limit=limit,
                only_target=only_target,
                dry_run=dry_run,
                confirm_execute=confirm_execute,
                self_test=self_test,
                self_test_doc_id=self_test_doc_id,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.5,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        error_msg = str(e)
        if "SECURITY_HARD_STOP" in error_msg or "GUARDRAIL_VIOLATION" in error_msg:
            raise HTTPException(status_code=403, detail=error_msg)
        # Capturar RuntimeError con mensaje DHX_BLOCKER_NOT_DISMISSED
        if "DHX_BLOCKER_NOT_DISMISSED" in error_msg:
            from backend.adapters.egestiona.priority_comms_headful import DhxBlockerNotDismissed
            error_detail = {
                "error": "dhx_blocker_not_dismissed",
                "message": error_msg,
                "detail": "No se pudo cerrar un overlay DHTMLX bloqueante después del login. "
                         "Revisar evidence en el directorio de runs para más detalles.",
            }
            raise HTTPException(status_code=422, detail=error_detail)
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        # Capturar excepciones de overlays DHTMLX bloqueantes
        from backend.adapters.egestiona.priority_comms_headful import PriorityCommsModalNotDismissed, DhxBlockerNotDismissed
        if isinstance(e, (PriorityCommsModalNotDismissed, DhxBlockerNotDismissed)):
            error_type = "priority_comms_modal_not_dismissed" if isinstance(e, PriorityCommsModalNotDismissed) else "dhx_blocker_not_dismissed"
            error_detail = {
                "error": error_type,
                "message": str(e),
                "detail": "No se pudo cerrar un overlay DHTMLX bloqueante después del login. "
                         "Revisar evidence en el directorio de runs para más detalles.",
            }
            if hasattr(e, 'run_id'):
                error_detail["run_id"] = e.run_id
            raise HTTPException(status_code=422, detail=error_detail)
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


def normalize_contract(payload: dict, run_id_opt: Optional[str]) -> dict:
    """
    Helper centralizado para normalizar contrato de respuesta.
    
    - Si run_id_opt existe => payload.run_id = run_id_opt y payload.artifacts.run_id = run_id_opt
    - Si NO existe => NO inventar run_id. Solo asegurar que payload.status y payload.error_code estén.
    - No debe haber objetos Path en JSON (todo str o null).
    
    Returns:
        payload modificado (mismo objeto)
    """
    if run_id_opt:
        payload["run_id"] = run_id_opt
        payload.setdefault("artifacts", {})["run_id"] = run_id_opt
    
    # Asegurar que no hay objetos Path en el payload (convertir a str)
    def clean_paths(obj):
        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: clean_paths(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_paths(item) for item in obj]
        return obj
    
    # Limpiar paths recursivamente
    payload = clean_paths(payload)
    
    return payload


# Alias para compatibilidad
normalize_run_id = normalize_contract


@router.post("/runs/egestiona/build_submission_plan_readonly")
async def egestiona_build_submission_plan_readonly(
    coord: str = "Kern",
    company_key: str = "",
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
    dry_run: bool = True,  # Explícitamente expuesto (siempre True en este endpoint, pero claro)
    fixture: bool = False,  # Activar fixture determinista
    request: Request = None,  # Para leer headers
):
    """
    HEADFUL / READ-ONLY: Genera plan de envío determinista para pendientes eGestiona.
    - Login -> nm_contenido -> click Gestion(3)
    - Carga grid DHTMLX en frame f3
    - Para cada pendiente: matching + evaluación de guardrails
    - Genera submission_plan.json con decisiones (AUTO_SUBMIT_OK | REVIEW_REQUIRED | NO_MATCH)
    - NO sube nada, NO hace clicks de "Enviar documento"
    
    Response estructurado:
    - status: "ok" | "error"
    - run_id: str (si ok)
    - summary: dict con counts (si ok)
    - items: array (si ok, puede estar vacío)
    - error_code, message, details (si error)
    """
    # HOTFIX C2.13.7: Logging de trace para identificar ramas
    print(f"[CAE][READONLY][TRACE] ========================================")
    print(f"[CAE][READONLY][TRACE] ENTRADA: coord={coord} company_key={company_key} person_key={person_key} limit={limit} only_target={only_target} dry_run={dry_run} fixture={fixture}")
    
    # HOTFIX C2.13.2: Inicializar run_id = None al principio (READ-ONLY no tiene run_id por defecto)
    run_id = None
    
    # Generar client_req_id SIEMPRE (uuid4 si no viene en header)
    import uuid
    client_request_id = None
    if request and hasattr(request, 'headers'):
        client_request_id = request.headers.get("X-CLIENT-REQ-ID")
        
        # Verificar si se activa fixture (header o param)
        fixture_header = request.headers.get("X-CAE-PLAN-FIXTURE", "0")
        if fixture_header == "1":
            fixture = True
    
    # Si no viene en header, generar uno
    if not client_request_id:
        client_request_id = str(uuid.uuid4())
    
    # HOTFIX C2.13.7: Verificar ENV para fixture (solo si explícito)
    import os
    env_fixture = os.getenv("EGESTIONA_READONLY_FIXTURE", "0")
    use_fixture = fixture or (env_fixture == "1")
    
    # HOTFIX C2.13.7: Logging de rama
    if use_fixture:
        print(f"[CAE][READONLY][TRACE] BRANCH: legacy_fixture reason=fixture={fixture} env_fixture={env_fixture}")
    else:
        print(f"[CAE][READONLY][TRACE] BRANCH: real_playwright reason=fixture=False env_fixture={env_fixture}")
    
    # Si fixture está activo, usar plan determinista
    if use_fixture:
        from backend.adapters.egestiona.fixture_plan import build_fixture_plan
        try:
            run_id = await run_in_threadpool(
                lambda: build_fixture_plan(base_dir="data")
            )
        except Exception as e:
            return {
                "status": "error",
                "error_code": "fixture_error",
                "message": f"Error generando fixture: {e}",
                "details": None,
            }
    else:
        # HOTFIX C2.13.7: Early return si falta company_key
        if not company_key:
            print(f"[CAE][READONLY][TRACE] BRANCH: early_return_missing_company_key reason=company_key is empty")
            return {
                "status": "error",
                "error_code": "missing_company_key",
                "message": "company_key is required",
                "details": None,
                "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                "items": [],  # HOTFIX C2.13.6: Siempre array, nunca null
                "artifacts": {
                    "client_request_id": client_request_id,
                    "run_id": None,
                },
                "diagnostics": {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
            }
        
        # HOTFIX C2.13.7: READ-ONLY debe ejecutar Playwright (solo sin subida, pero sí con scraping)
        # Usar return_plan_only=True para obtener plan directamente sin crear run
        print(f"[CAE][READONLY][TRACE] BRANCH: real_playwright_executing reason=company_key present, calling run_build_submission_plan_readonly_headful")
        plan_result = None
        try:
            print(f"[CAE][READONLY][TRACE] Llamando run_build_submission_plan_readonly_headful con return_plan_only=True")
            plan_result = await run_in_threadpool(
                lambda: run_build_submission_plan_readonly_headful(
                    base_dir="data",
                    platform="egestiona",
                    coordination=coord,
                    company_key=company_key,
                    person_key=person_key,
                    limit=limit,
                    only_target=only_target,
                    slow_mo_ms=300,
                    viewport={"width": 1600, "height": 1000},
                    wait_after_login_s=2.5,
                    return_plan_only=True,  # NO crear run ni tocar filesystem, pero SÍ ejecutar Playwright
                    max_pages=10,  # SPRINT C2.14.1: Límite de páginas para paginación
                    max_items=200,  # SPRINT C2.14.1: Límite de items totales
                )
            )
            print(f"[CAE][READONLY][TRACE] run_build_submission_plan_readonly_headful completado. plan_result type: {type(plan_result)}")
            if isinstance(plan_result, dict):
                items_count = len(plan_result.get("plan", []))
                print(f"[CAE][READONLY][TRACE] plan_result es dict con items_count={items_count}")
            elif isinstance(plan_result, str):
                print(f"[CAE][READONLY][TRACE] plan_result es string (run_id): {plan_result}")
            else:
                print(f"[CAE][READONLY][TRACE] plan_result es tipo inesperado: {type(plan_result)}")
        except Exception as e:
            # HOTFIX C2.13.7: Loggear excepción en lugar de hacer pass silencioso
            import traceback
            print(f"[CAE][READONLY][TRACE] BRANCH: exception_during_playwright reason={type(e).__name__}: {str(e)}")
            print(f"[CAE][READONLY][TRACE] Traceback:\n{traceback.format_exc()}")
            # La excepción se captura más abajo en el except general, pero loggeamos aquí para trace
            # NO hacer pass, dejar que se propague al except general
            raise
    
    # HOTFIX C2.13.7: Si plan_result es None, loggear y convertir a resultado válido
    if plan_result is None:
        # HOTFIX C2.13.7: Esto NO debería pasar si Playwright se ejecutó correctamente
        # Si llega aquí, significa que hubo una excepción que se capturó silenciosamente
        print(f"[CAE][READONLY][TRACE] BRANCH: plan_result_is_none reason=plan_result es None después de ejecutar Playwright")
        print("[CAE][READONLY] plan_result es None, convirtiendo a resultado válido vacío")
        plan_result = {
            "plan": [],
            "summary": {
                "pending_count": 0,
                "matched_count": 0,
                "unmatched_count": 0,
                "duration_ms": 0,
            },
            "pending_items": [],
            "match_results": [],
            "duration_ms": 0,
            "diagnostics": {
                "reason": "compute_returned_none",
                "note": "Computation returned None (possibly due to exception or empty state). Check logs for [CAE][READONLY][TRACE] to identify root cause.",
            },
            "instrumentation": {},  # HOTFIX C2.13.6: Incluir instrumentation vacío
        }
    
    try:
        # HOTFIX C2.13.7: Logging de rama de procesamiento
        if isinstance(plan_result, dict):
            print(f"[CAE][READONLY][TRACE] BRANCH: processing_dict_result reason=plan_result es dict (READ-ONLY puro)")
        elif isinstance(plan_result, str):
            print(f"[CAE][READONLY][TRACE] BRANCH: processing_string_result reason=plan_result es string (legacy/fixture)")
        else:
            print(f"[CAE][READONLY][TRACE] BRANCH: processing_unexpected_type reason=plan_result es {type(plan_result)}")
        
        # HOTFIX C2.12.6: Si plan_result es un dict (return_plan_only=True), usar directamente
        # Si es un string (run_id), es el caso legacy (fixture), leer del filesystem
        if isinstance(plan_result, dict):
            # Caso READ-ONLY puro: plan_result ya contiene plan, summary, etc.
            items = plan_result.get("plan", [])
            summary = plan_result.get("summary", {
                "pending_count": 0,
                "matched_count": 0,
                "unmatched_count": 0,
                "duration_ms": plan_result.get("duration_ms", 0),
            })
            
            # SPRINT C2.13.0: Incluir diagnostics si está disponible
            diagnostics = plan_result.get("diagnostics")
            
            # SPRINT C2.14.1: Asegurar que cada item incluye pending_item_key
            for item in items:
                if "pending_item_key" not in item.get("pending_ref", {}):
                    # Si no está en pending_ref, intentar obtenerlo del item original
                    pending_item_key = item.get("pending_item_key")
                    if pending_item_key:
                        if "pending_ref" not in item:
                            item["pending_ref"] = {}
                        item["pending_ref"]["pending_item_key"] = pending_item_key
            
            # SPRINT C2.13.1: Si items.length === 0, asegurar que status = ok y añadir diagnostics si no existe
            if len(items) == 0 and not diagnostics:
                # No hay items pero no hay diagnostics, añadir diagnostics informativo
                diagnostics = {
                    "reason": "no_matches_after_compute",
                    "note": "No matching documents found between eGestión and local repository",
                    "pending_count": summary.get("pending_count", 0),
                    "matches_found": 0,
                    "local_docs_considered": plan_result.get("instrumentation", {}).get("local_docs_considered", 0) if plan_result.get("instrumentation") else 0,
                }
            
            # Generar checksum y confirm_token para el plan (sin run_id)
            import hashlib
            import hmac
            from datetime import datetime, timedelta
            
            plan_items_for_checksum = []
            for item in items:
                plan_items_for_checksum.append({
                    "pending_ref": item.get("pending_ref", {}),
                    "matched_doc": {
                        "doc_id": item.get("matched_doc", {}).get("doc_id"),
                        "type_id": item.get("matched_doc", {}).get("type_id"),
                    } if item.get("matched_doc") else None,
                    "decision": item.get("decision", {}),
                    "proposed_fields": item.get("proposed_fields", {}),
                })
            
            checksum_data = pyjson.dumps(plan_items_for_checksum, sort_keys=True, ensure_ascii=False)
            plan_checksum = hashlib.sha256(checksum_data.encode('utf-8')).hexdigest()
            
            # Confirm token: HMAC con secret interno + timestamp (TTL 30 min)
            created_at = datetime.utcnow()
            expires_at = created_at + timedelta(minutes=30)
            
            import os
            secret_key = os.getenv("COMETLOCAL_PLAN_SECRET", "default-secret-key-change-in-production")
            
            # Usar placeholder para run_id en token (READ-ONLY no tiene run_id)
            token_payload = f"readonly_no_run:{plan_checksum}:{created_at.isoformat()}"
            confirm_token = hmac.new(
                secret_key.encode('utf-8'),
                token_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # HOTFIX C2.13.6: Asegurar que items siempre sea array, nunca null
            items_array = items if isinstance(items, list) else []
            
            # HOTFIX C2.13.6: Contrato de respuesta robusto - siempre incluir run_id, items, diagnostics, artifacts
            response = {
                "status": "ok",
                "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                "plan_id": None,  # READ-ONLY no tiene plan_id
                "runs_url": None,  # READ-ONLY no tiene runs_url
                "summary": summary,
                "items": items_array,  # HOTFIX C2.13.6: Siempre array, nunca null
                "plan": items_array,  # Alias para compatibilidad
                "dry_run": dry_run,
                "confirm_token": confirm_token,
                "plan_checksum": plan_checksum,
                "artifacts": {
                    "client_request_id": client_request_id,
                    "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
                },
                "diagnostics": diagnostics if diagnostics else {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
            }
            
            # NO normalizar contrato (no hay run_id)
            # NO guardar en filesystem
            
        elif isinstance(plan_result, str):
            # Caso legacy: fixture devuelve run_id, leer del filesystem
            run_id = plan_result
            
            from pathlib import Path
            # HOTFIX C2.13.3: Eliminado import json local (usa pyjson del import global)
            from backend.config import DATA_DIR
            from backend.shared.path_utils import safe_path_join
            
            plan_path = safe_path_join(Path(DATA_DIR) / "runs" / run_id / "evidence", "submission_plan.json")
            summary = {
                "pending_count": 0,
                "matched_count": 0,
                "unmatched_count": 0,
                "duration_ms": 0,
            }
            items = []
            
            if plan_path and plan_path.exists():
                try:
                    with open(plan_path, "r", encoding="utf-8") as f:
                        plan_data = pyjson.load(f)
                        plan = plan_data.get("plan", [])
                        items = plan
                        summary["pending_count"] = len(plan)
                        summary["matched_count"] = sum(1 for item in plan if item.get("matched_doc") and item.get("matched_doc", {}).get("doc_id"))
                        summary["unmatched_count"] = summary["pending_count"] - summary["matched_count"]
                except Exception as e:
                    pass
            
            # Cargar meta.json para duration
            meta_path = safe_path_join(Path(DATA_DIR) / "runs" / run_id / "evidence", "meta.json")
            if meta_path and meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = pyjson.load(f)
                        summary["duration_ms"] = meta.get("duration_ms", 0)
                except Exception:
                    pass
            
            # Cargar plan_meta.json para obtener confirm_token
            plan_meta_path = safe_path_join(Path(DATA_DIR) / "runs" / run_id, "plan_meta.json")
            confirm_token = None
            plan_checksum = None
            if plan_meta_path and plan_meta_path.exists():
                try:
                    with open(plan_meta_path, "r", encoding="utf-8") as f:
                        plan_meta = pyjson.load(f)
                        confirm_token = plan_meta.get("confirm_token")
                        plan_checksum = plan_meta.get("plan_checksum")
                except Exception:
                    pass
            
            # Cargar artifacts (storage_state_path)
            artifacts = {}
            run_finished_path = safe_path_join(Path(DATA_DIR) / "runs" / run_id, "run_finished.json")
            if run_finished_path and run_finished_path.exists():
                try:
                    with open(run_finished_path, "r", encoding="utf-8") as f:
                        run_finished = pyjson.load(f)
                        artifacts_data = run_finished.get("artifacts", {})
                        storage_state_rel = artifacts_data.get("storage_state_path")
                        if storage_state_rel:
                            from backend.shared.path_utils import safe_path_join, as_str
                            storage_state_abs = safe_path_join(Path(DATA_DIR), storage_state_rel)
                            if storage_state_abs:
                                artifacts["storage_state_path"] = as_str(storage_state_abs)
                except Exception:
                    pass
            
            # HOTFIX C2.13.6: Asegurar que items siempre sea array, nunca null
            items_array = items if isinstance(items, list) else []
            
            response = {
                "status": "ok",
                "run_id": run_id,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                "plan_id": run_id,
                "runs_url": f"/runs/{run_id}" if run_id else None,
                "summary": summary,
                "items": items_array,  # HOTFIX C2.13.6: Siempre array, nunca null
                "plan": items_array,  # Alias para compatibilidad
                "dry_run": dry_run,
                "confirm_token": confirm_token,
                "plan_checksum": plan_checksum,
                "artifacts": {
                    "client_request_id": client_request_id,
                    "run_id": run_id,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
                    **(artifacts if artifacts else {}),  # Merge otros artifacts si existen
                },
                "diagnostics": {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
            }
            
            normalize_contract(response, run_id)
            
            # Guardar response.json y client_request_id.txt (solo para fixture/legacy)
            try:
                if run_id:
                    run_dir = Path(DATA_DIR) / "runs" / run_id
                    if run_dir.exists():
                        response_path = run_dir / "response.json"
                        with open(response_path, "w", encoding="utf-8") as f:
                            pyjson.dump(response, f, indent=2, ensure_ascii=False, default=str)
                        client_req_id_path = run_dir / "client_request_id.txt"
                        with open(client_req_id_path, "w", encoding="utf-8") as f:
                            f.write(client_request_id)
            except Exception as e:
                import os
                if os.getenv("ENVIRONMENT", "").lower() == "dev":
                    print(f"[CAE_CONTRACT] Warning: No se pudo guardar response.json: {e}")
        else:
            # SPRINT C2.13.1: Caso inesperado - convertir a resultado válido en lugar de error
            # READ-ONLY nunca debe fallar, siempre devolver status: "ok" con items: []
            print(f"[CAE][READONLY] plan_result es de tipo inesperado: {type(plan_result)}, convirtiendo a resultado válido vacío")
            items = []
            summary = {
                "pending_count": 0,
                "matched_count": 0,
                "unmatched_count": 0,
                "duration_ms": 0,
            }
            diagnostics = {
                "reason": "unexpected_result_type",
                "note": f"Computation returned unexpected type: {type(plan_result)}",
                "result_type": str(type(plan_result)),
            }
            
            # Generar checksum y confirm_token para el plan (sin run_id)
            import hashlib
            import hmac
            from datetime import datetime, timedelta
            
            plan_items_for_checksum = []
            checksum_data = pyjson.dumps(plan_items_for_checksum, sort_keys=True, ensure_ascii=False)
            plan_checksum = hashlib.sha256(checksum_data.encode('utf-8')).hexdigest()
            
            created_at = datetime.utcnow()
            expires_at = created_at + timedelta(minutes=30)
            
            import os
            secret_key = os.getenv("COMETLOCAL_PLAN_SECRET", "default-secret-key-change-in-production")
            
            token_payload = f"readonly_no_run:{plan_checksum}:{created_at.isoformat()}"
            confirm_token = hmac.new(
                secret_key.encode('utf-8'),
                token_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # HOTFIX C2.13.6: Asegurar que items siempre sea array, nunca null
            items_array = items if isinstance(items, list) else []
            
            response = {
                "status": "ok",  # SPRINT C2.13.1: Siempre "ok", nunca "error"
                "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                "plan_id": None,
                "runs_url": None,
                "summary": summary,
                "items": items_array,  # HOTFIX C2.13.6: Siempre array, nunca null
                "plan": items_array,
                "dry_run": dry_run,
                "confirm_token": confirm_token,
                "plan_checksum": plan_checksum,
                "artifacts": {
                    "client_request_id": client_request_id,
                    "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
                },
                "diagnostics": diagnostics if diagnostics else {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
            }
        
        # HOTFIX C2.13.6: Loggear items_count antes de devolver
        items_count = len(response.get("items", []))
        error_code_str = "-"
        run_id_str = response.get("run_id") or response.get("plan_id") or "None"
        artifacts_run_id_str = response.get("artifacts", {}).get("run_id") if response.get("artifacts") else "None"
        print(f"[CAE][READONLY] items_count={items_count} run_id={run_id_str} client_req_id={client_request_id} status=ok error_code={error_code_str} artifacts.run_id={artifacts_run_id_str}")
        
        return response
        
    except ValueError as e:
        # HOTFIX C2.13.6: Contrato de respuesta robusto
        items_count = 0
        response = {
            "status": "error",
            "error_code": "readonly_compute_failed",  # HOTFIX C2.12.6: NUNCA run_id_missing
            "message": f"Validation error: {str(e)}",
            "details": None,
            "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
            "items": [],  # HOTFIX C2.13.6: Siempre array, nunca null
            "artifacts": {
                "client_request_id": client_request_id,
                "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
            },
            "diagnostics": {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
        }
        print(f"[CAE][READONLY] items_count={items_count} run_id=None client_req_id={client_request_id} status=error error_code={response['error_code']}")
        return response
    except RuntimeError as e:
        error_msg = str(e)
        # Verificar si es error de overlay DHTMLX bloqueante
        if "DHX_BLOCKER_NOT_DISMISSED" in error_msg:
            response = {
                "status": "error",
                "error_code": "dhx_blocker_not_dismissed",
                "message": error_msg,
                "details": "No se pudo cerrar un overlay DHTMLX bloqueante después del login. "
                         "Revisar evidence en el directorio de runs para más detalles.",
                "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                "items": [],  # HOTFIX C2.13.6: Siempre array, nunca null
                "artifacts": {
                    "client_request_id": client_request_id,
                    "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
                },
                "diagnostics": {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
            }
            items_count = 0
            print(f"[CAE][READONLY] items_count={items_count} run_id=None client_req_id={client_request_id} status=error error_code={response['error_code']}")
            return response
        response = {
            "status": "error",
            "error_code": "runtime_error",
            "message": error_msg,
            "details": None,
            "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
            "items": [],  # HOTFIX C2.13.6: Siempre array, nunca null
            "artifacts": {
                "client_request_id": client_request_id,
                "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
            },
            "diagnostics": {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
        }
        items_count = 0
        print(f"[CAE][READONLY] items_count={items_count} run_id=None client_req_id={client_request_id} status=error error_code={response['error_code']}")
        return response
    except Exception as e:
        # HOTFIX C2.13.2: Manejo de errores robusto - devolver HTTP 200 con JSON, nunca lanzar excepción secundaria
        try:
            # Capturar PageContractError primero (antes de otras excepciones)
            from backend.adapters.egestiona.page_contract_validator import PageContractError
            if isinstance(e, PageContractError):
                # Construir artifacts con run_id si existe
                artifacts = {}
                try:
                    # Intentar obtener run_id si existe (puede estar en locals o en el contexto)
                    if run_id:
                        from backend.shared.path_utils import as_str, safe_path_join
                        from backend.repository.data_bootstrap_v1 import DATA_DIR
                        artifacts["run_id"] = run_id
                        # Convertir evidence_paths a dict con strings (no Path objects, no None problemáticos)
                        evidence_paths_clean = {}
                        if e.evidence_paths:
                            for key, value in e.evidence_paths.items():
                                # Solo incluir si no es None y es string válido
                                if value is not None:
                                    evidence_paths_clean[key] = as_str(value)
                        artifacts["evidence"] = evidence_paths_clean if evidence_paths_clean else None
                        # Intentar añadir instrumentation_path si existe
                        instrumentation_path = safe_path_join(Path(DATA_DIR) / "runs" / run_id / "evidence", "instrumentation.json")
                        if instrumentation_path and instrumentation_path.exists():
                            artifacts["instrumentation_path"] = as_str(instrumentation_path.relative_to(Path(DATA_DIR)))
                except Exception:
                    pass
                
                # HOTFIX C2.13.6: Construir response de error con contrato robusto
                response = {
                    "status": "error",
                    "error_code": e.error_code,
                    "message": e.message,
                    "details": e.details,
                    "run_id": run_id if run_id else None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                    "items": [],  # HOTFIX C2.13.6: Siempre array, nunca null
                    "artifacts": {
                        "client_request_id": client_request_id,
                        "run_id": run_id if run_id else None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
                        **(artifacts if artifacts else {}),  # Merge otros artifacts si existen
                    },
                    "diagnostics": {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
                }
                
                # Normalizar contrato usando helper centralizado (run_id puede ser None)
                normalize_contract(response, run_id)
                
                # Añadir client_request_id a artifacts SIEMPRE
                if not response.get("artifacts"):
                    response["artifacts"] = {}
                response["artifacts"]["client_request_id"] = client_request_id
                
                # HOTFIX C2.13.6: Loggear items_count antes de devolver
                items_count = len(response.get("items", []))
                run_id_str = response.get("run_id") or "None"
                artifacts_run_id_str = response.get("artifacts", {}).get("run_id") if response.get("artifacts") else "None"
                print(f"[CAE][READONLY] items_count={items_count} run_id={run_id_str} client_req_id={client_request_id} status=error error_code={e.error_code} artifacts.run_id={artifacts_run_id_str}")
                
                # Guardar response.json SIEMPRE (solo si hay run_id, READ-ONLY no toca filesystem)
                try:
                    if run_id:
                        run_dir = Path(DATA_DIR) / "runs" / run_id
                        if run_dir.exists():
                            response_path = run_dir / "response.json"
                            with open(response_path, "w", encoding="utf-8") as f:
                                pyjson.dump(response, f, indent=2, ensure_ascii=False, default=str)
                            client_req_id_path = run_dir / "client_request_id.txt"
                            with open(client_req_id_path, "w", encoding="utf-8") as f:
                                f.write(client_request_id)
                    else:
                        # READ-ONLY: NO guardar en filesystem si no hay run_id
                        pass
                except Exception as save_err:
                    pass
                
                # Instrumentación: loggear JSON en dev
                import os
                if os.getenv("ENVIRONMENT", "").lower() == "dev":
                    try:
                        print(f"[CAE_CONTRACT] Response ERROR (PageContractError): {pyjson.dumps(response, indent=2, default=str)}")
                    except Exception:
                        pass
                
                return response
        
            # Capturar también PriorityCommsModalNotDismissed si viene como excepción directa
            from backend.adapters.egestiona.priority_comms_headful import PriorityCommsModalNotDismissed
            if isinstance(e, PriorityCommsModalNotDismissed):
                # HOTFIX C2.13.6: Contrato de respuesta robusto
                response = {
                    "status": "error",
                    "error_code": "priority_comms_modal_not_dismissed",
                    "message": str(e),
                    "details": "No se pudo cerrar el modal de comunicados prioritarios después del login. "
                             "Revisar evidence en el directorio de runs para más detalles.",
                    "run_id": run_id if run_id else None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                    "items": [],  # HOTFIX C2.13.6: Siempre array, nunca null
                    "artifacts": {
                        "client_request_id": client_request_id,
                        "run_id": run_id if run_id else None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
                    },
                    "diagnostics": {},  # HOTFIX C2.13.6: Siempre incluir diagnostics (object)
                }
                # Normalizar contrato usando helper centralizado (run_id puede ser None)
                normalize_contract(response, run_id)
                
                # Añadir client_request_id a artifacts SIEMPRE
                if not response.get("artifacts"):
                    response["artifacts"] = {}
                response["artifacts"]["client_request_id"] = client_request_id
                
                # HOTFIX C2.13.6: Loggear items_count antes de devolver
                items_count = len(response.get("items", []))
                run_id_str = response.get("run_id") or "None"
                artifacts_run_id_str = response.get("artifacts", {}).get("run_id") if response.get("artifacts") else "None"
                print(f"[CAE][READONLY] items_count={items_count} run_id={run_id_str} client_req_id={client_request_id} status=error error_code={response['error_code']} artifacts.run_id={artifacts_run_id_str}")
                
                # Guardar response.json SIEMPRE (solo si hay run_id, READ-ONLY no toca filesystem)
                try:
                    if run_id:
                        run_dir = Path(DATA_DIR) / "runs" / run_id
                        if run_dir.exists():
                            response_path = run_dir / "response.json"
                            with open(response_path, "w", encoding="utf-8") as f:
                                pyjson.dump(response, f, indent=2, ensure_ascii=False, default=str)
                            client_req_id_path = run_dir / "client_request_id.txt"
                            with open(client_req_id_path, "w", encoding="utf-8") as f:
                                f.write(client_request_id)
                    else:
                        # READ-ONLY: NO guardar en filesystem si no hay run_id
                        pass
                except Exception as save_err:
                    pass
                
                return response
        
            # En caso de error inesperado, intentar construir artifacts básicos si hay run_id
            artifacts = {}
            try:
                if run_id:
                    from backend.shared.path_utils import as_str
                    artifacts["run_id"] = run_id
            except Exception:
                pass
            
            # HOTFIX C2.13.6: Contrato de respuesta robusto - siempre incluir run_id, items, diagnostics, artifacts
            response = {
                "status": "error",
                "error_code": "readonly_compute_failed",  # HOTFIX C2.13.2: Usar error_code consistente
                "message": f"Error durante computación READ-ONLY: {str(e)}",
                "details": {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": None,  # No incluir traceback completo por defecto (puede ser muy largo)
                },
                "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                "items": [],  # HOTFIX C2.13.6: Siempre array, nunca null
                "artifacts": {
                    "client_request_id": client_request_id,
                    "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
                } if not artifacts else {**artifacts, "run_id": artifacts.get("run_id")},
                "diagnostics": {
                    "run_id": None,  # HOTFIX C2.13.2: READ-ONLY no tiene run_id
                },
            }
            
            # Normalizar contrato usando helper centralizado (run_id puede ser None)
            normalize_contract(response, run_id)
            
            # Añadir client_request_id a artifacts SIEMPRE
            if not response.get("artifacts"):
                response["artifacts"] = {}
            response["artifacts"]["client_request_id"] = client_request_id
            
            # HOTFIX C2.12.6: READ-ONLY NO guarda en filesystem
            # Solo guardar si es error y hay run_id (caso legacy/fixture)
            # Para READ-ONLY puro, NO tocar filesystem
            try:
                if run_id:
                    # Solo guardar si hay run_id (caso legacy/fixture)
                    run_dir = Path(DATA_DIR) / "runs" / run_id
                    if run_dir.exists():
                        response_path = run_dir / "response.json"
                        with open(response_path, "w", encoding="utf-8") as f:
                            pyjson.dump(response, f, indent=2, ensure_ascii=False, default=str)
                        client_req_id_path = run_dir / "client_request_id.txt"
                        with open(client_req_id_path, "w", encoding="utf-8") as f:
                            f.write(client_request_id)
                else:
                    # READ-ONLY: NO guardar en filesystem si no hay run_id
                    pass
            except Exception as save_err:
                pass
            
            # HOTFIX C2.13.6: Loggear items_count antes de devolver (incluso en error)
            items_count = len(response.get("items", []))
            run_id_str = response.get("run_id") or "None"
            artifacts_run_id_str = response.get("artifacts", {}).get("run_id") if response.get("artifacts") else "None"
            print(f"[CAE][READONLY] items_count={items_count} run_id={run_id_str} client_req_id={client_request_id} status=error error_code={response['error_code']} artifacts.run_id={artifacts_run_id_str}")
            
            return response
        except Exception as handler_error:
            # HOTFIX C2.13.2: Si el handler de errores falla, devolver respuesta mínima sin lanzar excepción
            print(f"[CAE][ERROR] Error en handler de excepciones: {handler_error}")
            # HOTFIX C2.13.6: Contrato de respuesta robusto - siempre incluir run_id, items, diagnostics, artifacts
            return {
                "status": "error",
                "error_code": "readonly_compute_failed",
                "message": f"Error durante computación READ-ONLY: {str(e)} (handler error: {str(handler_error)})",
                "details": None,
                "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id (puede ser null)
                "items": [],  # HOTFIX C2.13.6: Siempre array, nunca null
                "artifacts": {
                    "client_request_id": client_request_id,
                    "run_id": None,  # HOTFIX C2.13.6: Siempre incluir run_id en artifacts
                },
                "diagnostics": {
                    "run_id": None,
                },
            }
        
        # Instrumentación: loggear JSON en dev
        import os
        if os.getenv("ENVIRONMENT", "").lower() == "dev":
            # HOTFIX C2.13.3: Eliminado import json local (usa pyjson del import global)
            try:
                print(f"[CAE_CONTRACT] Response ERROR (unexpected): {pyjson.dumps(response, indent=2, default=str)}")
            except Exception:
                pass
        
        return response


@router.post("/runs/egestiona/build_auto_upload_plan")
async def egestiona_build_auto_upload_plan(
    coord: str = "Kern",
    company_key: str = "",
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
    max_items: int = 200,  # SPRINT C2.15: Límite de items para snapshot
    max_pages: int = 10,  # SPRINT C2.15: Límite de páginas para snapshot
    request: Request = None,  # Para leer headers
):
    """
    SPRINT C2.15: Construye plan de auto-upload sin ejecutar uploads.
    
    Reutiliza C2.14.1 snapshot paginado y aplica política de decisión
    para clasificar items en AUTO_UPLOAD, REVIEW_REQUIRED, NO_MATCH.
    
    Response:
    {
        status: "ok",
        snapshot: { items: [...] },  # incluye pending_item_key
        decisions: [
            { pending_item_key, decision, reason_code, reason, confidence, local_doc_ref? }
        ],
        summary: {
            total, auto_upload_count, review_required_count, no_match_count
        },
        diagnostics: { pagination... }
    }
    """
    import uuid
    import os
    client_request_id = None
    if request and hasattr(request, 'headers'):
        client_request_id = request.headers.get("X-CLIENT-REQ-ID")
    if not client_request_id:
        client_request_id = str(uuid.uuid4())
    
    if not company_key:
        return {
            "status": "error",
            "error_code": "missing_company_key",
            "message": "company_key is required",
            "details": None,
            "snapshot": {"items": []},
            "decisions": [],
            "summary": {
                "total": 0,
                "auto_upload_count": 0,
                "review_required_count": 0,
                "no_match_count": 0,
            },
            "diagnostics": {},
            "artifacts": {"client_request_id": client_request_id},
        }
    
    # SPRINT C2.16.2: Generar run_id propio para plan
    import time
    import uuid
    from datetime import datetime
    from pathlib import Path
    from backend.shared.run_summary import save_run_summary
    
    # Generar run_id temporal para logging (antes de generar plan_id)
    temp_run_id = f"plan_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    started_at = datetime.utcnow()
    
    try:
        # Reutilizar snapshot paginado de C2.14.1
        from starlette.concurrency import run_in_threadpool
        from backend.adapters.egestiona.submission_plan_headful import run_build_submission_plan_readonly_headful
        
        print(f"[CAE][AUTO_UPLOAD_PLAN] Construyendo plan de auto-upload (temp_run_id={temp_run_id})...")
        plan_result = await run_in_threadpool(
            lambda: run_build_submission_plan_readonly_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                company_key=company_key,
                person_key=person_key,
                limit=limit,
                only_target=only_target,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.5,
                return_plan_only=True,  # NO crear run
                max_pages=max_pages,
                max_items=max_items,
            )
        )
        
        if not isinstance(plan_result, dict):
            return {
                "status": "error",
                "error_code": "unexpected_result_type",
                "message": f"Expected dict, got {type(plan_result)}",
                "details": None,
                "snapshot": {"items": []},
                "decisions": [],
                "summary": {
                    "total": 0,
                    "auto_upload_count": 0,
                    "review_required_count": 0,
                    "no_match_count": 0,
                },
                "diagnostics": {},
                "artifacts": {"client_request_id": client_request_id},
            }
        
        # Obtener snapshot (pending_items) y plan (con decisions)
        pending_items = plan_result.get("pending_items", [])
        plan_items = plan_result.get("plan", [])
        match_results = plan_result.get("match_results", [])
        diagnostics = plan_result.get("diagnostics") or {}
        instrumentation = plan_result.get("instrumentation", {})
        
        # SPRINT C2.17: Aplicar motor de decisión explícita
        from backend.shared.upload_decision_engine import apply_decisions_to_plan
        
        decisions = apply_decisions_to_plan(
            plan_items=plan_items,
            match_results=match_results,
            company_key=company_key,
            person_key=person_key,
            only_target=only_target,
            base_dir="data",
            user_overrides=None,  # SPRINT C2.17: Se puede añadir override manual en el futuro
        )
        
        # Contar por decisión
        auto_upload_count = len([d for d in decisions if d.get("decision") == "AUTO_UPLOAD"])
        review_required_count = len([d for d in decisions if d.get("decision") == "REVIEW_REQUIRED"])
        no_match_count = len([d for d in decisions if d.get("decision") == "NO_MATCH"])
        skipped_count = len([d for d in decisions if d.get("decision") == "SKIPPED"])
        
        # Construir snapshot (items con pending_item_key)
        snapshot_items = []
        for pending_item in pending_items:
            # Asegurar que tiene pending_item_key
            if "pending_item_key" not in pending_item:
                # Construir desde raw_data si está disponible
                raw_data = pending_item.get("raw_data", {})
                if raw_data:
                    from backend.adapters.egestiona.grid_extract import canonicalize_row
                    canonical = canonicalize_row(raw_data)
                    pending_item["pending_item_key"] = canonical.get("pending_item_key")
            snapshot_items.append(pending_item)
        
        # Construir summary
        summary = {
            "total": len(snapshot_items),
            "auto_upload_count": auto_upload_count,
            "review_required_count": review_required_count,
            "no_match_count": no_match_count,
            "skipped_count": skipped_count,  # SPRINT C2.17: Incluir skipped_count
        }
        
        # Incluir diagnostics de paginación si está disponible
        if instrumentation.get("pagination"):
            if not diagnostics:
                diagnostics = {}
            diagnostics["pagination"] = instrumentation["pagination"]
        
        # SPRINT C2.17: Generar plan_id estable (hash del contenido) y run_id
        from backend.shared.upload_decision_engine import generate_plan_id
        
        # Generar plan_id basado en contenido
        plan_id = generate_plan_id({
            "snapshot": {"items": snapshot_items},
            "decisions": decisions,
        })
        
        # SPRINT C2.17: Usar plan_id como directorio (no run_id)
        plan_dir = Path("data") / "runs" / plan_id
        plan_dir.mkdir(parents=True, exist_ok=True)
        
        # También generar run_id para run_summary (usar temp_run_id o generar nuevo)
        run_id = temp_run_id
        
        response = {
            "status": "ok",
            "plan_id": plan_id,  # SPRINT C2.17: Plan congelado con ID estable
            "snapshot": {"items": snapshot_items},
            "decisions": decisions,
            "summary": summary,
            "diagnostics": diagnostics,
            "artifacts": {
                "client_request_id": client_request_id,
                "run_id": run_id,  # SPRINT C2.16.2: Incluir run_id
                "coord": coord,  # SPRINT C2.17: Guardar metadata para recuperación
                "company_key": company_key,
                "person_key": person_key,
            },
        }
        
        # SPRINT C2.17: Guardar plan_response.json en plan_dir (usando plan_id)
        plan_response_path = plan_dir / "plan_response.json"
        with open(plan_response_path, "w", encoding="utf-8") as f:
            pyjson.dump(response, f, indent=2, ensure_ascii=False)
        
        # SPRINT C2.16.2: Guardar run_summary.json
        finished_at = datetime.utcnow()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        
        evidence_root = str(plan_dir)
        evidence_paths = {
            "plan_dir": str(plan_dir),
            "plan_response": str(plan_response_path),
        }
        
        try:
            save_run_summary(
                run_id=run_id,
                platform="egestiona",
                coord=coord,
                company_key=company_key,
                person_key=person_key,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                pending_total=len(snapshot_items),
                auto_upload_count=auto_upload_count,
                review_required_count=review_required_count,
                no_match_count=no_match_count,
                attempted_uploads=0,  # Plan no ejecuta uploads
                success_uploads=0,
                failed_uploads=0,
                errors=None,
                evidence_root=evidence_root,
                evidence_paths=evidence_paths,
                run_kind="plan",  # SPRINT C2.16.2
                base_dir="data",
            )
        except Exception as summary_error:
            print(f"[CAE][AUTO_UPLOAD_PLAN] ⚠️ Error guardando run_summary: {summary_error}")
        
        print(f"[CAE][AUTO_UPLOAD_PLAN] Plan construido: total={summary['total']}, auto_upload={auto_upload_count}, review_required={review_required_count}, no_match={no_match_count}")
        
        return response
    
    except Exception as e:
        import traceback
        print(f"[CAE][AUTO_UPLOAD_PLAN] Error: {e}")
        print(f"[CAE][AUTO_UPLOAD_PLAN] Traceback:\n{traceback.format_exc()}")
        
        return {
            "status": "error",
            "error_code": "plan_build_failed",
            "message": str(e),
            "details": traceback.format_exc() if os.getenv("ENVIRONMENT", "").lower() == "dev" else None,
            "snapshot": {"items": []},
            "decisions": [],
            "summary": {
                "total": 0,
                "auto_upload_count": 0,
                "review_required_count": 0,
                "no_match_count": 0,
            },
            "diagnostics": {},
            "artifacts": {"client_request_id": client_request_id},
        }


@router.post("/runs/egestiona/execute_submission_plan_scoped")
async def egestiona_execute_submission_plan_scoped(
    coord: str = "Kern",
    company_key: str = "",
    person_key: Optional[str] = None,
    limit: int = 20,
    only_target: bool = True,
    dry_run: bool = True,
    confirm_execute: bool = False,
    self_test: bool = False,
    self_test_doc_id: Optional[str] = None,
):
    """
    HEADFUL / WRITE (con guardrails fuertes): Ejecuta plan de envío para items AUTO_SUBMIT_OK.
    - Construye submission plan (reutiliza lógica existente)
    - Si dry_run=true: solo genera plan, NO ejecuta
    - Si dry_run=false pero confirm_execute=false: hard stop
    - Si dry_run=false y confirm_execute=true: ejecuta items con AUTO_SUBMIT_OK
    - Usa fechas del plan (proposed_fields), NO "hoy"
    - Evidence completa: execution_results.json, confirmation_text_dump.txt, PNGs
    """
    if not company_key:
        raise HTTPException(status_code=400, detail="company_key is required")
    
    try:
        run_id = await run_in_threadpool(
            lambda: run_execute_submission_plan_scoped_headful(
                base_dir="data",
                platform="egestiona",
                coordination=coord,
                company_key=company_key,
                person_key=person_key,
                limit=limit,
                only_target=only_target,
                dry_run=dry_run,
                confirm_execute=confirm_execute,
                self_test=self_test,
                self_test_doc_id=self_test_doc_id,
                slow_mo_ms=300,
                viewport={"width": 1600, "height": 1000},
                wait_after_login_s=2.5,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        error_msg = str(e)
        if "SECURITY_HARD_STOP" in error_msg or "GUARDRAIL_VIOLATION" in error_msg:
            raise HTTPException(status_code=403, detail=error_msg)
        # Capturar RuntimeError con mensaje DHX_BLOCKER_NOT_DISMISSED
        if "DHX_BLOCKER_NOT_DISMISSED" in error_msg:
            from backend.adapters.egestiona.priority_comms_headful import DhxBlockerNotDismissed
            error_detail = {
                "error": "dhx_blocker_not_dismissed",
                "message": error_msg,
                "detail": "No se pudo cerrar un overlay DHTMLX bloqueante después del login. "
                         "Revisar evidence en el directorio de runs para más detalles.",
            }
            raise HTTPException(status_code=422, detail=error_detail)
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        # Capturar excepciones de overlays DHTMLX bloqueantes
        from backend.adapters.egestiona.priority_comms_headful import PriorityCommsModalNotDismissed, DhxBlockerNotDismissed
        if isinstance(e, (PriorityCommsModalNotDismissed, DhxBlockerNotDismissed)):
            error_type = "priority_comms_modal_not_dismissed" if isinstance(e, PriorityCommsModalNotDismissed) else "dhx_blocker_not_dismissed"
            error_detail = {
                "error": error_type,
                "message": str(e),
                "detail": "No se pudo cerrar un overlay DHTMLX bloqueante después del login. "
                         "Revisar evidence en el directorio de runs para más detalles.",
            }
            if hasattr(e, 'run_id'):
                error_detail["run_id"] = e.run_id
            raise HTTPException(status_code=422, detail=error_detail)
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")
    return {"run_id": run_id, "runs_url": f"/runs/{run_id}"}


