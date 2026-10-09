"use client";

import { useRef } from "react";
import { amountDecision, approverDecision, standInName, useDecisions } from "@/lib/decisions";
import { formatValue } from "@/lib/format";
import type { BuildState } from "@/lib/useBuilds";
import type { Workspace } from "@/lib/workspaces";
import type { Decision, WorkflowCandidate } from "@/lib/types";
import { AlertIcon, CheckIcon } from "../Icons";
import { OriginNote, Tag } from "../Section";
import { DepartmentCanvas } from "./DepartmentCanvas";
import { DepartmentPanel } from "./DepartmentPanel";

type Problem = {
  key: string;
  department: string;
  workflowId: string;
  workflow: string;
  text: string;
  confirm?: boolean;
  /** What a person decided, in words, once they have */
  decided?: string;
};

/** Every problem found in the built workflows, in plain words: open ones first, then the decided. */
export function problemsOf(workspace: Workspace, decisions: Decision[]): Problem[] {
  const out: Problem[] = [];
  const org = workspace.organization;
  for (const c of workspace.plan.workflows) {
    const b = workspace.built[c.id];
    if (!b) continue;
    for (const g of b.gaps) {
      const d = approverDecision(decisions, b.opportunity_id, g.actor);
      out.push({
        decided: d && `${standInName(d.role_id, org)} approves in place of ${g.actor}`,
        key: `${c.id}-actor-${g.step_id}-${g.actor}`,
        department: c.department,
        workflowId: c.id,
        workflow: c.name,
        confirm: g.status === "possible_match",
        text:
          g.status === "missing"
            ? `The policy requires ${g.actor} approval, and the org chart has no ${g.actor}`
            : `The policy requires ${g.actor} approval; confirm who that is`,
      });
    }
    for (const g of b.amount_gaps ?? []) {
      const value = formatValue(b, g.field, g.amount);
      const d = amountDecision(decisions, b.opportunity_id, g);
      out.push({
        decided: d && `Exactly ${value} goes to the level that ${d.level === "below" ? "ends" : "starts"} there`,
        confirm: g.kind === "unclear",
        key: `${c.id}-amount-${g.field}-${g.amount}`,
        department: c.department,
        workflowId: c.id,
        workflow: c.name,
        text:
          g.kind === "gap"
            ? `No approval level covers exactly ${value}`
            : g.kind === "overlap"
              ? `Two approval levels both cover exactly ${value}`
              : `The policy doesn't say which approval level covers exactly ${value}`,
      });
    }
  }
  return [...out.filter((p) => !p.decided), ...out.filter((p) => p.decided)];
}

export function Overview({
  workspace,
  selected,
  onSelect,
  states,
  blockedBy,
  canBuild,
  busy,
  onBuild,
  onOpenWorkflow,
}: {
  workspace: Workspace;
  selected: string | null;
  onSelect: (name: string) => void;
  states: Record<string, BuildState>;
  blockedBy: (c: WorkflowCandidate) => WorkflowCandidate | undefined;
  canBuild: boolean;
  busy: boolean;
  onBuild: (c: WorkflowCandidate) => void;
  onOpenWorkflow: (id: string) => void;
}) {
  const { departmentMap: map, organization: org, plan, built } = workspace;
  const { decisions, decide } = useDecisions();
  const problems = problemsOf(workspace, decisions);
  const panel = useRef<HTMLDivElement>(null);
  // When the panel sits below the map, bring it into view
  const select = (name: string) => {
    onSelect(name);
    const top = panel.current?.getBoundingClientRect().top ?? 0;
    if (top > window.innerHeight * 0.6) requestAnimationFrame(() => panel.current?.scrollIntoView({ behavior: "smooth" }));
  };
  // "No problems" only covers what was checked: built workflows, and in them only amount levels that passed
  const builtCount = plan.workflows.filter((c) => built[c.id]).length;
  const unbuilt = plan.workflows.length - builtCount;
  const unchecked = plan.workflows.filter((c) => built[c.id]?.amount_levels_unchecked);
  const notCheckedYet =
    unbuilt > 0
      ? `${unbuilt} planned ${unbuilt === 1 ? "workflow isn't" : "workflows aren't"} built yet, so nothing in ${unbuilt === 1 ? "it" : "them"} is checked.`
      : null;

  return (
    <div className="flex flex-col gap-10">
      <div className="grid items-start gap-6 min-[1400px]:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="card flex min-w-0 flex-col gap-5 p-5 sm:p-7">
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <h2 className="text-lg font-semibold">How work moves between departments</h2>
              <Tag kind="gemini" />
            </div>
            <p className="max-w-prose text-sm text-muted">
              Each box is a department, each arrow a handoff written in the documents. Click a department to open it.
            </p>
          </div>
          <div className="overflow-x-auto rounded-xl bg-[radial-gradient(circle,#e3e6ee_1px,transparent_1px)] [background-size:18px_18px] px-4 py-8 sm:px-6">
            <DepartmentCanvas map={map} org={org} plan={plan.workflows} built={built} selected={selected} onSelect={select} />
          </div>
          <OriginNote origin={map.origin} latencyMs={map.latency_ms} />
        </section>
        <div ref={panel} className="scroll-mt-6 min-[1400px]:sticky min-[1400px]:top-6">
          <DepartmentPanel
            name={selected}
            map={map}
            org={org}
            candidates={plan.workflows}
            built={built}
            states={states}
            blockedBy={blockedBy}
            canBuild={canBuild}
            busy={busy}
            onBuild={onBuild}
            onOpen={onOpenWorkflow}
          />
        </div>
      </div>

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h2 className="text-lg font-semibold">Needs attention</h2>
          <Tag kind="rules" />
        </div>
        {builtCount === 0 ? (
          <p className="card px-5 py-4 text-muted">
            Nothing is checked yet. Build workflows, and plain code checks each one against the org chart and the
            policy&apos;s amount levels.
          </p>
        ) : problems.length === 0 && unchecked.length === 0 ? (
          notCheckedYet ? (
            <p className="card px-5 py-4 text-muted">
              No problems in the {builtCount} built {builtCount === 1 ? "workflow" : "workflows"}. {notCheckedYet}
            </p>
          ) : (
            <p className="card flex items-center gap-2 px-5 py-4 text-ok">
              <CheckIcon /> No problems in the {builtCount} built {builtCount === 1 ? "workflow" : "workflows"}.
            </p>
          )
        ) : (
          <ul className="card divide-y divide-line overflow-hidden">
            {problems.map((p) => (
              <li key={p.key} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3.5 gap-y-2 px-5 py-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center">
                <span
                  className={`flex h-9 w-9 items-center justify-center rounded-lg ${
                    p.decided ? "bg-ok-soft text-ok" : p.confirm ? "bg-rule-soft text-rule" : "bg-alert-soft text-alert"
                  }`}
                >
                  {p.decided ? <CheckIcon /> : <AlertIcon />}
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className={`font-medium ${p.decided ? "text-muted line-through decoration-faint" : ""}`}>{p.text}</span>
                  {p.decided && <span className="text-sm font-medium text-ok">Decided: {p.decided}</span>}
                  <span className="truncate text-sm text-muted">
                    {p.department}, {p.workflow}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => onOpenWorkflow(p.workflowId)}
                  className="col-start-2 w-fit text-sm font-medium text-ai hover:underline sm:col-start-auto"
                >
                  {!decide ? "See the lines that prove it →" : p.decided ? "Change →" : "Review and decide →"}
                </button>
              </li>
            ))}
            {unchecked.map((c) => (
              <li key={`${c.id}-unchecked`} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3.5 gap-y-2 px-5 py-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-rule-soft text-rule">
                  <AlertIcon />
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className="font-medium">
                    The policy&apos;s amount levels couldn&apos;t be matched to its wording, so exact amounts aren&apos;t checked
                  </span>
                  <span className="truncate text-sm text-muted">
                    {c.department}, {c.name}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => onOpenWorkflow(c.id)}
                  className="col-start-2 w-fit text-sm font-medium text-ai hover:underline sm:col-start-auto"
                >
                  Open the workflow →
                </button>
              </li>
            ))}
            {notCheckedYet && <li className="px-5 py-3 text-sm text-muted">{notCheckedYet}</li>}
          </ul>
        )}
      </section>
    </div>
  );
}
