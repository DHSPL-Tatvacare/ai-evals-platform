/**
 * Shared helpers for review item/attribute keys.
 *
 * Backend stores item keys as `<type>:<id>` (e.g. `thread:thrd-xxx`, `call:abc`,
 * `segment:0`, `field:foo.bar`). Frontend sometimes needs the raw id portion
 * (e.g. to match against a router `:threadId` param).
 */

/** Strip the `<type>:` prefix from a review item key, returning the raw id. */
export function stripReviewItemPrefix(itemKey: string): string {
  const idx = itemKey.indexOf(':');
  return idx < 0 ? itemKey : itemKey.slice(idx + 1);
}

/** Compose the store key used inside review edit maps. */
export function reviewEditKey(itemKey: string, attributeKey: string): string {
  return `${itemKey}::${attributeKey}`;
}
