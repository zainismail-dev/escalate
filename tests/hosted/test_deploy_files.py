"""render.yaml and the tick workflow: hosted settings in place, secrets never in the repo."""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SECRETS = {
    "DATABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "FERNET_KEY",
    "LLM_API_KEY",
    "TICK_SECRET",
}
REQUIRED = SECRETS | {
    "DEPLOY_MODE",
    "SUPABASE_URL",
    "LLM_BASE_URL",
    "MODEL_SMART",
    "WEB_ORIGIN",
    "ALLOWED_HOSTS",
}


def test_render_blueprint_is_a_free_frankfurt_hosted_service() -> None:
    blueprint = yaml.safe_load((REPO / "render.yaml").read_text())
    [svc] = blueprint["services"]
    assert (svc["plan"], svc["region"], svc["runtime"]) == ("free", "frankfurt", "docker")
    assert svc["healthCheckPath"] == "/health"
    assert "--workers 1" in svc["dockerCommand"]
    env = {e["key"]: e for e in svc["envVars"]}
    assert env.keys() >= REQUIRED
    assert env["DEPLOY_MODE"]["value"] == "hosted"
    assert env["LLM_BASE_URL"]["value"].startswith("https://")
    for key in SECRETS:  # Render asks for them (or generates one); never a value in the repo
        assert "value" not in env[key], key
        assert env[key].get("sync") is False or env[key].get("generateValue") is True, key


def test_tick_workflow_uses_secrets_and_skips_without_them() -> None:
    wf = yaml.safe_load((REPO / ".github/workflows/tick.yml").read_text())
    assert wf["permissions"] == {}
    [job] = wf["jobs"].values()
    [step] = job["steps"]
    assert step["env"] == {
        "TICK_URL": "${{ secrets.TICK_URL }}",
        "TICK_SECRET": "${{ secrets.TICK_SECRET }}",
    }
    script = step["run"]
    assert 'if [ -z "$TICK_URL" ] || [ -z "$TICK_SECRET" ]' in script and "exit 0" in script
    assert "${{" not in script  # secrets reach the script as env vars, never inlined
    assert wf[True]["schedule"][0]["cron"].endswith("* * * *")  # hourly (yaml reads `on` as True)
