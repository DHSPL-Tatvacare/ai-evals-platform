import { useState } from "react";
import {
  MermaidDiagram,
  FilterPills,
  CodeBlock,
  PageHeader,
} from "@/components";
import { usePageExport } from "@/hooks/usePageExport";

const pipelineOptions = [
  { id: "frontend", label: "Frontend LLM Pipeline" },
  { id: "backend", label: "Backend Job Pipeline" },
  { id: "voicerx", label: "Voice RX Two-Call" },
  { id: "batch", label: "Batch Pipeline" },
  { id: "adversarial", label: "Adversarial Pipeline" },
];

const frontendDiagram = `flowchart LR
    A["1. Validate"] -->|"Check API key, model"| B["2. Prepare"]
    B -->|"Build prompt, attach schema"| C["3. Execute"]
    C -->|"Call Gemini/OpenAI API"| D["4. Post-process"]
    D -->|"Parse JSON, validate schema"| E["Result"]

    style A fill:#6366f1,color:#fff
    style B fill:#8b5cf6,color:#fff
    style C fill:#a78bfa,color:#fff
    style D fill:#c4b5fd,color:#000
    style E fill:#10b981,color:#fff`;

const frontendCode = `// src/services/llm/pipeline/index.ts
export function createLLMPipeline(): LLMInvocationPipeline {
  const { apiKey, selectedModel } = useLLMSettingsStore.getState();
  if (!apiKey) throw new Error('API key not configured');
  return new LLMInvocationPipeline(apiKey, selectedModel);
}`;

const backendDiagram = `flowchart TD
    Click["User clicks 'Run'"] -->|"POST /api/jobs"| Create["Create Job (status: queued)"]
    Create --> Queue["Jobs Table"]
    Worker["worker_loop()"] -->|"Polls every 5s"| Queue
    Worker -->|"Picks oldest queued"| Mark["Mark as 'running'"]
    Mark -->|"process_job()"| Dispatch["JOB_HANDLERS registry"]
    Dispatch -->|"evaluate-voice-rx"| VRX["voice_rx_runner.py"]
    Dispatch -->|"evaluate-batch"| Batch["batch_runner.py"]
    Dispatch -->|"evaluate-adversarial"| Adv["adversarial_runner.py"]
    Dispatch -->|"evaluate-custom"| Custom["custom_evaluator_runner.py"]
    VRX --> Save["Save EvalRun + mark Job completed"]
    Batch --> Save
    Adv --> Save
    Custom --> Save

    style Click fill:#6366f1,color:#fff
    style Worker fill:#8b5cf6,color:#fff
    style Save fill:#10b981,color:#fff`;

const backendCode = `# job_worker.py — Handler registry
@register_job_handler("evaluate-voice-rx")
async def handle_evaluate_voice_rx(job_id, params):
    return await run_voice_rx_evaluation(job_id=job_id, params=params)

@register_job_handler("evaluate-batch")
async def handle_evaluate_batch(job_id, params):
    return await run_batch_evaluation(job_id=job_id, ...)

@register_job_handler("evaluate-adversarial")
async def handle_evaluate_adversarial(job_id, params):
    return await run_adversarial_evaluation(job_id=job_id, ...)`;

const voicerxDiagram = `flowchart TD
    Start["run_voice_rx_evaluation()"] --> Load["Load Listing + Audio from DB"]
    Load --> Settings["get_llm_settings_from_db()"]
    Settings --> Provider["create_llm_provider() + LoggingLLMWrapper"]
    Provider --> Check{"skip_transcription?"}

    Check -->|No| Call1["CALL 1: Transcription"]
    Check -->|Yes| Reuse["Reuse previous AI transcript"]

    Call1 --> Resolve1["resolve_prompt(transcription_prompt)"]
    Resolve1 --> LLM1["llm.generate_with_audio(prompt, audio, schema)"]
    LLM1 --> Parse1["parse_transcript_response()"]
    Parse1 --> Norm{"normalize_original?"}

    Norm -->|Yes| NormStep["Normalize: transliterate script"]
    Norm -->|No| Call2["CALL 2: Critique"]
    NormStep --> Call2
    Reuse --> Call2

    Call2 --> Resolve2["resolve_prompt(evaluation_prompt)"]
    Resolve2 --> LLM2["llm.generate_with_audio(prompt, audio, schema)"]
    LLM2 --> Parse2["parse_critique_response()"]
    Parse2 --> Save["Save EvalRun to DB"]

    style Start fill:#6366f1,color:#fff
    style Call1 fill:#f59e0b,color:#fff
    style Call2 fill:#ec4899,color:#fff
    style Save fill:#10b981,color:#fff`;

const batchDiagram = `flowchart TD
    Start["run_batch_evaluation()"] --> LoadCSV["DataLoader: parse CSV"]
    LoadCSV --> Resolve["Resolve thread IDs (all / sample / selected)"]
    Resolve --> Loop["For each thread_id"]
    Loop --> GetThread["loader.get_thread(id)"]
    GetThread --> Intent["IntentEvaluator.evaluate_thread()"]
    Intent --> Correct["CorrectnessEvaluator.evaluate_thread()"]
    Correct --> Effic["EfficiencyEvaluator.evaluate_thread()"]
    Effic --> CustomEvals["Custom evaluators (resolve_prompt + generate_json)"]
    CustomEvals --> SaveThread["Save ThreadEvaluation row"]
    SaveThread -->|"Next thread"| Loop
    SaveThread -->|"All done"| Summary["Compute summary + save EvalRun"]

    style Start fill:#6366f1,color:#fff
    style Loop fill:#8b5cf6,color:#fff
    style Summary fill:#10b981,color:#fff`;

const adversarialDiagram = `flowchart TD
    Start["run_adversarial_evaluation()"] --> Gen["Phase 1: Generate Test Cases"]
    Gen -->|"AdversarialEvaluator.generate_test_cases(n)"| Cases["Test Cases (categories + difficulty)"]
    Cases --> Loop["For each test case"]
    Loop --> Conv["Phase 2: ConversationAgent.run_conversation()"]
    Conv -->|"Multi-turn SSE chat"| Kaira["Live Kaira API"]
    Kaira --> Transcript["Conversation Transcript"]
    Transcript --> Judge["Phase 3: evaluate_transcript()"]
    Judge -->|"LLM judges safety/compliance"| Verdict["Verdict + goal_achieved"]
    Verdict --> SaveAdv["Save AdversarialEvaluation row"]
    SaveAdv -->|"Next case"| Loop
    SaveAdv -->|"All done"| Summary["Summary: verdict distribution + goal counts"]

    style Start fill:#6366f1,color:#fff
    style Gen fill:#f59e0b,color:#fff
    style Conv fill:#ec4899,color:#fff
    style Judge fill:#8b5cf6,color:#fff
    style Summary fill:#10b981,color:#fff`;

interface PipelineView {
  title: string;
  subtitle: string;
  diagram: string;
  code?: { code: string; language: "typescript" | "python" };
}

const pipelines: Record<string, PipelineView> = {
  frontend: {
    title: "Frontend LLM Pipeline",
    subtitle:
      "Used for real-time AI features in the browser. 4-stage pipeline in LLMInvocationPipeline.ts.",
    diagram: frontendDiagram,
    code: { code: frontendCode, language: "typescript" },
  },
  backend: {
    title: "Backend Job Pipeline",
    subtitle: "Background job processing via worker_loop() in job_worker.py.",
    diagram: backendDiagram,
    code: { code: backendCode, language: "python" },
  },
  voicerx: {
    title: "Voice RX Two-Call Pipeline (Detailed)",
    subtitle: "",
    diagram: voicerxDiagram,
  },
  batch: {
    title: "Batch Evaluation Pipeline",
    subtitle: "",
    diagram: batchDiagram,
  },
  adversarial: {
    title: "Adversarial Testing Pipeline",
    subtitle: "",
    diagram: adversarialDiagram,
  },
};

export default function Pipelines() {
  const [active, setActive] = useState("frontend");
  const { contentRef } = usePageExport();
  const current = pipelines[active];

  return (
    <div
      ref={contentRef}
      className="page-content animate-fade-in-up"
      data-title="Pipelines"
    >
      <PageHeader
        title="Execution Pipelines"
        subtitle="Trace how each run moves from request submission to persisted evaluation results."
        pageTitle="Pipelines"
        contentRef={contentRef}
      />

      <FilterPills
        options={pipelineOptions}
        active={active}
        onChange={setActive}
        className="mb-3"
      />

      <h3
        className="text-xl font-bold mt-4 mb-2"
        style={{ color: "var(--text)" }}
      >
        {current.title}
      </h3>
      {current.subtitle && (
        <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
          {current.subtitle}
        </p>
      )}

      <MermaidDiagram chart={current.diagram} />

      {current.code && (
        <CodeBlock code={current.code.code} language={current.code.language} />
      )}
    </div>
  );
}
