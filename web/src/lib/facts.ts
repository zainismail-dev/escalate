/** A fact as people read it: the API formats money and dates in the case's locale. */
export function displayFact(f: { value: string; display?: string | null }): string {
  return f.display || f.value;
}

export function inputTypeFor(key: string): "date" | "email" | "text" {
  if (/(_on|_date)$/.test(key)) return "date";
  return "text";
}
