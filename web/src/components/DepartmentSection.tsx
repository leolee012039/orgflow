"use client";

import type { BuiltWorkflow, DepartmentMap, DepartmentProfile, Organization, WorkflowCandidate } from "@/lib/types";
import { Quote } from "./Quote";
import { ErrorNote, OriginNote, PrimaryButton, Working } from "./Section";
import { Findings, WorkflowView } from "./WorkflowView";

import type { BuildState } from "@/lib/useBuilds";
import { openProblems, settledProblems, useDecisions } from "@/lib/decisions";

const departmentAnchor = (name: string) => `dept-${encodeURIComponent(name).replace(/%/g, "")}`;

function Basis({ basis }: { basis: WorkflowCandidate["basis"] }) {
  return basis === "policy" ? (
    <span className="rounded-full bg-rule-soft px-2.5 py-0.5 text-xs font-medium text-rule">Rules from a policy</span>
  ) : (
    <span className="rounded-full border border-dashed border-muted px-2.5 py-0.5 text-xs font-medium text-muted">
      From the org chart only, needs confirming
    </span>
  );
}

function CandidateCard({
  candidate,
  org,
  built,
  state,
  blockedBy,
  canBuild,
  onBuild,
}: {
  candidate: WorkflowCandidate;
  org: Organization;
  built?: BuiltWorkflow;
  state?: BuildState;
  /** The upstream workflow that must be built first, if any */
  blockedBy?: WorkflowCandidate;
  canBuild: boolean;
  onBuild: () => void;
}) {
  const { decisions } = useDecisions();
  const problems = built ? openProblems(built, decisions) : 0;
  const settled = built ? settledProblems(built, decisions) : 0;
  return (
    <li className="flex flex-col gap-4 border-t border-line py-6 first:border-t-0 first:pt-0">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h4 className="text-lg font-semibold text-balance">{candidate.name}</h4>
          <Basis basis={candidate.basis} />
        </div>
        <p className="text-muted">
          {candidate.starts_from ? `Starts when ${candidate.starts_from} hands over work. ` : ""}
          {candidate.trigger}
          {candidate.hands_to ? ` Its result goes to ${candidate.hands_to}: ${candidate.output}.` : ""}
        </p>
      </div>
      <p className="max-w-prose leading-relaxed">{candidate.why}</p>
      {candidate.evidence.slice(0, 1).map((ev, i) => (
        <Quote key={i} text={ev.quote} doc={ev.doc} />
      ))}
      {candidate.evidence.length > 1 && (
        <details>
          <summary className="w-fit cursor-pointer text-sm text-ai underline underline-offset-4">
            {candidate.evidence.length - 1} more {candidate.evidence.length === 2 ? "passage" : "passages"}
          </summary>
          <div className="mt-3 flex flex-col gap-3">
            {candidate.evidence.slice(1).map((ev, i) => (
              <Quote key={i} text={ev.quote} doc={ev.doc} />
            ))}
          </div>
        </details>
      )}

      {built ? (
        <div className="flex flex-col gap-4">
          <p className={`font-medium ${problems ? "text-alert" : "text-ok"}`}>
            Built: {built.steps.length} steps, {built.rules.length} {built.rules.length === 1 ? "rule" : "rules"}
            {problems ? `, ${problems} ${problems === 1 ? "problem" : "problems"} found` : settled ? "" : ", no problems found"}
            {settled ? `, ${settled} settled by a decision` : ""}.
          </p>
          {problems + settled > 0 && <Findings workflow={built} gaps={built.gaps} amountGaps={built.amount_gaps ?? []} org={org} />}
          <details className="rounded-md border border-line bg-sheet p-4 open:pb-6">
            <summary className="cursor-pointer font-medium">See the workflow</summary>
            <div className="mt-6">
              <WorkflowView workflow={built} gaps={built.gaps} org={org} />
              <OriginNote origin={built.origin} latencyMs={built.latency_ms} />
            </div>
          </details>
        </div>
      ) : state?.status === "building" ? (
        <Working label="Gemini is building this workflow" />
      ) : (
        <div className="flex flex-col gap-3">
          {state?.status === "error" && <ErrorNote message={state.message} problems={state.problems} />}
          {blockedBy ? (
            <p className="text-sm text-muted">
              Build {blockedBy.department}&apos;s &ldquo;{blockedBy.name}&rdquo; first: this workflow starts from its
              result.
            </p>
          ) : canBuild ? (
            <div>
              <PrimaryButton onClick={onBuild}>Build this workflow</PrimaryButton>
            </div>
          ) : null}
        </div>
      )}
    </li>
  );
}

export function DepartmentSection({
  profile,
  map,
  org,
  candidates,
  built,
  states,
  blockedBy,
  canBuild,
  onBuild,
}: {
  profile: DepartmentProfile;
  map: DepartmentMap;
  org: Organization;
  candidates: WorkflowCandidate[];
  built: Record<string, BuiltWorkflow>;
  states: Record<string, BuildState>;
  blockedBy: (c: WorkflowCandidate) => WorkflowCandidate | undefined;
  canBuild: boolean;
  onBuild: (c: WorkflowCandidate) => void;
}) {
  const head = org.roles.find((r) => r.id === org.departments.find((d) => d.name === profile.name)?.head_role_id);
  const receives = map.handoffs.filter((h) => h.to === profile.name);
  const sends = map.handoffs.filter((h) => h.from === profile.name);
  return (
    <section id={departmentAnchor(profile.name)} className="flex scroll-mt-6 flex-col gap-6 border-t border-line py-10">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <h3 className="text-2xl font-semibold tracking-tight">{profile.name}</h3>
          {head && <span className="text-muted">led by the {head.title}</span>}
        </div>
        <p className="max-w-prose text-lg leading-relaxed">{profile.summary}</p>
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">What it does</p>
          <ul className="flex flex-col gap-1.5">
            {profile.work.map((w, i) => (
              <li key={i} title={w.evidence.quote} className="first-letter:uppercase">
                {w.task}
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Work in and out</p>
          {receives.length + sends.length === 0 ? (
            <p className="text-muted">No handoffs with other departments in the documents.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {receives.map((h) => (
                <li key={`in-${h.from}-${h.what}`}>
                  Receives {h.what} from {h.from}
                </li>
              ))}
              {sends.map((h) => (
                <li key={`out-${h.to}-${h.what}`}>
                  Hands {h.what} to {h.to}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <p className="text-sm font-medium">Workflows to automate, most valuable first</p>
        <ol className="flex flex-col">
          {candidates.map((c) => (
            <CandidateCard
              key={c.id}
              candidate={c}
              org={org}
              built={built[c.id]}
              state={states[c.id]}
              blockedBy={blockedBy(c)}
              canBuild={canBuild}
              onBuild={() => onBuild(c)}
            />
          ))}
        </ol>
      </div>
    </section>
  );
}
