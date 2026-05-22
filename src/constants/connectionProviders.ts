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
