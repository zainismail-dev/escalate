"""Escalate web UI (Streamlit). Run: uv run streamlit run ui/app.py"""

from typing import Any

import api_client as api
import streamlit as st

st.set_page_config(page_title="Escalate", page_icon="⚖️", layout="wide")

PAGES = ["New case", "Case dashboard", "Review draft"]
STATUS_COLOURS = {
    "resolved": "green",
    "withdrawn": "gray",
    "closed_unresolved": "gray",
    "awaiting_approval": "orange",
    "urgent_checklist": "red",
}


def show_error(exc: api.ApiError) -> None:
    detail = exc.detail.get("detail", exc.detail) if isinstance(exc.detail, dict) else exc.detail
    st.error(f"{detail}")
    if isinstance(exc.detail, dict) and exc.detail.get("issues"):
        for issue in exc.detail["issues"]:
            st.write(f"- {issue}")


def privacy_banner() -> None:
    try:
        health = api.get("/health")
    except Exception:
        st.error(f"Cannot reach the Escalate API at {api.API_URL}. Is it running?")
        st.stop()
    if health.get("is_cloud"):
        st.warning(
            f"Your AI model runs in the cloud ({health['llm_base_url']}). Free cloud tiers may "
            "use what you send for training. Avoid real personal data, or switch to a local model."
        )
    if health.get("demo_mode"):
        st.info("Demo mode: nothing is really sent, and cases are deleted after 24 hours.")


def pick_case() -> int | None:
    cases = api.get("/cases")
    if not cases:
        st.info("No cases yet. Start one on the New case page.")
        return None
    labels = {c["id"]: f"#{c['id']} · {c.get('company') or 'case'} · {c['status']}" for c in cases}
    ids = list(labels)
    current = st.session_state.get("case_id")
    index = ids.index(current) if current in ids else 0
    chosen = st.sidebar.selectbox("Case", ids, index=index, format_func=labels.get)
    st.session_state["case_id"] = chosen
    return int(chosen)


# --- pages -----------------------------------------------------------------------


def page_new_case() -> None:
    st.header("What happened?")
    st.caption(
        "Describe it in your own words: what you bought or paid for, when, how much, and what "
        "went wrong. Escalate will never ask for passwords, PINs or one-time codes."
    )
    with st.form("new_case"):
        text = st.text_area("Your story", height=220)
        files = st.file_uploader(
            "Evidence (receipts, screenshots, emails)",
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "pdf", "eml", "txt"],
        )
        c1, c2, c3 = st.columns(3)
        country = c1.text_input("Country (ISO code, e.g. PK, IN, GB, US)", max_chars=2)
        region = c2.text_input("Province/state (ISO 3166-2, e.g. PK-SD)", max_chars=6)
        language = c3.text_input("Language for letters (ISO 639-1)", value="en", max_chars=2)
        submitted = st.form_submit_button("Start my case", type="primary")
    if not submitted:
        return
    try:
        case = api.post(
            "/cases",
            json={
                "description": text,
                "country": country or None,
                "region": region or None,
                "language": language or "en",
            },
        )
        for f in files or []:
            api.post(f"/cases/{case['id']}/evidence", files={"file": (f.name, f.getvalue())})
        with st.spinner("Reading your evidence and preparing the first step…"):
            api.post(f"/cases/{case['id']}/start")
    except api.ApiError as exc:
        show_error(exc)
        return
    st.session_state["case_id"] = case["id"]
    st.session_state["page"] = "Case dashboard"
    st.rerun()


def pending_panel(case: dict[str, Any]) -> None:
    p = case.get("pending")
    cid = case["id"]
    if not p:
        return
    kind = p["type"]
    if kind == "questions":
        st.subheader("A few questions")
        with st.form("answers"):
            answers = {
                k: st.text_input(k.replace("_", " ").capitalize()) for k in p.get("missing", [])
            }
            if st.form_submit_button("Save answers", type="primary"):
                try:
                    api.post(f"/cases/{cid}/answers", json={"answers": answers})
                    st.rerun()
                except api.ApiError as exc:
                    show_error(exc)
    elif kind == "urgent_checklist":
        st.error("Do these now — they are time-critical")
        for item in p.get("items", []):
            st.markdown(f"**{item['title']}**  \n{item.get('detail', '')}")
        if st.button("I have done the urgent steps", type="primary"):
            api.post(f"/cases/{cid}/checklist/ack")
            st.rerun()
    elif kind == "approve_draft":
        st.info("A draft is waiting for your approval.")
        if st.button("Review draft", type="primary"):
            st.session_state["page"] = "Review draft"
            st.rerun()
    elif kind == "confirm_delivery":
        st.subheader("Deliver it yourself")
        st.write(p.get("note", ""))
        mid = p["message_id"]
        st.link_button("Download printable PDF", f"{api.API_URL}/messages/{mid}/printable.pdf")
        proof = st.file_uploader("Upload the receipt / proof", key=f"proof{mid}")
        if st.button("I have delivered it", type="primary"):
            try:
                eid = None
                if proof is not None:
                    ev = api.post(
                        f"/cases/{cid}/evidence", files={"file": (proof.name, proof.getvalue())}
                    )
                    eid = ev["id"]
                api.post(f"/messages/{mid}/confirm-delivery", json={"evidence_id": eid})
                st.rerun()
            except api.ApiError as exc:
                show_error(exc)
    elif kind == "waiting_reply":
        st.write("Waiting for a reply. Log it when it arrives; the follow-up is automatic.")


def page_dashboard() -> None:
    cid = pick_case()
    if cid is None:
        return
    case = api.get(f"/cases/{cid}")
    colour = STATUS_COLOURS.get(case["status"], "blue")
    st.header(f"Case #{cid}")
    st.markdown(f":{colour}[**{case['status'].replace('_', ' ')}**]")
    if case.get("generic_playbook"):
        st.caption("Generic international ladder — check the rules in your country.")
    c1, c2 = st.columns(2)
    c1.metric("Current step", case.get("step_name") or "—")
    c2.metric("Next action", (case.get("next_action_at") or "—")[:10])
    for d in case.get("deadlines", []):
        if d["late"]:
            st.error(f"Deadline passed: {d['rule']} (was due {d['due']})")
        elif d["warn"]:
            st.error(f"Deadline in {d['days_left']} days: {d['rule']} (due {d['due']})")
    pending_panel(case)
    st.subheader("Timeline")
    for ev in api.get(f"/cases/{cid}/timeline"):
        st.markdown(f"`{ev['created_at'][:16].replace('T', ' ')}` · {ev['type'].replace('_', ' ')}")


def page_review() -> None:
    cid = pick_case()
    if cid is None:
        return
    case = api.get(f"/cases/{cid}")
    draft = case.get("pending_draft")
    if not draft:
        st.info("No draft is waiting for approval in this case.")
        return
    st.header("Review draft")
    st.caption(f"To: {draft.get('recipient') or 'you deliver it'} · channel: {draft['channel']}")
    left, right = st.columns([3, 2])
    with left:
        subject = st.text_input("Subject", value=draft.get("subject") or "")
        body = st.text_area("Message", value=draft["body"], height=460)
    with right:
        st.subheader("Facts used")
        st.dataframe(
            [{"fact": f["key"], "value": f["value"]} for f in case["facts"]],
            hide_index=True,
            use_container_width=True,
        )
    mid = draft["id"]
    b1, b2, b3 = st.columns(3)
    try:
        if b1.button("Approve & send", type="primary"):
            edited = body != draft["body"] or subject != (draft.get("subject") or "")
            payload = {"body": body, "subject": subject} if edited else {}
            api.post(f"/messages/{mid}/approve", json=payload)
            st.success("Approved.")
            st.session_state["page"] = "Case dashboard"
            st.rerun()
        if b2.button("Save edit"):
            res = api.put(f"/messages/{mid}", json={"body": body, "subject": subject})
            for w in res["warnings"]:
                st.warning(w)
            if not res["warnings"]:
                st.success("Saved.")
        reason = b3.text_input("Reason to reject", key="reject_reason")
        if b3.button("Reject"):
            api.post(f"/messages/{mid}/reject", json={"reason": reason})
            st.rerun()
    except api.ApiError as exc:
        show_error(exc)


def main() -> None:
    privacy_banner()
    st.sidebar.title("Escalate")
    page = st.sidebar.radio(
        "Go to", PAGES, index=PAGES.index(st.session_state.get("page", "New case"))
    )
    st.session_state["page"] = page
    {"New case": page_new_case, "Case dashboard": page_dashboard, "Review draft": page_review}[
        page
    ]()
    st.sidebar.caption("Escalate is a self-help tool, not legal advice.")


main()
