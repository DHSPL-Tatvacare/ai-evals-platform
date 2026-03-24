import {
  TrendingUp,
  AlertTriangle,
  Target,
  BarChart3,
  Layers,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Card, InfoBox, PageHeader } from "@/features/guide/components";
import { usePageExport } from "@/features/guide/hooks/usePageExport";

/* ------------------------------------------------------------------ */
/*  Data                                                               */
/* ------------------------------------------------------------------ */

interface QuestionCard {
  icon: LucideIcon;
  question: string;
  answer: string;
  feature: string;
  accentVar: string;
}

const coreQuestions: QuestionCard[] = [
  {
    icon: AlertTriangle,
    question: "What keeps failing?",
    answer:
      "A recurring-issues table ranks problems by frequency across runs. When the same failure surfaces in 7 out of 12 runs, it stops being a one-off and becomes the obvious next fix.",
    feature: "Issues & Recommendations",
    accentVar: "var(--error)",
  },
  {
    icon: TrendingUp,
    question: "Are things improving?",
    answer:
      "A health-score trend line tracks quality over time. Push a prompt update, then watch whether scores climb or slide in subsequent runs — no manual tracking required.",
    feature: "Health & Trends",
    accentVar: "var(--success)",
  },
  {
    icon: Target,
    question: "What should we fix next?",
    answer:
      "Priority-ranked recommendations (P0 / P1 / P2) with projected impact. Gives your team a clear action list ordered by severity and recurrence — not a wall of individual failures.",
    feature: "Recommendations",
    accentVar: "var(--warning)",
  },
];

interface Differentiator {
  icon: LucideIcon;
  title: string;
  description: string;
}

const differentiators: Differentiator[] = [
  {
    icon: Layers,
    title: "Automatic cross-run synthesis",
    description:
      "Most eval tools show per-run results and leave you to spot patterns yourself. Cross-run analytics does that work automatically — deduplicating issues, counting frequency, and surfacing what matters most.",
  },
  {
    icon: BarChart3,
    title: "Rule compliance heatmaps",
    description:
      "See which evaluation rules chronically fail across runs. A rule passing at 40% over 10 runs is a clear signal that the prompt or schema needs rework — something you'd miss looking at individual reports.",
  },
  {
    icon: Zap,
    title: "Zero-config, on-demand compute",
    description:
      "No incremental pipelines or external dependencies. Reports compute on demand from cached single-run data, with two-level caching (single-run + cross-run) in one table. Simple, fast, debuggable.",
  },
];

const limitations = [
  {
    gap: "No statistical depth",
    meaning:
      "Arithmetic means and counts only. No confidence intervals, no significance testing.",
  },
  {
    gap: "No root-cause linking",
    meaning:
      "Issues report failure frequency ('Response Accuracy failed 7 times') but don't trace back to which prompt version or model caused it.",
  },
  {
    gap: "No trend intelligence",
    meaning:
      "Raw data points on a chart, not slope analysis. You see the line — recognizing 'declining at X%/week' is still on you.",
  },
  {
    gap: "Naive deduplication",
    meaning:
      "80-character prefix matching. Issues worded differently but describing the same problem may appear as separate entries.",
  },
];

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function ForWhatItsWorth() {
  const { contentRef } = usePageExport();

  return (
    <div
      ref={contentRef}
      className="page-content animate-fade-in-up"
      data-title="For What It's Worth?"
    >
      <PageHeader
        title="Cross-Run Analytics"
        subtitle="When you run evaluations repeatedly — across prompt iterations, model upgrades, or dataset changes — individual run reports aren't enough. Cross-run analytics aggregates results over time so you can track progress, spot regressions, and decide what to fix next."
        pageTitle="For What It's Worth?"
        contentRef={contentRef}
      />

      {/* Scope */}
      <h2
        className="text-2xl font-bold mb-4"
        style={{ color: "var(--text)" }}
      >
        What this is (and isn't)
      </h2>

      <InfoBox className="mb-10">
        This is <strong>operational visibility</strong>, not a full analytics
        platform. No statistical models, no anomaly detection, no drill-down
        query builders. It's built for team leads and PMs who need a quick
        read on eval health — are things getting better, what's still broken,
        and what should we prioritize.
      </InfoBox>

      {/* Core questions */}
      <h2
        className="text-2xl font-bold mb-5"
        style={{ color: "var(--text)" }}
      >
        Three questions it answers
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        {coreQuestions.map((q) => (
          <Card key={q.question} hoverable>
            <div className="flex flex-col gap-3 h-full">
              <div
                className="inline-flex h-10 w-10 items-center justify-center rounded-xl"
                style={{
                  background: "var(--bg-secondary)",
                  color: q.accentVar,
                }}
              >
                <q.icon size={20} />
              </div>
              <h3
                className="text-base font-bold tracking-tight"
                style={{ color: "var(--text)" }}
              >
                {q.question}
              </h3>
              <p
                className="text-sm leading-relaxed flex-1"
                style={{ color: "var(--text-secondary)" }}
              >
                {q.answer}
              </p>
              <span
                className="inline-block mt-auto text-xs font-semibold px-2 py-1 rounded-md"
                style={{
                  background: "var(--accent-surface)",
                  color: "var(--accent-text)",
                }}
              >
                {q.feature}
              </span>
            </div>
          </Card>
        ))}
      </div>

      {/* Audience */}
      <h2
        className="text-2xl font-bold mb-4"
        style={{ color: "var(--text)" }}
      >
        Built for
      </h2>

      <div
        className="rounded-xl px-5 py-4 mb-10"
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-subtle)",
        }}
      >
        <p
          className="text-sm leading-relaxed mb-3"
          style={{ color: "var(--text-secondary)" }}
        >
          Teams running evaluation suites regularly — especially{" "}
          <strong style={{ color: "var(--text)" }}>team leads and PMs</strong>{" "}
          who need to:
        </p>
        <ul
          className="list-disc list-inside space-y-1.5 text-sm"
          style={{ color: "var(--text-secondary)" }}
        >
          <li>
            <strong style={{ color: "var(--text)" }}>Report progress</strong>{" "}
            — "Health scores up 12% over the last 8 runs"
          </li>
          <li>
            <strong style={{ color: "var(--text)" }}>Prioritize fixes</strong>{" "}
            — "These 3 issues recur in every run"
          </li>
          <li>
            <strong style={{ color: "var(--text)" }}>Validate changes</strong>{" "}
            — "The prompt update eliminated the top P0 issue"
          </li>
          <li>
            <strong style={{ color: "var(--text)" }}>Track coverage</strong>{" "}
            — "Only 12 of 47 completed runs have an AI narrative"
          </li>
        </ul>
      </div>

      {/* How it works */}
      <h2
        className="text-2xl font-bold mb-5"
        style={{ color: "var(--text)" }}
      >
        How it works
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        {differentiators.map((d) => (
          <Card key={d.title}>
            <div className="flex flex-col gap-3">
              <div
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg"
                style={{
                  background: "var(--bg-secondary)",
                  color: "var(--accent-text)",
                }}
              >
                <d.icon size={16} />
              </div>
              <h3
                className="text-[1.0625rem] font-bold tracking-tight"
                style={{ color: "var(--text)" }}
              >
                {d.title}
              </h3>
              <p
                className="text-sm leading-relaxed"
                style={{ color: "var(--text-secondary)" }}
              >
                {d.description}
              </p>
            </div>
          </Card>
        ))}
      </div>

      {/* Known limitations */}
      <h2
        className="text-2xl font-bold mb-4"
        style={{ color: "var(--text)" }}
      >
        Known limitations
      </h2>

      <div
        className="rounded-xl overflow-hidden mb-10"
        style={{ border: "1px solid var(--border-subtle)" }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: "var(--bg-secondary)" }}>
              <th
                className="text-left px-4 py-2.5 font-semibold text-xs uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                Limitation
              </th>
              <th
                className="text-left px-4 py-2.5 font-semibold text-xs uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                In practice
              </th>
            </tr>
          </thead>
          <tbody>
            {limitations.map((l) => (
              <tr
                key={l.gap}
                className="border-t"
                style={{ borderColor: "var(--border-subtle)" }}
              >
                <td
                  className="px-4 py-2.5 font-medium whitespace-nowrap"
                  style={{ color: "var(--text)" }}
                >
                  {l.gap}
                </td>
                <td className="px-4 py-2.5" style={{ color: "var(--text-secondary)" }}>
                  {l.meaning}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Summary */}
      <h2
        className="text-2xl font-bold mb-4"
        style={{ color: "var(--text)" }}
      >
        The takeaway
      </h2>

      <InfoBox>
        Cross-run analytics turns individual evaluation runs into a
        longitudinal view of quality. The recurring-issues table and
        health-trend chart are the core — they answer questions that
        individual reports can't. The AI-generated narrative adds context
        but isn't the main value. Think of it as{" "}
        <strong>eval trend monitoring for teams that ship iteratively</strong>.
      </InfoBox>
    </div>
  );
}
