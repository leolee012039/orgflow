"use client";

import { useRef } from "react";
import { formatValue } from "@/lib/format";
import type { BuildState } from "@/lib/useBuilds";
import type { Workspace } from "@/lib/workspaces";
import type { WorkflowCandidate } from "@/lib/types";
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
        <section className="flex min-w-0 flex-col gap-4 rounded-md border border-ink bg-sheet p-5 sm:p-8">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h2 className="text-xl font-semibold">How work moves between departments</h2>
            <Tag kind="gemini" />
          </div>
          <p className="max-w-prose text-muted">
            Each box is a department, each arrow a handoff written in the documents. Solid boxes have built workflows;
            the red number counts their problems.
          </p>
          <div className="overflow-x-auto py-4">
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
          <h2 className="text-xl font-semibold">Needs attention</h2>
          <Tag kind="rules" />
        </div>
        {builtCount === 0 ? (
          <p className="text-muted">
            Nothing is checked yet. Build workflows, and plain code checks each one against the org chart and the
            policy&apos;s amount levels.
          </p>
        ) : problems.length === 0 ? (
          <p className="text-ok">No problems in the {builtCount} built workflows.</p>
        ) : (
          <ul className="divide-y divide-line overflow-hidden rounded-md border border-ink bg-sheet">
            {problems.map((p) => (
              <li key={p.key} className="grid gap-x-4 gap-y-1 px-5 py-3 sm:grid-cols-[8rem_minmax(0,1fr)_auto] sm:items-center">
                <span className="text-sm font-medium">{p.department}</span>
                <span className="flex min-w-0 flex-col">
                  <span className={p.confirm ? "text-rule" : "text-alert"}>{p.text}</span>
                  <span className="truncate text-sm text-muted">{p.workflow}</span>
                </span>
                <button
                  type="button"
                  onClick={() => onOpenWorkflow(p.workflowId)}
                  className="w-fit text-sm text-ai underline underline-offset-4"
                >
                  See the lines that prove it
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
