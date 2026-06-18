/**
 * Display helpers for provider lists shown in dropdowns/selects.
 *
 * Provider names are free-text and often include a courtesy title such as
 * "Dr. Smith". Stripping the leading title before display means an alphabetical
 * sort groups by surname rather than collapsing every entry under "Dr".
 */

/** Leading "Dr" / "Dr." title (case-insensitive), requiring trailing whitespace so
 *  real names like "Dryden" or "Drake" are never truncated. */
const TITLE_PREFIX_RE = /^\s*dr\.?\s+/i;

/** Remove a leading "Dr" / "Dr." courtesy title from a provider name. */
export function stripProviderTitle(name: string | null | undefined): string {
  return (name ?? "").replace(TITLE_PREFIX_RE, "").trim();
}

/**
 * Return a new array of providers sorted alphabetically by display name
 * (title-stripped, case-insensitive, natural numeric ordering). Does not mutate
 * the input.
 */
export function sortedProviders<T extends { name: string }>(providers: readonly T[]): T[] {
  return [...providers].sort((a, b) =>
    stripProviderTitle(a.name).localeCompare(stripProviderTitle(b.name), undefined, {
      sensitivity: "base",
      numeric: true,
    })
  );
}
