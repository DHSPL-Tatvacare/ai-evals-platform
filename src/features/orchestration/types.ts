export type WorkflowType = 'crm' | 'clinical';

// Phase 11 — neutral, functional palette categories.
export type DisplayCategory =
  | 'ingress'
  | 'qualification'
  | 'routing'
  | 'suspension'
  | 'synchronization'
  | 'dispatch'
  | 'mutation'
  | 'termination';

export type AuthoringStatus = 'active' | 'hidden' | 'experimental' | 'deprecated';

export type ExecutionKind =
  | 'entry_sql'
  | 'entry_event'
  | 'qualification'
  | 'routing'
  | 'suspension'
  | 'synchronization'
  | 'dispatch'
  | 'mutation'
  | 'termination';

// Legacy bucket — preserved on `NodeTypeDescriptor.category` so older builder
// code (palette grouping, badge colors) keeps rendering until it migrates to
// `displayCategory`.
export type NodeCategory = 'source' | 'filter' | 'logic' | 'action' | 'escalation' | 'sink';

export type RunStatus = 'pending' | 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled';
export type TriggerKind = 'cron' | 'event' | 'manual';
export type WorkflowVersionStatus = 'draft' | 'published' | 'archived';
export type OverrideAction = 'pause' | 'resume' | 'jump_to_node' | 'remove' | 'complete';

export interface NodeOutputEdge {
  id: string;
  label: string;
  cardinality: 'one' | 'many';
  dynamic: boolean;
}

export interface NodeGraphRules {
  requiresIncomingEdges?: boolean;
  requiresOutgoingEdges?: boolean;
  requiredOutputIds?: string[];
  allowsMultipleOutgoingPerOutput?: boolean;
  terminal?: boolean;
}

export interface NodeRuntimeContract {
  executionKind: ExecutionKind;
  supportsAttemptPolicy?: boolean;
  supportsSuspendResume?: boolean;
}

export interface NodeEditorHints {
  preferredEditor?: string;
  hiddenFields?: string[];
  readOnlyFields?: string[];
  fieldOrder?: string[];
  emptyStateMessage?: string;
}

export interface NodeTypeDescriptor {
  nodeType: string;
  workflowType: string;

  // Phase 11 canonical fields.
  displayLabel: string;
  displayCategory: DisplayCategory;
  description: string;
  authoringStatus: AuthoringStatus;

  configSchema: Record<string, unknown>;
  editorHints: NodeEditorHints;

  requiredPayloadFields: string[];
  emittedPayloadFields: string[];

  outputEdges: NodeOutputEdge[];

  graphRules: NodeGraphRules;
  runtimeContract: NodeRuntimeContract;

  // Back-compat fields — populated by the backend so legacy builder code keeps working.
  category: NodeCategory;
  label: string;
}

export interface WorkflowDefinitionNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: { label?: string; nodeType?: string };
  config: Record<string, unknown>;
}

export interface WorkflowDefinitionEdge {
  id: string;
  source: string;
  target: string;
  /**
   * Phase 11 routing key — the stable machine id of the source node's output edge.
   * Always populated on canonical (post-normalization) definitions.
   */
  outputId?: string;
  /**
   * Legacy field — superseded by `outputId`. Still accepted on read for back-compat
   * with pre-Phase-11 saved definitions; the backend's normalization layer rewrites
   * it to `outputId` at publish time.
   */
  label?: string;
}

export interface WorkflowDefinition {
  nodes: WorkflowDefinitionNode[];
  edges: WorkflowDefinitionEdge[];
  canvas?: { viewport?: { x: number; y: number; zoom: number } };
}

export interface Workflow {
  id: string;
  tenantId: string;
  appId: string;
  workflowType: WorkflowType;
  slug: string;
  name: string;
  description: string | null;
  currentPublishedVersionId: string | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowVersion {
  id: string;
  workflowId: string;
  version: number;
  definition: WorkflowDefinition;
  status: WorkflowVersionStatus;
  publishedBy: string | null;
  publishedAt: string | null;
  createdAt: string;
}

export interface WorkflowTrigger {
  id: string;
  workflowId: string;
  kind: TriggerKind;
  cronExpression: string | null;
  eventName: string | null;
  scheduledJobId: string | null;
  params: Record<string, unknown>;
  active: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowRun {
  id: string;
  workflowId: string;
  workflowVersionId: string;
  triggeredBy: TriggerKind;
  triggeredByUserId: string | null;
  status: RunStatus;
  cohortSizeAtEntry: number;
  startedAt: string | null;
  completedAt: string | null;
  error: string | null;
  params: Record<string, unknown>;
  createdAt: string;
}

export interface RecipientState {
  recipientId: string;
  currentNodeId: string | null;
  status: string;
  wakeupAt: string | null;
  payload: Record<string, unknown>;
  enrolledAt: string;
  completedAt: string | null;
  error: string | null;
}

export interface ActionRow {
  id: string;
  recipientId: string;
  channel: string;
  actionType: string;
  status: string;
  idempotencyKey: string;
  payload: Record<string, unknown>;
  response: Record<string, unknown> | null;
  error: string | null;
  parentActionId: string | null;
  createdAt: string;
  completedAt: string | null;
}

/**
 * Returns the routing key for an edge, accepting the canonical `outputId`
 * field, the legacy `label` field, or falling back to `'default'`.
 *
 * Use this whenever code needs to match an outgoing edge to a node's
 * declared output. The backend normalizer produces canonical edges with
 * `outputId` set, but unsynchronized FE state and old saved definitions
 * may still carry only `label`.
 */
export function getEdgeOutputId(edge: WorkflowDefinitionEdge): string {
  return edge.outputId ?? edge.label ?? 'default';
}
