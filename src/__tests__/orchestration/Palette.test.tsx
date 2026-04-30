import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Palette } from '@/features/orchestration/components/Palette';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';

describe('Palette', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    useWorkflowBuilderStore.getState().setPaletteCatalog([
      {
        nodeType: 'filter.eligibility',
        workflowType: '*',
        category: 'filter',
        label: 'Eligibility',
        description: 'Predicate filter',
        outputEdges: ['passed', 'skipped'],
        configSchema: { type: 'object', properties: {} },
      },
      {
        nodeType: 'filter.consent_gate',
        workflowType: '*',
        category: 'filter',
        label: 'Consent Gate',
        description: 'Drops opted-out recipients',
        outputEdges: ['allowed', 'blocked'],
        configSchema: { type: 'object', properties: {} },
      },
    ]);
  });

  it('hides consent gate from the authoring palette', () => {
    render(<Palette />);

    expect(screen.getByText('Eligibility')).toBeInTheDocument();
    expect(screen.queryByText('Consent Gate')).not.toBeInTheDocument();
  });
});
