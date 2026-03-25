# Component Specifications

Quick reference for each shared component — props, behavior, and usage.

## Layout.tsx

Top-level wrapper. Renders header, nav tabs, page content, footer.

```tsx
// No props — reads hash from URL, manages active tab
// Header: logo SVG + "AI Evals Platform" + "Interactive Guide" badge + theme toggle
// Nav: 7 horizontal pills, scrollable on mobile, active state with accent bg
// Content: renders active page component
// Footer: copyright line
```

Responsive: tabs become horizontally scrollable below 768px. Sticky header with glass blur.

## CodeBlock.tsx

```tsx
interface CodeBlockProps {
  code: string;
  language: 'typescript' | 'python' | 'json' | 'bash';
}
```

- Dark background (`--code-bg`), JetBrains Mono font
- "Copy" button top-right, shows "Copied!" for 2s on success
- Syntax highlighting via Prism.js (loaded as ESM)

## MermaidDiagram.tsx

```tsx
interface MermaidDiagramProps {
  chart: string;  // Raw mermaid markup
}
```

- Renders mermaid chart on mount and when theme changes
- Uses `mermaid.render()` with theme-aware config (dark/light)
- Stores original markup, re-renders cleanly on theme toggle
- Centered with max-width: 100%

## DataTable.tsx

```tsx
interface Column<T> {
  key: keyof T;
  header: string;
  render?: (value: T[keyof T], row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
}
```

- Styled table with hover rows, sticky header, horizontal scroll wrapper
- `render` function allows custom cell content (badges, code, etc.)

## Card.tsx

```tsx
interface CardProps {
  children: ReactNode;
  className?: string;
  hoverable?: boolean;  // default true — adds translateY(-2px) on hover
}
```

Surface card with border, rounded corners, shadow on hover.

## Accordion.tsx

```tsx
interface AccordionProps {
  title: string;
  icon?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}
```

- Chevron icon rotates on open/close
- Smooth max-height transition
- Triggers mermaid re-render when opened (if contains diagrams)

## StepperFlow.tsx

```tsx
interface Step {
  title: string;
  description: string;
}

interface StepperFlowProps {
  steps: Step[];
}
```

Horizontal numbered steps with connecting lines. Stacks vertically on mobile.

## FilterPills.tsx

```tsx
interface FilterPillsProps {
  options: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}
```

Horizontal pill group. Active pill gets accent bg + white text.

## ExportButton.tsx

```tsx
interface ExportButtonProps {
  pageTitle: string;
  contentRef: RefObject<HTMLDivElement>;
}
```

Two actions:
1. **Print PDF**: Calls `window.print()` — relies on `@media print` CSS to hide chrome and format content
2. **Download HTML**: Clones `contentRef` inner HTML, wraps with inline `<style>` block containing all design tokens + component styles, triggers download as `{pageTitle}.html`

Renders as a small icon button (Printer icon from lucide-react) with dropdown for the two options.

## BrainMap.tsx (D3 Component)

```tsx
// No props — reads data from data/brainMap.ts
```

Self-contained D3 force-directed graph:
- SVG with zoom/pan behavior
- 3 node types: feature (large purple), file (medium blue/green), method (small light)
- Links: feature→file (thick), file→method (thin)
- Feature pills for subgraph highlighting
- Layer pills (All/Frontend/Backend/Shared) for filtering
- Search input with debounced matching
- Click node → info panel shows details
- Responsive resize handler

Uses `useRef` for SVG element, `useEffect` for D3 initialization. Does not re-render on React state changes — D3 manages its own DOM within the SVG.

## Badge.tsx (utility)

```tsx
interface BadgeProps {
  color: 'blue' | 'green' | 'purple' | 'amber' | 'red';
  children: ReactNode;
}
```

Small pill badge with color-coded background. Dark mode overrides via `[data-theme="dark"]`.

## Print CSS Strategy

```css
@media print {
  /* Hide navigation chrome */
  .header, .nav-tabs, .theme-toggle, .export-btn, .footer { display: none; }

  /* Show only active page, full width */
  .page-content { display: block !important; }

  /* Force light theme for readability */
  :root { --bg: #fff; --text: #000; --surface: #fff; }

  /* Prevent card/table splitting across pages */
  .card, .table-wrapper, .mermaid { break-inside: avoid; }

  /* Add page title at top */
  .page-content::before { content: attr(data-title); font-size: 24px; font-weight: 700; }
}
```
