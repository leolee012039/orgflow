"use client";

import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { actorName, FIELD_LABELS, money, ruleExpression, STEP_KIND } from "@/lib/format";
import type { Organization, PurchaseRequest, Rule, StepTrace, Trace, Workflow } from "@/lib/types";
import { PrimaryButton } from "./Section";

export const SAMPLE_REQUEST: PurchaseRequest = {
  request_id: "PR-2026-0142",
  requester: "Emma Chen",
  department: "Operations",
  item: "MacBook Pro",
  estimated_cost: 2400,
  business_justification: "Laptop required for a new Product Designer supporting the Operations team.",
};

const PRESET_AMOUNTS = [750, 2400, 8000];

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

const inputClass = "rounded-md border border-line bg-sheet px-3 py-2 text-ink";

function RequestForm({
  org,
  busy,
  onRun,
}: {
  org: Organization;
  busy: boolean;
  onRun: (request: PurchaseRequest) => void;
}) {
  const [request, setRequest] = useState<PurchaseRequest>(SAMPLE_REQUEST);
  const set = (patch: Partial<PurchaseRequest>) => setRequest((r) => ({ ...r, ...patch }));

  function submit(e: FormEvent) {
    e.preventDefault();
    onRun(request);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Field label="Requester">
        {(id) => <input id={id} className={inputClass} value={request.requester} onChange={(e) => set({ requester: e.target.value })} />}
      </Field>
      <Field label="Department">
        {(id) => (
          <select id={id} className={inputClass} value={request.department} onChange={(e) => set({ department: e.target.value })}>
            {org.departments.map((d) => (
              <option key={d.name}>{d.name}</option>
            ))}
          </select>
        )}
      </Field>
      <Field label="Item">
        {(id) => <input id={id} className={inputClass} value={request.item} onChange={(e) => set({ item: e.target.value })} />}
      </Field>
      <Field label="Estimated cost (USD)">
        {(id) => (
          <input
            id={id}
            type="number"
            min={0}
            step={1}
            className={`${inputClass} tabular-nums`}
            value={request.estimated_cost}
            onChange={(e) => set({ estimated_cost: Number(e.target.value) })}
          />
        )}
      </Field>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">Try</span>
        {PRESET_AMOUNTS.map((amount) => (
          <button
            key={amount}
            type="button"
            onClick={() => set({ estimated_cost: amount })}
            aria-pressed={request.estimated_cost === amount}
            className="rounded-full border border-line bg-sheet px-3 py-1 tabular-nums aria-pressed:border-ink"
          >
            {money(amount)}
          </button>
        ))}
      </div>
      <Field label="Business justification">
        {(id) => (
          <textarea
            id={id}
            rows={3}
            className={inputClass}
            value={request.business_justification}
            onChange={(e) => set({ business_justification: e.target.value })}
          />
        )}
      </Field>
      <div>
        <PrimaryButton type="submit" disabled={busy}>
          Run request
        </PrimaryButton>
      </div>
    </form>
  );
}

type Tone = "ok" | "ai" | "muted" | "alert";

function stampFor(step: StepTrace): { text: string; tone: Tone } {
  switch (step.result) {
    case "PASSED":
      return step.type === "ai_review" ? { text: "Checked", tone: "ai" } : { text: "Approved", tone: "ok" };
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

function missingFields(reason: string): string[] {
  const match = reason.match(/Missing required field\(s\): (.+)$/);
  return match ? match[1].split(", ").map((f) => FIELD_LABELS[f] ?? f) : [];
}

function explain(step: StepTrace, workflow: Workflow, rules: Map<string, Rule>, request: PurchaseRequest): string {
  const cost = money(request.estimated_cost);
  if (step.result === "SKIPPED" && step.rule_id && rules.get(step.rule_id)) {
    return `${ruleExpression(rules.get(step.rule_id)!)} is not true for ${cost}.`;
  }
  if (step.result === "RETURNED") {
    const fields = missingFields(step.reason);
    if (fields.length) return `Missing ${fields.join(", ")}. The policy says incomplete requests must not go to approval.`;
  }
  if (step.type === "approval" && step.result === "PASSED") {
    const ruleId = workflow.steps.find((s) => s.id === step.step_id)?.only_if;
    const rule = ruleId ? rules.get(ruleId) : undefined;
    return rule ? `${ruleExpression(rule)} is true for ${cost}. Simulated approval.` : "Simulated approval.";
  }
  if (step.result === "HUMAN_REVIEW" && workflow.unresolved_actors.includes(step.actor)) {
    return `The org chart has no ${step.actor}, so a person picks the approver.`;
  }
  if (step.result === "HUMAN_REVIEW" && step.type === "ai_review") {
    return step.reason
      .replace(/^Gemini review requested human review: /, "Gemini flagged: ")
      .replace(/^fallback check: /, "Checked by code: ");
  }
  if (step.type === "ai_review" && step.result === "PASSED") {
    return step.reason.includes("fallback")
      ? "Required information is present (checked by code because Gemini was unavailable)."
      : "Gemini confirmed the required information is present and meaningful.";
  }
  return step.reason;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function RoutingSlip({
  trace,
  workflow,
  org,
  request,
}: {
  trace: Trace;
  workflow: Workflow;
  org: Organization;
  request: PurchaseRequest;
}) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? trace.steps.length : 0));
  const rules = new Map(workflow.rules.map((r) => [r.id, r]));
  const done = shown >= trace.steps.length;

  useEffect(() => {
    if (shown >= trace.steps.length) return;
    const timer = setTimeout(() => setShown((n) => n + 1), shown === 0 ? 200 : 700);
    return () => clearTimeout(timer);
  }, [shown, trace.steps.length]);

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-md border border-ink bg-sheet">
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink px-5 py-3">
          <h3 className="font-semibold">Routing slip</h3>
          <p className="text-sm text-muted tabular-nums">
            {trace.request_id}, {request.item}, {money(request.estimated_cost)}
          </p>
        </div>
        <ol aria-live="polite">
          {trace.steps.slice(0, shown).map((step) => {
            const wfStep = workflow.steps.find((s) => s.id === step.step_id);
            const stamp = stampFor(step);
            return (
              <li key={step.step_id} className="grid grid-cols-[1fr_auto] items-center gap-4 border-b border-line px-5 py-4 last:border-b-0">
                <div className="flex flex-col gap-1">
                  <p>
                    <span className="font-medium">{wfStep ? actorName(wfStep.actor, org) : "Rules engine"}</span>
                    <span className="ml-2 text-sm text-muted">
                      {wfStep ? STEP_KIND[wfStep.type] : "Submission check"}
                    </span>
                  </p>
                  <p className="text-sm text-muted">{explain(step, workflow, rules, request)}</p>
                </div>
                <span className={`stamp rounded border-2 px-2.5 py-1 text-sm font-semibold whitespace-nowrap ${STAMP_TONE[stamp.tone]}`}>
                  {stamp.text}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
      {done && <Outcome trace={trace} workflow={workflow} org={org} request={request} />}
    </div>
  );
}

function Outcome({ trace, workflow, org, request }: { trace: Trace; workflow: Workflow; org: Organization; request: PurchaseRequest }) {
  const last = trace.steps[trace.steps.length - 1];
  const task = workflow.steps.find((s) => s.type === "task");
  const m = trace.metrics;

  if (trace.status === "COMPLETED") {
    return (
      <div className="flex flex-col gap-2 border-l-4 border-ok pl-4">
        <p className="text-lg font-semibold text-ok">Completed</p>
        <p>
          The request is with {task ? actorName(task.actor, org) : "the next team"}, and {request.requester} has been notified.
        </p>
        <p className="text-muted">
          Before OrgFlow this request changed hands {m.manual_handoffs_before} times by hand. Here people only gave{" "}
          {m.human_approvals} {m.human_approvals === 1 ? "approval" : "approvals"} and Gemini ran {m.ai_checks}{" "}
          {m.ai_checks === 1 ? "check" : "checks"}. Routing, rule checks and handoffs ran on their own.
        </p>
      </div>
    );
  }

  const unresolved = last && workflow.unresolved_actors.includes(last.actor);
  return (
    <div className="flex flex-col gap-2 border-l-4 border-alert pl-4">
      <p className="text-lg font-semibold text-alert">{trace.status === "RETURNED" ? `Returned to ${request.requester}` : "Waiting for a person"}</p>
      <p>
        {trace.status === "RETURNED"
          ? "Nothing was approved. The requester can add the missing information and submit again."
          : unresolved
            ? `The policy requires ${last.actor} approval for ${money(request.estimated_cost)}, and ${org.company}'s org chart has no ${last.actor}. OrgFlow stopped here instead of guessing who should approve.`
            : "Gemini flagged the request details, so a person decides before anyone approves it."}
      </p>
    </div>
  );
}

export function RunPanel({
  org,
  workflow,
  trace,
  runKey,
  lastRequest,
  busy,
  onRun,
}: {
  org: Organization;
  workflow: Workflow;
  trace: Trace | null;
  runKey: number;
  lastRequest: PurchaseRequest | null;
  busy: boolean;
  onRun: (request: PurchaseRequest) => void;
}) {
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <RequestForm org={org} busy={busy} onRun={onRun} />
      <div>
        {trace && lastRequest ? (
          <RoutingSlip key={runKey} trace={trace} workflow={workflow} org={org} request={lastRequest} />
        ) : (
          <div className="rounded-md border border-dashed border-line px-5 py-10 text-muted">
            The routing slip appears here. Each step is stamped as the request moves through the workflow.
          </div>
        )}
      </div>
    </div>
  );
}
