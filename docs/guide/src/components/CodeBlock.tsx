import { useEffect, useRef, useState } from 'react';
import Prism from 'prismjs';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-json';
import 'prismjs/components/prism-bash';
import 'prismjs/themes/prism-tomorrow.min.css';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  code: string;
  language: 'typescript' | 'python' | 'json' | 'bash';
}

export default function CodeBlock({ code, language }: CodeBlockProps) {
  const codeRef = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (codeRef.current) {
      Prism.highlightElement(codeRef.current);
    }
  }, [code, language]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-lg my-4 overflow-hidden" style={{ background: 'var(--code-bg)' }}>
      <div className="overflow-x-auto relative">
        <button
          onClick={handleCopy}
          className="export-btn sticky top-3 z-10 flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors"
          style={{
            background: 'rgba(255, 255, 255, 0.1)',
            color: '#94a3b8',
            border: 'none',
            float: 'right',
            margin: '12px 12px -32px 0',
          }}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied!' : 'Copy'}
        </button>
        <pre className="p-4 text-sm leading-relaxed" style={{ margin: 0 }}>
          <code ref={codeRef} className={`language-${language}`} style={{ fontFamily: 'var(--font-mono)' }}>
            {code}
          </code>
        </pre>
      </div>
    </div>
  );
}
