"use client";

import { useEffect, useState, type ReactNode } from "react";
import { buildOrder, upstreamOf } from "@/lib/chain";
import { layers } from "./DepartmentCanvas";
import { useBuilds } from "@/lib/useBuilds";
import type { BuiltWorkflow, CaseRecord, Documents, WorkflowCandidate } from "@/lib/types";
import { MAX_CASES, type Workspace } from "@/lib/workspaces";
import { DepartmentSection } from "../DepartmentSection";
import { DocumentNames } from "../Quote";
import { buttonClass, PrintButton } from "../ReportActions";
import { CasesView } from "./CasesView";
import { DocumentsView } from "./DocumentsView";
import { Overview, problemsOf } from "./Overview";
import { SECTIONS, Shell, type Section } from "./Shell";
import { WorkflowsView } from "./WorkflowsView";

const analyzedOn = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

function initialSection(): Section {
  if (typeof window === "undefined") return "overview";
  const hash = window.location.hash.slice(1);
  return SECTIONS.some((s) => s.id === hash) ? (hash as Section) : "overview";
}

/** The whole company on paper, for Save as PDF: every department with its workflows and problems. */
function PrintReport({ workspace }: { workspace: Workspace }) {
  const { departmentMap: map, organization: org, plan, built } = workspace;
  const { columns } = layers(map.departments.map((d) => d.name), map.handoffs);
  return (
    <div className="hidden print:block">
      <p className="mt-6">How work moves: {map.handoffs.map((h) => `${h.from} → ${h.to} (${h.what})`).join("; ") || "no handoffs found"}.</p>
      <p className="text-sm text-muted">Departments in the order work flows: {columns.map((c) => c.join(", ")).join(" → ")}.</p>
      {map.departments.map((profile) => (
        <DepartmentSection
          key={profile.name}
          profile={profile}
          map={map}
          org={org}
          candidates={plan.workflows.filter((c) => c.department === profile.name)}
          built={built}
          states={{}}
          blockedBy={() => undefined}
          canBuild={false}
          onBuild={() => undefined}
        />
      ))}
    </div>
  );
}

/** One company in the console: overview with the department map, workflows, cases and documents. */
export function CompanyConsole({
  workspace,
  docs,
  onDocs,
  editable,
  onBuilt,
  onCases,
  onNew,
  notice,
  ownerActions,
}: {
  workspace: Workspace;
  docs: Documents | null;
  onDocs: (docs: Documents) => void;
  editable: boolean;
  onBuilt: (built: Record<string, BuiltWorkflow>) => void;
  onCases: (cases: CaseRecord[]) => void;
  onNew: () => void;
  notice?: ReactNode;
  ownerActions?: ReactNode;
}) {
  const { departmentMap: map, organization: org, plan, built } = workspace;
  const candidates = plan.workflows;
  const [section, setSectionState] = useState<Section>(initialSection);
  const [selected, setSelected] = useState<string | null>(() => layers(map.departments.map((d) => d.name), map.handoffs).columns[0]?.[0] ?? map.departments[0]?.name ?? null);
  const [openWorkflow, setOpenWorkflow] = useState<string | null>(null);
  const [cases, setCases] = useState<CaseRecord[]>(workspace.cases ?? []);
  const { states, build, buildAll, busy } = useBuilds({ org, candidates, initial: built, docs, onBuilt });
  const canBuild = editable && docs !== null;
  const unbuilt = buildOrder(candidates, built).length;
  const problems = problemsOf(workspace).filter((p) => !p.confirm).length;

  const setSection = (s: Section) => {
    setSectionState(s);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${s}`);
    window.scrollTo({ top: 0 });
  };
  const openInWorkflows = (id: string) => {
    setOpenWorkflow(id);
    setSection("workflows");
    requestAnimationFrame(() => document.getElementById(`wf-${id}`)?.scrollIntoView({ block: "start" }));
  };
  const blockedBy = (c: WorkflowCandidate) => {
    const upstream = upstreamOf(c, candidates, built);
    return upstream && !built[upstream.id] ? upstream : undefined;
  };
  function addCase(record: CaseRecord) {
    const next = [record, ...cases].slice(0, MAX_CASES);
    setCases(next);
    onCases(next);
  }

  // Save as PDF prints the full report: open its folded sections first, and fold them back after
  useEffect(() => {
    let opened: HTMLDetailsElement[] = [];
    const before = () => {
      opened = [...document.querySelectorAll<HTMLDetailsElement>("details:not([open])")];
      opened.forEach((d) => (d.open = true));
    };
    const after = () => opened.forEach((d) => (d.open = false));
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  const builtCount = Object.keys(built).length;
  const badge = (n: number, tone: string) =>
    n > 0 ? <span className={`rounded-full px-1.5 text-xs font-semibold tabular-nums ${tone}`}>{n}</span> : undefined;

  return (
    <DocumentNames.Provider value={workspace.documents}>
      <Shell
        company={workspace.company}
        section={section}
        onSection={setSection}
        onNew={onNew}
        badges={{
          overview: badge(problems, "bg-alert text-sheet"),
          workflows: badge(builtCount, "bg-line text-ink"),
          cases: badge(cases.length, "bg-line text-ink"),
        }}
      >
        <div className="flex flex-col gap-8">
          {notice}
          <header className="flex flex-col gap-5 border-b border-ink pb-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="flex min-w-0 flex-col gap-1">
                <p className="text-sm text-muted">
                  Analyzed {analyzedOn(workspace.analyzedAt)}
                  {workspace.sample ? ", a fictional sample company" : ""}
                </p>
                <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">{workspace.company}</h1>
              </div>
              <div className="flex flex-wrap gap-3 print:hidden">
                {canBuild && unbuilt > 0 && (
                  <button type="button" onClick={buildAll} disabled={busy} className={`${buttonClass} border-ink bg-ink text-sheet hover:bg-ai`}>
                    {busy ? "Building…" : `Build ${unbuilt} linked ${unbuilt === 1 ? "workflow" : "workflows"}`}
                  </button>
                )}
                <PrintButton />
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:flex sm:flex-wrap sm:gap-x-10">
              {[
                ["Departments", map.departments.length],
                ["Handoffs", map.handoffs.length],
                ["Workflows built", `${builtCount} of ${candidates.length}`],
                ["Problems", problems],
              ].map(([label, value]) => (
                <div key={label} className="flex flex-col">
                  <dt className="text-sm text-muted">{label}</dt>
                  <dd className={`text-2xl font-semibold tabular-nums ${label === "Problems" && Number(value) > 0 ? "text-alert" : ""}`}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            {editable && !docs && unbuilt > 0 && (
              <p className="text-sm text-muted print:hidden">
                To build more workflows, add the documents again under{" "}
                <button type="button" onClick={() => setSection("documents")} className="text-ai underline underline-offset-4">
                  Documents
                </button>
                . OrgFlow doesn&apos;t keep your PDFs.
              </p>
            )}
            {ownerActions && <div className="print:hidden">{ownerActions}</div>}
          </header>

          <div className="print:hidden">
            {section === "overview" && (
              <Overview
                workspace={workspace}
                selected={selected}
                onSelect={setSelected}
                states={states}
                blockedBy={blockedBy}
                canBuild={canBuild}
                busy={busy}
                onBuild={build}
                onOpenWorkflow={openInWorkflows}
              />
            )}
            {section === "workflows" && (
              <WorkflowsView
                candidates={candidates}
                built={built}
                states={states}
                blockedBy={blockedBy}
                org={org}
                canBuild={canBuild}
                busy={busy}
                open={openWorkflow}
                onOpen={setOpenWorkflow}
                onBuild={build}
              />
            )}
            {section === "cases" && <CasesView plan={candidates} built={built} org={org} cases={cases} onCase={addCase} />}
            {section === "documents" && <DocumentsView workspace={workspace} docs={docs} editable={editable} onDocs={onDocs} />}
          </div>
          <PrintReport workspace={workspace} />
        </div>
      </Shell>
    </DocumentNames.Provider>
  );
}
