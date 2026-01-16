from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.config_store_v1 import _atomic_write_json
from backend.shared.document_repository_v1 import SubmissionRuleV1


class SubmissionRulesStoreV1:
    """
    Store local (JSON) para reglas de envío.
    - rules/submission_rules.json: lista de reglas
    """

    def __init__(self, *, base_dir: str | Path = "data"):
        self.base_dir = ensure_data_layout(base_dir=base_dir)
        self.repo_dir = (Path(self.base_dir) / "repository").resolve()
        self.rules_dir = self.repo_dir / "rules"
        
        # Asegurar estructura de directorios
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        
        self.rules_path = self.rules_dir / "submission_rules.json"
        
        # Seed inicial si no existe
        self._ensure_seed()

    def _ensure_seed(self) -> None:
        """Crea el seed inicial (lista vacía) si no existe."""
        if not self.rules_path.exists():
            self._write_rules([])

    def _read_json(self, path: Path) -> dict:
        """Lee JSON desde un path."""
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict) -> None:
        """Escribe JSON de forma atómica."""
        _atomic_write_json(path, payload)

    def _read_rules(self) -> Dict[str, SubmissionRuleV1]:
        """Lee todas las reglas desde submission_rules.json."""
        raw = self._read_json(self.rules_path)
        rules_list = raw.get("rules", [])
        result: Dict[str, SubmissionRuleV1] = {}
        for rule_dict in rules_list:
            try:
                rule = SubmissionRuleV1.model_validate(rule_dict)
                result[rule.rule_id] = rule
            except Exception:
                continue
        return result

    def _write_rules(self, rules: List[SubmissionRuleV1]) -> None:
        """Escribe la lista de reglas."""
        payload = {
            "schema_version": "v1",
            "rules": [rule.model_dump(mode="json") for rule in rules]
        }
        self._write_json(self.rules_path, payload)

    def list_rules(self, include_disabled: bool = False) -> List[SubmissionRuleV1]:
        """Lista todas las reglas."""
        all_rules = list(self._read_rules().values())
        if not include_disabled:
            all_rules = [r for r in all_rules if r.enabled]
        return sorted(all_rules, key=lambda r: r.rule_id)

    def get_rule(self, rule_id: str) -> Optional[SubmissionRuleV1]:
        """Obtiene una regla por ID."""
        rules = self._read_rules()
        return rules.get(rule_id)

    def create_rule(self, rule: SubmissionRuleV1) -> SubmissionRuleV1:
        """Crea una nueva regla."""
        rules = self._read_rules()
        if rule.rule_id in rules:
            raise ValueError(f"Rule {rule.rule_id} already exists")
        rules[rule.rule_id] = rule
        self._write_rules(list(rules.values()))
        return rule

    def update_rule(self, rule_id: str, rule: SubmissionRuleV1) -> SubmissionRuleV1:
        """Actualiza una regla existente."""
        if rule.rule_id != rule_id:
            raise ValueError(f"rule_id mismatch: {rule_id} != {rule.rule_id}")
        rules = self._read_rules()
        if rule_id not in rules:
            raise ValueError(f"Rule {rule_id} not found")
        rules[rule_id] = rule
        self._write_rules(list(rules.values()))
        return rule

    def delete_rule(self, rule_id: str) -> None:
        """Elimina una regla."""
        rules = self._read_rules()
        if rule_id not in rules:
            raise ValueError(f"Rule {rule_id} not found")
        del rules[rule_id]
        self._write_rules(list(rules.values()))

    def duplicate_rule(self, rule_id: str, new_rule_id: str) -> SubmissionRuleV1:
        """Duplica una regla con nuevo ID."""
        original = self.get_rule(rule_id)
        if not original:
            raise ValueError(f"Rule {rule_id} not found")
        
        # Crear copia con nuevo ID
        new_rule_dict = original.model_dump()
        new_rule_dict["rule_id"] = new_rule_id
        new_rule = SubmissionRuleV1.model_validate(new_rule_dict)
        
        return self.create_rule(new_rule)





