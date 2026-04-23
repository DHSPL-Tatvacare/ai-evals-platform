// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, test, vi } from 'vitest';

// jsdom doesn't ship IntersectionObserver; ChatMessages uses it for the
// bottom-sentinel follow-scroll effect. A minimal no-op shim is enough.
class _IO {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}
class _RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('IntersectionObserver', _IO as unknown as typeof IntersectionObserver);
vi.stubGlobal('ResizeObserver', _RO as unknown as typeof ResizeObserver);

import { ChatMessages } from './ChatMessages';
import { useChatWidgetStore } from './useChatWidget';
import {
  applyArtifactToParts,
  isContractStubNotePart,
  partsFromStoredMessage,
} from './chatWidgetHelpers';
import type { Artifact, ContractStubNotePart, MessagePart } from './types';

const stubArtifact: Artifact = {
  pack_id: 'contract_stub',
  contract_id: 'contract_stub.note.v1',
  payload: {
    title: 'Stub warning',
    body: 'watch the transcript',
    variant: 'warning',
    source_text: 'watch the transcript',
  },
  extras: {
    rendered_variant: 'warning',
    truncated: false,
  },
};

describe('contract_stub frontend artifact lane', () => {
  beforeEach(() => {
    useChatWidgetStore.setState({
      dbSessionId: null,
      sessions: [],
      streamingParts: [],
    });
  });

  test('applyArtifactToParts turns a contract_stub.note.v1 artifact into a stub-note part', () => {
    const parts = applyArtifactToParts([], stubArtifact);

    expect(parts).toHaveLength(1);
    const [part] = parts;
    expect(isContractStubNotePart(part)).toBe(true);

    const stubPart = part as ContractStubNotePart;
    expect(stubPart).toEqual({
      type: 'contract-stub-note',
      title: 'Stub warning',
      body: 'watch the transcript',
      variant: 'warning',
      sourceText: 'watch the transcript',
      renderedVariant: 'warning',
      truncated: false,
    });
  });

  test('applyArtifactToParts drops malformed contract_stub payloads', () => {
    const bogus: Artifact = {
      pack_id: 'contract_stub',
      contract_id: 'contract_stub.note.v1',
      payload: { body: 'no title or variant' },
    };
    expect(applyArtifactToParts([], bogus)).toEqual([]);
  });

  test('partsFromStoredMessage rebuilds a stub-note part from persisted metadata', () => {
    const parts = partsFromStoredMessage('Here is your note.', {
      artifacts: [stubArtifact],
    });

    expect(parts).toEqual([
      { type: 'text', content: 'Here is your note.' },
      {
        type: 'contract-stub-note',
        title: 'Stub warning',
        body: 'watch the transcript',
        variant: 'warning',
        sourceText: 'watch the transcript',
        renderedVariant: 'warning',
        truncated: false,
      },
    ] satisfies MessagePart[]);
  });

  test('ChatMessages renders ContractStubNoteCard for the restored stub part', () => {
    render(
      <MemoryRouter>
        <ChatMessages
          messages={[
            {
              id: 'assistant-stub-1',
              role: 'assistant',
              status: 'complete',
              parts: [
                { type: 'text', content: 'Here is your note.' },
                {
                  type: 'contract-stub-note',
                  title: 'Stub success',
                  body: 'all good',
                  variant: 'success',
                  sourceText: 'all good',
                  renderedVariant: 'success',
                  truncated: false,
                },
              ],
            },
          ]}
          status="idle"
          appId="voice-rx"
          onRetry={() => {}}
        />
      </MemoryRouter>,
    );

    const card = screen.getByTestId('contract-stub-note-card');
    expect(card).toBeInTheDocument();
    expect(card).toHaveAttribute('data-pack-id', 'contract_stub');
    expect(card).toHaveAttribute('data-contract-id', 'contract_stub.note.v1');
    expect(card).toHaveTextContent('Stub success');
    expect(card).toHaveTextContent('all good');
  });

  test('ChatMessages renders the stub card rehydrated through partsFromStoredMessage (replay parity)', () => {
    const rehydrated = partsFromStoredMessage('Here is your note.', {
      artifacts: [stubArtifact],
    });

    render(
      <MemoryRouter>
        <ChatMessages
          messages={[
            {
              id: 'assistant-stub-replay',
              role: 'assistant',
              status: 'complete',
              parts: rehydrated,
            },
          ]}
          status="idle"
          appId="voice-rx"
          onRetry={() => {}}
        />
      </MemoryRouter>,
    );

    const card = screen.getByTestId('contract-stub-note-card');
    expect(card).toHaveAttribute('data-pack-id', 'contract_stub');
    expect(card).toHaveAttribute('data-contract-id', 'contract_stub.note.v1');
    expect(card).toHaveTextContent('Stub warning');
    expect(card).toHaveTextContent('watch the transcript');
  });
});
