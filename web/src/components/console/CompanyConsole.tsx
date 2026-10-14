"use client";

import { useEffect, useState, type ReactNode } from "react";
import { buildOrder, upstreamOf } from "@/lib/chain";
import { Decisions, openProblems, settledProblems, withDecision, withoutDecision } from "@/lib/decisions";
import { layers } from "./DepartmentCanvas";
import { sampleById } from "@/lib/samples";
import { useBuilds } from "@/lib/useBuilds";
import type { BuiltWorkflow, CaseRecord, Decision, Documents, WorkflowCandidate } from "@/lib/types";
import { MAX_CASES, type Workspace } from "@/lib/workspaces";
import { DocumentNames } from "../Quote";
import { PrintButton } from "../ReportActions";
import { primaryClass } from "../Section";
import { AlertIcon, BuildingIcon, CheckIcon, FlowIcon, MapIcon } from "../Icons";
import { CasesView } from "./CasesView";
import { DocumentsView } from "./DocumentsView";
import { Overview } from "./Overview";
import { PrintReport } from "./PrintReport";
import { SECTIONS, Shell, type Section } from "./Shell";
import { WorkflowsView } from "./WorkflowsView";

const analyzedOn = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

function initialSection(): Section {
  if (typeof window === "undefined") return "overview";
  const hash = window.location.hash.slice(1);
  return SECTIONS.some((s) => s.id === hash) ? (hash as Section) : "overview";
}

/** One company in the console: overview with the department map, workflows, cases and documents. */
export function CompanyConsole({
  workspace,
  docs,
  onDocs,
  editable,
  onBuilt,
  onCases,
  onDecisions,
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
  onDecisions: (decisions: Decision[]) => void;
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
  const [decisions, setDecisions] = useState<Decision[]>(workspace.decisions ?? []);
  const { states, build, buildAll, busy } = useBuilds({ org, candidates, initial: built, docs, onBuilt });
  const canBuild = editable && docs !== null;
  const unbuilt = buildOrder(candidates, built).length;
  const builtList = Object.values(built);
  const problems = builtList.reduce((n, w) => n + openProblems(w, decisions), 0);
  const settled = builtList.reduce((n, w) => n + settledProblems(w, decisions), 0);
  const byHand = candidates.reduce((n, c) => n + c.manual_handoffs, 0);
  const routed = candidates.filter((c) => built[c.id]).reduce((n, c) => n + c.manual_handoffs, 0);

  // Each section is a history entry, so the browser's back button goes to the section before
  const setSection = (s: Section) => {
    if (s !== section) window.history.pushState(null, "", `${window.location.pathname}${window.location.search}#${s}`);
    setSectionState(s);
    window.scrollTo({ top: 0 });
  };
  useEffect(() => {
    const onPop = () => setSectionState(initialSection());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const showProblems = () => {
    setSection("overview");
    requestAnimationFrame(() => document.getElementById("needs-attention")?.scrollIntoView({ behavior: "smooth", block: "start" }));
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
  function changeDecisions(next: Decision[]) {
    setDecisions(next);
    onDecisions(next);
  }
  const decisionsValue = {
    decisions,
    decide: editable ? (d: Decision) => changeDecisions(withDecision(decisions, d)) : undefined,
    undo: editable ? (d: Decision) => changeDecisions(withoutDecision(decisions, d)) : undefined,
  };

  function addCase(record: CaseRecord) {
    const next = [record, ...cases].slice(0, MAX_CASES);
    setCases(next);
    if (editable) onCases(next); // someone viewing a shared company sees their cases here, unsaved
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
    n > 0 ? <span className={`rounded-full px-1.5 py-px text-xs font-semibold tabular-nums ${tone}`}>{n}</span> : undefined;

  return (
    <DocumentNames.Provider value={workspace.documents}>
      <Decisions.Provider value={decisionsValue}>
      <Shell
        company={workspace.company}
        section={section}
        onSection={setSection}
        onNew={onNew}
        badges={{
          overview: badge(problems, "bg-alert text-sheet"),
          workflows: badge(builtCount, "bg-paper text-muted ring-1 ring-line"),
          cases: badge(cases.length, "bg-paper text-muted ring-1 ring-line"),
        }}
      >
        <div className="flex flex-col gap-8">
          {notice}
          {/* The printed report has its own first page with these numbers */}
          <header className="flex flex-col gap-6 print:hidden">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="flex min-w-0 flex-col gap-1">
                <p className="text-sm text-muted">
                  Analyzed {analyzedOn(workspace.analyzedAt)}
                  {workspace.sample ? ", a fictional sample company" : ""}
                </p>
                <h1 className="text-[1.75rem] leading-tight font-semibold tracking-tight text-balance sm:text-[2rem]">
                  {workspace.company}
                </h1>
              </div>
              <div className="flex flex-wrap gap-2.5 print:hidden">
                <PrintButton />
                {canBuild && unbuilt > 0 && (
                  <button type="button" onClick={buildAll} disabled={busy} className={primaryClass}>
                    <FlowIcon />
                    {busy ? "Building…" : `Build ${unbuilt} linked ${unbuilt === 1 ? "workflow" : "workflows"}`}
                  </button>
                )}
              </div>
            </div>
            {section === "overview" && (
            <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                {
                  label: "Departments",
                  value: map.departments.length,
                  note: `linked by ${map.handoffs.length} ${map.handoffs.length === 1 ? "kind of handoff" : "kinds of handoff"}`,
                  Icon: BuildingIcon,
                  tone: "bg-ai-soft text-ai",
                },
                {
                  label: "Manual hand-offs per case",
                  value: byHand,
                  note: `today, before OrgFlow, in ${candidates.length} ${candidates.length === 1 ? "process" : "processes"}`,
                  Icon: MapIcon,
                  tone: "bg-ai-soft text-ai",
                },
                {
                  label: "Routed automatically",
                  value: `${routed} of ${byHand}`,
                  note: `${builtCount} of ${candidates.length} workflows built`,
                  Icon: FlowIcon,
                  tone: routed ? "bg-ok-soft text-ok" : "bg-paper text-faint",
                },
                {
                  label: "Places a case stops",
                  value: problems,
                  note: problems
                    ? settled
                      ? `open, ${settled} decided`
                      : "each needs one decision"
                    : settled
                      ? `${settled} settled by your decisions`
                      : builtCount
                        ? "None found"
                        : "Checked as workflows are built",
                  Icon: !problems && settled ? CheckIcon : AlertIcon,
                  tone: problems ? "bg-alert-soft text-alert" : settled ? "bg-ok-soft text-ok" : "bg-paper text-faint",
                  alert: problems > 0,
                  onClick: problems + settled > 0 ? showProblems : undefined,
                },
              ].map(({ label, value, note, Icon, tone, alert, onClick }) => {
                const inner = (
                  <>
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl sm:h-10 sm:w-10 ${tone}`}>
                      <Icon width="19" height="19" />
                    </span>
                    <div className="flex min-w-0 flex-col">
                      <dt className="text-xs leading-tight text-muted sm:text-sm">{label}</dt>
                      <dd className={`text-xl font-semibold tabular-nums ${alert ? "text-alert" : ""}`}>{value}</dd>
                      <dd className="text-xs leading-snug text-faint">{note}</dd>
                    </div>
                  </>
                );
                const className = "card flex items-center gap-3 px-3.5 py-3 text-left sm:gap-3.5 sm:px-4 sm:py-3.5";
                // A dl may only hold dt/dd groups in divs; the clickable card is a div with a button role
                return onClick ? (
                  <div
                    key={label}
                    role="button"
                    tabIndex={0}
                    onClick={onClick}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onClick())}
                    aria-label={`${label}: ${value}. Show them`}
                    className={`${className} cursor-pointer hover:border-faint`}
                  >
                    {inner}
                  </div>
                ) : (
                  <div key={label} className={className}>
                    {inner}
                  </div>
                );
              })}
            </dl>
            )}
            {section === "overview" && byHand > 0 && (
              <p className="-mt-2 text-xs text-faint">
                Hand-offs are counted by Gemini from your documents: how many times one case changes hands today.
              </p>
            )}
            {section === "overview" && problems > 0 && (
              <button
                type="button"
                onClick={showProblems}
                className="flex w-full items-center gap-3 rounded-xl border border-alert/25 bg-alert-soft px-4 py-3 text-left text-alert print:hidden"
              >
                <AlertIcon className="shrink-0" />
                <span className="flex-1">
                  {problems === 1 ? "1 place a case stops needs" : `${problems} places a case stops need`} your decision.
                </span>
                <span className="font-medium whitespace-nowrap">Review them ↓</span>
              </button>
            )}
            {editable && !docs && unbuilt > 0 && workspace.sample && (
              // A sample's documents come from the site itself; they failed to load, so the page says that
              <p className="text-sm text-muted print:hidden" role="status">
                The sample&apos;s documents didn&apos;t load, so its workflows can&apos;t be built yet. Reload the page
                to try again.
              </p>
            )}
            {editable && !docs && unbuilt > 0 && !workspace.sample && (
              <p className="text-sm text-muted print:hidden">
                To build more workflows, add the documents again under{" "}
                <button type="button" onClick={() => setSection("documents")} className="font-medium text-ai hover:underline">
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
            {section === "cases" && (
              <CasesView
                plan={candidates}
                built={built}
                org={org}
                cases={cases}
                editable={editable}
                examples={workspace.sample ? sampleById(workspace.sampleId).examples : undefined}
                onCase={addCase}
                onResolve={openInWorkflows}
              />
            )}
            {section === "documents" && <DocumentsView workspace={workspace} docs={docs} editable={editable} onDocs={onDocs} />}
          </div>
          {/* Paper can't change a decision: the printed report reads them only */}
          <Decisions.Provider value={{ decisions }}>
            <PrintReport workspace={workspace} />
          </Decisions.Provider>
        </div>
      </Shell>
      </Decisions.Provider>
    </DocumentNames.Provider>
  );
}
