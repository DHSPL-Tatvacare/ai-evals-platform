/**
 * Drift-lock parity — frontend half.
 *
 * Reads the JSON fixtures under ``backend/tests/fixtures/contract_drift/``
 * and runs them through ``parseNodeConfig(mode: 'draft')``. The backend
 * mirror (``backend/tests/test_contract_drift_fixtures.py``) runs the SAME
 * files through ``validate_definition(mode='draft')``. Together they ensure
 * the four historically-drifted node contracts (``logic.split`` /
 * ``logic.wait`` / ``source.cohort_query`` / ``crm.send_wati``) stay
 * aligned until Phase 16 codegen replaces the hand-written Zod mirror.
 *
 * A change that lands on only one side will fail the matching test on the
 * other side, surfacing drift in CI rather than at publish-time 422.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { isHardParseIssue, parseNodeConfig } from "../nodeConfig";

const FIXTURES_DIR = join(
  __dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "backend",
  "tests",
  "fixtures",
  "contract_drift",
);

function loadFixture(name: string): { node_type: string; config: unknown } {
  const raw = readFileSync(join(FIXTURES_DIR, name), "utf-8");
  return JSON.parse(raw) as { node_type: string; config: unknown };
}

const VALID = [
  "logic_split.valid_draft.json",
  "logic_wait.valid_draft.json",
  "source_cohort_query.valid_draft.json",
  "crm_send_wati.valid_draft.json",
];

const INVALID = [
  "logic_split.invalid_fabricated_key.json",
  "logic_wait.invalid_fabricated_key.json",
  "source_cohort_query.invalid_fabricated_key.json",
  "crm_send_wati.invalid_fabricated_key.json",
];

describe("contract drift fixtures — frontend half", () => {
  it.each(VALID)(
    "%s parses as a valid draft",
    (name) => {
      const fx = loadFixture(name);
      const result = parseNodeConfig(fx.node_type, fx.config, { mode: "draft" });
      expect(result.ok).toBe(true);
    },
  );

  it.each(INVALID)(
    "%s is rejected with a hard parse issue",
    (name) => {
      const fx = loadFixture(name);
      const result = parseNodeConfig(fx.node_type, fx.config, { mode: "draft" });
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.issues.some(isHardParseIssue)).toBe(true);
      }
    },
  );
});
