"use client";

import type { BuildState } from "@/lib/useBuilds";
import type { BuiltWorkflow, DepartmentMap, Organization, WorkflowCandidate } from "@/lib/types";
import { Quote } from "../Quote";
import { Working } from "../Section";

/** "Approved purchase request" inside a sentence, unless it starts with an acronym such as "PO". */
const midSentence = (s: string) => (/^[A-Z][a-z]/.test(s) ? s.charAt(0).toLowerCase() + s.slice(1) : s);

export function Basis({ basis }: { basis: WorkflowCandidate["basis"] }) {
  return basis === "policy" ? (
    <span className="rounded-full bg-rule-soft px-2 py-0.5 text-xs font-medium whitespace-nowrap text-rule">From a policy</span>
  ) : (
    <span className="rounded-full border border-dashed border-muted px-2 py-0.5 text-xs font-medium whitespace-nowrap text-muted">
      Org chart only
    </span>
  );
}

/** Where a planned workflow stands, in a word or two. */
export function StatusText({
  built,
  state,
  blockedBy,
}: {
  built?: BuiltWorkflow;
  state?: BuildState;
  blockedBy?: WorkflowCandidate;
}) {
  if (built) {
    const problems = built.gaps.length + (built.amount_gaps?.length ?? 0);
    return problems ? (
      <span className="font-medium text-alert">
        Built, {problems} {problems === 1 ? "problem" : "problems"}
      </span>
    ) : (
      <span className="font-medium text-ok">Built</span>
    );
  }
  if (state?.status === "building") return <Working label="Building" />;
  if (state?.status === "error") return <span className="font-medium text-alert">Couldn&apos;t build</span>;
  if (blockedBy) return <span className="text-muted">Waits for {blockedBy.department}</span>;
  return <span className="text-muted">Not built</span>;
}

export function DepartmentPanel({
  name,
  map,
  org,
  candidates,
  built,
  states,
  blockedBy,
  canBuild,
  busy,
  onBuild,
  onOpen,
}: {
  name: string | null;
  map: DepartmentMap;
  org: Organization;
  candidates: WorkflowCandidate[];
  built: Record<string, BuiltWorkflow>;
  states: Record<string, BuildState>;
  blockedBy: (c: WorkflowCandidate) => WorkflowCandidate | undefined;
  canBuild: boolean;
  busy: boolean;
  onBuild: (c: WorkflowCandidate) => void;
  /** Open a workflow in the Workflows section */
  onOpen: (id: string) => void;
}) {
  const profile = map.departments.find((d) => d.name === name);
  if (!profile) {
    return (
      <div className="rounded-md border border-dashed border-line px-5 py-10 text-muted">
        Select a department on the map to see what it does and the workflows planned for it.
      </div>
    );
  }
  const head = org.roles.find((r) => r.id === org.departments.find((d) => d.name === profile.name)?.head_role_id);
  const receives = map.handoffs.filter((h) => h.to === profile.name);
  const sends = map.handoffs.filter((h) => h.from === profile.name);
  const mine = candidates.filter((c) => c.department === profile.name);

  return (
    <div className="flex flex-col gap-6 rounded-md border border-ink bg-sheet p-5">
      <div className="flex flex-col gap-1">
        <h3 className="text-2xl font-semibold tracking-tight">{profile.name}</h3>
        {head && <p className="text-sm text-muted">Led by the {head.title}</p>}
        <p className="mt-2 leading-relaxed">{profile.summary}</p>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">What it does</p>
        <ul className="flex flex-col gap-1">
          {profile.work.map((w, i) => (
            <li key={i} className="first-letter:uppercase">
              {w.task}
            </li>
          ))}
        </ul>
        <details>
          <summary className="w-fit cursor-pointer text-sm text-ai underline underline-offset-4">Where it says so</summary>
          <div className="mt-3 flex flex-col gap-3">
            {profile.work.map((w, i) => (
              <Quote key={i} text={w.evidence.quote} doc={w.evidence.doc} />
            ))}
          </div>
        </details>
      </div>

      {receives.length + sends.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Work in and out</p>
          <ul className="flex flex-col gap-1">
            {receives.map((h) => (
              <li key={`in-${h.from}-${h.what}`}>
                ← {h.what} from {h.from}
              </li>
            ))}
            {sends.map((h) => (
              <li key={`out-${h.to}-${h.what}`}>
                → {h.what} to {h.to}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-3">
        <p className="text-sm font-medium">Workflows to automate</p>
        <ol className="flex flex-col divide-y divide-line rounded-md border border-line">
          {mine.map((c) => {
            const b = built[c.id];
            const blocked = blockedBy(c);
            const state = states[c.id];
            return (
              <li key={c.id} className="flex flex-col gap-2 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => onOpen(c.id)}
                    className="text-left font-medium underline-offset-4 hover:underline"
                  >
                    {c.name}
                  </button>
                  <Basis basis={c.basis} />
                </div>
                <p className="text-sm text-muted">
                  {c.starts_from ? `From ${c.starts_from}. ` : ""}
                  {c.hands_to ? `Hands ${midSentence(c.output)} to ${c.hands_to}.` : c.output}
                </p>
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                  <StatusText built={b} state={state} blockedBy={blocked} />
                  {!b && state?.status !== "building" && canBuild && !blocked && (
                    <button
                      type="button"
                      onClick={() => onBuild(c)}
                      disabled={busy}
                      className="rounded-md bg-ink px-3 py-1.5 font-medium text-sheet hover:bg-ai disabled:bg-line disabled:text-muted"
                    >
                      {state?.status === "error" ? "Try again" : "Build"}
                    </button>
                  )}
                  {b && (
                    <button type="button" onClick={() => onOpen(c.id)} className="text-ai underline underline-offset-4">
                      Open
                    </button>
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
