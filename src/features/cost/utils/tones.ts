import type { HBarTone } from '@/components/ui';

const APP_TONE_MAP: Record<string, HBarTone> = {
  'voice-rx': 'app:voicerx',
  voicerx: 'app:voicerx',
  'kaira-bot': 'app:kaira',
  kaira: 'app:kaira',
  'inside-sales': 'app:insidesales',
  insidesales: 'app:insidesales',
  report: 'app:report',
  'report-builder': 'app:report',
  system: 'app:system',
};

const PURPOSE_TONE_CYCLE: HBarTone[] = [
  'purpose:purple',
  'purpose:purple-light',
  'purpose:blue',
  'purpose:blue-light',
  'purpose:orange',
  'purpose:green',
  'purpose:gray',
  'purpose:gray-light',
];

const ERROR_CODE_TONE_MAP: Record<string, HBarTone> = {
  rate_limited: 'error',
  provider_500: 'error',
  provider_error: 'error',
  auth: 'error',
  timeout: 'warning',
  cancelled: 'neutral',
  ok: 'success',
};

export function toneForApp(key: string): HBarTone {
  const normalized = key.toLowerCase().replace(/\s+/g, '-');
  return APP_TONE_MAP[normalized] ?? 'app:system';
}

export function toneForPurpose(index: number): HBarTone {
  return PURPOSE_TONE_CYCLE[index % PURPOSE_TONE_CYCLE.length];
}

export function toneForErrorCode(code: string): HBarTone {
  return ERROR_CODE_TONE_MAP[code.toLowerCase()] ?? 'error';
}
