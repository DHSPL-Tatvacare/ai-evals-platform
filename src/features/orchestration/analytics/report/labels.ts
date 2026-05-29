import type { RunReportChannel } from '../types';

/** Title-case a capability slug, e.g. 'voice' -> 'Voice', 'messaging' -> 'Messaging'. */
export function capabilityLabel(capability: string): string {
  if (!capability) return '';
  return capability
    .replace(/[_-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Channel-strip header label: "{Capability} · {Connection}" when a connection
 * label is present, else just the capability label. Never hardcodes a vendor.
 */
export function channelHeaderLabel(channel: RunReportChannel): string {
  const cap = capabilityLabel(channel.capability);
  const connection = channel.connectionLabel?.trim();
  return connection ? `${cap} · ${connection}` : cap;
}

/** Distinct capability labels, in first-seen order, for the subtitle —
 *  consistent Title-cased capabilities (e.g. "Voice and Messaging"), never a
 *  mix of connection name + capability. Provider detail lives in the strips. */
export function distinctChannelNames(channels: RunReportChannel[]): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const channel of channels) {
    const name = capabilityLabel(channel.capability);
    if (name && !seen.has(name)) {
      seen.add(name);
      names.push(name);
    }
  }
  return names;
}

/** Join names as "A", "A and B", "A, B and C" for the subtitle. */
export function joinChannelNames(names: string[]): string {
  if (names.length === 0) return '';
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}
