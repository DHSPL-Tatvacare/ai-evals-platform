import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { Canvas } from '@/features/orchestration/components/Canvas';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';

beforeAll(() => {
  // React Flow uses ResizeObserver and DOMRect APIs that jsdom does not implement.
  if (!('ResizeObserver' in globalThis)) {
    class MockResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    (globalThis as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver =
      MockResizeObserver;
  }
});

describe('Canvas', () => {
  it('renders without crashing', () => {
    const { container } = render(<Canvas />);
    expect(container.querySelector('.react-flow')).toBeTruthy();
  });
});

describe('Canvas drag/drop allowlist (Section 7)', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
  });

  function dropPayload(nodeType: string) {
    const data = JSON.stringify({ nodeType, label: nodeType });
    return {
      dataTransfer: {
        getData: (key: string) =>
          key === 'application/orchestration-node' ? data : '',
        dropEffect: 'move',
      },
      clientX: 100,
      clientY: 100,
    };
  }

  it('rejects a drop of a node_type not in the palette catalog', () => {
    const store = useWorkflowBuilderStore.getState();
    store.setViewMode('edit');
    store.setPaletteCatalog([
      {
        nodeType: 'sink.complete',
        workflowType: 'crm',
        displayLabel: 'Sink',
        displayCategory: 'termination',
        description: '',
        authoringStatus: 'active',
        configSchema: {},
        editorHints: {},
        requiredPayloadFields: [],
        emittedPayloadFields: [],
        outputEdges: [],
        graphRules: {
          requiresOutgoingEdges: false,
          allowsMultipleOutgoingPerOutput: false,
          requiredOutputIds: [],
        },
        runtimeContract: { executionKind: 'termination' },
        category: 'sink',
        label: 'Sink',
      },
    ]);
    const { container } = render(<Canvas />);
    const dropZone = container.firstElementChild as HTMLElement;
    fireEvent.drop(dropZone, dropPayload('not.a.real.node'));
    expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(0);
  });

  it('allows a drop of a node_type registered in the palette catalog', () => {
    const store = useWorkflowBuilderStore.getState();
    store.setViewMode('edit');
    store.setPaletteCatalog([
      {
        nodeType: 'sink.complete',
        workflowType: 'crm',
        displayLabel: 'Sink',
        displayCategory: 'termination',
        description: '',
        authoringStatus: 'active',
        configSchema: {},
        editorHints: {},
        requiredPayloadFields: [],
        emittedPayloadFields: [],
        outputEdges: [],
        graphRules: {
          requiresOutgoingEdges: false,
          allowsMultipleOutgoingPerOutput: false,
          requiredOutputIds: [],
        },
        runtimeContract: { executionKind: 'termination' },
        category: 'sink',
        label: 'Sink',
      },
    ]);
    const { container } = render(<Canvas />);
    const dropZone = container.firstElementChild as HTMLElement;
    fireEvent.drop(dropZone, dropPayload('sink.complete'));
    const nodes = useWorkflowBuilderStore.getState().nodes;
    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe('sink.complete');
  });

  it('rejects a drop while in view mode regardless of allowlist', () => {
    const store = useWorkflowBuilderStore.getState();
    store.setViewMode('view');
    store.setPaletteCatalog([
      {
        nodeType: 'sink.complete',
        workflowType: 'crm',
        displayLabel: 'Sink',
        displayCategory: 'termination',
        description: '',
        authoringStatus: 'active',
        configSchema: {},
        editorHints: {},
        requiredPayloadFields: [],
        emittedPayloadFields: [],
        outputEdges: [],
        graphRules: {
          requiresOutgoingEdges: false,
          allowsMultipleOutgoingPerOutput: false,
          requiredOutputIds: [],
        },
        runtimeContract: { executionKind: 'termination' },
        category: 'sink',
        label: 'Sink',
      },
    ]);
    const { container } = render(<Canvas />);
    const dropZone = container.firstElementChild as HTMLElement;
    fireEvent.drop(dropZone, dropPayload('sink.complete'));
    expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(0);
  });
});
