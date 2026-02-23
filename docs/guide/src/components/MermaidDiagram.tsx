import { useEffect, useRef } from 'react';
import mermaid from 'mermaid';
import { useTheme } from '@/hooks/useTheme';

let renderCounter = 0;

interface MermaidDiagramProps {
  chart: string;
}

export default function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();

  useEffect(() => {
    let cancelled = false;

    const render = async () => {
      if (!containerRef.current) return;

      mermaid.initialize({
        startOnLoad: false,
        theme: theme === 'dark' ? 'dark' : 'default',
        fontFamily: 'Inter, sans-serif',
        securityLevel: 'loose',
      });

      try {
        // Use a unique ID per render call to avoid ID collisions
        // (React StrictMode double-fires effects, reusing IDs causes empty SVGs)
        const id = `mmd-${Date.now()}-${++renderCounter}`;
        const { svg } = await mermaid.render(id, chart);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch {
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = `<pre style="color: var(--error); padding: 1rem;">${chart}</pre>`;
        }
      }
    };

    render();

    return () => { cancelled = true; };
  }, [chart, theme]);

  return (
    <div
      ref={containerRef}
      className="mermaid my-6 flex justify-center overflow-x-auto rounded-xl"
      style={{
        maxWidth: '100%',
        minHeight: '120px',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        padding: '1.5rem',
      }}
    />
  );
}
