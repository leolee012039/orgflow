"use client";

import { useEffect, useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { api } from "@/lib/api";
import { activeDecisions, useDecisions } from "@/lib/decisions";
import { chainFrom, orderedBuilt, startPoints } from "@/lib/chain";
import { actorName, fieldLabel, fieldsOf, formatValue, ruleExpression, STEP_KIND, tryValues } from "@/lib/format";
import type {
  BuiltWorkflow,
  CaseRecord,
  CaseRequest,
  ChainTrace,
  FormField,
  Organization,
  StepTrace,
  Workflow,
  WorkflowCandidate,
} from "@/lib/types";
import { ErrorNote, PrimaryButton, primaryClass, Working } from "./Section";

// Example answers for fields the NovaGear sample uses; other fields start empty
const EXAMPLES: Record<string, string> = {
  item: "MacBook Pro",
  requested_item: "MacBook Pro",
  business_justification: "Laptop required for a new product designer joining the team.",
  customer: "Acme Retail",
  product: "Wireless headset",
  reason: "Annual renewal for a key account that orders every quarter.",
};

const inputClass = "w-full rounded-lg border border-line bg-sheet px-3 py-2 text-ink shadow-[0_1px_2px_rgb(22_26_35/0.04)] focus:border-ai focus:ring-4 focus:ring-ai/15 focus:outline-none";

function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children(id)}
    </div>
  );
}

/** Example answers: "workflow id.field" first, then the field name, then the NovaGear sample's */
export type Examples = Record<string, string>;

/** An example date for a date field, YYYY-MM-DD: two weeks ahead for one that looks forward (a delivery, a start, a
 * deadline), today for the rest (an invoice, a payment, an inspection) */
function exampleDate(field: FormField): string {
  const ahead = /deliver|due|start|deadline|期限|納期|기한|마감|tenggat|jatuh/i.test(`${field.name} ${field.label}`);
  const day = new Date(Date.now() + (ahead ? 14 : 0) * 86_400_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

function initialCase(wf: Workflow, start: WorkflowCandidate, gaps: number[], examples?: Examples): CaseRequest {
  const requester = examples?.requester ?? "Emma Chen";
  const values: CaseRequest = { request_id: "CASE-0001", requester, department: start.department };
  for (const f of fieldsOf(wf)) {
    const example = examples?.[`${wf.opportunity_id}.${f.name}`] ?? examples?.[f.name] ?? EXAMPLES[f.name];
    if (f.type === "number") {
      const tries = tryValues(wf, f.name, gaps);
      values[f.name] = tries[Math.min(1, tries.length - 1)] ?? 1000;
    } else if (f.type === "choice") values[f.name] = f.options[0] ?? "";
    else if (f.type === "date") values[f.name] = example ?? exampleDate(f);
    else values[f.name] = example ?? "";
  }
  return values;
}

function CaseForm({
  wf,
  start,
  org,
  busy,
  initial,
  examples,
  onRun,
}: {
  wf: BuiltWorkflow;
  start: WorkflowCandidate;
  org: Organization;
  busy: boolean;
  /** The last case's request, so coming back to Cases keeps what was typed */
  initial?: CaseRequest;
  /** A sample company's example answers, in its own language */
  examples?: Examples;
  onRun: (request: CaseRequest) => void;
}) {
  const gapsFor = (field: string) => (wf.amount_gaps ?? []).filter((g) => g.field === field).map((g) => g.amount);
  const [values, setValues] = useState<CaseRequest>(
    () => initial ?? initialCase(wf, start, gapsFor("estimated_cost"), examples),
  );
  const set = (name: string, value: string | number) => setValues((v) => ({ ...v, [name]: value }));
  const longText = (f: FormField) => /justification|reason|description|purpose/i.test(f.name);

  function submit(e: FormEvent) {
    e.preventDefault();
    onRun(values);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Field label="Requester">
        {(id) => <input id={id} className={inputClass} value={values.requester} onChange={(e) => set("requester", e.target.value)} />}
      </Field>
      <Field label="Department">
        {(id) => (
          <select id={id} className={inputClass} value={values.department} onChange={(e) => set("department", e.target.value)}>
            {org.departments.map((d) => (
              <option key={d.name}>{d.name}</option>
            ))}
          </select>
        )}
      </Field>
      {fieldsOf(wf).map((f) => (
        <Field key={f.name} label={f.label}>
          {(id) =>
            f.type === "number" ? (
              <div className="flex flex-col gap-2">
                <input
                  id={id}
                  type="number"
                  min={0}
                  step="any"
                  className={`${inputClass} tabular-nums`}
                  value={values[f.name] ?? ""}
                  // Blank stays blank, not 0: the case is then returned for the missing amount
                  onChange={(e) => set(f.name, e.target.value === "" ? "" : Number(e.target.value))}
                />
                {tryValues(wf, f.name, gapsFor(f.name)).length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-muted">Try</span>
                    {tryValues(wf, f.name, gapsFor(f.name)).map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => set(f.name, n)}
                        aria-pressed={values[f.name] === n}
                        className="rounded-full border border-line bg-sheet px-3 py-1 tabular-nums hover:border-faint aria-pressed:border-ai aria-pressed:bg-ai-soft aria-pressed:text-ai"
                      >
                        {formatValue(wf, f.name, n)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : f.type === "choice" ? (
              <select id={id} className={inputClass} value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}>
                {f.options.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            ) : longText(f) ? (
              <textarea id={id} rows={3} className={inputClass} value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)} />
            ) : (
              <input
                id={id}
                type={f.type === "date" ? "date" : "text"}
                className={inputClass}
                value={String(values[f.name] ?? "")}
                onChange={(e) => set(f.name, e.target.value)}
              />
            )
          }
        </Field>
      ))}
      <div>
        <PrimaryButton type="submit" disabled={busy}>
          Run this case
        </PrimaryButton>
      </div>
    </form>
  );
}

type Tone = "ok" | "ai" | "muted" | "alert";

/** An AI check plain code made instead of Gemini: no Gemini review for this case, or Gemini didn't answer */
const byCode = (step: StepTrace) => /^(fallback check|Completeness verified by fallback|Checked by code)/.test(step.reason);

function stampFor(step: StepTrace): { text: string; tone: Tone } {
  switch (step.result) {
    case "PASSED":
      if (step.type !== "ai_review") return { text: "Approved", tone: "ok" };
      // Gemini's check is blue; a check plain code made instead says so
      return byCode(step) ? { text: "Checked by code", tone: "ok" } : { text: "Checked", tone: "ai" };
    case "DONE":
      return { text: "Done", tone: "ok" };
    case "SKIPPED":
      return { text: "Not required", tone: "muted" };
    case "RETURNED":
      return { text: "Returned", tone: "alert" };
    case "HUMAN_REVIEW":
      return { text: "Needs a person", tone: "alert" };
  }
}

const STAMP_TONE: Record<Tone, string> = {
  ok: "border-ok text-ok",
  ai: "border-ai text-ai",
  muted: "border-dashed border-muted text-muted",
  alert: "border-alert text-alert",
};

function explain(step: StepTrace, wf: BuiltWorkflow, request: CaseRequest): string {
  const rules = new Map(wf.rules.map((r) => [r.id, r]));
  const rule = step.rule_id ? rules.get(step.rule_id) : undefined;
  if (step.result === "SKIPPED" && rule) {
    return `${ruleExpression(rule, wf)} is not true for ${formatValue(wf, rule.when.field, request[rule.when.field])}.`;
  }
  if (step.result === "RETURNED") {
    const match = step.reason.match(/Missing required field\(s\): (.+)$/);
    if (match) return `Missing ${match[1].split(", ").map((f) => fieldLabel(wf, f)).join(", ")}. Incomplete requests don't go to approval.`;
  }
  if (step.step_id === "amount_check") {
    const hit = (wf.amount_gaps ?? []).find((g) => Number(request[g.field]) === g.amount);
    if (!hit) return step.reason.replace(/ → human review$/, ".");
    const value = formatValue(wf, hit.field, hit.amount);
    return hit.kind === "gap"
      ? `No approval level in the policy covers exactly ${value}.`
      : hit.kind === "overlap"
        ? `Two approval levels in the policy both cover exactly ${value}.`
        : `The policy's wording doesn't say which approval level covers exactly ${value}.`;
  }
  if (step.step_id.startsWith("amount_decision")) {
    const hit = (wf.amount_gaps ?? []).find((g) => Number(request[g.field]) === g.amount);
    const value = hit ? formatValue(wf, hit.field, hit.amount) : "this amount";
    return `By your decision, exactly ${value} goes to the level “${step.source ?? ""}”.`;
  }
  if (step.type === "approval" && step.result === "PASSED") {
    const wfStep = wf.steps.find((s) => s.id === step.step_id);
    const conditions = [wfStep?.only_if, wfStep?.also_if].map((id) => (id ? rules.get(id) : undefined)).filter(Boolean);
    const standIn = step.stands_in_for ? `Approves in place of ${step.stands_in_for}, by your decision. ` : "";
    return conditions.length
      ? `${standIn}${conditions.map((r) => ruleExpression(r!, wf)).join(" and ")} is true. Simulated approval.`
      : `${standIn}Simulated approval.`;
  }
  if (step.result === "HUMAN_REVIEW" && wf.unresolved_actors.includes(step.actor)) {
    return `The org chart has no ${step.actor}, so a person picks the approver.`;
  }
  if (step.result === "HUMAN_REVIEW" && step.type === "ai_review") {
    return step.reason.replace(/^Gemini review requested human review: /, "Gemini flagged: ").replace(/^fallback check: /, "Checked by code: ");
  }
  if (step.type === "ai_review" && step.result === "PASSED") {
    return byCode(step)
      ? "Required information is present. Plain code checked it: Gemini didn't review this case."
      : "Gemini confirmed the required information is present and meaningful.";
  }
  return step.reason;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** One routing slip that crosses departments, stamped step by step (or all at once for a past case). */
export function ChainSlip({
  trace,
  built,
  org,
  request,
  animate = true,
  onResolve,
}: {
  trace: ChainTrace;
  built: BuiltWorkflow[];
  org: Organization;
  request: CaseRequest;
  animate?: boolean;
  onResolve?: (workflowId: string) => void;
}) {
  const total = trace.legs.reduce((n, leg) => n + leg.trace.steps.length, 0);
  const [shown, setShown] = useState(() => (!animate || prefersReducedMotion() ? total : 0));
  const done = shown >= total;
  useEffect(() => {
    if (shown >= total) return;
    const timer = setTimeout(() => setShown((n) => n + 1), shown === 0 ? 200 : 550);
    return () => clearTimeout(timer);
  }, [shown, total]);

  // Where each department's steps begin in the one stamping sequence
  const offsets = trace.legs.map((_, i) => trace.legs.slice(0, i).reduce((n, l) => n + l.trace.steps.length, 0));
  return (
    <div className="flex flex-col gap-6">
      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
          <h3 className="font-semibold">Routing slip</h3>
          <p className="text-sm text-muted tabular-nums">
            {trace.request_id}, {trace.legs.map((l) => l.department).join(" → ")}
          </p>
        </div>
        <ol aria-live="polite">
          {trace.legs.map((leg, i) => {
            const wf = built.find((w) => w.opportunity_id === leg.workflow_id);
            if (!wf) return null; // the workflow was rebuilt or removed since this case ran
            const visible = leg.trace.steps.slice(0, Math.max(0, shown - offsets[i]));
            if (visible.length === 0) return null;
            return (
              <li key={leg.workflow_id} className="border-b border-line last:border-b-0">
                <p className="flex items-center gap-2 bg-paper px-5 py-2 text-sm">
                  <span className="font-semibold">{leg.department}</span>
                  <span className="ml-2 text-muted">{leg.workflow_name}</span>
                </p>
                <ol>
                  {visible.map((step) => {
                    const wfStep = wf.steps.find((s) => s.id === step.step_id);
                    const stamp = stampFor(step);
                    return (
                      <li key={step.step_id} className="grid grid-cols-[1fr_auto] items-center gap-4 border-t border-line px-5 py-3">
                        <div className="flex flex-col gap-1">
                          <p>
                            <span className="font-medium">
                              {step.stands_in_for
                                ? actorName(step.actor, org)
                                : wfStep
                                  ? actorName(wfStep.actor, org)
                                  : "Rules engine"}
                            </span>
                            <span className="ml-2 text-sm text-muted">
                              {wfStep
                                ? STEP_KIND[wfStep.type]
                                : step.step_id === "amount_check"
                                  ? "Amount check"
                                  : step.step_id.startsWith("amount_decision")
                                    ? "Your decision"
                                    : "Submission check"}
                            </span>
                          </p>
                          <p className="text-sm text-muted">{explain(step, wf, request)}</p>
                        </div>
                        <span className={`stamp rounded border-2 px-2.5 py-1 text-sm font-semibold whitespace-nowrap ${STAMP_TONE[stamp.tone]}`}>
                          {stamp.text}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              </li>
            );
          })}
        </ol>
      </div>
      {done && <ChainOutcome trace={trace} built={built} org={org} request={request} onResolve={onResolve} />}
    </div>
  );
}

/** A finished case in one line, for the case list. needsDecision: it stopped where the documents leave something
 * open, so it goes on once that is decided; a case returned for missing information or flagged by the check doesn't */
export function caseResult(trace: ChainTrace, built: BuiltWorkflow[]): { ok: boolean; text: string; needsDecision: boolean } {
  if (trace.status === "COMPLETED") {
    const n = trace.legs.length;
    return {
      ok: true,
      text: `Completed in ${n} ${n === 1 ? "department" : "departments"}${trace.waiting_for ? `, ready for ${trace.waiting_for}` : ""}`,
      needsDecision: false,
    };
  }
  const last = trace.legs[trace.legs.length - 1];
  const step = last?.trace.steps[last.trace.steps.length - 1];
  const wf = built.find((w) => w.opportunity_id === last?.workflow_id);
  if (trace.status === "RETURNED") return { ok: false, text: `Returned in ${last.department}: information missing`, needsDecision: false };
  if (step?.step_id === "amount_check")
    return { ok: false, text: `Stopped in ${last.department}: the policy doesn't settle this exact amount`, needsDecision: true };
  if (wf?.unresolved_actors.includes(step?.actor ?? ""))
    return { ok: false, text: `Stopped in ${last.department}: no ${step.actor} in the org chart`, needsDecision: true };
  return { ok: false, text: `Stopped in ${last.department}: flagged for a person`, needsDecision: false };
}

function ChainOutcome({
  trace,
  built,
  org,
  request,
  onResolve,
}: {
  trace: ChainTrace;
  built: BuiltWorkflow[];
  org: Organization;
  request: CaseRequest;
  onResolve?: (workflowId: string) => void;
}) {
  const { decide } = useDecisions();
  const departments = trace.legs.map((l) => l.department);
  const followed = trace.legs.reduce(
    (n, l) =>
      n +
      l.trace.steps.filter(
        (s) => (s.stands_in_for && (s.result === "PASSED" || s.result === "DONE")) || s.step_id.startsWith("amount_decision"),
      ).length,
    0,
  );
  const approvals = trace.legs.reduce((n, l) => n + l.trace.metrics.human_approvals, 0);
  const checks = trace.legs.reduce((n, l) => n + l.trace.metrics.ai_checks, 0);
  const codeChecks = trace.legs.reduce((n, l) => n + (l.trace.metrics.code_checks ?? 0), 0);
  const handoffs = trace.legs.reduce((n, l) => n + l.trace.metrics.manual_handoffs_before, 0);
  if (trace.status === "COMPLETED") {
    return (
      <div className="flex flex-col gap-2 rounded-xl border border-ok/20 bg-ok-soft px-5 py-4">
        <p className="text-lg font-semibold text-ok">
          Completed in {departments.length} {departments.length === 1 ? "department" : "departments"}
        </p>
        <p>
          The case moved {departments.join(" → ")} on its own.{" "}
          {trace.waiting_for ? `It is ready for ${trace.waiting_for}, which has no workflow built yet.` : `${request.requester} has been notified.`}
        </p>
        <p className="text-muted">
          People gave {approvals} {approvals === 1 ? "approval" : "approvals"} and Gemini ran {checks} {checks === 1 ? "check" : "checks"}
          {codeChecks > 0 ? `; plain code made ${codeChecks} more ${codeChecks === 1 ? "check" : "checks"}` : ""}.
          {handoffs > 0 ? ` By hand, this work changes hands ${handoffs} times today.` : ""}
        </p>
        {followed > 0 && (
          <p className="text-muted">
            It followed {followed === 1 ? "one of your decisions" : `${followed} of your decisions`} where the documents
            leave the approver open.
          </p>
        )}
      </div>
    );
  }
  const last = trace.legs[trace.legs.length - 1];
  const lastStep = last.trace.steps[last.trace.steps.length - 1];
  const wf = built.find((w) => w.opportunity_id === last.workflow_id);
  const needsDecision =
    trace.status === "NEEDS_HUMAN_REVIEW" &&
    (lastStep?.step_id === "amount_check" || Boolean(wf?.unresolved_actors.includes(lastStep?.actor ?? "")));
  const why =
    trace.status === "RETURNED"
      ? "Nothing was approved. The requester can add the missing information and submit again."
      : lastStep?.step_id === "amount_check"
        ? `${org.company}'s policy doesn't settle who approves this exact amount, so OrgFlow stopped before any approval.`
        : wf?.unresolved_actors.includes(lastStep?.actor ?? "")
          ? `The policy requires ${lastStep.actor} approval, and ${org.company}'s org chart has no ${lastStep.actor}. OrgFlow stopped instead of guessing.`
          : "Gemini flagged the request details, so a person decides before anyone approves it.";
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-alert/20 bg-alert-soft px-5 py-4">
      <p className="text-lg font-semibold text-alert">
        {trace.status === "RETURNED" ? `Returned to ${request.requester}` : `Waiting for a person in ${last.department}`}
      </p>
      <p>{why}</p>
      {needsDecision && decide && onResolve && (
        <div className="pt-1">
          <button type="button" onClick={() => onResolve(last.workflow_id)} className={primaryClass}>
            Decide who approves
          </button>
          <p className="mt-2 text-sm text-muted">Decide once, and every case like this one runs through.</p>
        </div>
      )}
    </div>
  );
}

/** Run a case from one department's workflow through every department it hands to. */
export function CaseRun({
  plan,
  built,
  org,
  nextNumber = 1,
  lastCase,
  examples,
  onCase,
  onResolve,
}: {
  plan: WorkflowCandidate[];
  built: Record<string, BuiltWorkflow>;
  org: Organization;
  /** The number the next case gets: CASE-0001, CASE-0002 ... */
  nextNumber?: number;
  /** The latest case: shown again when the page comes back, for instance after a decision */
  lastCase?: CaseRecord;
  /** A sample company's example answers for its forms */
  examples?: Examples;
  onCase?: (record: CaseRecord) => void;
  onResolve?: (workflowId: string) => void;
}) {
  const { decisions } = useDecisions();
  const starts = useMemo(() => startPoints(plan, built), [plan, built]);
  const builtList = useMemo(() => orderedBuilt(plan, built), [plan, built]);
  const lastHere = lastCase && starts.some((s) => s.id === lastCase.startId) ? lastCase : undefined;
  const [startId, setStartId] = useState<string | null>(lastHere?.startId ?? null);
  const start = starts.find((s) => s.id === startId) ?? starts[0];
  const [trace, setTrace] = useState<ChainTrace | null>(lastHere?.trace ?? null);
  const [lastRequest, setLastRequest] = useState<CaseRequest | null>(lastHere?.request ?? null);
  const [restored, setRestored] = useState(Boolean(lastHere)); // a slip shown again isn't stamped again
  const [runKey, setRunKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!start) return null;
  const wf = built[start.id];
  const path = chainFrom(wf, builtList);
  const last = path[path.length - 1];
  const handoffsBefore = Object.fromEntries(plan.map((c) => [c.id, c.manual_handoffs]));

  async function run(form: CaseRequest) {
    const request = { ...form, request_id: `CASE-${String(nextNumber).padStart(4, "0")}` };
    setBusy(true);
    setError(null);
    setTrace(null); // the last case's slip would read as this one's answer
    setLastRequest(request);
    try {
      const result = await api.runChain(builtList, org, start.id, request, handoffsBefore, activeDecisions(decisions, builtList));
      setTrace(result);
      setRestored(false);
      setRunKey((k) => k + 1);
      onCase?.({ id: request.request_id, at: new Date().toISOString(), startId: start.id, request, trace: result });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {starts.length > 1 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Where the case starts">
          {starts.map((s) => (
            <button
              key={s.id}
              type="button"
              aria-pressed={s.id === start.id}
              onClick={() => {
                setStartId(s.id);
                setTrace(null);
                setLastRequest(null);
              }}
              className="rounded-lg border border-line bg-sheet px-3 py-2 text-left text-sm shadow-[0_1px_2px_rgb(22_26_35/0.04)] hover:border-faint aria-pressed:border-ai aria-pressed:bg-ai-soft aria-pressed:font-medium aria-pressed:text-ai"
            >
              {s.department}: {s.name}
            </button>
          ))}
        </div>
      )}
      <p className="max-w-prose text-lg leading-relaxed">
        This case starts in {start.department} and goes {path.map((w) => w.department).join(" → ")}
        {last.hands_to && !path.some((w) => w.department === last.hands_to)
          ? `, then waits for ${last.hands_to}, which has no workflow built yet`
          : ""}
        . Plain code moves it along; Gemini only checks that the required information makes sense.
      </p>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <CaseForm
          key={start.id}
          wf={wf}
          start={start}
          org={org}
          busy={busy}
          initial={lastRequest && lastHere?.startId === start.id ? lastRequest : undefined}
          examples={examples}
          onRun={run}
        />
        <div className="flex flex-col gap-4">
          {error && <ErrorNote message={error} />}
          {busy && <Working label="Running the case" />}
          {trace && lastRequest && !busy && caseResult(trace, builtList).needsDecision && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-sheet px-4 py-3">
              <span className="flex-1 text-sm text-muted">
                {restored ? `${lastRequest.request_id} stopped here.` : "This case stopped."} Once you decide what the documents leave open, run it again
                to see where it goes now.
              </span>
              <PrimaryButton onClick={() => run(lastRequest)}>Run it again</PrimaryButton>
            </div>
          )}
          {trace && lastRequest ? (
            <ChainSlip
              key={runKey}
              trace={trace}
              built={builtList}
              org={org}
              request={lastRequest}
              animate={!restored}
              onResolve={onResolve}
            />
          ) : (
            !busy && (
              <div className="rounded-xl border border-dashed border-faint/50 bg-sheet/60 px-5 py-10 text-muted">
                The routing slip appears here. Each department stamps its steps as the case moves through.
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
