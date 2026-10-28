import type { Segment } from "@/lib/types";
import { cn } from "@/lib/utils";

/** A letter on paper. Verified facts are lime-highlighted; blanks to fill are orange. */
export function Letter({
  subject,
  body,
  lang,
  dir,
  factLabel,
  blankLabel,
  className,
  testId,
}: {
  subject: Segment[] | string | null;
  body: Segment[] | string;
  lang: string;
  dir: "ltr" | "rtl";
  factLabel: (key: string | null) => string;
  blankLabel: string;
  className?: string;
  testId?: string;
}) {
  const render = (segs: Segment[] | string) =>
    typeof segs === "string"
      ? segs
      : segs.map((s, i) =>
          s.kind === "fact" ? (
            <mark key={i} className="fact-mark" title={factLabel(s.key)}>
              {s.text}
            </mark>
          ) : s.kind === "blank" ? (
            <mark key={i} className="blank-mark" title={blankLabel} data-blank>
              {s.text}
            </mark>
          ) : (
            <span key={i}>{s.text}</span>
          ),
        );
  return (
    <article
      lang={lang}
      dir={dir}
      data-testid={testId}
      className={cn(
        "letter rounded-md border border-line px-6 py-7 text-[0.97rem] leading-7 shadow-[0_1px_0_#e3e5ea,0_12px_32px_-18px_rgba(20,22,31,0.35)] sm:px-10 sm:py-9",
        className,
      )}
    >
      {subject && (typeof subject === "string" ? subject : subject.length > 0) ? (
        <p className="mb-5 font-semibold">{render(subject)}</p>
      ) : null}
      <div className="whitespace-pre-wrap break-words">{render(body)}</div>
    </article>
  );
}
