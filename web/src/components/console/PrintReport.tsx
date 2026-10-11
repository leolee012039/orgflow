"use client";

import { flowLanes } from "@/lib/chain";
import { openProblems, settledProblems, useDecisions } from "@/lib/decisions";
import type { BuiltWorkflow, DepartmentMap, DepartmentProfile, Organization, WorkflowCandidate } from "@/lib/types";
import type { Workspace } from "@/lib/workspaces";
import { Quote } from "../Quote";
import { OriginNote } from "../Section";
import { Findings, WorkflowView } from "../WorkflowView";
import { problemsOf } from "./Overview";

const analyzedOn = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

/**
 * The company on paper, for Save as PDF. The first page answers what a reader opens it for: what was read,
 * how work moves, and every place a case stops with what was decided. Then one page per department with its
 * workflows written out in full: nothing to click, and no box split across pages.
 */
export function PrintReport({ workspace }: { workspace: Workspace }) {
  const { departmentMap: map, organization: org, plan, built } = workspace;
  return (
    <div className="hidden text-[10.5pt] leading-relaxed print:block">
      <Summary workspace={workspace} />
      {map.departments.map((profile) => (
        <DepartmentPage
          key={profile.name}
          profile={profile}
          map={map}
          org={org}
          candidates={plan.workflows.filter((c) => c.department === profile.name)}
          built={built}
        />
      ))}
    </div>
  );
}

function Summary({ workspace }: { workspace: Workspace }) {
  const { departmentMap: map, plan, built } = workspace;
  const { decisions } = useDecisions();
  const problems = problemsOf(workspace, decisions);
  const builtList = plan.workflows.map((c) => built[c.id]).filter((w): w is BuiltWorkflow => Boolean(w));
  const open = builtList.reduce((n, w) => n + openProblems(w, decisions), 0);
  const settled = builtList.reduce((n, w) => n + settledProblems(w, decisions), 0);
  const byHand = plan.workflows.reduce((n, c) => n + c.manual_handoffs, 0);
  const routed = plan.workflows.filter((c) => built[c.id]).reduce((n, c) => n + c.manual_handoffs, 0);
  const unbuilt = plan.workflows.length - builtList.length;
  const unchecked = plan.workflows.filter((c) => built[c.id]?.amount_levels_unchecked);
  const { lanes, alone } = flowLanes(map.handoffs, map.departments.map((d) => d.name));

  const stats = [
    { label: "Departments", value: map.departments.length, note: `${map.handoffs.length} handoffs between them` },
    { label: "Hand-offs done by hand", value: byHand, note: `per case today, in ${plan.workflows.length} processes` },
    { label: "Routed automatically", value: `${routed} of ${byHand}`, note: `${builtList.length} of ${plan.workflows.length} workflows built` },
    { label: "Places a case stops", value: open, note: settled ? `${settled} settled by a decision` : open ? "each needs one decision" : "none open" },
  ];

  return (
    <section className="flex flex-col gap-7">
      <header className="flex flex-col gap-1 border-b border-line pb-4">
        <p className="text-sm text-muted">
          <span className="font-semibold text-ink">OrgFlow</span> report · analyzed {analyzedOn(workspace.analyzedAt)}
          {workspace.sample ? ", a fictional sample company" : ""}
        </p>
        <h1 className="text-[22pt] leading-tight font-semibold tracking-tight">{workspace.company}</h1>
        <p className="text-sm text-muted">
          Read from {workspace.documents.orgChart}
          {workspace.documents.policies.length ? ` and ${workspace.documents.policies.join(", ")}` : ""}.
        </p>
      </header>

      <dl className="grid break-inside-avoid grid-cols-4 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="flex flex-col rounded-md border border-line px-3 py-2.5">
            <dt className="text-xs text-muted">{s.label}</dt>
            <dd className="text-[15pt] font-semibold tabular-nums">{s.value}</dd>
            <dd className="text-xs text-faint">{s.note}</dd>
          </div>
        ))}
      </dl>

      <div className="flex break-inside-avoid flex-col gap-3">
        <h2 className="text-[13pt] font-semibold">How work moves between departments</h2>
        {lanes.length === 0 ? (
          <p className="text-muted">The documents name no handoffs between departments.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {lanes.map((lane, i) => (
              <li key={i} className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                <Dept name={lane[0].from} />
                {lane.map((h) => (
                  <span key={`${h.from}-${h.to}-${h.what}`} className="contents">
                    <span className="flex flex-col items-center px-1 text-center">
                      <span className="max-w-[9rem] text-[8.5pt] leading-tight text-muted">{h.what}</span>
                      <span aria-hidden className="text-muted">→</span>
                    </span>
                    <Dept name={h.to} />
                  </span>
                ))}
              </li>
            ))}
          </ul>
        )}
        {alone.length > 0 && (
          <p className="text-sm text-muted">No handoffs in the documents for {alone.join(", ")}.</p>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="text-[13pt] font-semibold break-after-avoid">Where a case stops, and what was decided</h2>
        {builtList.length === 0 ? (
          <p className="text-muted">No workflow is built yet, so nothing has been checked.</p>
        ) : problems.length + unchecked.length === 0 ? (
          <p>No problems in the {builtList.length} built {builtList.length === 1 ? "workflow" : "workflows"}.</p>
        ) : (
          <ol className="flex flex-col divide-y divide-line rounded-md border border-line">
            {problems.map((p, i) => (
              <li key={p.key} className="grid break-inside-avoid grid-cols-[1.75rem_1fr] gap-x-2 px-3 py-2.5">
                <span className="text-muted tabular-nums">{i + 1}.</span>
                <div className="flex flex-col">
                  <span className="font-medium">{p.text}</span>
                  <span className="text-sm text-muted">
                    {p.department}, {p.workflow}
                  </span>
                  <span className={`text-sm font-medium ${p.decided ? "text-ok" : p.confirm ? "text-rule" : "text-alert"}`}>
                    {p.decided ? `Decided: ${p.decided}` : p.confirm ? "To confirm: a person checks who or which level it is" : "Open: a case stops here until a person decides"}
                  </span>
                </div>
              </li>
            ))}
            {unchecked.map((c, i) => (
              <li key={`${c.id}-unchecked`} className="grid break-inside-avoid grid-cols-[1.75rem_1fr] gap-x-2 px-3 py-2.5">
                <span className="text-muted tabular-nums">{problems.length + i + 1}.</span>
                <div className="flex flex-col">
                  <span className="font-medium">The policy&apos;s amount levels couldn&apos;t be matched to its wording</span>
                  <span className="text-sm text-muted">
                    {c.department}, {c.name}
                  </span>
                  <span className="text-sm font-medium text-rule">Not checked: exact amounts in this workflow</span>
                </div>
              </li>
            ))}
          </ol>
        )}
        {unbuilt > 0 && (
          <p className="text-sm text-muted">
            {unbuilt} planned {unbuilt === 1 ? "workflow isn't" : "workflows aren't"} built yet, so nothing in{" "}
            {unbuilt === 1 ? "it" : "them"} is checked.
          </p>
        )}
        <p className="text-sm text-muted">
          Gemini read the documents and wrote each rule with the passage it came from. Plain code checked every quote
          against the PDFs and found these problems by comparing the documents. The pages that follow show each
          department&apos;s workflows in full.
        </p>
      </div>
    </section>
  );
}

function Dept({ name }: { name: string }) {
  return <span className="rounded-md border border-ink/40 px-2.5 py-1 font-medium">{name}</span>;
}

function DepartmentPage({
  profile,
  map,
  org,
  candidates,
  built,
}: {
  profile: DepartmentProfile;
  map: DepartmentMap;
  org: Organization;
  candidates: WorkflowCandidate[];
  built: Record<string, BuiltWorkflow>;
}) {
  const head = org.roles.find((r) => r.id === org.departments.find((d) => d.name === profile.name)?.head_role_id);
  const receives = map.handoffs.filter((h) => h.to === profile.name);
  const sends = map.handoffs.filter((h) => h.from === profile.name);
  return (
    <section className="flex break-before-page flex-col gap-6">
      <div className="flex break-inside-avoid flex-col gap-2 border-b border-line pb-4">
        <h2 className="text-[17pt] font-semibold tracking-tight">
          {profile.name}
          {head && <span className="ml-2 text-[11pt] font-normal text-muted">led by the {head.title}</span>}
        </h2>
        <p>{profile.summary}</p>
        <div className="mt-2 grid grid-cols-2 gap-6">
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold">What it does</p>
            <ul className="flex list-disc flex-col gap-0.5 pl-5">
              {profile.work.map((w, i) => (
                <li key={i} className="first-letter:uppercase">
                  {w.task}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold">Work in and out</p>
            {receives.length + sends.length === 0 ? (
              <p className="text-muted">No handoffs with other departments in the documents.</p>
            ) : (
              <ul className="flex list-disc flex-col gap-0.5 pl-5">
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
      </div>

      {candidates.length === 0 ? (
        <p className="text-muted">No workflow planned for this department.</p>
      ) : (
        candidates.map((c, i) => <PlannedWorkflow key={c.id} candidate={c} org={org} built={built[c.id]} first={i === 0} />)
      )}
    </section>
  );
}

function PlannedWorkflow({
  candidate,
  org,
  built,
  first,
}: {
  candidate: WorkflowCandidate;
  org: Organization;
  built?: BuiltWorkflow;
  first: boolean;
}) {
  const { decisions } = useDecisions();
  const problems = built ? openProblems(built, decisions) : 0;
  const settled = built ? settledProblems(built, decisions) : 0;
  return (
    <article className={`flex flex-col gap-4 ${first ? "" : "border-t border-line pt-6"}`}>
      <div className="flex break-inside-avoid break-after-avoid flex-col gap-1.5">
        <h3 className="text-[13pt] font-semibold">
          {candidate.name}
          <span className="ml-2 text-[9pt] font-medium text-rule">
            {candidate.basis === "policy" ? "Rules from a policy" : "From the org chart only, needs confirming"}
          </span>
        </h3>
        <p className="text-muted">
          {candidate.starts_from ? `Starts when ${candidate.starts_from} hands over work. ` : ""}
          {candidate.trigger}
          {candidate.hands_to ? ` Its result goes to ${candidate.hands_to}: ${candidate.output}.` : ""}
        </p>
        <p>{candidate.why}</p>
      </div>
      {candidate.evidence.map((ev, i) => (
        <Quote key={i} text={ev.quote} doc={ev.doc} />
      ))}
      {built ? (
        <>
          <p className={`font-medium break-after-avoid ${problems ? "text-alert" : "text-ok"}`}>
            Built: {built.steps.length} steps, {built.rules.length} {built.rules.length === 1 ? "rule" : "rules"}
            {problems ? `, ${problems} ${problems === 1 ? "problem" : "problems"} found` : settled ? "" : ", no problems found"}
            {settled ? `, ${settled} settled by a decision` : ""}.
          </p>
          {problems + settled > 0 && <Findings workflow={built} gaps={built.gaps} amountGaps={built.amount_gaps ?? []} org={org} />}
          <WorkflowView workflow={built} gaps={built.gaps} org={org} />
          <OriginNote origin={built.origin} latencyMs={built.latency_ms} />
        </>
      ) : (
        <p className="text-muted">Not built yet, so it has no rules or steps to show.</p>
      )}
    </article>
  );
}
