/** A step name where it starts a heading or a label ("Review: Written complaint to the
 * trader"). The API sends step names for mid-sentence use ("Approve written complaint to the
 * trader"), so only these places capitalise. */
export function stepHeading(name: string | null | undefined, locale?: string): string {
  if (!name) return "";
  const first = String.fromCodePoint(name.codePointAt(0)!);
  return first.toLocaleUpperCase(locale) + name.slice(first.length);
}
