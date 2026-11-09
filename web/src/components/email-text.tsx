import { Fragment } from "react";
import { emailBreakParts } from "@/lib/email-breaks";

/** An email address that wraps between its parts, never in the middle of a word. */
export function EmailText({ address }: { address: string }) {
  return (
    <>
      {emailBreakParts(address).map((part, i) => (
        <Fragment key={i}>
          {i > 0 && <wbr />}
          {part}
        </Fragment>
      ))}
    </>
  );
}
