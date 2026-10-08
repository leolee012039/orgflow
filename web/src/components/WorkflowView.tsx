"use client";

import { useId, useState } from "react";
import {
  amountDecision,
  approverDecision,
  decidedOn,
  REQUESTER_MANAGER,
  standInName,
  useDecisions,
} from "@/lib/decisions";
import { actorName, fieldsOf, formatValue, ruleExpression, STEP_KIND } from "@/lib/format";
import type { AmountGap, Decision, Gap, Organization, Rule, Workflow } from "@/lib/types";
import { CheckIcon } from "./Icons";
import { Quote } from "./Quote";
import { primaryClass, secondaryClass } from "./Section";

const selectClass =
  "min-w-0 flex-1 rounded-lg border border-line bg-sheet px-3 py-2 text-ink shadow-[0_1px_2px_rgb(22_26_35/0.04)] focus:border-ai focus:ring-4 focus:ring-ai/15 focus:outline-none sm:max-w-xs";

/** A decision someone made: what it settled, when, and a way to change it. */
function Decided({ title, text, at, onChange }: { title: string; text: string; at: string; onChange?: () => void }) {
  return (
    <div className="card flex break-inside-avoid flex-col gap-3 border-l-4 border-l-ok p-5">
      <p className="flex items-center gap-1.5 text-sm font-medium text-ok">
        <CheckIcon width="15" height="15" /> Decided on {decidedOn(at)}
      </p>
      <h3 className="text-xl font-semibold text-balance">{title}</h3>
      <p className="max-w-prose text-muted">{text}</p>
      {onChange && (
        <div className="print:hidden">
          <button type="button" onClick={onChange} className={`${secondaryClass} text-sm`}>
            Change this decision
          </button>
        </div>
      )}
    </div>
  );
}

/** Pick the role that approves in place of an approver the org chart doesn't have. */
function ChooseApprover({
  gap,
  org,
  workflow,
  onDecide,
}: {
  gap: Gap;
  org: Organization;
  workflow: Workflow;
  onDecide: (roleId: string) => void;
}) {
  const id = useId();
  const [roleId, setRoleId] = useState("");
  // Someone who already approves this workflow would sign twice
  const approves = new Set(workflow.steps.filter((s) => s.type === "approval").map((s) => s.actor));
  const already = (roleId: string) => (approves.has(roleId) ? " (already approves here)" : "");
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-paper p-4 print:hidden">
      <label htmlFor={id} className="font-medium">
        Who approves in place of {gap.actor}?
      </label>
      <p className="text-sm text-muted">
        Pick someone your org chart has. OrgFlow records your decision, and every case after this one goes to them.
      </p>
      <div className="flex flex-wrap gap-2">
        <select id={id} value={roleId} onChange={(e) => setRoleId(e.target.value)} className={selectClass}>
          <option value="">Choose a role</option>
          <option value={REQUESTER_MANAGER}>The requester&apos;s department head{already(REQUESTER_MANAGER)}</option>
          {org.roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title}
              {r.department && r.department !== r.title ? `, ${r.department}` : ""}
              {already(r.id)}
            </option>
          ))}
        </select>
        <button type="button" disabled={!roleId} onClick={() => onDecide(roleId)} className={primaryClass}>
          Use this role
        </button>
      </div>
    </div>
  );
}

/** The headline finding: an approver the policy requires that the organization doesn't have. */
function GapCard({ gap, org, rule, workflow }: { gap: Gap; org: Organization; rule?: Rule; workflow: Workflow }) {
  const { decisions, decide, undo } = useDecisions();
  const decision = approverDecision(decisions, workflow.opportunity_id, gap.actor);
  if (decision) {
    const who = standInName(decision.role_id, org);
    return (
      <Decided
        title={`${who.charAt(0).toUpperCase()}${who.slice(1)} approves in place of ${gap.actor}.`}
        text={`The policy requires ${gap.actor} approval, and the org chart has no ${gap.actor}. Cases now go to ${who} at that step. The policy still names ${gap.actor}, so update it when you can.`}
        at={decision.decided_at}
        onChange={undo && (() => undo(decision))}
      />
    );
  }
  const missing = gap.status === "missing";
  const titles = org.roles.map((r) => r.title);
  return (
    <div className={`card flex break-inside-avoid flex-col gap-4 border-l-4 p-5 ${missing ? "border-l-alert" : "border-l-rule"}`}>
      <div className="flex flex-col gap-1">
        <p className={`text-sm font-medium ${missing ? "text-alert" : "text-rule"}`}>
          {missing ? "This workflow can't run as written" : "Please confirm"}
        </p>
        <h3 className="text-xl font-semibold text-balance">
          {missing
            ? `The policy requires ${gap.actor} approval, but the org chart has no ${gap.actor}.`
            : `The policy requires ${gap.actor} approval. The org chart mentions ${gap.actor}, but OrgFlow couldn't match it to a role.`}
        </h3>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">The policy says</p>
          {gap.policy_quote ? <Quote text={gap.policy_quote} doc="policy" /> : <p>{gap.actor} approval is a required step.</p>}
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">The org chart shows</p>
          <p className="leading-relaxed">
            {titles.length} roles: {titles.slice(0, 5).join(", ")}
            {titles.length > 5 ? `, and ${titles.length - 5} more` : ""}.{" "}
            {missing ? `None of them is ${gap.actor}.` : `None of them is clearly ${gap.actor}.`}
          </p>
        </div>
      </div>
      <p className="text-muted">
        {rule
          ? `Requests where ${ruleExpression(rule, workflow)} will stop and wait for a person to name the approver.`
          : "Requests that reach this step will stop and wait for a person to name the approver."}{" "}
        OrgFlow doesn&apos;t guess who should approve.
      </p>
      {decide && (
        <ChooseApprover
          gap={gap}
          org={org}
          workflow={workflow}
          onDecide={(roleId) =>
            decide({
              kind: "approver",
              workflow_id: workflow.opportunity_id,
              actor: gap.actor,
              role_id: roleId,
              decided_at: new Date().toISOString(),
            })
          }
        />
      )}
    </div>
  );
}

const AMOUNT_WORDS: Record<AmountGap["kind"], { headline: (v: string) => string; below: string; above: string; lead: string }> = {
  gap: {
    headline: (v) => `No approval level covers exactly ${v}. One level stops just below it, and the next starts just above it.`,
    below: "This level stops below it",
    above: "The next level starts above it",
    lead: "This workflow can't run as written",
  },
  overlap: {
    headline: (v) => `Two approval levels both cover exactly ${v}, so the policy names two sets of approvers for it.`,
    below: "This level includes it",
    above: "The next level includes it too",
    lead: "This workflow can't run as written",
  },
  unclear: {
    headline: (v) => `The policy's wording doesn't say which approval level covers exactly ${v}.`,
    below: "This level ends at it",
    above: "The next level starts at it",
    lead: "Please confirm",
  },
};

/** For an unclear amount: the passage that words it both ways. */
const BOTH_WAYS = {
  above: "The next level starts at it, worded as both over it and from it",
  below: "This level ends at it, worded as both under it and up to it",
};

/** A number the policy's approval levels leave out, include twice, or word both ways. Found by plain code. */
function AmountGapCard({ finding, workflow }: { finding: AmountGap; workflow: Workflow }) {
  const { decisions, decide, undo } = useDecisions();
  const amount = formatValue(workflow, finding.field, finding.amount);
  const decision = amountDecision(decisions, workflow.opportunity_id, finding);
  if (decision) {
    const quote = decision.level === "below" ? finding.below : finding.above;
    return (
      <Decided
        title={`Exactly ${amount} goes to the level that ${decision.level === "below" ? "ends" : "starts"} there.`}
        text={`That level reads “${quote}”. Requests for exactly ${amount} now run through its approvers. The policy's wording is unchanged, so fix it when you can.`}
        at={decision.decided_at}
        onChange={undo && (() => undo(decision))}
      />
    );
  }
  const unclear = finding.kind === "unclear";
  const words = {
    ...AMOUNT_WORDS[finding.kind],
    ...(unclear && finding.unclear_side ? { [finding.unclear_side]: BOTH_WAYS[finding.unclear_side] } : {}),
  };
  const choose = (level: "below" | "above") =>
    decide?.({
      kind: "amount",
      workflow_id: workflow.opportunity_id,
      field: finding.field,
      amount: finding.amount,
      level,
      decided_at: new Date().toISOString(),
    } satisfies Decision);
  return (
    <div className={`card flex break-inside-avoid flex-col gap-4 border-l-4 p-5 ${unclear ? "border-l-rule" : "border-l-alert"}`}>
      <div className="flex flex-col gap-1">
        <p className={`text-sm font-medium ${unclear ? "text-rule" : "text-alert"}`}>{words.lead}</p>
        <h3 className="text-xl font-semibold text-balance">{words.headline(amount)}</h3>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">{words.below}</p>
          <Quote text={finding.below} doc="policy" />
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">{words.above}</p>
          <Quote text={finding.above} doc="policy" />
        </div>
      </div>
      <p className="text-muted">
        A request for exactly {amount} will stop and wait for a person. Plain code read the wording on both sides, so
        this finding doesn&apos;t depend on Gemini.
      </p>
      {decide && (
        <div className="flex flex-col gap-3 rounded-lg border border-line bg-paper p-4 print:hidden">
          <p className="font-medium">Who approves exactly {amount}?</p>
          <p className="text-sm text-muted">
            Pick a level. OrgFlow records your decision, and every request for exactly {amount} follows it.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {(["below", "above"] as const).map((level) => (
              <button
                key={level}
                type="button"
                onClick={() => choose(level)}
                className="flex flex-col items-start gap-1 rounded-lg border border-line bg-sheet px-4 py-3 text-left shadow-[0_1px_2px_rgb(22_26_35/0.04)] hover:border-ai"
              >
                <span className="font-medium">The level that {level === "below" ? "ends" : "starts"} there</span>
                <span className="font-serif text-sm text-muted">{level === "below" ? finding.below : finding.above}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Every place a workflow can't run as written: approvers that don't exist, numbers no level covers. */
export function Findings({
  workflow,
  gaps,
  amountGaps,
  org,
}: {
  workflow: Workflow;
  gaps: Gap[];
  amountGaps: AmountGap[];
  org: Organization;
}) {
  const rules = new Map(workflow.rules.map((r) => [r.id, r]));
  const ruleOf = (stepId: string | null) => {
    const ruleId = workflow.steps.find((s) => s.id === stepId)?.only_if;
    return ruleId ? rules.get(ruleId) : undefined;
  };
  return (
    <div className="flex flex-col gap-4">
      {gaps.map((gap) => (
        <GapCard key={`${gap.step_id}-${gap.actor}`} gap={gap} org={org} rule={ruleOf(gap.step_id)} workflow={workflow} />
      ))}
      {amountGaps.map((finding) => (
        <AmountGapCard key={`${finding.kind}-${finding.field}-${finding.amount}`} finding={finding} workflow={workflow} />
      ))}
    </div>
  );
}

export function WorkflowView({ workflow, gaps, org }: { workflow: Workflow; gaps: Gap[]; org: Organization }) {
  const { decisions } = useDecisions();
  const rules = new Map(workflow.rules.map((r) => [r.id, r]));
  const gapFor = new Map(gaps.map((g) => [g.actor, g]));
  const fields = fieldsOf(workflow);

  return (
    <div className="flex flex-col gap-8">
      <p className="max-w-prose leading-relaxed">{workflow.explanation}</p>

      <div className="flex flex-col gap-3">
        <h4 className="font-semibold">Form</h4>
        <p className="text-muted">
          {workflow.starts_from
            ? `Arrives filled in from ${workflow.starts_from}: `
            : "Requester, department, and "}
          {fields.map((f) => f.label).join(", ")}.
        </p>
      </div>

      {workflow.rules.length > 0 && (
        <div className="flex flex-col gap-4">
          <h4 className="font-semibold">Rules taken from the policy</h4>
          <p className="max-w-prose text-muted">
            Gemini wrote each rule once, with the passage it came from. When a request runs, plain code compares the
            numbers, so the same request always gets the same answer.
          </p>
          <ul className="flex flex-col gap-5">
            {workflow.rules.map((rule) => (
              <li key={rule.id} className="grid gap-3 sm:grid-cols-[minmax(0,15rem)_1fr] sm:items-start">
                <code className="w-fit rounded-md bg-rule-soft px-2 py-1 font-mono text-sm text-rule">
                  {ruleExpression(rule, workflow)}
                </code>
                <Quote text={rule.source} doc="policy" />
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-4">
        <h4 className="font-semibold">Steps</h4>
        <ol className="flex flex-col">
          {workflow.steps.map((step, i) => {
            const conditions = [step.only_if, step.also_if].map((id) => (id ? rules.get(id) : undefined)).filter(Boolean) as Rule[];
            const missing = workflow.unresolved_actors.includes(step.actor);
            const decision = missing ? approverDecision(decisions, workflow.opportunity_id, step.actor) : undefined;
            return (
              <li key={step.id} className="grid grid-cols-[2rem_1fr] gap-x-4 border-l border-line pb-6 pl-0 last:pb-0">
                <span className="-ml-[0.8rem] flex h-6 w-6 items-center justify-center rounded-full border border-line bg-paper text-xs tabular-nums">
                  {i + 1}
                </span>
                <div className="flex flex-col gap-1.5">
                  <p>
                    <span className={`text-sm font-medium ${step.type === "ai_review" ? "text-ai" : "text-muted"}`}>
                      {STEP_KIND[step.type]}
                    </span>
                    <span className="mx-2 text-line">|</span>
                    <span className="font-medium">{actorName(step.actor, org)}</span>
                  </p>
                  {step.check && <p className="text-muted">{step.check}</p>}
                  {conditions.length > 0 && (
                    <p className="text-sm">
                      Only when{" "}
                      {conditions.map((rule, j) => (
                        <span key={rule.id}>
                          {j > 0 && " and "}
                          <code className="font-mono text-rule">{ruleExpression(rule, workflow)}</code>
                        </span>
                      ))}
                    </p>
                  )}
                  {decision ? (
                    <p className="w-fit rounded-md bg-ok-soft px-3 py-2 text-sm text-ok">
                      Not in the org chart. By your decision, {standInName(decision.role_id, org)} approves instead.
                    </p>
                  ) : (
                    missing && (
                      <p
                        className={`w-fit rounded-md px-3 py-2 text-sm ${
                          gapFor.get(step.actor)?.status === "possible_match"
                            ? "bg-rule-soft text-rule"
                            : "bg-alert-soft text-alert"
                        }`}
                      >
                        {gapFor.get(step.actor)?.status === "possible_match"
                          ? `Not matched to a role yet. A person confirms who ${step.actor} is.`
                          : `Not in the org chart. A person names the approver.`}
                      </p>
                    )
                  )}
                </div>
              </li>
            );
          })}
        </ol>
        {workflow.hands_to && (
          <p className="text-sm text-muted">
            When it completes, the case goes to {workflow.hands_to}
            {workflow.output ? ` as ${workflow.output}` : ""}.
          </p>
        )}
      </div>
    </div>
  );
}
