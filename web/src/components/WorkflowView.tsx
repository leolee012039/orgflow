import { actorName, ruleExpression, STEP_KIND } from "@/lib/format";
import type { Organization, Workflow } from "@/lib/types";
import { Quote } from "./Quote";

export function WorkflowView({ workflow, org }: { workflow: Workflow; org: Organization }) {
  const rules = new Map(workflow.rules.map((r) => [r.id, r]));

  return (
    <div className="flex flex-col gap-10">
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
                    <p className="w-fit rounded-md bg-alert-soft px-3 py-2 text-sm text-alert">
                      The policy names {step.actor}, but {org.company}&apos;s org chart has no such role. OrgFlow
                      will hand this step to a person instead of guessing who approves.
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
