import { useState, useRef, useEffect, type RefObject } from 'react';
import { Printer, Download, ChevronDown } from 'lucide-react';

interface ExportButtonProps {
  pageTitle: string;
  contentRef: RefObject<HTMLDivElement | null>;
}

export default function ExportButton({ pageTitle, contentRef }: ExportButtonProps) {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handlePrint = () => {
    setOpen(false);
    document.title = `${pageTitle} — AI Evals Platform Guide`;
    window.print();
    document.title = 'AI Evals Platform — Interactive Guide';
  };

  const handleDownloadHtml = () => {
    setOpen(false);
    if (!contentRef.current) return;

    const styles = Array.from(document.styleSheets)
      .map((sheet) => {
        try {
          return Array.from(sheet.cssRules)
            .map((rule) => rule.cssText)
            .join('\n');
        } catch {
          return '';
        }
      })
      .join('\n');

    const html = `<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${pageTitle} — AI Evals Platform Guide</title>
  <style>${styles}</style>
</head>
<body style="padding: 2rem; max-width: 1200px; margin: 0 auto;">
  ${contentRef.current.innerHTML}
</body>
</html>`;

    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${pageTitle.replace(/\s+/g, '-').toLowerCase()}.html`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div ref={dropdownRef} className="export-btn relative inline-block">
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors"
        style={{
          background: 'var(--bg-secondary)',
          color: 'var(--text-secondary)',
          border: '1px solid var(--border)',
        }}
      >
        <Printer size={16} />
        Export
        <ChevronDown size={14} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 rounded-lg py-1 z-10 min-w-[160px]"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <button
            onClick={handlePrint}
            className="w-full flex items-center gap-2 px-4 py-2 text-sm text-left cursor-pointer transition-colors"
            style={{ background: 'transparent', border: 'none', color: 'var(--text)', fontFamily: 'inherit' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <Printer size={14} />
            Print PDF
          </button>
          <button
            onClick={handleDownloadHtml}
            className="w-full flex items-center gap-2 px-4 py-2 text-sm text-left cursor-pointer transition-colors"
            style={{ background: 'transparent', border: 'none', color: 'var(--text)', fontFamily: 'inherit' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <Download size={14} />
            Download HTML
          </button>
        </div>
      )}
    </div>
  );
}
