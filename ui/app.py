"""Escalate web UI (Streamlit). Run: uv run streamlit run ui/app.py

The UI talks only to the API (ui/api_client.py). Every string comes from locales/<lang>.json.
"""

from typing import Any

import api_client as api
import i18n
import streamlit as st

st.set_page_config(page_title="Escalate", page_icon="⚖️", layout="wide")

PAGE_IDS = ["scam", "new_case", "cases", "dashboard", "questions", "review", "reply", "settings"]
STATUS_COLOURS = {
    "resolved": "green",
    "withdrawn": "gray",
    "closed_unresolved": "gray",
    "awaiting_approval": "orange",
    "urgent_checklist": "red",
}


def t(key: str, **values: Any) -> str:
    return i18n.translate(st.session_state.get("ui_lang", "en"), key, **values)


def go(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


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
        st.error(t("app.api_down", url=api.API_URL))
        st.stop()
    if health.get("is_cloud"):
        st.warning(t("app.cloud_warning", url=health["llm_base_url"]))
    if health.get("demo_mode"):
        st.info(t("app.demo_mode"))


def pick_case() -> int | None:
    cases = api.get("/cases")
    if not cases:
        st.info(t("app.no_cases"))
        return None
    labels = {
        c["id"]: f"#{c['id']} · {c.get('company') or ''} · {t('status.' + c['status'])}"
        for c in cases
    }
    ids = list(labels)
    current = st.session_state.get("case_id")
    index = ids.index(current) if current in ids else 0
    chosen = st.sidebar.selectbox(t("app.case"), ids, index=index, format_func=labels.get)
    st.session_state["case_id"] = chosen
    return int(chosen)


def show_checklist(items: list[dict[str, Any]], warnings: list[str]) -> None:
    for w in warnings:
        st.warning(w)
    for n, item in enumerate(items, start=1):
        marker = "🔴" if item.get("urgent", True) else "⚪"
        st.markdown(f"{marker} **{n}. {item['title']}**  \n{item.get('detail', '')}")


# --- pages -----------------------------------------------------------------------


def page_scam() -> None:
    st.header(t("scam.header"))
    st.caption(t("scam.caption"))
    country = st.text_input(t("scam.country"), max_chars=2)
    checklist = api.get("/checklist", **({"country": country} if country else {}))
    show_checklist(checklist["items"], checklist.get("warnings", []))
    if checklist["country"] == "INTL":
        st.caption(t("scam.generic"))
    st.divider()
    st.write(t("scam.then"))
    if st.button(t("scam.open_case"), type="primary"):
        go("new_case")


def page_new_case() -> None:
    st.header(t("new.header"))
    st.caption(t("new.caption"))
    with st.form("new_case"):
        text = st.text_area(t("new.story"), height=220)
        files = st.file_uploader(
            t("new.evidence"),
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "pdf", "eml", "txt"],
        )
        c1, c2, c3 = st.columns(3)
        country = c1.text_input(t("new.country"), max_chars=2)
        region = c2.text_input(t("new.region"), max_chars=6)
        language = c3.text_input(
            t("new.language"), value=st.session_state.get("draft_lang", "en"), max_chars=2
        )
        submitted = st.form_submit_button(t("new.submit"), type="primary")
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
        with st.spinner(t("new.working")):
            api.post(f"/cases/{case['id']}/start")
    except api.ApiError as exc:
        show_error(exc)
        return
    st.session_state["case_id"] = case["id"]
    go("dashboard")


def questions_form(cid: int, missing: list[str]) -> None:
    with st.form("answers"):
        answers = {k: st.text_input(k.replace("_", " ").capitalize()) for k in missing}
        if st.form_submit_button(t("pending.save_answers"), type="primary"):
            api.post(f"/cases/{cid}/answers", json={"answers": answers})
            st.rerun()


def pending_panel(case: dict[str, Any]) -> None:
    p = case.get("pending")
    cid = case["id"]
    if not p:
        return
    kind = p["type"]
    try:
        if kind == "questions":
            st.subheader(t("pending.questions"))
            questions_form(cid, p.get("missing", []))
        elif kind == "urgent_checklist":
            st.error(t("pending.urgent"))
            params = {"country": case["country"]} if case["country"] else {}
            checklist = api.get("/checklist", **params)
            show_checklist(p.get("items", []), checklist.get("warnings", []))
            if st.button(t("pending.urgent_done"), type="primary"):
                api.post(f"/cases/{cid}/checklist/ack")
                st.rerun()
        elif kind == "approve_draft":
            st.info(t("pending.draft_waiting"))
            if st.button(t("pending.review"), type="primary"):
                go("review")
        elif kind == "confirm_delivery":
            st.subheader(t("pending.deliver"))
            st.write(p.get("note", ""))
            mid = p["message_id"]
            st.link_button(
                t("pending.download_pdf"), f"{api.PUBLIC_API_URL}/messages/{mid}/printable.pdf"
            )
            proof = st.file_uploader(t("pending.upload_proof"), key=f"proof{mid}")
            if st.button(t("pending.delivered"), type="primary"):
                eid = None
                if proof is not None:
                    ev = api.post(
                        f"/cases/{cid}/evidence", files={"file": (proof.name, proof.getvalue())}
                    )
                    eid = ev["id"]
                api.post(f"/messages/{mid}/confirm-delivery", json={"evidence_id": eid})
                st.rerun()
        elif kind == "waiting_reply":
            st.write(t("pending.waiting"))
    except api.ApiError as exc:
        show_error(exc)


def page_dashboard() -> None:
    cid = pick_case()
    if cid is None:
        return
    case = api.get(f"/cases/{cid}")
    colour = STATUS_COLOURS.get(case["status"], "blue")
    st.header(t("dash.header", id=cid))
    st.markdown(f":{colour}[**{t('status.' + case['status'])}**]")
    if case.get("generic_playbook"):
        st.caption(t("dash.generic"))
    c1, c2 = st.columns(2)
    c1.metric(t("dash.current_step"), case.get("step_name") or "—")
    c2.metric(t("dash.next_action"), (case.get("next_action_at") or "—")[:10])
    for d in case.get("deadlines", []):
        if d["late"]:
            st.error(t("dash.deadline_passed", rule=d["rule"], due=d["due"]))
        elif d["warn"]:
            st.error(t("dash.deadline_soon", days=d["days_left"], rule=d["rule"], due=d["due"]))
    pending_panel(case)
    c3, c4 = st.columns(2)
    c3.link_button(t("dash.export"), f"{api.PUBLIC_API_URL}/cases/{cid}/export.pdf")
    if case["status"] not in ("resolved", "withdrawn") and c4.button(t("dash.withdraw")):
        try:
            api.post(f"/cases/{cid}/withdraw", json={"reason": "withdrawn by user"})
            st.success(t("dash.withdrawn"))
            st.rerun()
        except api.ApiError as exc:
            show_error(exc)
    with st.expander(t("dash.delete")):
        if st.button(t("dash.delete_confirm"), type="secondary"):
            api.delete(f"/cases/{cid}")
            st.session_state.pop("case_id", None)
            st.success(t("dash.deleted"))
            go("cases")
    st.subheader(t("dash.timeline"))
    for ev in api.get(f"/cases/{cid}/timeline"):
        st.markdown(f"`{ev['created_at'][:16].replace('T', ' ')}` · {ev['type'].replace('_', ' ')}")


def page_review() -> None:
    cid = pick_case()
    if cid is None:
        return
    case = api.get(f"/cases/{cid}")
    draft = case.get("pending_draft")
    if not draft:
        st.info(t("review.none"))
        return
    st.header(t("review.header"))
    st.caption(
        t(
            "review.to",
            to=draft.get("recipient") or t("review.you_deliver"),
            channel=draft["channel"],
        )
    )
    left, right = st.columns([3, 2])
    with left:
        subject = st.text_input(t("review.subject"), value=draft.get("subject") or "")
        body = st.text_area(t("review.message"), value=draft["body"], height=460)
    with right:
        st.subheader(t("review.facts"))
        st.dataframe(
            [{t("review.fact"): f["key"], t("review.value"): f["value"]} for f in case["facts"]],
            hide_index=True,
            use_container_width=True,
        )
    mid = draft["id"]
    b1, b2, b3 = st.columns(3)
    try:
        if b1.button(t("review.approve"), type="primary"):
            edited = body != draft["body"] or subject != (draft.get("subject") or "")
            payload: dict[str, object] = {"confirm": True}  # the API needs explicit confirmation
            if edited:
                payload.update(body=body, subject=subject)
            api.post(f"/messages/{mid}/approve", json=payload)
            st.success(t("review.approved"))
            go("dashboard")
        if b2.button(t("review.save")):
            res = api.put(f"/messages/{mid}", json={"body": body, "subject": subject})
            for w in res["warnings"]:
                st.warning(w)
            if not res["warnings"]:
                st.success(t("review.saved"))
        reason = b3.text_input(t("review.reject_reason"), key="reject_reason")
        if b3.button(t("review.reject")):
            api.post(f"/messages/{mid}/reject", json={"reason": reason})
            st.rerun()
    except api.ApiError as exc:
        show_error(exc)


def page_questions() -> None:
    cid = pick_case()
    if cid is None:
        return
    st.header(t("page.questions"))
    p = api.get(f"/cases/{cid}").get("pending") or {}
    if p.get("type") != "questions":
        st.info(t("questions.none"))
        return
    st.caption(t("questions.intro"))
    try:
        questions_form(cid, p.get("missing", []))
    except api.ApiError as exc:
        show_error(exc)


def page_reply() -> None:
    cid = pick_case()
    if cid is None:
        return
    st.header(t("reply.header"))
    p = api.get(f"/cases/{cid}").get("pending") or {}
    if p.get("type") != "waiting_reply":
        st.info(t("reply.not_waiting"))
        return
    with st.form("reply"):
        text = st.text_area(t("reply.text"), height=240)
        submitted = st.form_submit_button(t("reply.submit"), type="primary")
    if submitted and text.strip():
        try:
            res = api.post(f"/cases/{cid}/replies", json={"text": text})
        except api.ApiError as exc:
            show_error(exc)
            return
        verdict = res.get("verdict") or "no_reply"
        show = st.success if verdict == "resolved" else st.warning
        show(t("reply.verdict", verdict=t(f"verdict.{verdict}")))
        if res.get("reason"):
            st.write(t("reply.reason", reason=res["reason"]))


def page_cases() -> None:
    st.header(t("cases.header"))
    cases = api.get("/cases")
    statuses = sorted({c["status"] for c in cases})
    chosen = st.multiselect(
        t("cases.filter"), statuses, default=statuses, format_func=lambda s: t(f"status.{s}")
    )
    rows = [
        {
            t("cases.col_id"): c["id"],
            t("cases.col_company"): c.get("company") or "",
            t("cases.col_type"): (c.get("case_type") or "").replace("_", " "),
            t("cases.col_country"): c.get("country") or "",
            t("cases.col_status"): t(f"status.{c['status']}"),
            t("cases.col_next"): (c.get("next_action_at") or "")[:10],
        }
        for c in cases
        if c["status"] in chosen
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
    ids = [c["id"] for c in cases if c["status"] in chosen]
    if ids:
        pick = st.selectbox(t("cases.open"), ids, format_func=lambda i: f"#{i}")
        if st.button(t("cases.open"), type="primary"):
            st.session_state["case_id"] = pick
            go("dashboard")


def page_settings() -> None:
    st.header(t("settings.header"))
    health = api.get("/health")
    st.subheader(t("settings.llm"))
    st.write(t("settings.llm_endpoint", url=health["llm_base_url"]))
    if st.button(t("settings.llm_test")):
        res = api.post("/settings/llm-test")
        if res["ok"]:
            st.success(t("settings.llm_ok", reply=res["reply"]))
        else:
            st.error(t("settings.llm_fail", error=res["error"]))
    st.subheader(t("settings.email"))
    st.write(t("settings.email_mode", mode=health["email_mode"]))
    st.caption(t("settings.email_help"))
    st.subheader(t("settings.languages"))
    st.session_state["draft_lang"] = st.text_input(
        t("settings.draft_language"), value=st.session_state.get("draft_lang", "en"), max_chars=2
    )
    st.caption(t("settings.ui_language_help"))
    st.caption(t("settings.version", version=health["version"]))


PAGES = {
    "scam": page_scam,
    "new_case": page_new_case,
    "cases": page_cases,
    "dashboard": page_dashboard,
    "questions": page_questions,
    "review": page_review,
    "reply": page_reply,
    "settings": page_settings,
}


def sidebar() -> str:
    langs = i18n.available()
    current = st.session_state.get("ui_lang", "en")
    st.session_state["ui_lang"] = st.sidebar.selectbox(
        "🌐 " + t("app.ui_language"), langs, index=langs.index(current) if current in langs else 0
    )
    if st.session_state["ui_lang"] in i18n.RTL:
        st.markdown("<style>.main, section.main {direction: rtl;}</style>", unsafe_allow_html=True)
    st.sidebar.title(t("app.title"))
    page = st.session_state.get("page", "new_case")
    chosen = st.sidebar.radio(
        t("app.go_to"),
        PAGE_IDS,
        index=PAGE_IDS.index(page) if page in PAGE_IDS else 1,
        format_func=lambda p: t(f"page.{p}"),
    )
    st.session_state["page"] = chosen
    st.sidebar.caption(t("app.disclaimer"))
    return chosen


def main() -> None:
    page = sidebar()
    privacy_banner()
    PAGES[page]()


main()
