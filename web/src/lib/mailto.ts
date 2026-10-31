/** "Open in my email app": a mailto: link with the recipient, subject and letter (RFC 6068).
 * Mail apps and browsers cut long links, so a letter that doesn't fit is left out of the link:
 * the user copies it (or attaches the PDF) instead. */
export const MAILTO_MAX = 1800;

const EMAIL = /^[^\s@<>(),;:"]+@[^\s@<>(),;:"]+\.[^\s@<>(),;:"]+$/;

export function mailtoHref(recipient: string | null | undefined, subject: string | null | undefined, body: string, max = MAILTO_MAX): { href: string; bodyIncluded: boolean } {
  const to = recipient && EMAIL.test(recipient.trim()) ? encodeURIComponent(recipient.trim()).replace(/%40/g, "@") : "";
  const q = (s: string) => encodeURIComponent(s.replace(/\r?\n/g, "\r\n"));
  const head = `mailto:${to}?subject=${q(subject ?? "")}`;
  const full = `${head}&body=${q(body)}`;
  return full.length <= max ? { href: full, bodyIncluded: true } : { href: head, bodyIncluded: false };
}

/** What "Copy letter" puts on the clipboard. */
export function letterText(subject: string | null | undefined, body: string): string {
  return subject ? `Subject: ${subject}\n\n${body}` : body;
}
