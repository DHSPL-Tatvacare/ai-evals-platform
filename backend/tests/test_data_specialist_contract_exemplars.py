"""Seam B — every verified-query exemplar shipped to the data_specialist
prompt MUST pass the real enforcers (sql_bouncer.check_before +
sql_agent.prepare_query) for its app's catalog/graph.

This IS the boot guard, exercised as a test. A failing exemplar here is
a contract divergence the next tasks fix — it is NOT a reason to delete
the guard.
"""
from __future__ import annotations

import unittest

from app.services.chat_engine.manifest import load_all_manifests
from app.services.chat_engine.manifest_validator import (
    ExemplarContractError,
    validate_exemplars_through_enforcers,
)
from app.services.chat_engine.workbench_catalog import (
    load_workbench_catalog_strict,
)

# Exemplars known to FAIL the enforcers today. Marked rather than deleted
# so the guard stays honest while later tasks (P1/P2/P3) repair the
# contract. Format: (app_id, verified_query_name).
KNOWN_FAILING_EXEMPLARS: frozenset[tuple[str, str]] = frozenset()


class ExemplarContractTest(unittest.TestCase):
    def test_every_app_exemplar_passes_the_real_enforcers(self) -> None:
        app_ids = sorted(load_all_manifests().keys())
        self.assertTrue(app_ids, "no manifests registered")

        failures: list[str] = []
        for app_id in app_ids:
            catalog = load_workbench_catalog_strict(app_id)
            rejected = validate_exemplars_through_enforcers(catalog, app_id)
            for name, reason in rejected:
                if (app_id, name) in KNOWN_FAILING_EXEMPLARS:
                    continue
                failures.append(f"[{app_id}] {name}: {reason}")

        self.assertEqual(
            failures,
            [],
            "verified-query exemplars rejected by the real enforcers:\n  - "
            + "\n  - ".join(failures),
        )

    def test_guard_raises_on_a_deliberately_broken_exemplar(self) -> None:
        # The guard must surface a rejection, not silently pass, when an
        # exemplar references a table the bouncer forbids.
        app_id = sorted(load_all_manifests().keys())[0]
        catalog = load_workbench_catalog_strict(app_id)
        rejected = validate_exemplars_through_enforcers(
            catalog,
            app_id,
            extra_exemplars=[("__broken__", "SELECT * FROM nonexistent_table_xyz")],
        )
        names = {name for name, _ in rejected}
        self.assertIn("__broken__", names)

    def test_raise_if_rejected_blocks_boot(self) -> None:
        app_id = sorted(load_all_manifests().keys())[0]
        catalog = load_workbench_catalog_strict(app_id)
        with self.assertRaises(ExemplarContractError):
            validate_exemplars_through_enforcers(
                catalog,
                app_id,
                extra_exemplars=[("__broken__", "SELECT * FROM nonexistent_table_xyz")],
                raise_on_reject=True,
            )


if __name__ == "__main__":
    unittest.main()
