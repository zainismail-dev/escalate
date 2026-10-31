"""The hosted app's route inventory. A new route fails tests/hosted/test_routes.py until it is
listed here, which is the moment to decide who may call it, and until the IDOR suite
(tests/hosted/test_idor.py) covers it."""

HOSTED_ROUTES = {
    ("GET", "/health"),
    ("GET", "/checklist"),
    ("GET", "/countries"),
    ("GET", "/settings"),
    ("PUT", "/settings"),
    ("GET", "/me"),
    ("POST", "/me/consent"),
    ("POST", "/me/delete"),
    ("GET", "/me/export"),
    ("POST", "/internal/tick"),
    ("POST", "/cases"),
    ("GET", "/cases"),
    ("GET", "/cases/{case_id}"),
    ("PATCH", "/cases/{case_id}"),
    ("DELETE", "/cases/{case_id}"),
    ("POST", "/cases/{case_id}/evidence"),
    ("POST", "/cases/{case_id}/start"),
    ("POST", "/cases/{case_id}/answers"),
    ("POST", "/cases/{case_id}/checklist/ack"),
    ("POST", "/cases/{case_id}/retry"),
    ("GET", "/cases/{case_id}/timeline"),
    ("POST", "/cases/{case_id}/replies"),
    ("POST", "/cases/{case_id}/resolution"),
    ("POST", "/cases/{case_id}/verdict"),
    ("GET", "/cases/{case_id}/export.pdf"),
    ("POST", "/cases/{case_id}/letter-language"),
    ("POST", "/cases/{case_id}/withdraw"),
    ("PUT", "/messages/{message_id}"),
    ("POST", "/messages/{message_id}/approve"),
    ("POST", "/messages/{message_id}/recipient"),
    ("POST", "/messages/{message_id}/reject"),
    ("POST", "/messages/{message_id}/confirm-delivery"),
    ("GET", "/messages/{message_id}/printable.pdf"),
    ("GET", "/messages/{message_id}/review"),
    ("GET", "/messages/{message_id}/preview"),
}

# Open without a token (everything else: 401 without a valid Supabase token).
OPEN = {("GET", "/health"), ("POST", "/internal/tick")}  # the tick has its own secret
# Open to anyone signed in (the waitlist and consent pages; static reference data).
SIGNED_IN = {
    ("GET", "/me"),
    ("POST", "/me/consent"),
    ("POST", "/me/delete"),
    ("GET", "/me/export"),
    ("GET", "/checklist"),
    ("GET", "/countries"),
}
# The rest: invited users who have accepted the beta terms (403 waitlist / consent_required).
MEMBERS = HOSTED_ROUTES - OPEN - SIGNED_IN

# A request body for each route that takes one: valid, so only the ownership check can stop it.
BODIES: dict[tuple[str, str], dict[str, object]] = {
    ("PUT", "/settings"): {"default_country": "GB"},
    ("POST", "/me/consent"): {"confirm": True},
    ("POST", "/me/delete"): {"confirm": "DELETE"},
    ("POST", "/cases"): {"description": "The shop refuses my refund for a broken kettle."},
    ("PATCH", "/cases/{case_id}"): {"title": "pwned"},
    ("POST", "/cases/{case_id}/answers"): {"answers": {"order_id": "PWNED-1"}},
    ("POST", "/cases/{case_id}/replies"): {"text": "We refuse."},
    ("POST", "/cases/{case_id}/resolution"): {"resolved": True},
    ("POST", "/cases/{case_id}/verdict"): {"verdict": "resolved"},
    ("POST", "/cases/{case_id}/letter-language"): {"language": "en"},
    ("POST", "/cases/{case_id}/withdraw"): {"reason": "pwned"},
    ("PUT", "/messages/{message_id}"): {"body": "pwned", "subject": "pwned"},
    ("POST", "/messages/{message_id}/approve"): {
        "confirm": True,
        "recipient": "support@brightmart.example",
    },
    ("POST", "/messages/{message_id}/recipient"): {"recipient": "evil@example.com"},
    ("POST", "/messages/{message_id}/reject"): {"reason": "pwned"},
    ("POST", "/messages/{message_id}/confirm-delivery"): {"evidence_id": None},
}
QUERIES = {("GET", "/messages/{message_id}/preview"): {"language": "en"}}
