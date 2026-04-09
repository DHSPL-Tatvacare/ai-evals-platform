import type {
  AppId,
  ReviewDecision,
  ReviewableItem,
  ReviewableAttribute,
  EvalReviewDetail,
  RunReviewContext,
} from '@/types';

export interface InlineEditState {
  itemKey: string;
  itemType: string;
  attributeKey: string;
  decision: ReviewDecision | '';
  originalValue: string | null;
  reviewedValue: string | null;
  reasonCode: string | null;
  note: string | null;
}

export interface InlineReviewContextValue {
  appId: AppId;
  isEditing: boolean;
  hasDirtyChanges: boolean;
  loading: boolean;
  saving: boolean;
  context: RunReviewContext | null;
  selectedReview: EvalReviewDetail | null;
  edits: Record<string, InlineEditState>;
  dirtyCount: number;
  dirtySummary: string;
  startDraft: () => Promise<void>;
  getEdit: (itemKey: string, attributeKey: string) => InlineEditState | undefined;
  updateAttribute: (
    item: ReviewableItem,
    attribute: ReviewableAttribute,
    patch: Partial<InlineEditState>,
  ) => void;
  acceptAttribute: (item: ReviewableItem, attribute: ReviewableAttribute) => void;
  correctAttribute: (
    item: ReviewableItem,
    attribute: ReviewableAttribute,
    reviewedValue: string,
  ) => void;
  setAttributeNote: (
    item: ReviewableItem,
    attribute: ReviewableAttribute,
    note: string | null,
  ) => void;
  saveDraft: () => Promise<void>;
  finalize: () => Promise<void>;
  discardDraft: () => Promise<void>;
}
