/**
 * Section 5 — frontend save gate.
 *
 * Pure helpers that compute "should the Save/Publish click proceed" from
 * the result of ``selectHardParseIssues``. The side-effect (notification
 * fired, click dropped) lives in ``WorkflowHeaderBar.tsx``; the decision
 * + message-building logic is here so it can be unit-tested without
 * mounting the header.
 *
 * Contract:
 *   - ``shouldBlockSave([])`` returns ``false`` — empty list = clean canvas
 *     OR partial-draft-only state. Both are saveable per the plan.
 *   - ``shouldBlockSave([...])`` returns ``true`` — every group has at
 *     least one hard issue (``selectHardParseIssues`` skips empty groups).
 *   - ``buildSaveBlockedMessage`` produces the notification copy. Single
 *     source of truth so tests can assert on the message shape.
 */
import type { HardParseIssueGroup } from "@/features/orchestration/store/workflowBuilderStore";

export function shouldBlockSave(groups: readonly HardParseIssueGroup[]): boolean {
  return groups.length > 0;
}

export function buildSaveBlockedMessage(
  groups: readonly HardParseIssueGroup[],
): string {
  const totalIssues = groups.reduce((acc, g) => acc + g.hardIssues.length, 0);
  const head = groups[0];
  const firstField = head?.hardIssues[0]?.field || "(node-level)";
  const issueWord = totalIssues === 1 ? "issue" : "issues";
  const nodeWord = groups.length === 1 ? "node" : "nodes";
  return (
    `Cannot save — ${totalIssues} schema ${issueWord} on ${groups.length} ` +
    `${nodeWord} (first: ${head?.nodeType ?? "?"} · ${firstField}). ` +
    `Fix the highlighted nodes and retry.`
  );
}
