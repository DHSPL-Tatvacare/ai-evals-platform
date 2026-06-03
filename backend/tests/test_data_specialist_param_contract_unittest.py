"""P1 — the param/entity-id teaching must match the binder's real behavior.

Only :tenant_id/:app_id/:user_id bind; every other filter value is a
literal (quoted UUIDs auto-parameterized by parameterize_sql). The prompt
must NOT instruct ``:uuid_1``-style placeholders, and its quoted-uuid
exemplar must pass the real enforcers (check_before + prepare_query).
"""
from __future__ import annotations

import unittest

from app.services.chat_engine.manifest import load_all_manifests
from app.services.chat_engine.manifest_validator import (
    validate_exemplars_through_enforcers,
)
from app.services.chat_engine.workbench_catalog import (
    load_workbench_catalog_strict,
)
from app.services.sherlock_v3.data_specialist_prompt import (
    ENTITY_ID_FILTER_EXEMPLAR_SQL,
    build_data_specialist_prompt,
)


class ParamContractTest(unittest.TestCase):
    def _prompt(self) -> str:
        return build_data_specialist_prompt(
            app_id="inside-sales",
            schema_context={"tables": {}},
            allowed_tables=["fact_evaluation"],
            column_role_hints=[],
            exemplars=[],
            max_rows=200,
        )

    def test_prompt_does_not_teach_invented_param_placeholders(self) -> None:
        prompt = self._prompt()
        self.assertNotIn(":uuid_1", prompt)
        self.assertNotIn("Entity IDs are bind parameters too", prompt)
        self.assertNotIn("never hardcode UUID", prompt)

    def test_prompt_teaches_only_three_bound_params_and_literal_uuids(self) -> None:
        prompt = self._prompt()
        self.assertIn(":tenant_id", prompt)
        self.assertIn(":app_id", prompt)
        self.assertIn(":user_id", prompt)
        # Literal quoted UUID filter is the taught shape.
        self.assertIn("run_id = '", prompt)
        self.assertIn("never invent", prompt.lower())

    def test_entity_id_exemplar_passes_the_real_enforcers(self) -> None:
        # The shipped exemplar must survive check_before + prepare_query
        # against a real app catalog (Seam B mechanism, exercised here).
        app_id = "inside-sales"
        self.assertIn(app_id, load_all_manifests())
        catalog = load_workbench_catalog_strict(app_id)
        rejected = validate_exemplars_through_enforcers(
            catalog,
            app_id,
            extra_exemplars=[
                ("__p1_entity_id_filter__", ENTITY_ID_FILTER_EXEMPLAR_SQL)
            ],
        )
        offending = [r for r in rejected if r[0] == "__p1_entity_id_filter__"]
        self.assertEqual(offending, [], offending)


if __name__ == "__main__":
    unittest.main()
