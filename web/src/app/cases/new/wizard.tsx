"use client";
import { ArrowLeft, ArrowRight, Check, FileUp, Loader2, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AgentProgress, lastEventId } from "@/components/agent-progress";
import { CaseChip, PackBadge } from "@/components/case-bits";
import { FactChip, useFactLabel } from "@/components/fact-chip";
import { CountryPicker, LanguagePicker } from "@/components/pickers";
import { QuestionsForm } from "@/components/questions-form";
import { ErrorState, PageSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FieldHint, Input, Label, Textarea } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { displayFact } from "@/lib/facts";
import type { CaseDetail, Country, Evidence } from "@/lib/types";
import { useAction, useApi } from "@/lib/use-api";
import { useLetterLanguages } from "@/lib/letter-languages";
import { cn } from "@/lib/utils";

const STEPS = ["where", "what", "evidence", "missing", "review"] as const;
type Step = (typeof STEPS)[number];

function Stepper({ current }: { current: Step }) {
  const t = useTranslations("wizard.steps");
  const idx = STEPS.indexOf(current);
  return (
    <ol className="grid grid-cols-5 gap-1.5" aria-label={t("label")}>
      {STEPS.map((s, i) => (
        <li key={s} aria-current={i === idx ? "step" : undefined} className="min-w-0">
          <div className={cn("h-1.5 rounded-full", i < idx ? "bg-ink" : i === idx ? "bg-lime ring-1 ring-ink dark:ring-lime" : "bg-line")} />
          <p className={cn("mt-1.5 truncate text-[0.6875rem] font-semibold sm:text-xs", i === idx ? "text-text" : "text-muted")}>
            <span className="label-mono me-1">{i + 1}</span>
            {t(s)}
          </p>
        </li>
      ))}
    </ol>
  );
}

export function Wizard() {
  const t = useTranslations("wizard");
  const ui = useLocale();
  const router = useRouter();
  const params = useSearchParams();
  const label = useFactLabel();
  const countries = useApi(() => api.countries(), []);
  const letterLanguages = useLetterLanguages();
  const settings = useApi(() => api.settings(), []);

  const [step, setStep] = useState<Step>("where");
  const [country, setCountry] = useState("");
  const [region, setRegion] = useState("");
  const [language, setLanguage] = useState("");
  const [description, setDescription] = useState("");
  const [company, setCompany] = useState("");
  const [c, setCase] = useState<CaseDetail | null>(null);
  const [files, setFiles] = useState<Evidence[]>([]);
  const [running, setRunning] = useState(false);
  const [since, setSince] = useState(0);
  const action = useAction();

  // Defaults from Settings; the user can change everything.
  useEffect(() => {
    if (!settings.data) return;
    /* eslint-disable react-hooks/set-state-in-effect */
    setCountry((v) => v || settings.data?.default_country || "");
    setLanguage((v) => v || settings.data?.default_language || ui);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [settings.data, ui]);

  const goFor = useCallback((detail: CaseDetail) => {
    if (detail.waiting_for === "urgent_checklist") return "urgent";
    if (detail.waiting_for === "questions") return "missing";
    if (detail.waiting_for) return "review";
    return "evidence";
  }, []);

  // Resume an unfinished case: /cases/new?case=12
  const resumeId = Number(params.get("case")) || null;
  useEffect(() => {
    if (!resumeId) return;
    api
      .getCase(resumeId)
      .then((d) => {
        setCase(d);
        setFiles(d.evidence);
        setCountry(d.country ?? "");
        setLanguage(d.language);
        const next = goFor(d);
        if (next === "urgent") router.replace(`/cases/${d.id}/urgent`);
        else setStep(next as Step);
      })
      .catch(() => undefined);
  }, [resumeId, goFor, router]);

  const selected: Country | undefined = countries.data?.find((x) => x.code === country);
  const regionOk = !region || /^[A-Za-z]{2}-[A-Za-z0-9]{1,3}$/.test(region);

  async function createCase() {
    const created = await action.run(() =>
      api.createCase({
        description,
        country: country || undefined,
        region: region ? region.toUpperCase() : undefined,
        language: letterLanguages.length > 1 ? language || undefined : undefined, // API default
        company: company || undefined,
      }),
    );
    if (created) {
      setCase(created);
      router.replace(`/cases/new?case=${created.id}`, { scroll: false });
      setStep("evidence");
    }
  }

  async function upload(list: FileList | null) {
    if (!c || !list) return;
    for (const f of Array.from(list)) {
      const ev = await action.run(() => api.uploadEvidence(c.id, f));
      if (ev) setFiles((prev) => [...prev, ev]);
    }
  }

  async function runAgent(fn: () => Promise<unknown>) {
    if (!c) return;
    setSince(await lastEventId(c.id));
    setRunning(true);
    const ok = await action.run(fn);
    setRunning(false);
    const detail = await api.getCase(c.id).catch(() => null);
    if (detail) setCase(detail);
    if (ok && detail) {
      const next = goFor(detail);
      if (next === "urgent") router.push(`/cases/${detail.id}/urgent`);
      else setStep(next as Step);
    }
  }

  const start = () =>
    runAgent(async () => {
      try {
        return await api.start(c!.id);
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) return api.retry(c!.id);
        throw e;
      }
    });

  const facts = useMemo(() => {
    if (!c) return [];
    const names = new Map(c.evidence.map((e) => [e.id, e.filename]));
    return c.facts.map((f) => ({ ...f, file: f.source_evidence_id ? names.get(f.source_evidence_id) : null }));
  }, [c]);

  if (countries.loading && !countries.data) return <PageSkeleton />;
  if (countries.error) return <ErrorState error={countries.error} onRetry={countries.reload} />;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <p className="label-mono text-muted">{t("eyebrow")}</p>
        <h1 className="mt-1 font-display text-3xl">{t(`titles.${step}`)}</h1>
        <p className="mt-1 text-text-2">{t(`intros.${step}`)}</p>
      </div>
      <Stepper current={step} />
      {c && <CaseChip country={c.country} region={c.region} currency={c.currency} language={c.language} />}

      {action.error && !running && <ErrorState error={action.error} onRetry={step === "evidence" ? start : undefined} />}

      {step === "where" && (
        <Card>
          <CardContent className="space-y-6">
            <CountryPicker countries={countries.data ?? []} value={country} onChange={setCountry} />
            <div className={cn("grid gap-4", letterLanguages.length > 1 && "sm:grid-cols-2")}>
              <div className="space-y-1.5">
                <Label htmlFor="region">{t("region")}</Label>
                <Input
                  id="region"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  list="region-options"
                  placeholder={selected?.regions[0] ?? t("regionPlaceholder")}
                  aria-invalid={!regionOk}
                  aria-describedby="region-hint"
                  className="font-mono uppercase"
                />
                <datalist id="region-options">
                  {selected?.regions.map((r) => <option key={r} value={r} />)}
                </datalist>
                <FieldHint id="region-hint">{regionOk ? t("regionHint") : t("regionInvalid")}</FieldHint>
              </div>
              {letterLanguages.length > 1 && (
                <div className="space-y-1.5">
                  <LanguagePicker id="letter-language" value={language || ui} onChange={setLanguage} label={t("letterLanguage")} />
                  <FieldHint>{t("letterLanguageHint")}</FieldHint>
                </div>
              )}
            </div>
            <div className="flex justify-end">
              <Button variant="lime" size="lg" disabled={!regionOk} onClick={() => setStep("what")}>
                {t("next")}
                <ArrowRight className="rtl:rotate-180" aria-hidden />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "what" && (
        <Card>
          <CardContent className="space-y-5">
            <div className="space-y-1.5">
              <Label htmlFor="description">{t("description")}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t("descriptionPlaceholder")}
                className="min-h-44"
                aria-describedby="description-hint"
              />
              <FieldHint id="description-hint">{t("descriptionHint")}</FieldHint>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="company">
                {t("company")} <span className="font-normal text-muted">({t("optional")})</span>
              </Label>
              <Input id="company" value={company} onChange={(e) => setCompany(e.target.value)} />
            </div>
            <p className="flex gap-2 rounded-xl bg-warning-bg p-3 text-xs text-warning">
              <ShieldAlert className="size-4 shrink-0" aria-hidden />
              {t("noSecrets")}
            </p>
            <div className="flex justify-between gap-2">
              <Button variant="ghost" onClick={() => setStep("where")}>
                <ArrowLeft className="rtl:rotate-180" aria-hidden />
                {t("back")}
              </Button>
              <Button variant="lime" size="lg" disabled={description.trim().length < 10 || action.busy} onClick={createCase}>
                {action.busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {t("next")}
                <ArrowRight className="rtl:rotate-180" aria-hidden />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "evidence" && c && (
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-4">
              <label
                htmlFor="evidence"
                className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-line bg-raised px-4 py-8 text-center hover:border-muted focus-within:outline-2 focus-within:outline-focus"
              >
                <FileUp className="size-8 text-muted" aria-hidden />
                <span className="font-semibold">{t("dropTitle")}</span>
                <span className="text-xs text-muted">{t("dropHint")}</span>
                <input
                  id="evidence"
                  type="file"
                  multiple
                  className="sr-only"
                  accept="image/*,application/pdf,.eml,.txt"
                  onChange={(e) => upload(e.target.files)}
                />
              </label>
              {files.length > 0 && (
                <ul className="space-y-2" aria-label={t("uploaded")}>
                  {files.map((f) => (
                    <li key={f.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm">
                      <Check className="size-4 text-success" aria-hidden />
                      <span className="font-semibold">{f.filename}</span>
                      <span className="label-mono text-muted">{f.sha256.slice(0, 10)}</span>
                      {f.needs_review && <span className="text-xs text-warning">{t("needsReview")}</span>}
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-muted">{t("encrypted")}</p>
            </CardContent>
          </Card>

          {(running || facts.length > 0) && (
            <div className="grid gap-4 md:grid-cols-[1fr_1.2fr]">
              <AgentProgress caseId={c.id} running={running} since={since} />
              {facts.length > 0 && (
                <div>
                  <h2 className="font-display text-lg">{t("found")}</h2>
                  <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {facts.map((f) => (
                      <FactChip key={f.key} label={label(f.key)} value={displayFact(f)} source={f.file} />
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="lime" size="lg" disabled={files.length === 0 || running} onClick={start} data-testid="read-evidence">
              {running ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {running ? t("reading") : t("readEvidence")}
            </Button>
          </div>
        </div>
      )}

      {step === "missing" && c && (
        <div className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
          <QuestionsForm
            missing={c.pending?.missing ?? []}
            busy={running}
            onSubmit={(a) => runAgent(() => api.answers(c.id, a))}
          />
          <div className="space-y-4">
            {running && <AgentProgress caseId={c.id} running={running} since={since} />}
            {facts.length > 0 && (
              <div>
                <h2 className="font-display text-lg">{t("alreadyKnown")}</h2>
                <ul className="mt-3 grid gap-2">
                  {facts.map((f) => (
                    <FactChip key={f.key} label={label(f.key)} value={displayFact(f)} source={f.file} />
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {step === "review" && c && (
        <Card>
          <CardContent className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <PackBadge generic={c.generic_playbook} />
              <span className="font-mono text-xs text-muted">{c.playbook_id}</span>
            </div>
            {c.generic_playbook && <p className="rounded-xl bg-warning-bg p-3 text-sm text-warning">{t("genericWarning")}</p>}
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="label-mono text-muted">{t("firstStep")}</dt>
                <dd className="mt-0.5 font-semibold">{c.step_name}</dd>
              </div>
              <div>
                <dt className="label-mono text-muted">{t("factsCount")}</dt>
                <dd className="mt-0.5 font-semibold">{c.facts.length}</dd>
              </div>
            </dl>
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {facts.slice(0, 9).map((f) => (
                <FactChip key={f.key} label={label(f.key)} value={displayFact(f)} source={f.file} />
              ))}
            </ul>
            <div className="flex flex-wrap justify-end gap-2">
              <Button asChild>
                <Link href={`/cases/${c.id}`}>{t("openCase")}</Link>
              </Button>
              {c.waiting_for === "approve_draft" && (
                <Button variant="lime" size="lg" asChild>
                  <Link href={`/cases/${c.id}/review`}>
                    {t("reviewDraft")}
                    <ArrowRight className="rtl:rotate-180" aria-hidden />
                  </Link>
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
