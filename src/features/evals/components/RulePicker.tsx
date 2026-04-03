import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { Badge, Button, EmptyState, Input } from '@/components/ui';
import type { RuleCatalogEntry } from '@/types';

interface RulePickerProps {
  rules: RuleCatalogEntry[];
  selectedRuleIds: string[];
  onChange: (nextRuleIds: string[]) => void;
  disabled?: boolean;
  title?: string;
  description?: string;
}

export function RulePicker({
  rules,
  selectedRuleIds,
  onChange,
  disabled = false,
  title = 'Rules',
  description = 'Link published app rules to this evaluator so shared contracts stay explicit.',
}: RulePickerProps) {
  const [search, setSearch] = useState('');

  const filteredRules = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return rules;
    }
    return rules.filter((rule) => {
      const haystack = [
        rule.ruleId,
        rule.section,
        rule.ruleText,
        rule.tags.join(' '),
      ].join(' ').toLowerCase();
      return haystack.includes(query);
    });
  }, [rules, search]);

  const toggleRule = (ruleId: string) => {
    if (selectedRuleIds.includes(ruleId)) {
      onChange(selectedRuleIds.filter((id) => id !== ruleId));
      return;
    }
    onChange([...selectedRuleIds, ruleId]);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {description}
          </p>
        </div>
        <Badge variant="info">{selectedRuleIds.length} selected</Badge>
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search rules by id, section, or text"
          className="pl-9"
        />
      </div>

      {filteredRules.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No matching rules"
          description="Try a different search term."
          compact
        />
      ) : (
        <div className="space-y-2">
          {filteredRules.map((rule) => {
            const isSelected = selectedRuleIds.includes(rule.ruleId);
            return (
              <button
                key={rule.ruleId}
                type="button"
                disabled={disabled}
                onClick={() => toggleRule(rule.ruleId)}
                className="w-full rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-primary)] px-4 py-3 text-left transition-colors hover:border-[var(--border-focus)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant={isSelected ? 'primary' : 'neutral'}>
                        {rule.ruleId}
                      </Badge>
                      {rule.section ? <Badge variant="neutral">{rule.section}</Badge> : null}
                    </div>
                    <p className="mt-2 text-sm text-[var(--text-primary)]">{rule.ruleText}</p>
                    {rule.tags.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {rule.tags.map((tag) => (
                          <Badge key={tag} variant="neutral">{tag}</Badge>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <Button variant={isSelected ? 'primary' : 'secondary'} size="sm" disabled={disabled}>
                    {isSelected ? 'Selected' : 'Select'}
                  </Button>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
