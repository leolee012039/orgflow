import { actorName, currencyOf, money, ruleExpression, STEP_KIND } from "@/lib/format";
import type { AmountGap, Gap, Organization, Rule, Workflow } from "@/lib/types";
import { Quote } from "./Quote";

/** The headline finding: an approver the policy requires that the organization doesn't have. */
function GapCard({ gap, org, rule }: { gap: Gap; org: Organization; rule?: Rule }) {
  const missing = gap.status === "missing";
  const titles = org.roles.map((r) => r.title);
  return (
    <div className={`flex flex-col gap-4 rounded-md border-l-4 bg-sheet p-5 ${missing ? "border-alert" : "border-rule"}`}>
      <div className="flex flex-col gap-1">
        <p className={`text-sm font-medium ${missing ? "text-alert" : "text-rule"}`}>
          {missing ? "Your policy can't run as written" : "Please confirm"}
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
          ? `Requests where ${ruleExpression(rule)} will stop and wait for a person to name the approver.`
          : "Requests that reach this step will stop and wait for a person to name the approver."}{" "}
        OrgFlow doesn&apos;t guess who should approve.
      </p>
    </div>
  );
}

/** An amount the policy's approval levels leave out, or include twice. Found by plain code, not Gemini. */
function AmountGapCard({ finding, currency }: { finding: AmountGap; currency: string }) {
  const amount = money(finding.amount, currency);
  const gap = finding.kind === "gap";
  return (
    <div className="flex flex-col gap-4 rounded-md border-l-4 border-alert bg-sheet p-5">
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-alert">Your policy can&apos;t run as written</p>
        <h3 className="text-xl font-semibold text-balance">
          {gap
            ? `No approval level covers exactly ${amount}. One level stops just below it, and the next starts just above it.`
            : `Two approval levels both cover exactly ${amount}, so the policy names two sets of approvers for it.`}
        </h3>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">{gap ? "This level stops below it" : "This level includes it"}</p>
          <Quote text={finding.below} doc="policy" />
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">{gap ? "The next level starts above it" : "The next level includes it too"}</p>
          <Quote text={finding.above} doc="policy" />
        </div>
      </div>
      <p className="text-muted">
        A request for exactly {amount} will stop and wait for a person. Plain code read the wording on both sides, so
        this finding doesn&apos;t depend on Gemini.
      </p>
    </div>
  );
}

export function WorkflowView({
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
  const gapFor = new Map(gaps.map((g) => [g.actor, g]));
  const currency = currencyOf(workflow.rules);
  const ruleOf = (stepId: string | null) => {
    const ruleId = workflow.steps.find((s) => s.id === stepId)?.only_if;
    return ruleId ? rules.get(ruleId) : undefined;
  };

  return (
    <div className="flex flex-col gap-10">
      {gaps.length + amountGaps.length > 0 && (
        <div className="flex flex-col gap-4">
          {gaps.map((gap) => (
            <GapCard key={gap.actor} gap={gap} org={org} rule={ruleOf(gap.step_id)} />
          ))}
          {amountGaps.map((finding) => (
            <AmountGapCard key={`${finding.kind}-${finding.amount}`} finding={finding} currency={currency} />
          ))}
        </div>
      )}

      <p className="max-w-prose text-lg leading-relaxed">{workflow.explanation}</p>

      <div className="flex flex-col gap-4">
        <h3 className="font-semibold">Rules taken from the policy</h3>
        <p className="max-w-prose text-muted">
          Gemini wrote each rule once, with the passage it came from. When a request runs, plain code compares the
          numbers, so the same request always gets the same answer.
        </p>
        <ul className="flex flex-col gap-5">
          {workflow.rules.map((rule) => (
            <li key={rule.id} className="grid gap-3 sm:grid-cols-[minmax(0,15rem)_1fr] sm:items-start">
              <code className="w-fit rounded bg-rule-soft px-2 py-1 font-mono text-sm text-rule">
                {ruleExpression(rule)}
              </code>
              <Quote text={rule.source} doc="policy" />
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-4">
        <h3 className="font-semibold">Steps</h3>
        <ol className="flex flex-col">
          {workflow.steps.map((step, i) => {
            const rule = step.only_if ? rules.get(step.only_if) : undefined;
            const missing = workflow.unresolved_actors.includes(step.actor);
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
                  {rule && (
                    <p className="text-sm">
                      Only when <code className="font-mono text-rule">{ruleExpression(rule)}</code>
                    </p>
                  )}
                  {missing && (
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
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
