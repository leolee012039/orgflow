"use client";

import type { BuildState } from "@/lib/useBuilds";
import type { BuiltWorkflow, Organization, WorkflowCandidate } from "@/lib/types";
import { Quote } from "../Quote";
import { ErrorNote, OriginNote, PrimaryButton } from "../Section";
import { Findings, WorkflowView } from "../WorkflowView";
import { Basis, StatusText } from "./DepartmentPanel";

function Detail({
  candidate,
  built,
  state,
  blockedBy,
  org,
  canBuild,
  busy,
  onBuild,
}: {
  candidate: WorkflowCandidate;
  built?: BuiltWorkflow;
  state?: BuildState;
  blockedBy?: WorkflowCandidate;
  org: Organization;
  canBuild: boolean;
  busy: boolean;
  onBuild: () => void;
}) {
  return (
    <div className="flex flex-col gap-6 border-t border-line bg-paper/70 px-5 py-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Why automate it</p>
          <p className="leading-relaxed">{candidate.why}</p>
          <p className="text-sm text-muted">
            {candidate.trigger} Today it changes hands {candidate.manual_handoffs}{" "}
            {candidate.manual_handoffs === 1 ? "time" : "times"} by hand.
          </p>
        </div>
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium">From the documents</p>
          {candidate.evidence.map((ev, i) => (
            <Quote key={i} text={ev.quote} doc={ev.doc} />
          ))}
        </div>
      </div>
      {built ? (
        <>
          {built.gaps.length + (built.amount_gaps?.length ?? 0) > 0 && (
            <Findings workflow={built} gaps={built.gaps} amountGaps={built.amount_gaps ?? []} org={org} />
          )}
          <div className="card p-5">
            <WorkflowView workflow={built} gaps={built.gaps} org={org} />
            <OriginNote origin={built.origin} latencyMs={built.latency_ms} />
          </div>
        </>
      ) : (
        <div className="flex flex-col gap-3">
          {state?.status === "error" && <ErrorNote message={state.message} problems={state.problems} />}
          {blockedBy ? (
            <p className="text-muted">
              Build {blockedBy.department}&apos;s &ldquo;{blockedBy.name}&rdquo; first: this workflow starts from its result.
            </p>
          ) : canBuild && state?.status !== "building" ? (
            <div>
              <PrimaryButton onClick={onBuild} disabled={busy}>
                Build this workflow
              </PrimaryButton>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** Every planned workflow in one table; a row opens to its plan, its problems and the built workflow. */
export function WorkflowsView({
  candidates,
  built,
  states,
  blockedBy,
  org,
  canBuild,
  busy,
  open,
  onOpen,
  onBuild,
}: {
  candidates: WorkflowCandidate[];
  built: Record<string, BuiltWorkflow>;
  states: Record<string, BuildState>;
  blockedBy: (c: WorkflowCandidate) => WorkflowCandidate | undefined;
  org: Organization;
  canBuild: boolean;
  busy: boolean;
  open: string | null;
  onOpen: (id: string | null) => void;
  onBuild: (c: WorkflowCandidate) => void;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="hidden grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)_minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1.1fr)] gap-4 border-b border-line bg-paper px-5 py-2.5 text-xs font-semibold text-faint md:grid">
        <span>Workflow</span>
        <span>Department</span>
        <span>Case flow</span>
        <span>Rules</span>
        <span>Status</span>
      </div>
      <ul className="divide-y divide-line">
        {candidates.map((c) => {
          const isOpen = open === c.id;
          return (
            <li key={c.id} id={`wf-${c.id}`} className="scroll-mt-6">
              <button
                type="button"
                onClick={() => onOpen(isOpen ? null : c.id)}
                aria-expanded={isOpen}
                className="grid w-full gap-x-4 gap-y-1 px-5 py-4 text-left hover:bg-paper md:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)_minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1.1fr)] md:items-center"
              >
                <span className="font-medium">
                  <span aria-hidden className="mr-2 inline-block w-3 text-muted">
                    {isOpen ? "▾" : "▸"}
                  </span>
                  {c.name}
                </span>
                <span className="text-sm md:text-base">{c.department}</span>
                <span className="text-sm text-muted">
                  {c.starts_from ? `${c.starts_from} → ` : "Form → "}
                  {c.department}
                  {c.hands_to ? ` → ${c.hands_to}` : ""}
                </span>
                <span>
                  <Basis basis={c.basis} />
                </span>
                <span className="text-sm">
                  <StatusText built={built[c.id]} state={states[c.id]} blockedBy={blockedBy(c)} />
                </span>
              </button>
              {isOpen && (
                <Detail
                  candidate={c}
                  built={built[c.id]}
                  state={states[c.id]}
                  blockedBy={blockedBy(c)}
                  org={org}
                  canBuild={canBuild}
                  busy={busy}
                  onBuild={() => onBuild(c)}
                />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
