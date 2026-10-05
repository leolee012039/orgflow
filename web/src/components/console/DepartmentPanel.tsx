"use client";

import { openProblems, settledProblems, useDecisions } from "@/lib/decisions";
import type { BuildState } from "@/lib/useBuilds";
import type { BuiltWorkflow, DepartmentMap, Organization, WorkflowCandidate } from "@/lib/types";
import { Quote } from "../Quote";
import { AlertIcon, BuildingIcon, CheckIcon, FileIcon } from "../Icons";
import { Working } from "../Section";

/** "Approved purchase request" inside a sentence, unless it starts with an acronym such as "PO". */
const midSentence = (s: string) => (/^[A-Z][a-z]/.test(s) ? s.charAt(0).toLowerCase() + s.slice(1) : s);

export function Basis({ basis }: { basis: WorkflowCandidate["basis"] }) {
  return basis === "policy" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-rule-soft px-2 py-0.5 text-xs font-medium whitespace-nowrap text-rule">
      <FileIcon width="12" height="12" /> From a policy
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-paper px-2 py-0.5 text-xs font-medium whitespace-nowrap text-muted ring-1 ring-line">
      <BuildingIcon width="12" height="12" /> Org chart only
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
  const { decisions } = useDecisions();
  const pill = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap";
  if (built) {
    const problems = openProblems(built, decisions);
    const settled = settledProblems(built, decisions);
    return problems ? (
      <span className={`${pill} bg-alert-soft text-alert`}>
        <AlertIcon width="12" height="12" /> Built, {problems} {problems === 1 ? "problem" : "problems"}
      </span>
    ) : (
      <span className={`${pill} bg-ok-soft text-ok`}>
        <CheckIcon width="12" height="12" /> Built{settled ? `, ${settled} decided` : ""}
      </span>
    );
  }
  if (state?.status === "building") return <Working label="Building" />;
  if (state?.status === "error") return <span className={`${pill} bg-alert-soft text-alert`}>Couldn&apos;t build</span>;
  if (blockedBy) return <span className={`${pill} bg-paper text-muted ring-1 ring-line`}>Waits for {blockedBy.department}</span>;
  return <span className={`${pill} bg-paper text-muted ring-1 ring-line`}>Not built</span>;
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
      <div className="card px-5 py-10 text-muted">
        Select a department on the map to see what it does and the workflows planned for it.
      </div>
    );
  }
  const head = org.roles.find((r) => r.id === org.departments.find((d) => d.name === profile.name)?.head_role_id);
  const receives = map.handoffs.filter((h) => h.to === profile.name);
  const sends = map.handoffs.filter((h) => h.from === profile.name);
  const mine = candidates.filter((c) => c.department === profile.name);

  return (
    <div className="card flex flex-col gap-6 p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-ai-soft text-ai">
          <BuildingIcon width="20" height="20" />
        </span>
        <div className="flex min-w-0 flex-col">
          <h3 className="text-xl font-semibold tracking-tight">{profile.name}</h3>
          {head && <p className="text-sm text-muted">Led by the {head.title}</p>}
        </div>
      </div>
      <p className="-mt-2 leading-relaxed text-muted">{profile.summary}</p>

      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold text-faint">What it does</p>
        <ul className="flex flex-col gap-1.5">
          {profile.work.map((w, i) => (
            <li key={i} className="flex gap-2">
              <CheckIcon width="16" height="16" className="mt-0.5 shrink-0 text-ok" />
              <span className="first-letter:uppercase">{w.task}</span>
            </li>
          ))}
        </ul>
        <details>
          <summary className="w-fit cursor-pointer text-sm font-medium text-ai">Where it says so</summary>
          <div className="mt-3 flex flex-col gap-3">
            {profile.work.map((w, i) => (
              <Quote key={i} text={w.evidence.quote} doc={w.evidence.doc} />
            ))}
          </div>
        </details>
      </div>

      {receives.length + sends.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-semibold text-faint">Work in and out</p>
          <ul className="flex flex-col gap-1.5">
            {receives.map((h) => (
              <li key={`in-${h.from}-${h.what}`} className="flex gap-2">
                <span className="mt-0.5 h-fit shrink-0 rounded-md bg-paper px-1.5 py-0.5 text-[11px] leading-none font-semibold text-muted ring-1 ring-line">IN</span>
                <span>
                  {h.what} from <span className="font-medium">{h.from}</span>
                </span>
              </li>
            ))}
            {sends.map((h) => (
              <li key={`out-${h.to}-${h.what}`} className="flex gap-2">
                <span className="mt-0.5 h-fit shrink-0 rounded-md bg-ai-soft px-1.5 py-0.5 text-[11px] leading-none font-semibold text-ai">OUT</span>
                <span>
                  {h.what} to <span className="font-medium">{h.to}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold text-faint">Workflows to automate</p>
        <ol className="flex flex-col divide-y divide-line overflow-hidden rounded-xl border border-line">
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
                  {c.starts_from ? `Starts from ${c.starts_from}. ` : ""}
                  {c.hands_to ? `Result goes to ${c.hands_to}.` : `Produces ${midSentence(c.output)}.`}
                </p>
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                  <StatusText built={b} state={state} blockedBy={blocked} />
                  {!b && state?.status !== "building" && canBuild && !blocked && (
                    <button
                      type="button"
                      onClick={() => onBuild(c)}
                      disabled={busy}
                      className="rounded-lg bg-ai px-3 py-1.5 font-medium text-sheet hover:bg-ai-strong disabled:bg-line disabled:text-faint"
                    >
                      {state?.status === "error" ? "Try again" : "Build"}
                    </button>
                  )}
                  {b && (
                    <button type="button" onClick={() => onOpen(c.id)} className="font-medium text-ai hover:underline">
                      Open →
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
