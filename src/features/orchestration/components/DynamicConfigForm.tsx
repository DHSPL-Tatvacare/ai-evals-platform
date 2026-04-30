import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import { cn } from '@/utils';

interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  enum?: string[];
  default?: unknown;
  items?: JsonSchemaProperty;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
}

export interface JsonSchema extends JsonSchemaProperty {
  properties: Record<string, JsonSchemaProperty>;
}

interface Props {
  schema: JsonSchema;
  value: Record<string, unknown>;
  onChange(next: Record<string, unknown>): void;
}

export function DynamicConfigForm({ schema, value, onChange }: Props) {
  if (!schema?.properties) return null;
  const required = new Set(schema.required ?? []);

  const handleField = (key: string, fieldValue: unknown) => {
    onChange({ ...value, [key]: fieldValue });
  };

  return (
    <div className="space-y-4">
      {Object.entries(schema.properties).map(([key, prop]) => {
        const fieldValue = value[key] ?? prop.default ?? '';
        const label = prop.title ?? key;
        const isRequired = required.has(key);
        const fieldId = `field-${key}`;
        return (
          <div key={key} className="flex flex-col gap-1">
            <label
              htmlFor={fieldId}
              className={cn('text-sm font-medium text-[var(--text-primary)]')}
            >
              {label}
              {isRequired && <span className="ml-1 text-[var(--color-error)]">*</span>}
            </label>
            {prop.description && (
              <p className="text-xs text-[var(--text-secondary)]">{prop.description}</p>
            )}
            <FieldRenderer
              fieldId={fieldId}
              fieldKey={key}
              prop={prop}
              fieldValue={fieldValue}
              label={label}
              onChange={handleField}
            />
          </div>
        );
      })}
    </div>
  );
}

interface FieldRendererProps {
  fieldId: string;
  fieldKey: string;
  prop: JsonSchemaProperty;
  fieldValue: unknown;
  label: string;
  onChange: (key: string, value: unknown) => void;
}

function FieldRenderer({
  fieldId,
  fieldKey,
  prop,
  fieldValue,
  label,
  onChange,
}: FieldRendererProps) {
  if (prop.enum) {
    return (
      <Select
        value={String(fieldValue ?? '')}
        onChange={(next) => onChange(fieldKey, next)}
        placeholder={`Select ${label}`}
        options={prop.enum.map((opt) => ({ value: opt, label: opt }))}
      />
    );
  }
  if (prop.type === 'boolean') {
    return (
      <div>
        <Switch
          id={fieldId}
          checked={Boolean(fieldValue)}
          onCheckedChange={(checked) => onChange(fieldKey, checked)}
        />
      </div>
    );
  }
  if (prop.type === 'number' || prop.type === 'integer') {
    return (
      <Input
        id={fieldId}
        type="number"
        value={fieldValue === null || fieldValue === undefined ? '' : String(fieldValue)}
        onChange={(e) =>
          onChange(fieldKey, e.target.value === '' ? null : Number(e.target.value))
        }
      />
    );
  }
  if (prop.type === 'object' && prop.properties) {
    return (
      <div className="rounded-[var(--radius-default)] border border-[var(--border-default)] p-3">
        <DynamicConfigForm
          schema={prop as JsonSchema}
          value={(fieldValue as Record<string, unknown>) ?? {}}
          onChange={(next) => onChange(fieldKey, next)}
        />
      </div>
    );
  }
  const isLong =
    fieldKey.includes('predicate') ||
    fieldKey.includes('payload') ||
    prop.type === 'object';
  if (isLong) {
    const text =
      typeof fieldValue === 'string'
        ? fieldValue
        : JSON.stringify(fieldValue, null, 2);
    return (
      <textarea
        id={fieldId}
        className={cn(
          'min-h-24 w-full rounded-[var(--radius-default)] border border-[var(--border-default)]',
          'bg-[var(--bg-primary)] px-3 py-2 font-mono text-xs text-[var(--text-primary)]',
          'focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50',
        )}
        value={text}
        onChange={(e) => {
          try {
            onChange(fieldKey, JSON.parse(e.target.value));
          } catch {
            onChange(fieldKey, e.target.value);
          }
        }}
      />
    );
  }
  return (
    <Input
      id={fieldId}
      type="text"
      value={String(fieldValue ?? '')}
      onChange={(e) => onChange(fieldKey, e.target.value)}
    />
  );
}
