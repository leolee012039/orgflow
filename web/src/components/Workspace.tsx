"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { buildOrder, upstreamOf } from "@/lib/chain";
import { findings, type Workspace as WorkspaceData } from "@/lib/workspaces";
import type { BuiltWorkflow, Documents, WorkflowCandidate } from "@/lib/types";
import { CaseRun } from "./CaseRun";
import { DepartmentMap } from "./DepartmentMap";
import { DepartmentSection, type BuildState } from "./DepartmentSection";
import { OrgView } from "./OrgView";
import { DocumentNames } from "./Quote";
import { buttonClass, PrintButton } from "./ReportActions";
import { OriginNote, Tag } from "./Section";
import { DocumentPicker, type DraftDocuments } from "./UploadStep";

const analyzedOn = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

function Part({ title, tags, children, screenOnly }: { title: string; tags?: ReactNode; children: ReactNode; screenOnly?: boolean }) {
  return (
    <section className={`flex flex-col gap-6 border-t border-ink py-10 ${screenOnly ? "print:hidden" : ""}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 break-after-avoid">
        <h2 className="text-3xl font-semibold tracking-tight text-balance">{title}</h2>
        {tags && <div className="flex flex-wrap gap-2">{tags}</div>}
      </div>
      {children}
    </section>
  );
}

function Verdict({ built }: { built: Record<string, BuiltWorkflow> }) {
  const count = Object.keys(built).length;
  const { problems, toConfirm } = findings(built);
  if (count === 0) return null;
  const [text, tone] =
    problems > 0
      ? [`${problems} ${problems === 1 ? "problem" : "problems"}`, "border-alert text-alert"]
      : toConfirm.length > 0
        ? [`${toConfirm.length} to confirm`, "border-rule text-rule"]
        : ["No problems", "border-ok text-ok"];
  return (
    <span className={`stamp inline-block w-fit rounded border-[3px] px-4 py-2 text-xl font-semibold whitespace-nowrap sm:mt-8 ${tone}`}>
      {text}
    </span>
  );
}

/** One company: its department map, each department's workflows to build, and cases run across them. */
export function Workspace({
  workspace,
  docs,
  onDocs,
  editable,
  onBuilt,
  actions,
}: {
  workspace: WorkspaceData;
  /** The PDFs, when this session has them; building needs them */
  docs: Documents | null;
  onDocs: (docs: Documents) => void;
  /** Whether this viewer may build workflows */
  editable: boolean;
  onBuilt: (built: Record<string, BuiltWorkflow>) => void;
  actions?: ReactNode;
}) {
  const { organization: org, departmentMap: map, plan } = workspace;
  const [states, setStates] = useState<Record<string, BuildState>>({});
  const [draft, setDraft] = useState<DraftDocuments>({ policies: [] });
  // Builds that finish while others run must see each other's results before the next render
  const builtRef = useRef(workspace.built);
  useEffect(() => {
    builtRef.current = workspace.built;
  }, [workspace.built]);
  const built = workspace.built;
  const candidates = plan.workflows;

  // Save as PDF prints everything: open the folded sections first, and fold them back after
  useEffect(() => {
    let opened: HTMLDetailsElement[] = [];
    const before = () => {
      opened = [...document.querySelectorAll<HTMLDetailsElement>("article details:not([open])")];
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
  const busy = Object.values(states).some((s) => s.status === "building");
  const canBuild = editable && docs !== null;

  const blockedBy = (c: WorkflowCandidate) => {
    const upstream = upstreamOf(c, candidates, built);
    return upstream && !built[upstream.id] ? upstream : undefined;
  };

  async function build(c: WorkflowCandidate): Promise<boolean> {
    if (!docs) return false;
    const upstream = upstreamOf(c, candidates, builtRef.current);
    setStates((s) => ({ ...s, [c.id]: { status: "building" } }));
    try {
      const result = await api.build(docs, org, c, upstream ? builtRef.current[upstream.id] ?? null : null);
      builtRef.current = { ...builtRef.current, [c.id]: result };
      onBuilt(builtRef.current);
      setStates((s) => Object.fromEntries(Object.entries(s).filter(([key]) => key !== c.id)));
      return true;
    } catch (e) {
      setStates((s) => ({
        ...s,
        [c.id]: { status: "error", message: (e as Error).message, problems: e instanceof ApiError ? e.problems : [] },
      }));
      return false;
    }
  }

  async function buildAll() {
    // Upstream first; workflows whose upstream is ready are built side by side
    let pending = buildOrder(candidates, builtRef.current);
    while (pending.length) {
      const ready = pending.filter((c) => {
        const up = upstreamOf(c, candidates, builtRef.current);
        return !up || builtRef.current[up.id] || !pending.includes(up);
      });
      if (!ready.length) break;
      const results = await Promise.all(ready.map(build));
      pending = pending.filter((c) => !ready.includes(c));
      if (results.some((ok) => !ok)) pending = pending.filter((c) => !blockedBy(c));
    }
  }

  const unbuilt = buildOrder(candidates, built).length;
  const { problems } = findings(built);
  const builtCount = Object.keys(built).length;

  return (
    <DocumentNames.Provider value={workspace.documents}>
      <article className="flex flex-col">
        <header className="flex flex-col gap-6 pb-10">
          <div className="grid items-start gap-6 sm:grid-cols-[minmax(0,1fr)_auto]">
            <div className="flex min-w-0 flex-col gap-2">
              <p className="text-muted">Analyzed {analyzedOn(workspace.analyzedAt)}</p>
              <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">{workspace.company}</h1>
              <p className="text-lg">
                {map.departments.length} departments, {map.handoffs.length}{" "}
                {map.handoffs.length === 1 ? "handoff" : "handoffs"} between them, {candidates.length} workflows
                planned, {builtCount} built
                {builtCount ? (problems ? `, ${problems} ${problems === 1 ? "problem" : "problems"} found` : ", no problems found") : ""}.
              </p>
              <p className="text-sm break-words text-muted">
                Read from {[workspace.documents.orgChart, ...workspace.documents.policies].join(", ")}
                {workspace.sample ? ". NovaGear is a fictional sample company." : "."}
              </p>
            </div>
            <Verdict built={built} />
          </div>
          <div className="flex flex-wrap items-start gap-3 print:hidden">
            {canBuild && unbuilt > 0 && (
              <button type="button" onClick={buildAll} disabled={busy} className={`${buttonClass} border-ink bg-ink text-sheet hover:bg-ai`}>
                Build {unbuilt} linked {unbuilt === 1 ? "workflow" : "workflows"}
              </button>
            )}
            <PrintButton />
          </div>
          {actions && <div className="print:hidden">{actions}</div>}
          {editable && !docs && unbuilt > 0 && (
            <div className="flex flex-col gap-3 rounded-md border border-line bg-sheet p-4 print:hidden">
              <p>OrgFlow doesn&apos;t keep your PDFs. To build more workflows, add the same documents again.</p>
              <DocumentPicker docs={draft} onDocs={setDraft} />
              <div>
                <button
                  type="button"
                  disabled={!draft.orgChart}
                  onClick={() => draft.orgChart && onDocs({ orgChart: draft.orgChart, policies: draft.policies })}
                  className={buttonClass}
                >
                  Use these documents
                </button>
              </div>
            </div>
          )}
        </header>

        <Part title="How work moves between departments" tags={<Tag kind="gemini" />}>
          <p className="max-w-prose text-lg leading-relaxed">
            Gemini read what each department does and where its work goes next. Every box links to the department
            below; every arrow comes with the passage that states it.
          </p>
          <DepartmentMap map={map} org={org} plan={candidates} built={built} />
          <OriginNote origin={workspace.departmentMap.origin} latencyMs={workspace.departmentMap.latency_ms} />
        </Part>

        <Part title="Each department and what to automate" tags={<><Tag kind="gemini" /><Tag kind="rules" /></>}>
          <p className="max-w-prose text-lg leading-relaxed">
            Gemini planned workflows for each department and linked them along the handoffs. Building one turns it into
            rules and steps that plain code runs, and checks it against the org chart.
          </p>
          <div className="flex flex-col">
            {map.departments.map((profile) => (
              <DepartmentSection
                key={profile.name}
                profile={profile}
                map={map}
                org={org}
                candidates={candidates.filter((c) => c.department === profile.name)}
                built={built}
                states={states}
                blockedBy={blockedBy}
                canBuild={canBuild && !busy}
                onBuild={build}
              />
            ))}
          </div>
          <OriginNote origin={workspace.plan.origin} latencyMs={workspace.plan.latency_ms} />
        </Part>

        {builtCount > 0 && (
          <Part title="Run a case across departments" tags={<><Tag kind="rules" /><Tag kind="gemini" /></>} screenOnly>
            <CaseRun plan={candidates} built={built} org={org} />
          </Part>
        )}

        <Part title="The organization as OrgFlow read it" tags={<Tag kind="gemini" />}>
          <OrgView org={org} />
          <OriginNote origin={workspace.organization.origin} latencyMs={workspace.organization.latency_ms} />
        </Part>

        <footer className="border-t border-line pt-6 text-sm text-muted">
          Gemini read the documents, mapped the departments and designed the workflows. Code matched every quote against
          the PDFs, checked every workflow against the org chart, and runs the cases. The PDFs themselves are not saved.
        </footer>
      </article>
    </DocumentNames.Provider>
  );
}
