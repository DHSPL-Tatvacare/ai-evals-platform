/**
 * Storage barrel export.
 * All repositories delegate to HTTP API (src/services/api/).
 */
export {
  appsRepository,
  listingsRepository,
  filesRepository,
  promptsRepository,
  schemasRepository,
  evaluatorsRepository,
  chatSessionsRepository,
  chatMessagesRepository,
  historyRepository,
  settingsRepository,
  tagRegistryRepository,
  rulesRepository,
} from '@/services/api';

export type { TagRegistryItem, TagRegistryData } from '@/services/api';
export { authApi } from '@/services/api';
