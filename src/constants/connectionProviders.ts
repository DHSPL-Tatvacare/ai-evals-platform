// Vendor brand logos + labels for provider connections (WhatsApp / voice / CRM / SMS).
// One registry, mirrors LLM_PROVIDER_LOGOS. Vendors without a brand asset
// fall back to a neutral lucide icon in <ConnectionProviderLogo>.
export const CONNECTION_PROVIDER_LOGOS: Record<string, string> = {
  wati: '/connection-logos/wati.png',
  aisensy: '/connection-logos/aisensy.jpg',
  bolna: '/connection-logos/bolna.png',
};

export const CONNECTION_PROVIDER_LABELS: Record<string, string> = {
  bolna: 'Bolna',
  wati: 'WATI',
  aisensy: 'AiSensy',
  lsq: 'LeadSquared',
  msg91: 'MSG91',
  webhook: 'Generic Webhook',
};

// Capability category per provider, mirroring the backend ProviderSpec.kind.
// Surfaces filter on this — the CRM mapping shows only 'crm_source'. The
// authoritative value rides on the schema response (ProviderSchema.kind); this
// map is the static fallback for list views that don't fetch a schema.
export const CONNECTION_PROVIDER_KINDS: Record<string, string> = {
  bolna: 'voice',
  wati: 'messaging',
  aisensy: 'messaging',
  lsq: 'crm_source',
  msg91: 'messaging',
  webhook: 'messaging',
};
