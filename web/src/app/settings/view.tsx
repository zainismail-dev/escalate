"use client";
import { CheckCircle2, Cpu, Globe2, Loader2, Lock, Mail, Trash2, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { UiLanguageSelect } from "@/components/app-shell";
import { LanguagePicker } from "@/components/pickers";
import { ErrorState, PageSkeleton } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { FieldHint, Input, Label, NativeSelect } from "@/components/ui/input";
import { ENABLED_LOCALES } from "@/i18n/config";
import { api } from "@/lib/api";
import { countryName } from "@/lib/format";
import { HOSTED } from "@/lib/hosted";
import type { Settings } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";
import { AccountSection } from "./account";

/** OpenAI-compatible endpoints (the same ones .env.example lists). Any other URL works too. */
const MODEL_SOURCES = [
  { id: "ollama", url: "http://localhost:11434/v1", cloud: false },
  { id: "groq", url: "https://api.groq.com/openai/v1", cloud: true },
  { id: "gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai/", cloud: true },
  { id: "openrouter", url: "https://openrouter.ai/api/v1", cloud: true },
] as const;

/** Common SMTP servers for app-password sign-in; "other" takes any host and port. */
const MAIL_PROVIDERS = [
  { id: "gmail", host: "smtp.gmail.com", port: 465 },
  { id: "outlook", host: "smtp-mail.outlook.com", port: 587 },
  { id: "yahoo", host: "smtp.mail.yahoo.com", port: 465 },
  { id: "icloud", host: "smtp.mail.me.com", port: 587 },
] as const;

function Saved({ show, warnings = [] }: { show: boolean; warnings?: string[] }) {
  const t = useTranslations("common");
  return show ? (
    <span role="status" className="inline-flex flex-col gap-1 text-xs font-semibold">
      <span className="inline-flex items-center gap-1 text-success">
        <CheckCircle2 className="size-3.5" aria-hidden />
        {t("saved")}
      </span>
      {warnings.map((w) => (
        <span key={w} className="text-warning" data-testid="settings-warning">
          {w}
        </span>
      ))}
    </span>
  ) : null;
}

function ModelSection({ s, onSaved }: { s: Settings; onSaved: (s: Settings) => void }) {
  const t = useTranslations("settings.model");
  const tc = useTranslations("common");
  const [url, setUrl] = useState(s.llm_base_url);
  const [smart, setSmart] = useState(s.model_smart);
  const [fast, setFast] = useState(s.model_fast);
  const [key, setKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [test, setTest] = useState<{ ok: boolean; reply?: string; error?: string } | null>(null);
  const [keyCleared, setKeyCleared] = useState(false);
  const act = useAction();
  const source = MODEL_SOURCES.find((m) => url.startsWith(m.url) || (m.id === "ollama" && url.includes(":11434")))?.id ?? "custom";

  async function save() {
    const body: Record<string, string> = { llm_base_url: url, model_smart: smart, model_fast: fast };
    if (key) body.llm_api_key = key;
    const out = await act.run(() => api.saveSettings(body));
    if (out) {
      onSaved(out);
      setKey("");
      setSaved(true);
      setKeyCleared(!!out.cleared_secrets?.includes("llm_api_key"));
      setWarnings(out.warnings ?? []);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cpu className="size-5" aria-hidden />
          {t("title")}
        </CardTitle>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="model-source">{t("source")}</Label>
          <NativeSelect
            id="model-source"
            value={source}
            onChange={(e) => {
              const m = MODEL_SOURCES.find((x) => x.id === e.target.value);
              if (m) setUrl(m.id === "ollama" && s.llm_base_url.includes(":11434") ? s.llm_base_url : m.url);
              setSaved(false);
            }}
          >
            {MODEL_SOURCES.map((m) => (
              <option key={m.id} value={m.id}>
                {t(`sources.${m.id}`)}
              </option>
            ))}
            <option value="custom">{t("sources.custom")}</option>
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="model-url">{t("url")}</Label>
          <Input
            id="model-url"
            value={url}
            onChange={(e) => (setUrl(e.target.value), setSaved(false))}
            className="font-mono"
            inputMode="url"
            aria-describedby={source === "ollama" ? "model-url-hint" : undefined}
          />
          {source === "ollama" && <FieldHint id="model-url-hint">{t("ollamaHint")}</FieldHint>}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="model-smart">{t("smart")}</Label>
            <Input id="model-smart" value={smart} onChange={(e) => (setSmart(e.target.value), setSaved(false))} className="font-mono" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="model-fast">{t("fast")}</Label>
            <Input id="model-fast" value={fast} onChange={(e) => (setFast(e.target.value), setSaved(false))} className="font-mono" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="model-key">{t("key")}</Label>
          <Input
            id="model-key"
            type="password"
            value={key}
            onChange={(e) => (setKey(e.target.value), setSaved(false))}
            placeholder={s.has_llm_api_key ? t("keySaved") : t("keyNone")}
            autoComplete="off"
          />
          <FieldHint>{t("keyHint")}</FieldHint>
        </div>
        {keyCleared && (
          <p role="status" className="rounded-xl bg-warning-bg p-3 text-sm text-warning" data-testid="key-cleared">
            {t("keyCleared")}
          </p>
        )}
        {s.is_cloud && <p className="rounded-xl bg-warning-bg p-3 text-sm text-warning" data-testid="cloud-warning">{t("cloudWarning")}</p>}
        {act.error && <ErrorState error={act.error} />}
        {test && (
          <p role="status" className={test.ok ? "flex items-center gap-2 text-sm text-success" : "flex items-start gap-2 text-sm text-danger"}>
            {test.ok ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden />}
            <span className="break-all">{test.ok ? t("testOk", { reply: test.reply ?? "" }) : t("testFail", { error: test.error ?? "" })}</span>
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ink" onClick={save} disabled={act.busy}>
            {tc("save")}
          </Button>
          <Button
            onClick={async () => {
              setTest(null);
              const out = await act.run(() => api.testModel());
              if (out) setTest(out);
            }}
            disabled={act.busy}
          >
            {act.busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("test")}
          </Button>
          <Saved show={saved} warnings={warnings} />
        </div>
      </CardContent>
    </Card>
  );
}

function EmailSection({ s, onSaved }: { s: Settings; onSaved: (s: Settings) => void }) {
  const t = useTranslations("settings.email");
  const tc = useTranslations("common");
  const [host, setHost] = useState(s.smtp_host);
  const [port, setPort] = useState(String(s.smtp_port));
  const [user, setUser] = useState(s.smtp_user);
  const [password, setPassword] = useState("");
  const [passwordCleared, setPasswordCleared] = useState(false);
  const [saved, setSaved] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const act = useAction();
  const provider = MAIL_PROVIDERS.find((p) => p.host === host)?.id ?? "other";

  async function save() {
    const body: Record<string, string | number> = { smtp_host: host, smtp_port: Number(port), smtp_user: user };
    if (password) body.smtp_app_password = password.replace(/\s+/g, "");
    const out = await act.run(() => api.saveSettings(body));
    if (out) {
      onSaved(out);
      setPassword("");
      setSaved(true);
      setPasswordCleared(!!out.cleared_secrets?.includes("smtp_app_password"));
      setWarnings(out.warnings ?? []);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="size-5" aria-hidden />
          {t("title")}
        </CardTitle>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {s.demo_mode && <Badge tone="info">{t("demoMode")}</Badge>}
        <div className="space-y-1.5">
          <Label htmlFor="mail-provider">{t("provider")}</Label>
          <NativeSelect
            id="mail-provider"
            value={provider}
            onChange={(e) => {
              const p = MAIL_PROVIDERS.find((x) => x.id === e.target.value);
              if (p) {
                setHost(p.host);
                setPort(String(p.port));
              }
              setSaved(false);
            }}
          >
            {MAIL_PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {t(`providers.${p.id}`)}
              </option>
            ))}
            <option value="other">{t("providers.other")}</option>
          </NativeSelect>
        </div>
        <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
          <div className="space-y-1.5">
            <Label htmlFor="smtp-host">{t("host")}</Label>
            <Input id="smtp-host" value={host} onChange={(e) => (setHost(e.target.value), setSaved(false))} className="font-mono" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="smtp-port">{t("port")}</Label>
            <Input id="smtp-port" value={port} inputMode="numeric" onChange={(e) => (setPort(e.target.value.replace(/\D/g, "")), setSaved(false))} className="font-mono" />
          </div>
        </div>
        <FieldHint>{t("portHint")}</FieldHint>
        <div className="space-y-1.5">
          <Label htmlFor="smtp-user">{t("user")}</Label>
          <Input id="smtp-user" type="email" value={user} onChange={(e) => (setUser(e.target.value), setSaved(false))} autoComplete="email" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="smtp-password">{t("password")}</Label>
          <Input
            id="smtp-password"
            type="password"
            value={password}
            onChange={(e) => (setPassword(e.target.value), setSaved(false))}
            placeholder={s.has_smtp_password ? t("passwordSaved") : t("passwordNone")}
            autoComplete="off"
            aria-describedby="smtp-password-hint"
          />
          <FieldHint id="smtp-password-hint">{t("passwordHint")}</FieldHint>
        </div>
        {passwordCleared && (
          <p role="status" className="rounded-xl bg-warning-bg p-3 text-sm text-warning">
            {t("passwordCleared")}
          </p>
        )}
        {act.error && <ErrorState error={act.error} />}
        <div className="flex items-center gap-2">
          <Button variant="ink" onClick={save} disabled={act.busy || !port}>
            {tc("save")}
          </Button>
          <Saved show={saved} warnings={warnings} />
        </div>
      </CardContent>
    </Card>
  );
}

function RegionSection({ s, onSaved }: { s: Settings; onSaved: (s: Settings) => void }) {
  const t = useTranslations("settings.region");
  const tc = useTranslations("common");
  const ui = useLocale();
  const countries = useApi(() => api.countries(), []);
  const [country, setCountry] = useState(s.default_country ?? "");
  const [language, setLanguage] = useState(s.default_language);
  const [saved, setSaved] = useState(false);
  const act = useAction();
  const sorted = useMemo(
    () =>
      (countries.data ?? [])
        .map((c) => ({ code: c.code, name: countryName(c.code, ui) ?? c.code }))
        .sort((a, b) => a.name.localeCompare(b.name, ui)),
    [countries.data, ui],
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Globe2 className="size-5" aria-hidden />
          {ENABLED_LOCALES.length > 1 || s.enabled_letter_languages.length > 1 ? t("title") : t("titleRegion")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {ENABLED_LOCALES.length > 1 && (
          <div className="space-y-1.5">
            <Label htmlFor="settings-ui-language">{t("appLanguage")}</Label>
            <div>
              <UiLanguageSelect id="settings-ui-language" className="h-10 w-full text-sm" />
            </div>
            <FieldHint>{t("appLanguageHint")}</FieldHint>
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="default-country">{t("country")}</Label>
          <NativeSelect id="default-country" value={country} onChange={(e) => (setCountry(e.target.value), setSaved(false))}>
            <option value="">{t("askEachTime")}</option>
            {sorted.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        {s.enabled_letter_languages.length > 1 && (
          <LanguagePicker id="default-letter-language" value={language} onChange={(v) => (setLanguage(v), setSaved(false))} label={t("letterLanguage")} />
        )}
        {act.error && <ErrorState error={act.error} />}
        <div className="flex items-center gap-2">
          <Button
            variant="ink"
            disabled={act.busy}
            onClick={async () => {
              const body: Record<string, string> = { default_country: country };
              if (s.enabled_letter_languages.length > 1) body.default_language = language;
              const out = await act.run(() => api.saveSettings(body));
              if (out) {
                onSaved(out);
                setSaved(true);
              }
            }}
          >
            {tc("save")}
          </Button>
          <Saved show={saved} />
        </div>
      </CardContent>
    </Card>
  );
}

function PrivacySection({ s }: { s: Settings }) {
  const t = useTranslations("settings.privacy");
  const tc = useTranslations("common");
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  const act = useAction();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Lock className="size-5" aria-hidden />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="space-y-2 text-sm text-text-2">
          {(["local", "encrypted", "masked", "noTracking"] as const).map((k) => (
            <li key={k} className="flex gap-2">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
              {t(k)}
            </li>
          ))}
          <li className="flex gap-2">
            {s.is_cloud ? <XCircle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />}
            {s.is_cloud ? t("cloud") : t("localModel")}
          </li>
        </ul>
        <div className="rounded-xl border border-danger/40 bg-danger-bg p-4">
          <p className="font-semibold text-text">{t("deleteTitle")}</p>
          <p className="mt-1 text-sm text-text-2">{t("deleteBody")}</p>
          <Button variant="danger" className="mt-3" onClick={() => setOpen(true)}>
            <Trash2 aria-hidden />
            {t("deleteCta")}
          </Button>
          {done && <p role="status" className="mt-2 text-sm font-semibold text-success">{t("deleted")}</p>}
        </div>
        <p className="label-mono text-muted">{t("version", { version: s.version })}</p>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent closeLabel={tc("close")}>
          <DialogTitle>{t("confirmTitle")}</DialogTitle>
          <DialogDescription>{t("confirmBody")}</DialogDescription>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={act.busy}
              onClick={async () => {
                // deleteAll returns nothing (204): mark success explicitly, or a failure looks done.
                const ok = await act.run(async () => {
                  await api.deleteAll();
                  return true;
                });
                setOpen(false);
                if (ok) setDone(true);
              }}
            >
              {t("deleteCta")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export function SettingsView() {
  const t = useTranslations("settings");
  const q = useApi(() => api.settings(), []);
  const [s, setS] = useState<Settings | undefined>(undefined);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (q.data) setS(q.data);
  }, [q.data]);
  if (q.loading && !s) return <PageSkeleton />;
  if (q.error && !s) return <ErrorState error={q.error} onRetry={q.reload} />;
  if (!s) return null;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <p className="label-mono text-muted">{t("eyebrow")}</p>
        <h1 className="mt-1 font-display text-3xl">{t("title")}</h1>
        <p className="mt-1 text-text-2">{t("intro")}</p>
      </div>
      {HOSTED ? (
        // Hosted beta: the AI provider and email are the server's; deleting is per account.
        <>
          <RegionSection s={s} onSaved={setS} />
          <AccountSection />
        </>
      ) : (
        <>
          <ModelSection s={s} onSaved={setS} />
          <EmailSection s={s} onSaved={setS} />
          <RegionSection s={s} onSaved={setS} />
          <PrivacySection s={s} />
        </>
      )}
    </div>
  );
}
