import type { Opportunity } from "@/lib/types";
import { Quote } from "./Quote";
import { PrimaryButton } from "./Section";

const IMPACT: Record<Opportunity["impact"], string> = { HIGH: "High impact", MEDIUM: "Medium impact", LOW: "Low impact" };

export function OpportunityList({
  opportunities,
  onBuild,
  busy,
}: {
  opportunities: Opportunity[];
  onBuild: (o: Opportunity) => void;
  busy: boolean;
}) {
  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-prose text-lg leading-relaxed">
        Nobody told OrgFlow what to automate. Gemini compared the roles with the policy and ranked these on its own.
      </p>
      <ol className="flex flex-col">
        {opportunities.map((opp, i) => (
          <li
            key={opp.id}
            className={`grid gap-x-5 gap-y-3 border-t border-line py-6 sm:grid-cols-[2rem_1fr] ${
              opp.executable ? "" : "text-ink/80"
            }`}
          >
            <span className="text-2xl font-semibold tabular-nums text-muted">{i + 1}</span>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <h3 className="text-xl font-semibold text-balance">{opp.name}</h3>
                <p className="text-sm text-muted">
                  {IMPACT[opp.impact]}. {opp.departments.join(" → ")}. {opp.manual_handoffs} {opp.manual_handoffs === 1 ? "handoff" : "handoffs"} today.
                </p>
              </div>
              <p className="max-w-prose leading-relaxed">{opp.why}</p>
              {opp.evidence.map((ev, j) => (
                <Quote key={j} text={ev.quote} doc={ev.doc} />
              ))}
              <div className="pt-1">
                {opp.executable ? (
                  <PrimaryButton disabled={busy} onClick={() => onBuild(opp)}>
                    Build this workflow
                  </PrimaryButton>
                ) : (
                  <p className="text-sm text-muted">Blueprint only for this demo.</p>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
