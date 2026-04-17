import { isToolCallPart } from './chatWidgetHelpers';
import type { MessagePart } from './types';

export const SHERLOCK_THINKING_PHRASES = [
  'Deducing…',
  'Investigating…',
  'Sleuthing…',
  'Chasing leads…',
  'Piecing it together…',
  'Cross-referencing…',
  'Inferring…',
  'Consulting the archives…',
  'Interrogating the data…',
  'Tracing the thread…',
  'Closing in…',
  'On the scent…',
] as const;

export const SHERLOCK_ERROR_PHRASES = [
  'Reconsidering…',
  'Doubling back…',
  'Re-examining the evidence…',
  'Trying another angle…',
] as const;

const CATALOG_PHRASES = [
  'Examining the records…',
  'Reading the index…',
  'Cataloguing the evidence…',
  'Mapping the territory…',
] as const;

const DISCOVERY_PHRASES = [
  'Surveying the landscape…',
  'Canvassing the sources…',
  'Taking stock of the scene…',
] as const;

const ENTITY_PHRASES = [
  'Identifying the person of interest…',
  'Matching names to faces…',
  'Narrowing the suspect list…',
] as const;

const SURFACE_PHRASES = [
  'Pulling the logs…',
  'Gathering raw testimony…',
  'Combing the transcripts…',
] as const;

const ANALYTICS_PHRASES = [
  'Interrogating the data…',
  'Drafting the inquiry…',
  'Running the numbers…',
  'Cross-examining the figures…',
] as const;

const DATA_CHECK_PHRASES = [
  'Checking the evidence…',
  'Verifying the premise…',
  'Confirming the witness…',
] as const;

const BLUEPRINT_PHRASES = [
  'Composing the dossier…',
  'Assembling the case file…',
  'Drafting the report…',
] as const;

const TOOL_PHRASE_MAP: Record<string, readonly string[]> = {
  // catalog
  catalog_inspect: CATALOG_PHRASES,
  catalog_relations: CATALOG_PHRASES,
  catalog_values: CATALOG_PHRASES,
  catalog_sample: CATALOG_PHRASES,
  // discovery
  discover: DISCOVERY_PHRASES,
  lookup: DISCOVERY_PHRASES,
  // evidence / entity resolution
  resolve_entity: ENTITY_PHRASES,
  get_surface_records: SURFACE_PHRASES,
  // analytics
  data_check: DATA_CHECK_PHRASES,
  data_query: ANALYTICS_PHRASES,
  // blueprint / report builder
  blueprint_blocks: BLUEPRINT_PHRASES,
  blueprint_compose: BLUEPRINT_PHRASES,
  blueprint_save: BLUEPRINT_PHRASES,
  blueprint_list: BLUEPRINT_PHRASES,
};

export function phrasesForContext(parts: readonly MessagePart[]): readonly string[] {
  if (parts.length === 0) {
    return SHERLOCK_THINKING_PHRASES;
  }
  const last = parts[parts.length - 1];
  if (!isToolCallPart(last)) {
    return SHERLOCK_THINKING_PHRASES;
  }
  if (last.state === 'error') {
    return SHERLOCK_ERROR_PHRASES;
  }
  return TOOL_PHRASE_MAP[last.toolName] ?? SHERLOCK_THINKING_PHRASES;
}
