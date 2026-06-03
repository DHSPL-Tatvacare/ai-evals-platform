"""Seam A — the query-contract section is an OUTPUT of the enforcers.

Each bouncer rule owns a one-line ``teach`` string (so a new rule cannot
ship untaught), and ``prepare_query`` owns the bound-param + quoting
contract. ``build_data_specialist_prompt`` RENDERS both in place of the
old hand-written contract prose — teach == enforce by construction.
"""
from __future__ import annotations

import unittest

from app.services.chat_engine.manifest import load_all_manifests
from app.services.chat_engine.manifest_validator import (
    validate_exemplars_through_enforcers,
)
from app.services.chat_engine.sql_agent import BINDER_CONTRACT
from app.services.chat_engine.sql_bouncer import RULE_TEACH
from app.services.chat_engine.workbench_catalog import (
    load_workbench_catalog_strict,
)
from app.services.sherlock_v3.data_specialist_prompt import (
    GRAIN_GROUP_BY_EXEMPLAR_SQL,
    MULTI_GRAIN_JOIN_EXEMPLAR_SQL,
    build_data_specialist_prompt,
)


class RuleTeachTest(unittest.TestCase):
    def _prompt(self) -> str:
        return build_data_specialist_prompt(
            app_id="inside-sales",
            schema_context={"tables": {}},
            allowed_tables=["fact_evaluation"],
            column_role_hints=[],
            exemplars=[],
            max_rows=200,
        )

    def test_every_bouncer_rule_exposes_a_nonempty_teach_string(self) -> None:
        # Cover every rule the bouncer applies pre-execution (R1..R8s),
        # so a new rule can't ship without a model-facing teaching line.
        expected_rules = {
            "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R7s", "R8a", "R8b",
        }
        self.assertEqual(set(RULE_TEACH), expected_rules)
        for rule_id, teach in RULE_TEACH.items():
            self.assertIsInstance(teach, str, rule_id)
            self.assertTrue(teach.strip(), f"{rule_id} has an empty teach string")
            self.assertEqual(teach, teach.strip(), rule_id)

    def test_binder_contract_states_bound_params_and_quoting_rule(self) -> None:
        self.assertTrue(BINDER_CONTRACT.strip())
        self.assertIn(":tenant_id", BINDER_CONTRACT)
        self.assertIn(":app_id", BINDER_CONTRACT)
        self.assertIn(":user_id", BINDER_CONTRACT)
        # The quoting rule is the binder's truth (parameterize_sql).
        self.assertIn("never invent", BINDER_CONTRACT.lower())

    def test_assembled_prompt_renders_every_rule_teach_string(self) -> None:
        prompt = self._prompt()
        for rule_id, teach in RULE_TEACH.items():
            self.assertIn(teach, prompt, f"prompt missing teach for {rule_id}")

    def test_assembled_prompt_renders_the_binder_contract(self) -> None:
        prompt = self._prompt()
        self.assertIn(BINDER_CONTRACT.strip(), prompt)

    def test_r5_teaches_complete_group_by(self) -> None:
        # P2 — every non-aggregated SELECT column in GROUP BY.
        self.assertIn("GROUP BY", RULE_TEACH["R5"])
        self.assertIn("non-aggregated", RULE_TEACH["R5"].lower())

    def test_r6_r8_teach_grain_fan_chasm(self) -> None:
        # P3 — aggregate at the lowest grain; never sum a one-side column
        # across a many-to-one join; never join two facts through a dimension.
        self.assertIn("lowest-grain", RULE_TEACH["R6"].lower())
        self.assertIn("fan trap", RULE_TEACH["R8a"].lower())
        self.assertIn("chasm trap", RULE_TEACH["R8b"].lower())

    def test_r7s_teaches_scope_in_where_and_join_on(self) -> None:
        # P4 — tenant/app scope on every alias, in WHERE AND in JOIN ON.
        teach = RULE_TEACH["R7s"].lower()
        self.assertIn(":tenant_id", RULE_TEACH["R7s"])
        self.assertIn(":app_id", RULE_TEACH["R7s"])
        self.assertIn("where", teach)
        self.assertIn("join on", teach)

    def test_r1_teaches_single_select_no_comments_no_stacked(self) -> None:
        # P6 — R1's enforced bans (comments, stacked statements, non-SELECT)
        # are taught from the rule, not a separate prose block.
        teach = RULE_TEACH["R1"].lower()
        self.assertIn("select", teach)
        self.assertIn("comment", teach)
        self.assertIn("stacked", teach)

    def test_r7_teaches_server_owns_limit(self) -> None:
        # P6 — R7 rewrites LIMIT server-side; the model must not hand-write
        # its own LIMIT for the cap.
        teach = RULE_TEACH["R7"].lower()
        self.assertIn("server", teach)
        self.assertIn("limit", teach)

    def test_assembled_prompt_surfaces_r1_and_r7_from_the_rules(self) -> None:
        # P6 — the assembled prompt renders R1/R7 verbatim from RULE_TEACH;
        # no parallel prose authors these behaviors.
        prompt = self._prompt()
        self.assertIn(RULE_TEACH["R1"], prompt)
        self.assertIn(RULE_TEACH["R7"], prompt)

    def test_prompt_renders_grain_and_multi_grain_exemplars(self) -> None:
        # The prompt indents each exemplar; assert on stable first lines.
        prompt = self._prompt()
        self.assertIn(GRAIN_GROUP_BY_EXEMPLAR_SQL.splitlines()[0], prompt)
        self.assertIn("GROUP BY agent", prompt)
        self.assertIn(MULTI_GRAIN_JOIN_EXEMPLAR_SQL.splitlines()[0], prompt)
        self.assertIn("JOIN analytics.dim_lead dl ON la.lead_id = dl.lead_id", prompt)

    def test_grain_exemplars_pass_the_real_enforcers(self) -> None:
        # Seam B — both new exemplars survive check_before + prepare_query.
        app_id = "inside-sales"
        self.assertIn(app_id, load_all_manifests())
        catalog = load_workbench_catalog_strict(app_id)
        rejected = validate_exemplars_through_enforcers(
            catalog,
            app_id,
            extra_exemplars=[
                ("__p2_grain_group_by__", GRAIN_GROUP_BY_EXEMPLAR_SQL),
                ("__p3_multi_grain_join__", MULTI_GRAIN_JOIN_EXEMPLAR_SQL),
            ],
        )
        self.assertEqual(rejected, [], rejected)

    def test_p1_param_wording_is_sourced_from_the_binder(self) -> None:
        # P1's corrected wording must live in the binder contract, not in
        # hand-prose — and must NOT teach invented :uuid_N placeholders.
        prompt = self._prompt()
        self.assertNotIn(":uuid_1", prompt)
        self.assertIn(":tenant_id", prompt)
        self.assertIn("run_id = '", prompt)


if __name__ == "__main__":
    unittest.main()
