/**
 * Info tooltip content for each report section.
 * Mirrors the Scoring & Grading Reference from the PDF export
 * so the on-screen report is self-sustained without needing the PDF.
 */

// ── Shared sub-components ──────────────────────────────────────

function Dot({ color }: { color: string }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full shrink-0"
      style={{ backgroundColor: color }}
    />
  );
}

function Row({ dot, label, desc }: { dot?: string; label: string; desc: string }) {
  return (
    <div className="flex items-start gap-1.5 py-0.5">
      {dot && <Dot color={dot} />}
      <span>
        <span className="font-semibold text-[var(--text-primary)]">{label}</span>
        {' \u2014 '}
        {desc}
      </span>
    </div>
  );
}

function SectionTitle({ children }: { children: string }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)] mt-2 mb-1 first:mt-0">
      {children}
    </p>
  );
}

// ── Executive Summary ──────────────────────────────────────────

export function EXECUTIVE_SUMMARY_INFO({ isAdversarial }: { isAdversarial?: boolean }) {
  return (
    <>
      <SectionTitle>Health Score</SectionTitle>
      <p className="mb-1.5">
        Equally-weighted average of four dimensions, each scored 0-100%.
        If a dimension has no data, its weight is redistributed among active dimensions.
      </p>

      <SectionTitle>Metrics</SectionTitle>
      {isAdversarial ? (
        <>
          <Row label="Pass Rate" desc="Percentage of adversarial tests the bot passed." />
          <Row label="Goal Achievement" desc="How often the adversarial goal was achieved/blocked correctly." />
          <Row label="Rule Compliance" desc="Percentage of tests where evaluation rules were satisfied." />
          <Row label="Difficulty Score" desc="Weighted score factoring test difficulty levels." />
        </>
      ) : (
        <>
          <Row label="Intent Accuracy" desc="How well the bot understood what the user was asking for." />
          <Row label="Correctness" desc="Percentage of threads where all evaluation rules were satisfied." />
          <Row label="Efficiency" desc="Percentage of threads rated EFFICIENT or ACCEPTABLE." />
          <Row label="Task Completion" desc="Percentage of threads where the user's task was fully completed." />
        </>
      )}

      <SectionTitle>Grade Scale</SectionTitle>
      <div className="grid grid-cols-3 gap-x-3 gap-y-0.5 text-[11px]">
        <span><span className="font-semibold" style={{ color: '#10b981' }}>A+</span> 95-100</span>
        <span><span className="font-semibold" style={{ color: '#10b981' }}>A</span> 90-94</span>
        <span><span className="font-semibold" style={{ color: '#10b981' }}>A-</span> 85-89</span>
        <span><span className="font-semibold" style={{ color: '#10b981' }}>B+</span> 80-84</span>
        <span><span className="font-semibold" style={{ color: '#10b981' }}>B</span> 75-79</span>
        <span><span className="font-semibold" style={{ color: '#10b981' }}>B-</span> 70-74</span>
        <span><span className="font-semibold" style={{ color: '#f59e0b' }}>C+</span> 65-69</span>
        <span><span className="font-semibold" style={{ color: '#f59e0b' }}>C</span> 60-64</span>
        <span><span className="font-semibold" style={{ color: '#f59e0b' }}>C-</span> 55-59</span>
        <span><span className="font-semibold" style={{ color: '#ef4444' }}>D+</span> 50-54</span>
        <span><span className="font-semibold" style={{ color: '#ef4444' }}>D</span> 45-49</span>
        <span><span className="font-semibold" style={{ color: '#ef4444' }}>F</span> 0-44</span>
      </div>

      <SectionTitle>Top Issues Priority</SectionTitle>
      <Row dot="#ef4444" label="P0" desc="Must fix immediately — high user impact or safety concern." />
      <Row dot="#f59e0b" label="P1" desc="Should fix soon — noticeable quality or compliance gap." />
      <Row dot="#3b82f6" label="P2" desc="Improvement opportunity — nice-to-have refinement." />
    </>
  );
}

// ── Verdict Distributions ──────────────────────────────────────

export function VERDICT_DISTRIBUTIONS_INFO({ isAdversarial }: { isAdversarial?: boolean }) {
  return (
    <>
      <SectionTitle>Correctness Verdicts</SectionTitle>
      <Row dot="#16a34a" label="PASS" desc="All evaluation rules satisfied; response is correct." />
      <Row dot="#6b7280" label="NOT APPLICABLE" desc="Thread could not be meaningfully evaluated." />
      <Row dot="#ca8a04" label="SOFT FAIL" desc="Minor rule violations that don't break the core task." />
      <Row dot="#dc2626" label="HARD FAIL" desc="Significant rule violations; response is substantially wrong." />
      <Row dot="#7c2d12" label="CRITICAL" desc="Severe failure — safety, compliance, or data-integrity violation." />

      <SectionTitle>Efficiency Verdicts</SectionTitle>
      <Row dot="#16a34a" label="EFFICIENT" desc="Task completed in the minimum expected turns." />
      <Row dot="#3b82f6" label="ACCEPTABLE" desc="Slightly more turns than optimal, but reasonable." />
      <Row dot="#6b7280" label="INCOMPLETE" desc="Conversation ended before the task was finished." />
      <Row dot="#ca8a04" label="FRICTION" desc="Unnecessary back-and-forth that delayed task completion." />
      <Row dot="#dc2626" label="BROKEN" desc="Conversation loop or dead-end; task could not progress." />

      <SectionTitle>Intent Accuracy Tiers</SectionTitle>
      <Row dot="#16a34a" label="High (>=80%)" desc="Bot accurately identified the user's intent." />
      <Row dot="#ca8a04" label="Medium (50-79%)" desc="Partial intent recognition, some misunderstanding." />
      <Row dot="#dc2626" label="Low (<50%)" desc="Bot significantly misunderstood the user's intent." />

      {isAdversarial && (
        <>
          <SectionTitle>Adversarial Verdicts</SectionTitle>
          <Row dot="#16a34a" label="PASS" desc="Bot successfully resisted the adversarial attack." />
          <Row dot="#ca8a04" label="SOFT FAIL" desc="Minor vulnerability — bot partially complied." />
          <Row dot="#dc2626" label="FAIL / HARD FAIL" desc="Bot was successfully exploited by the adversarial prompt." />
        </>
      )}
    </>
  );
}

// ── Rule Compliance ────────────────────────────────────────────

export function RULE_COMPLIANCE_INFO() {
  return (
    <>
      <SectionTitle>Compliance Rate Bands</SectionTitle>
      <Row dot="#10b981" label=">=80%" desc="Rule is well-addressed by the current prompt/bot." />
      <Row dot="#f59e0b" label="50-79%" desc="Rule needs attention — inconsistent compliance." />
      <Row dot="#ef4444" label="<50%" desc="Rule is frequently violated — likely a prompt gap." />

      <SectionTitle>Severity Levels</SectionTitle>
      <Row dot="#6b7280" label="LOW" desc="Informational rule, minor impact if violated." />
      <Row dot="#F59E0B" label="MEDIUM" desc="Noticeable quality issue if violated." />
      <Row dot="#EF4444" label="HIGH" desc="Significant impact on user experience or correctness." />
      <Row dot="#7c2d12" label="CRITICAL" desc="Safety or compliance violation — must be fixed." />

      <SectionTitle>Co-Failure Patterns</SectionTitle>
      <p>
        Shows rules that tend to fail together, indicating shared root causes or dependencies.
        High co-occurrence rates suggest fixing one rule may also fix the other.
      </p>
    </>
  );
}

// ── Friction & Efficiency Analysis ─────────────────────────────

export function FRICTION_INFO() {
  return (
    <>
      <SectionTitle>Friction Metrics</SectionTitle>
      <p className="mb-1">
        Friction turns are conversation exchanges that added unnecessary effort or confusion.
      </p>
      <Row dot="#EF4444" label="Bot-Caused" desc="Friction from incorrect, unclear, or unhelpful bot responses." />
      <Row dot="#3b82f6" label="User-Caused" desc="Friction from ambiguous or incomplete user messages." />

      <SectionTitle>Recovery Quality</SectionTitle>
      <Row dot="#16a34a" label="Smooth" desc="Bot recovered gracefully from the friction." />
      <Row dot="#3b82f6" label="Adequate" desc="Bot recovered but with some extra effort." />
      <Row dot="#ca8a04" label="Partial" desc="Bot only partially recovered, issue lingered." />
      <Row dot="#dc2626" label="Failed" desc="Bot could not recover from the friction point." />

      <SectionTitle>Avg Turns by Verdict</SectionTitle>
      <p>
        Average number of conversation turns for threads in each efficiency verdict category.
        Lower is better for EFFICIENT; high turn counts in FRICTION/BROKEN indicate problems.
      </p>
    </>
  );
}

// ── Adversarial Breakdown ──────────────────────────────────────

export function ADVERSARIAL_INFO() {
  return (
    <>
      <SectionTitle>Category Results</SectionTitle>
      <p className="mb-1">
        Pass rate for each adversarial attack category. Categories with lower pass rates
        indicate areas where the bot is most vulnerable.
      </p>

      <SectionTitle>Difficulty Levels</SectionTitle>
      <Row dot="#10b981" label="EASY" desc="Basic adversarial attempts that the bot should always resist." />
      <Row dot="#f59e0b" label="MEDIUM" desc="Moderate sophistication — requires good guardrails." />
      <Row dot="#ef4444" label="HARD" desc="Advanced attacks — tests the limits of bot safety." />
    </>
  );
}

// ── Exemplar Threads ───────────────────────────────────────────

export function EXEMPLAR_INFO({ isAdversarial }: { isAdversarial?: boolean }) {
  return (
    <>
      <SectionTitle>What Are Exemplars?</SectionTitle>
      <p className="mb-1">
        {isAdversarial
          ? 'Representative best and worst adversarial test cases selected by composite score. Each includes AI-generated analysis explaining what happened and why.'
          : 'Representative best and worst threads selected by composite score (weighted blend of intent accuracy, correctness, efficiency, and task completion). Each includes AI-generated analysis.'
        }
      </p>

      <SectionTitle>Card Elements</SectionTitle>
      <Row label="Best / Worst" desc="Whether this is a top-performing or bottom-performing example." />
      <Row label="Thread ID" desc="Click the pop-out icon to view the full thread detail in a new tab." />
      {isAdversarial ? (
        <>
          <Row label="Category" desc="The adversarial attack type used." />
          <Row label="Difficulty" desc="EASY, MEDIUM, or HARD test difficulty." />
          <Row label="Goal Achieved/Failed" desc="Whether the adversarial goal was met." />
        </>
      ) : (
        <Row label="Complete / Incomplete" desc="Whether the user's task was fully completed." />
      )}
      <Row label="Verdict Badge" desc="The correctness verdict for this thread." />

      <SectionTitle>AI Analysis</SectionTitle>
      <Row label="What happened" desc="Factual summary of the conversation." />
      <Row label="Why" desc="Root cause analysis of success or failure." />
      <Row label="Prompt gap" desc="If identified, where the prompt may need improvement." />
    </>
  );
}

// ── Prompt Gap Analysis ────────────────────────────────────────

export function PROMPT_GAP_INFO() {
  return (
    <>
      <SectionTitle>Gap Types</SectionTitle>
      <Row dot="#3b82f6" label="UNDERSPEC" desc="Prompt lacks explicit guidance on behavior that evaluation rules expect." />
      <Row dot="#f59e0b" label="SILENT" desc="Prompt doesn't address a rule at all — expected behavior is neither required nor prohibited." />
      <Row dot="#ef4444" label="LEAKAGE" desc="Internal evaluation criteria are leaking into the prompt, potentially biasing the agent." />
      <Row dot="#8b5cf6" label="CONFLICTING" desc="Prompt actively contradicts what evaluation rules require." />

      <SectionTitle>How To Read</SectionTitle>
      <p>
        Each row maps a prompt section to an evaluation rule, showing where the two are misaligned.
        Click any row to reveal the AI-suggested fix.
      </p>
    </>
  );
}

// ── Recommendations ────────────────────────────────────────────

export function RECOMMENDATIONS_INFO() {
  return (
    <>
      <SectionTitle>Priority Levels</SectionTitle>
      <Row dot="#ef4444" label="P0 - CRITICAL" desc="Must fix immediately — high user impact or safety concern." />
      <Row dot="#f59e0b" label="P1 - HIGH" desc="Should fix soon — noticeable quality or compliance gap." />
      <Row dot="#3b82f6" label="P2 - MEDIUM" desc="Improvement opportunity — nice-to-have refinement." />

      <SectionTitle>Projected Reduction</SectionTitle>
      <p>
        AI-estimated impact of implementing the recommendation, shown as expected reduction
        in specific verdict categories. These are projections, not guarantees.
      </p>
    </>
  );
}
