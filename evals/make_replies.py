"""Writes evals/replies.json: 40 sample company replies with the expected verdict.

    uv run python -m evals.make_replies

Rule under test: a vague promise with no date is "refused"; an auto-acknowledgement that
says nothing about the remedy is "no_reply".
"""

import json
from pathlib import Path

OUT = Path(__file__).parent / "replies.json"

R = "a full refund"
X = "a replacement"
C = "cancel the subscription and refund the charges"

REPLIES: list[tuple[str, str, str]] = [
    # resolved (10)
    (
        R,
        "We have processed a full refund of PKR 45,000 to your card today. Ref RF-1001.",
        "resolved",
    ),
    (R, "Your refund has been issued in full. It will show in 3-5 working days.", "resolved"),
    (
        X,
        "A replacement unit will be delivered on 2026-11-05. Please keep the old one for collection.",
        "resolved",
    ),
    (
        X,
        "We have dispatched a new LED TV. Tracking number TRK-5520, arriving 2026-11-02.",
        "resolved",
    ),
    (C, "Your subscription is cancelled and both charges have been refunded today.", "resolved"),
    (
        C,
        "We confirm cancellation effective immediately and have refunded all payments since your request.",
        "resolved",
    ),
    (
        R,
        "Apologies. A full refund of $89.99 was sent to your original payment method this morning.",
        "resolved",
    ),
    (
        X,
        "Replacement approved and shipped today by courier; you will receive it by 2026-11-03.",
        "resolved",
    ),
    (R, "Hemos realizado el reembolso completo de 349 EUR hoy.", "resolved"),
    (C, "Account closed. Refund of GBP 69.00 issued to your card on 2026-10-28.", "resolved"),
    # partial (10)
    (R, "We can refund 50% of the price as a goodwill gesture.", "partial"),
    (R, "We will refund the item price today but not the delivery charge.", "partial"),
    (X, "We can't replace it, but we have issued a 30% store voucher today.", "partial"),
    (
        C,
        "We have cancelled your subscription today, but the past charges are non-refundable.",
        "partial",
    ),
    (C, "Cancellation confirmed. We refunded one of the two charges today.", "partial"),
    (
        X,
        "We have refunded PKR 10,000 for the inconvenience today; replacement is not possible.",
        "partial",
    ),
    (
        R,
        "We will repair the item free of charge; collection is booked for 2026-11-04. A refund is not possible.",
        "partial",
    ),
    (R, "Store credit for the full amount has been added to your account today.", "partial"),
    (
        C,
        "We have stopped future billing. Refunds for previous months are not available.",
        "partial",
    ),
    (X, "We can offer a cheaper model as a replacement, shipping on 2026-11-06.", "partial"),
    # refused (14), including undated promises
    (X, "We will replace the LED when the company claim is approved.", "refused"),
    (R, "Our policy does not allow refunds after 7 days. We cannot help.", "refused"),
    (R, "This damage is not covered by warranty. Your request is declined.", "refused"),
    (X, "Your case is with our technical team. We will update you soon.", "refused"),
    (
        C,
        "Subscriptions cannot be cancelled during the minimum term. Charges will continue.",
        "refused",
    ),
    (R, "We are looking into it and will get back to you in due course.", "refused"),
    (
        X,
        "The manufacturer will decide. Please be patient, we will inform you when we hear back.",
        "refused",
    ),
    (C, "Our records show no cancellation request, so the charges are valid.", "refused"),
    (R, "Refund will be processed once our finance department approves it.", "refused"),
    (X, "We will send a replacement as soon as stock arrives.", "refused"),
    (R, "We regret that we cannot accept returns on sale items.", "refused"),
    (C, "Please call our retention team to discuss your options.", "refused"),
    (R, "Nous ne pouvons pas rembourser ce produit.", "refused"),
    (X, "We are escalating your case. Expect a resolution shortly.", "refused"),
    # no_reply / auto-acknowledgements (6)
    (
        R,
        "Thank you for contacting us. Your ticket number is #88213. An agent will respond.",
        "no_reply",
    ),
    (X, "This is an automated message: we have received your email.", "no_reply"),
    (C, "Out of office until Monday.", "no_reply"),
    (R, "Your message has been received. Please do not reply to this email.", "no_reply"),
    (X, "Ticket #4410 created. Average response time is 5 business days.", "no_reply"),
    (C, "Thanks! We got your request and will be in touch.", "no_reply"),
]


def main() -> None:
    rows = [
        {"id": f"r{i:02d}", "remedy_wanted": remedy, "reply_text": text, "expected": verdict}
        for i, (remedy, text, verdict) in enumerate(REPLIES, start=1)
    ]
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} replies to {OUT}")


if __name__ == "__main__":
    main()
