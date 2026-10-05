"use client";

import { useRef } from "react";
import { formatValue } from "@/lib/format";
import type { BuildState } from "@/lib/useBuilds";
import type { Workspace } from "@/lib/workspaces";
import type { WorkflowCandidate } from "@/lib/types";
import { AlertIcon, CheckIcon } from "../Icons";
import { OriginNote, Tag } from "../Section";
import { DepartmentCanvas } from "./DepartmentCanvas";
import { DepartmentPanel } from "./DepartmentPanel";

type Problem = { key: string; department: string; workflowId: string; workflow: string; text: string; confirm?: boolean };

/** Every problem found in the built workflows, in plain words. */
export function problemsOf(workspace: Workspace): Problem[] {
  const out: Problem[] = [];
  for (const c of workspace.plan.workflows) {
    const b = workspace.built[c.id];
    if (!b) continue;
    for (const g of b.gaps) {
      out.push({
        key: `${c.id}-actor-${g.actor}`,
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
      out.push({
        key: `${c.id}-amount-${g.field}-${g.amount}`,
        department: c.department,
        workflowId: c.id,
        workflow: c.name,
        text: g.kind === "gap" ? `No approval level covers exactly ${value}` : `Two approval levels both cover exactly ${value}`,
      });
    }
  }
  return out;
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
  const problems = problemsOf(workspace);
  const panel = useRef<HTMLDivElement>(null);
  // When the panel sits below the map, bring it into view
  const select = (name: string) => {
    onSelect(name);
    const top = panel.current?.getBoundingClientRect().top ?? 0;
    if (top > window.innerHeight * 0.6) requestAnimationFrame(() => panel.current?.scrollIntoView({ behavior: "smooth" }));
  };
  const builtCount = Object.keys(built).length;

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
        ) : problems.length === 0 ? (
          <p className="card flex items-center gap-2 px-5 py-4 text-ok">
            <CheckIcon /> No problems in the {builtCount} built workflows.
          </p>
        ) : (
          <ul className="card divide-y divide-line overflow-hidden">
            {problems.map((p) => (
              <li key={p.key} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3.5 gap-y-2 px-5 py-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center">
                <span
                  className={`flex h-9 w-9 items-center justify-center rounded-lg ${p.confirm ? "bg-rule-soft text-rule" : "bg-alert-soft text-alert"}`}
                >
                  <AlertIcon />
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className="font-medium">{p.text}</span>
                  <span className="truncate text-sm text-muted">
                    {p.department}, {p.workflow}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => onOpenWorkflow(p.workflowId)}
                  className="col-start-2 w-fit text-sm font-medium text-ai hover:underline sm:col-start-auto"
                >
                  See the lines that prove it →
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
