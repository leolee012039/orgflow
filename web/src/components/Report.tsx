"use client";

import { useState, type ReactNode } from "react";
import { summarize, type HealthCheck } from "@/lib/audits";
import { api } from "@/lib/api";
import { currencyOf, money } from "@/lib/format";
import type { PurchaseRequest, Trace } from "@/lib/types";
import { OpportunityList } from "./OpportunityList";
import { OrgView } from "./OrgView";
import { RunPanel } from "./RunPanel";
import { ErrorNote, OriginNote, Tag, Working } from "./Section";
import { Findings, WorkflowView } from "./WorkflowView";

const checkedOn = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

function ReportSection({ title, tags, children, screenOnly }: {
  title: string;
  tags?: ReactNode;
  children: ReactNode;
  screenOnly?: boolean;
}) {
  return (
    <section className={`flex flex-col gap-6 border-t border-line py-10 ${screenOnly ? "print:hidden" : ""}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 break-after-avoid">
        <h2 className="text-2xl font-semibold tracking-tight text-balance">{title}</h2>
        {tags && <div className="flex flex-wrap gap-2">{tags}</div>}
      </div>
      {children}
    </section>
  );
}

type Mark = "pass" | "fail" | "confirm" | "skip";

const MARK: Record<Mark, { symbol: string; label: string; tone: string }> = {
  pass: { symbol: "✓", label: "Passed", tone: "border-ok text-ok" },
  fail: { symbol: "✕", label: "Problem found", tone: "border-alert text-alert" },
  confirm: { symbol: "?", label: "Please confirm", tone: "border-rule text-rule" },
  skip: { symbol: "–", label: "Not checked", tone: "border-line text-muted" },
};

function CheckRow({ mark, check, result }: { mark: Mark; check: string; result: string }) {
  const m = MARK[mark];
  return (
    <li className="grid grid-cols-[1.75rem_1fr] gap-x-4 gap-y-1 border-t border-line py-4 first:border-t-0 sm:grid-cols-[1.75rem_minmax(0,1fr)_minmax(0,16rem)]">
      <span
        role="img"
        aria-label={m.label}
        className={`flex h-7 w-7 items-center justify-center rounded-full border-2 text-sm font-semibold ${m.tone}`}
      >
        {m.symbol}
      </span>
      <p className="font-medium">{check}</p>
      <p className="col-start-2 text-muted sm:col-start-3">{result}</p>
    </li>
  );
}

/** The checks OrgFlow ran, each with its outcome, like an inspection form. */
function CheckList({ check }: { check: HealthCheck }) {
  const { missing, toConfirm, amountGaps } = summarize(check);
  const wf = check.workflow;
  const currency = currencyOf(wf.rules);
  const tiers = wf.amount_tiers ?? [];
  const approverMark: Mark = missing.length ? "fail" : toConfirm.length ? "confirm" : "pass";
  const approverResult = missing.length
    ? `Missing from the org chart: ${missing.map((g) => g.actor).join(", ")}`
    : toConfirm.length
      ? `Not matched to a role: ${toConfirm.map((g) => g.actor).join(", ")}`
      : "All found";
  const amountMark: Mark = amountGaps.length ? "fail" : tiers.length ? "pass" : "skip";
  const amountResult = amountGaps.length
    ? amountGaps.map((f) => `${money(f.amount, currency)} ${f.kind === "gap" ? "has no level" : "is in two levels"}`).join("; ")
    : tiers.length
      ? `${tiers.length} levels, no gaps or overlaps`
      : "The policy's amount levels couldn't be read with confidence";
  return (
    <ul className="rounded-md border border-line bg-sheet px-5">
      <CheckRow mark={approverMark} check="Every approver the policy requires exists in the org chart" result={approverResult} />
      <CheckRow mark={amountMark} check="Every amount falls into exactly one approval level" result={amountResult} />
      <CheckRow
        mark="pass"
        check="Every rule quotes the policy word for word"
        result={`${wf.rules.length} ${wf.rules.length === 1 ? "rule" : "rules"} matched against the PDF`}
      />
    </ul>
  );
}

function Verdict({ check }: { check: HealthCheck }) {
  const { problems, toConfirm } = summarize(check);
  const [text, tone] =
    problems > 0
      ? [`${problems} ${problems === 1 ? "problem" : "problems"}`, "border-alert text-alert"]
      : toConfirm.length > 0
        ? [`${toConfirm.length} to confirm`, "border-rule text-rule"]
        : ["No problems", "border-ok text-ok"];
  return (
    <span className={`stamp inline-block w-fit rounded border-[3px] px-4 py-2 text-xl font-semibold whitespace-nowrap sm:mt-8 ${tone}`}>
      {text}
    </span>
  );
}

/** Try requests against the generated workflow. Screen only. */
function TryRequest({ check }: { check: HealthCheck }) {
  const [trace, setTrace] = useState<Trace | null>(null);
  const [lastRequest, setLastRequest] = useState<PurchaseRequest | null>(null);
  const [runKey, setRunKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const top = check.opportunities.opportunities.find((o) => o.executable);

  async function run(request: PurchaseRequest) {
    setBusy(true);
    setError(null);
    setLastRequest(request);
    try {
      setTrace(await api.run(check.workflow, check.organization, request, top?.manual_handoffs ?? 4));
      setRunKey((k) => k + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-prose text-lg leading-relaxed">
        Submit a purchase request. The rules engine walks it through the workflow; Gemini only checks that the required
        information makes sense.
      </p>
      {error && <ErrorNote message={error} />}
      {busy && <Working label="Running the request" />}
      <RunPanel
        org={check.organization}
        workflow={check.workflow}
        boundaries={(check.workflow.amount_gaps ?? []).map((g) => g.amount)}
        trace={trace}
        runKey={runKey}
        lastRequest={lastRequest}
        busy={busy}
        onRun={run}
      />
    </div>
  );
}

/** A policy health check: findings first, then the evidence and the workflow that can run. */
export function Report({ check, actions }: { check: HealthCheck; actions?: ReactNode }) {
  const { problems, toConfirm, missing, amountGaps } = summarize(check);
  const wf = check.workflow;
  return (
    <article className="flex flex-col">
      <header className="flex flex-col gap-6 pb-10">
        <div className="grid items-start gap-6 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="flex min-w-0 flex-col gap-2">
            <p className="text-muted">Policy health check, {checkedOn(check.checkedAt)}</p>
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">{check.company}</h1>
            <p className="text-sm text-muted break-words">
              Read from {check.documents.orgChart} and {check.documents.policy}
              {check.sample ? ". NovaGear is a fictional sample company." : ""}
            </p>
          </div>
          <Verdict check={check} />
        </div>
        {actions && <div className="print:hidden">{actions}</div>}
        <CheckList check={check} />
      </header>

      {problems + toConfirm.length > 0 && (
        <ReportSection title={problems > 0 ? "Where the policy can't run as written" : "What to confirm"} tags={<Tag kind="rules" />}>
          <p className="max-w-prose text-lg leading-relaxed">
            {problems > 0
              ? `${problems === 1 ? "This is" : "These are"} where a request would get stuck today. Each comes with the lines that prove it.`
              : "OrgFlow couldn't match these approvers to a role. A person should confirm who they are."}
          </p>
          <Findings
            workflow={wf}
            gaps={[...missing, ...toConfirm]}
            amountGaps={amountGaps}
            org={check.organization}
          />
        </ReportSection>
      )}

      <ReportSection title={`How ${check.company} is organized`} tags={<Tag kind="gemini" />}>
        <OrgView org={check.organization} />
        <OriginNote origin={check.organization.origin} latencyMs={check.organization.latency_ms} />
      </ReportSection>

      <ReportSection title="What could be automated" tags={<Tag kind="gemini" />}>
        <OpportunityList opportunities={check.opportunities.opportunities} />
        <OriginNote origin={check.opportunities.origin} latencyMs={check.opportunities.latency_ms} />
      </ReportSection>

      <ReportSection title={wf.workflow_name} tags={<><Tag kind="gemini" /><Tag kind="rules" /></>}>
        <WorkflowView workflow={wf} gaps={wf.gaps ?? []} org={check.organization} />
        <OriginNote origin={wf.origin} latencyMs={wf.latency_ms} />
      </ReportSection>

      <ReportSection title="Try a request" tags={<><Tag kind="rules" /><Tag kind="gemini" /></>} screenOnly>
        <TryRequest check={check} />
      </ReportSection>

      <footer className="border-t border-line pt-6 text-sm text-muted">
        Gemini read the documents and designed the workflow. Code matched every quote against the PDFs and found the
        problems listed above. The PDFs themselves are not saved.
      </footer>
    </article>
  );
}
