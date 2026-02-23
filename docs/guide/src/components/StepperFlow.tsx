interface Step {
  title: string;
  description: string;
}

interface StepperFlowProps {
  steps: Step[];
}

export default function StepperFlow({ steps }: StepperFlowProps) {
  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-0 my-6">
      {steps.map((step, i) => (
        <div key={i} className="flex items-center gap-0">
          <div className="flex flex-col items-center sm:items-start gap-2 min-w-[140px]">
            <div className="flex items-center gap-3">
              <div
                className="flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold shrink-0"
                style={{ background: 'var(--accent)', color: '#ffffff' }}
              >
                {i + 1}
              </div>
              <div>
                <div className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
                  {step.title}
                </div>
                <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {step.description}
                </div>
              </div>
            </div>
          </div>
          {i < steps.length - 1 && (
            <div
              className="hidden sm:block w-8 h-px mx-2 shrink-0"
              style={{ background: 'var(--border)' }}
            />
          )}
          {i < steps.length - 1 && (
            <div
              className="sm:hidden w-px h-6 ml-4"
              style={{ background: 'var(--border)' }}
            />
          )}
        </div>
      ))}
    </div>
  );
}
