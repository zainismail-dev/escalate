"""Build the static live demo's data (web/src/demo/*.json) from a throwaway DEMO_MODE API.

    make demo-fixtures        # = uv run python -m scripts.demo_fixtures

The API runs in-process on a scratch database in a temp folder: never ./escalate.db, never
./data, never the developer's .env. It seeds the four demo cases, records every read the web app
makes, then approves one draft and logs a sample reply to record a reply verdict (DEMO_MODE:
nothing is sent).
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "src" / "demo"

SAMPLE_REPLY = (
    "Dear customer, thank you for your patience. We can offer a 50% refund as a goodwill "
    "gesture within 14 days, provided you return the item in its original packaging."
)
REPLY_VERDICT = {
    "verdict": "partial",
    "promise": "a 50% refund as a goodwill gesture",
    "promise_date": None,
    "condition": "you return the item in its original packaging",
    "reason": "They offer half the amount, with a condition, not the full refund you asked for.",
}


def _isolate(tmp: Path) -> None:
    from cryptography.fernet import Fernet

    os.environ.update(
        DEMO_MODE="true",
        DATABASE_URL=f"sqlite:///{tmp / 'escalate.db'}",
        CHECKPOINT_DB=str(tmp / "checkpoints.db"),
        EVIDENCE_DIR=str(tmp / "evidence"),
        ESCALATE_SETTINGS_FILE=str(tmp / "settings.json"),
        FERNET_KEY=Fernet.generate_key().decode(),
        LLM_BASE_URL="http://127.0.0.1:9/v1",  # nothing listens: no model is ever called
        MODEL_SMART="none",
        MODEL_FAST="none",
        APP_PASSCODE="",
    )
    from escalate.config import Settings, get_settings

    Settings.model_config["env_file"] = None  # never the developer's .env
    get_settings.cache_clear()


class _ReplyJudge:
    """The demo model, with a richer reply verdict for the sample reply."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def complete(self, prompt: str, slot: Any = "smart") -> str:
        if "A company replied" in prompt:
            return json.dumps(REPLY_VERDICT)
        return str(self.inner.complete(prompt, slot))


def _ok(r: Any) -> Any:
    if r.status_code >= 400:
        raise SystemExit(f"{r.request.method} {r.request.url}: {r.status_code} {r.text}")
    return r.json()


def build() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from escalate import llm as llm_module
    from escalate.api.main import create_app
    from escalate.demo import CASES, DemoLLM

    headers = {"Origin": "http://localhost:3000", "X-Escalate-Request": "1"}
    data: dict[str, Any] = {"cases": {}, "timelines": {}, "reviews": {}, "checklists": {}}
    with TestClient(create_app(), base_url="http://localhost", headers=headers) as api:
        ids = _ok(api.post("/demo/seed"))["case_ids"]
        data["countries"] = _ok(api.get("/countries"))
        data["settings"] = _ok(api.get("/settings"))
        data["checklists"]["_generic"] = _ok(api.get("/checklist"))

        def snapshot(cid: str) -> dict[str, Any]:
            detail = _ok(api.get(f"/cases/{cid}"))
            data["cases"][cid] = detail
            data["timelines"][cid] = _ok(api.get(f"/cases/{cid}/timeline"))
            draft = detail.get("pending_draft")
            if draft:
                data["reviews"][draft["id"]] = _ok(api.get(f"/messages/{draft['id']}/review"))
            if detail["country"]:
                data["checklists"][detail["country"]] = _ok(
                    api.get("/checklist", params={"country": detail["country"]})
                )
            return detail

        details = [snapshot(cid) for cid in ids]

        # One case goes one step further: its letter is approved (DEMO_MODE: not sent) and the
        # company's sample reply is judged, so the demo shows a sent letter and a verdict.
        ready = next(
            d
            for d in details
            if d["waiting_for"] == "approve_draft"
            and not data["reviews"][d["pending_draft"]["id"]].get("blanks")
        )
        mid = ready["pending_draft"]["id"]
        recipient = data["reviews"][mid]["message"]["recipient"]
        _ok(api.post(f"/messages/{mid}/approve", json={"confirm": True, "recipient": recipient}))
        waiting = snapshot(ready["id"])
        assert waiting["waiting_for"] == "waiting_reply", waiting["waiting_for"]
        data["reviews"].pop(mid, None)

        previous = llm_module._llm
        llm_module.set_llm(_ReplyJudge(DemoLLM(CASES)))
        try:
            judged = _ok(api.post(f"/cases/{ready['id']}/replies", json={"text": SAMPLE_REPLY}))
        finally:
            llm_module.set_llm(previous)
        data["reply"] = {"case_id": ready["id"], "text": SAMPLE_REPLY, "result": judged}
        data["list"] = _ok(api.get("/cases"))
        # The list as it was before the reply: the case still waits for one.
        for row in data["list"]:
            if row["id"] == ready["id"]:
                row.update(
                    {k: waiting[k] for k in ("status", "waiting_for", "step_name") if k in waiting}
                )
    data["settings"].update(
        llm_base_url="http://localhost:11434/v1",  # what a real install shows: local Ollama
        model_smart="llama3.1:8b",
        model_fast="llama3.1:8b",
        is_cloud=False,
        smtp_user="",
    )
    return data


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="escalate-demo-") as tmp:
        _isolate(Path(tmp))
        data = build()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in data.items():
        (OUT / f"{name}.json").write_text(
            json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"wrote {len(data)} files to {OUT.relative_to(ROOT)}: {', '.join(sorted(data))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
