import { Mic, MessageSquare, Shield } from 'lucide-react';
import { Card, MermaidDiagram, Badge, ExportButton } from '@/components';
import { usePageExport } from '@/hooks/usePageExport';

const archDiagram = `graph TB
    Browser["Browser (React + Vite)"] -->|"/api/*"| Vite["Vite Dev Proxy :5173"]
    Vite -->|"Proxy"| FastAPI["FastAPI :8721"]
    FastAPI -->|"async SQLAlchemy"| PG["PostgreSQL :5432"]
    FastAPI -->|"Starts on boot"| Worker["Job Worker Loop"]
    Worker -->|"Polls every 5s"| PG
    Worker -->|"evaluate-voice-rx"| VRX["voice_rx_runner"]
    Worker -->|"evaluate-batch"| Batch["batch_runner"]
    Worker -->|"evaluate-adversarial"| Adv["adversarial_runner"]
    Worker -->|"evaluate-custom"| Custom["custom_evaluator_runner"]
    VRX -->|"API calls"| LLM["LLM Provider (Gemini / OpenAI)"]
    Batch --> LLM
    Adv --> LLM
    Custom --> LLM

    style Browser fill:#6366f1,color:#fff
    style FastAPI fill:#10b981,color:#fff
    style PG fill:#f59e0b,color:#fff
    style Worker fill:#8b5cf6,color:#fff
    style LLM fill:#ec4899,color:#fff`;

const workspaces = [
  {
    icon: Mic,
    iconBg: '#dbeafe',
    iconColor: '#2563eb',
    title: 'Voice RX',
    description: 'Evaluate medical voice transcription quality. Upload audio + transcripts, run AI-judged transcription and per-segment critique using a two-call LLM pipeline.',
    badges: [
      { color: 'blue' as const, label: 'Transcription' },
      { color: 'purple' as const, label: 'Evaluation' },
    ],
  },
  {
    icon: MessageSquare,
    iconBg: '#d1fae5',
    iconColor: '#059669',
    title: 'Kaira Bot',
    description: 'Test the Kaira health assistant chatbot. Run live chat sessions via SSE streaming, then evaluate conversations using custom evaluators with structured output schemas.',
    badges: [
      { color: 'green' as const, label: 'Chat' },
      { color: 'purple' as const, label: 'Evaluation' },
    ],
  },
  {
    icon: Shield,
    iconBg: '#ede9fe',
    iconColor: '#7c3aed',
    title: 'Kaira Evals',
    description: 'Batch and adversarial testing at scale. Upload CSV chat threads for batch evaluation, or run automated adversarial stress tests against the live Kaira API.',
    badges: [
      { color: 'amber' as const, label: 'Batch' },
      { color: 'purple' as const, label: 'Adversarial' },
    ],
  },
];

const techStack = [
  { title: 'Frontend', items: ['React 19', 'Vite', 'TypeScript', 'Zustand', 'Tailwind CSS v4'] },
  { title: 'Backend', items: ['FastAPI', 'async SQLAlchemy', 'asyncpg', 'Python'] },
  { title: 'Database', items: ['PostgreSQL 16', 'JSONB columns', 'Docker Compose'] },
];

export default function Overview() {
  const { contentRef } = usePageExport();

  return (
    <div ref={contentRef} className="page-content animate-fade-in-up" data-title="Overview">
      <div className="flex items-center justify-between mb-6">
        <div />
        <ExportButton pageTitle="Overview" contentRef={contentRef} />
      </div>

      {/* Hero */}
      <div
        className="rounded-2xl text-center py-8 px-6 mb-8 relative overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6, #a78bfa)', color: '#ffffff' }}
      >
        <div
          className="absolute -top-1/2 -left-1/2 w-[150%] h-[150%] pointer-events-none"
          style={{ background: 'radial-gradient(circle at 30% 40%, rgba(255,255,255,0.05) 0%, transparent 60%)' }}
        />
        <h1 className="text-2xl font-extrabold tracking-tight mb-2 relative">AI Evals Platform</h1>
        <p className="text-sm opacity-90 max-w-[480px] mx-auto relative">
          An interactive guide to understanding how the platform evaluates AI systems across Voice RX, Kaira Bot, and Kaira Evals workspaces.
        </p>
      </div>

      {/* Three Workspaces */}
      <h2 className="text-2xl font-bold mt-2 mb-5 flex items-center gap-2" style={{ color: 'var(--text)' }}>
        Three Workspaces
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        {workspaces.map((ws) => (
          <Card key={ws.title}>
            <div className="flex flex-col gap-3">
              <div
                className="w-12 h-12 rounded-full inline-flex items-center justify-center mb-1"
                style={{ background: ws.iconBg }}
              >
                <ws.icon size={28} color={ws.iconColor} />
              </div>
              <h3 className="text-[1.0625rem] font-bold tracking-tight" style={{ color: 'var(--text)' }}>
                {ws.title}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {ws.description}
              </p>
              <div className="flex flex-wrap gap-2 mt-1">
                {ws.badges.map((b) => (
                  <Badge key={b.label} color={b.color}>{b.label}</Badge>
                ))}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Technology Stack */}
      <h2 className="text-2xl font-bold mb-5 flex items-center gap-2" style={{ color: 'var(--text)' }}>
        Technology Stack
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        {techStack.map((stack) => (
          <Card key={stack.title}>
            <div className="flex flex-col gap-3">
              <h3 className="text-[1.0625rem] font-bold tracking-tight" style={{ color: 'var(--text)' }}>
                {stack.title}
              </h3>
              <ul className="list-disc list-inside text-sm" style={{ color: 'var(--text-secondary)' }}>
                {stack.items.map((item) => (
                  <li key={item} className="py-0.5">{item}</li>
                ))}
              </ul>
            </div>
          </Card>
        ))}
      </div>

      {/* Architecture Overview */}
      <h2 className="text-2xl font-bold mb-5 flex items-center gap-2" style={{ color: 'var(--text)' }}>
        Architecture Overview
      </h2>
      <MermaidDiagram chart={archDiagram} />
    </div>
  );
}
