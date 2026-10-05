"use client";

import { useState } from "react";
import { orderedBuilt } from "@/lib/chain";
import type { BuiltWorkflow, CaseRecord, Organization, WorkflowCandidate } from "@/lib/types";
import { CaseRun, caseResult, ChainSlip } from "../CaseRun";

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Run a case across departments, and every case run so far. */
export function CasesView({
  plan,
  built,
  org,
  cases,
  onCase,
}: {
  plan: WorkflowCandidate[];
  built: Record<string, BuiltWorkflow>;
  org: Organization;
  cases: CaseRecord[];
  onCase: (record: CaseRecord) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const ordered = orderedBuilt(plan, built);
  const next = cases.reduce((n, c) => Math.max(n, Number(c.id.replace(/\D/g, "")) || 0), 0) + 1;

  return (
    <div className="flex flex-col gap-12">
      {Object.keys(built).length === 0 ? (
        <div className="rounded-md border border-dashed border-line px-5 py-10 text-muted">
          Build a workflow first. Then you can submit a case here and watch it move from department to department.
        </div>
      ) : (
        <CaseRun plan={plan} built={built} org={org} nextNumber={next} onCase={onCase} />
      )}

      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold">Case history</h2>
        {cases.length === 0 ? (
          <p className="text-muted">No cases yet. Each case you run is listed here with where it went and how it ended.</p>
        ) : (
          <ul className="divide-y divide-line overflow-hidden rounded-md border border-ink bg-sheet">
            {cases.map((c) => {
              const result = caseResult(c.trace, ordered);
              const isOpen = open === c.id;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => setOpen(isOpen ? null : c.id)}
                    aria-expanded={isOpen}
                    className="grid w-full gap-x-4 gap-y-1 px-5 py-3 text-left hover:bg-paper sm:grid-cols-[6rem_8rem_minmax(0,1fr)_minmax(0,1.4fr)] sm:items-center"
                  >
                    <span className="font-medium tabular-nums">{c.id}</span>
                    <span className="text-sm text-muted tabular-nums">{when(c.at)}</span>
                    <span className="text-sm">{c.trace.legs.map((l) => l.department).join(" → ")}</span>
                    <span className={`text-sm font-medium ${result.ok ? "text-ok" : "text-alert"}`}>{result.text}</span>
                  </button>
                  {isOpen && (
                    <div className="border-t border-line bg-paper px-5 py-5">
                      <ChainSlip trace={c.trace} built={ordered} org={org} request={c.request} animate={false} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
