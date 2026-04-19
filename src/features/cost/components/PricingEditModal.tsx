import { useMemo, useState } from 'react';
import { Modal, Button, Input } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { notificationService } from '@/services/notifications';
import type { PricingRow } from '../types';

interface PricingEditModalProps {
  mode: 'create' | 'patch';
  pricing?: PricingRow;
  onClose: () => void;
}

type FieldKey =
  | 'inputPer1MUsd'
  | 'outputPer1MUsd'
  | 'cachedReadPer1MUsd'
  | 'cacheWrite5MPer1MUsd'
  | 'cacheWrite1HPer1MUsd'
  | 'reasoningPer1MUsd';

const NUMERIC_FIELDS: { key: FieldKey; label: string }[] = [
  { key: 'inputPer1MUsd', label: 'Input $/1M' },
  { key: 'outputPer1MUsd', label: 'Output $/1M' },
  { key: 'cachedReadPer1MUsd', label: 'Cached read $/1M' },
  { key: 'cacheWrite5MPer1MUsd', label: 'Cache write 5m $/1M' },
  { key: 'cacheWrite1HPer1MUsd', label: 'Cache write 1h $/1M' },
  { key: 'reasoningPer1MUsd', label: 'Reasoning $/1M' },
];

export function PricingEditModal({ mode, pricing, onClose }: PricingEditModalProps) {
  const createPricing = useCostStore((s) => s.createPricing);
  const patchPricing = useCostStore((s) => s.patchPricing);

  const [submitting, setSubmitting] = useState(false);
  const [provider, setProvider] = useState(pricing?.provider ?? '');
  const [model, setModel] = useState(pricing?.model ?? '');
  const [notes, setNotes] = useState(pricing?.notes ?? '');
  const [rates, setRates] = useState<Record<FieldKey, string>>(() =>
    Object.fromEntries(
      NUMERIC_FIELDS.map((f) => [f.key, pricing ? String(pricing[f.key] ?? 0) : '0']),
    ) as Record<FieldKey, string>,
  );

  const title = useMemo(
    () => (mode === 'create' ? 'New pricing row' : `Edit pricing — ${pricing?.provider}/${pricing?.model}`),
    [mode, pricing],
  );

  const updateRate = (key: FieldKey, value: string) =>
    setRates((prev) => ({ ...prev, [key]: value }));

  const submit = async () => {
    const numericPayload: Record<FieldKey, number> = Object.fromEntries(
      NUMERIC_FIELDS.map((f) => [f.key, parseFloat(rates[f.key] || '0') || 0]),
    ) as Record<FieldKey, number>;

    if (Object.values(numericPayload).some((v) => v < 0)) {
      notificationService.error('Rates must be non-negative.');
      return;
    }
    if (mode === 'create' && (!provider.trim() || !model.trim())) {
      notificationService.error('Provider and model are required.');
      return;
    }

    setSubmitting(true);
    try {
      if (mode === 'create') {
        await createPricing({
          provider: provider.trim(),
          model: model.trim(),
          notes: notes.trim() || null,
          ...numericPayload,
        });
      } else if (pricing) {
        await patchPricing(pricing.id, {
          notes: notes.trim() || null,
          ...numericPayload,
        });
      }
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Save failed';
      notificationService.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen onClose={onClose} title={title}>
      <div className="space-y-3">
        {mode === 'create' && (
          <div className="grid grid-cols-2 gap-3">
            <LabeledField label="Provider">
              <Input value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="openai" />
            </LabeledField>
            <LabeledField label="Model">
              <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o-mini" />
            </LabeledField>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          {NUMERIC_FIELDS.map((f) => (
            <LabeledField key={f.key} label={f.label}>
              <Input
                type="number"
                inputMode="decimal"
                min="0"
                step="0.01"
                value={rates[f.key]}
                onChange={(e) => updateRate(f.key, e.target.value)}
              />
            </LabeledField>
          ))}
        </div>

        <LabeledField label="Notes (optional)">
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Contract-negotiated, etc." />
        </LabeledField>

        <p className="text-[11px] text-[var(--text-muted)]">
          {mode === 'create'
            ? 'Saving will close the currently-active row (if any) for this provider/model and insert a new one with effect date = now.'
            : 'Saving closes the current row and inserts a new one with effect date = now. Historical rows are preserved.'}
        </p>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={submit} isLoading={submitting}>
            {mode === 'create' ? 'Create' : 'Save'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function LabeledField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-[12px]">
      <span className="text-[var(--text-muted)]">{label}</span>
      {children}
    </label>
  );
}
