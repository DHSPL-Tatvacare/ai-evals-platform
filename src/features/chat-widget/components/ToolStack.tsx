import { ToolItem } from './ToolItem';
import type { ToolCallPart } from '../types';

interface ToolStackProps {
  tools: ToolCallPart[];
  compact?: boolean;
}

export function ToolStack({ tools, compact = false }: ToolStackProps) {
  if (tools.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2">
      {tools.map((tool) => (
        <ToolItem key={tool.toolCallId} part={tool} compact={compact} />
      ))}
    </div>
  );
}
