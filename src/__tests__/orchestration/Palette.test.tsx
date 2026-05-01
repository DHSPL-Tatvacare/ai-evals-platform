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
        displayLabel: 'Eligibility',
        displayCategory: 'qualification',
        description: 'Predicate filter',
        authoringStatus: 'active',
        configSchema: { type: 'object', properties: {} },
        editorHints: {},
        requiredPayloadFields: [],
        emittedPayloadFields: [],
        outputEdges: [
          { id: 'passed', label: 'Passed', cardinality: 'one', dynamic: false },
          { id: 'skipped', label: 'Skipped', cardinality: 'one', dynamic: false },
        ],
        graphRules: {},
        runtimeContract: { executionKind: 'qualification' },
        category: 'filter',
        label: 'Eligibility',
      },
      {
        nodeType: 'filter.consent_gate',
        workflowType: '*',
        displayLabel: 'Consent Gate',
        displayCategory: 'qualification',
        description: 'Drops opted-out recipients',
        authoringStatus: 'hidden',
        configSchema: { type: 'object', properties: {} },
        editorHints: {},
        requiredPayloadFields: [],
        emittedPayloadFields: [],
        outputEdges: [
          { id: 'allowed', label: 'Allowed', cardinality: 'one', dynamic: false },
          { id: 'blocked', label: 'Blocked', cardinality: 'one', dynamic: false },
        ],
        graphRules: {},
        runtimeContract: { executionKind: 'qualification' },
        category: 'filter',
        label: 'Consent Gate',
      },
    ]);
  });

  it('hides consent gate from the authoring palette', () => {
    render(<Palette />);

    expect(screen.getByText('Eligibility')).toBeInTheDocument();
    expect(screen.queryByText('Consent Gate')).not.toBeInTheDocument();
  });
});
