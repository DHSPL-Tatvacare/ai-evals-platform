import { Card, MermaidDiagram, DataTable, Badge, CodeBlock, ExportButton, InfoBox } from '@/components';
import { usePageExport } from '@/hooks/usePageExport';
import { templateVariables, type TemplateVariable } from '@/data/templateVars';

const variableResolutionDiagram = `flowchart LR
    Prompt["Prompt Template"] -->|"extractVariables()"| Extract["Extract {{var}} tokens"]
    Extract -->|"For each variable"| Resolve["resolveVariable()"]
    Resolve -->|"text type"| Sub["Substitute in prompt string"]
    Resolve -->|"file type"| Keep["Keep as placeholder (handled by LLM service)"]
    Resolve -->|"computed type"| Compute["Compute from context (transcript, AI eval)"]
    Compute --> Sub
    Sub --> Final["Resolved Prompt"]
    Keep --> Final

    style Prompt fill:#6366f1,color:#fff
    style Final fill:#10b981,color:#fff`;

const jsonSchemaExample = `{
  "type": "object",
  "properties": {
    "segments": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "speaker": { "type": "string" },
          "text": { "type": "string" },
          "score": { "type": "number" }
        },
        "required": ["speaker", "text", "score"]
      }
    }
  },
  "required": ["segments"]
}`;

const fieldBasedExample = `[
  {
    "key": "overall_score",
    "type": "number",
    "label": "Overall Score",
    "description": "0-100 quality score",
    "isMainMetric": true,
    "thresholds": { "red": 40, "yellow": 70, "green": 90 }
  },
  {
    "key": "reasoning",
    "type": "string",
    "label": "Reasoning",
    "description": "Explanation for the score"
  }
]`;

const promptTemplateExample = `You are an expert medical transcription evaluator.

Listen to the audio file: {{audio}}

Compare the original transcript below with the AI-generated transcript.

=== ORIGINAL TRANSCRIPT ===
{{transcript}}

=== AI TRANSCRIPT (Judge) ===
{{llm_transcript}}

The original transcript uses {{original_script}} script.
There are {{segment_count}} segments to evaluate.

For each segment, provide:
- Accuracy score (0-100)
- Speaker identification correctness
- Medical terminology accuracy
- Overall assessment`;

const badgeColorMap: Record<string, 'amber' | 'blue' | 'purple'> = {
  file: 'amber',
  text: 'blue',
  computed: 'purple',
};

const variableColumns = [
  {
    key: 'name' as const,
    header: 'Variable',
    render: (val: unknown) => <code style={{ color: 'var(--accent-text)' }}>{String(val)}</code>,
  },
  {
    key: 'type' as const,
    header: 'Type',
    render: (val: unknown) => <Badge color={badgeColorMap[String(val)] || 'blue'}>{String(val)}</Badge>,
  },
  { key: 'description' as const, header: 'Description', wrap: true },
  { key: 'apps' as const, header: 'Apps' },
  { key: 'promptTypes' as const, header: 'Prompt Types', wrap: true },
  { key: 'flows' as const, header: 'Flows', wrap: true },
];

export default function PromptsSchemas() {
  const { contentRef } = usePageExport();

  return (
    <div ref={contentRef} className="page-content animate-fade-in-up" data-title="Prompts & Schemas">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold" style={{ color: 'var(--text)' }}>Why Prompts Matter</h2>
        <ExportButton pageTitle="Prompts & Schemas" contentRef={contentRef} />
      </div>

      <InfoBox className="mb-8">
        Prompts are the control surface for LLM evaluations. They confine the AI&apos;s narrative to a structured evaluation layer &mdash; transforming open-ended language models into deterministic scoring engines. Template variables (<code>{'{{variable}}'}</code>) inject runtime context (audio files, transcripts, chat messages) while JSON schemas enforce output structure.
      </InfoBox>

      {/* Template Variable Registry */}
      <h2 className="text-2xl font-bold mb-2" style={{ color: 'var(--text)' }}>Template Variable Registry</h2>
      <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
        All 15 template variables defined in variableRegistry.ts, organized by type and availability.
      </p>

      <DataTable<TemplateVariable> columns={variableColumns} data={templateVariables} />

      {/* Variable Resolution Flow */}
      <h2 className="text-2xl font-bold mt-12 mb-4" style={{ color: 'var(--text)' }}>Variable Resolution Flow</h2>
      <MermaidDiagram chart={variableResolutionDiagram} />

      {/* Two Schema Systems */}
      <h2 className="text-2xl font-bold mt-12 mb-4" style={{ color: 'var(--text)' }}>Two Schema Systems</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <Card>
          <h3 className="text-[1.0625rem] font-bold tracking-tight mb-3" style={{ color: 'var(--text)' }}>
            JSON Schema (SchemaDefinition)
          </h3>
          <table className="w-full text-sm mb-4" style={{ borderCollapse: 'collapse' }}>
            <tbody>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="px-3 py-2 font-semibold whitespace-nowrap" style={{ color: 'var(--text)' }}>Used in</td>
                <td className="px-3 py-2" style={{ color: 'var(--text-secondary)' }}>Evaluation overlays, passed directly to Gemini/OpenAI SDK</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="px-3 py-2 font-semibold whitespace-nowrap" style={{ color: 'var(--text)' }}>Format</td>
                <td className="px-3 py-2" style={{ color: 'var(--text-secondary)' }}>Standard JSON Schema with type, properties, required</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="px-3 py-2 font-semibold whitespace-nowrap" style={{ color: 'var(--text)' }}>Purpose</td>
                <td className="px-3 py-2" style={{ color: 'var(--text-secondary)' }}>Enforces structured output from LLM (<code>response_json_schema</code> in Gemini, <code>response_format</code> in OpenAI)</td>
              </tr>
            </tbody>
          </table>
          <CodeBlock code={jsonSchemaExample} language="json" />
        </Card>

        <Card>
          <h3 className="text-[1.0625rem] font-bold tracking-tight mb-3" style={{ color: 'var(--text)' }}>
            Field-Based (EvaluatorOutputField[])
          </h3>
          <table className="w-full text-sm mb-4" style={{ borderCollapse: 'collapse' }}>
            <tbody>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="px-3 py-2 font-semibold whitespace-nowrap" style={{ color: 'var(--text)' }}>Used in</td>
                <td className="px-3 py-2" style={{ color: 'var(--text-secondary)' }}>Custom evaluators, built via <code>InlineSchemaBuilder</code> visual editor</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="px-3 py-2 font-semibold whitespace-nowrap" style={{ color: 'var(--text)' }}>Format</td>
                <td className="px-3 py-2" style={{ color: 'var(--text-secondary)' }}>Array of field definitions with key, type, label, description, thresholds, isMainMetric, displayMode</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="px-3 py-2 font-semibold whitespace-nowrap" style={{ color: 'var(--text)' }}>Conversion</td>
                <td className="px-3 py-2" style={{ color: 'var(--text-secondary)' }}><code>generateJsonSchema()</code> in schema_generator.py converts to JSON Schema at runtime</td>
              </tr>
            </tbody>
          </table>
          <CodeBlock code={fieldBasedExample} language="json" />
        </Card>
      </div>

      {/* Prompt Template Example */}
      <h2 className="text-2xl font-bold mt-12 mb-4" style={{ color: 'var(--text)' }}>Prompt Template Example</h2>
      <Card>
        <CodeBlock code={promptTemplateExample} language="bash" />
      </Card>
    </div>
  );
}
