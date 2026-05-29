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

// Generic messaging capability surfaces its provider's product name (e.g.
// "WhatsApp") in copy; other capabilities read fine as the Title-cased
// capability. 'messaging' is the platform capability slug, not a vendor name.
const PROVIDER_NAMED_CAPABILITIES = new Set(['messaging']);

/**
 * The friendly channel name used in the header subtitle. For provider-named
 * capabilities (messaging) prefer the connection/vendor label so the subtitle
 * reads "WhatsApp" rather than "Messaging"; otherwise use the Title-cased
 * capability. Derived from data — no channel-product literal in code.
 */
export function channelDisplayName(channel: RunReportChannel): string {
  if (PROVIDER_NAMED_CAPABILITIES.has(channel.capability)) {
    return (
      channel.connectionLabel?.trim() ||
      channel.vendor?.trim() ||
      capabilityLabel(channel.capability)
    );
  }
  return capabilityLabel(channel.capability);
}

/** Distinct capability labels, in first-seen order, for the subtitle. */
export function distinctChannelNames(channels: RunReportChannel[]): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const channel of channels) {
    const name = channelDisplayName(channel);
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
