"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { CompanyConsole } from "@/components/console/CompanyConsole";
import { Shell } from "@/components/console/Shell";
import { AlertIcon, BuildingIcon, FlowIcon, MapIcon } from "@/components/Icons";
import { OwnerActions } from "@/components/ReportActions";
import { ErrorNote, Tag, Working } from "@/components/Section";
import { UploadStep, type DraftDocuments } from "@/components/UploadStep";
import { AnalysisError, runAnalysis, type AnalysisStep } from "@/lib/api";
import { accountsEnabled, signIn, signInMessage, useUser } from "@/lib/firebase";
import type { BuiltWorkflow, CaseRecord, Decision, Documents } from "@/lib/types";
import {
  loadWorkspace,
  saveBuilt,
  saveCases,
  saveDecisions,
  saveWorkspace,
  type SavedWorkspace,
  type Workspace as WorkspaceData,
} from "@/lib/workspaces";

const STEPS: { id: AnalysisStep; label: string }[] = [
  { id: "organization", label: "Reading how the company is organized" },
  { id: "departments", label: "Mapping what each department does and hands to the others" },
  { id: "plan", label: "Planning workflows for each department" },
];

function Progress({ step }: { step: AnalysisStep }) {
  const current = STEPS.findIndex((s) => s.id === step);
  return (
    <ol className="card flex flex-col gap-4 p-5">
      {STEPS.map((s, i) => (
        <li key={s.id} className="flex items-center gap-3">
          <span
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs tabular-nums ${
              i < current ? "border-ok bg-ok text-sheet" : i === current ? "border-ai bg-ai-soft text-ai" : "border-line text-faint"
            }`}
          >
            {i < current ? "✓" : i + 1}
          </span>
          {i === current ? <Working label={s.label} /> : <span className={i < current ? "" : "text-muted"}>{s.label}</span>}
        </li>
      ))}
      <p className="text-sm text-muted">Usually 30 to 45 seconds. Long documents take up to two minutes.</p>
    </ol>
  );
}

const LOOKS_FOR = [
  {
    title: "What each department does",
    text: "Gemini reads the org chart and your policies, and writes down each department's work with the line that says so.",
  },
  {
    title: "How work moves between departments",
    text: "Where a request, an order or an invoice goes next. These handoffs become the links between workflows.",
  },
  {
    title: "A workflow for each department",
    text: "Build one per department and they chain: a purchase request in Operations can run on through Procurement and Finance.",
  },
  {
    title: "Where requests get stuck",
    text: "An approver the org chart doesn't have, or an amount no approval level clearly covers, with the lines that prove it. Decide once, and every case after follows your decision.",
  },
];

type View =
  | { status: "idle" }
  | { status: "analyzing"; step: AnalysisStep }
  | { status: "error"; message: string; problems: string[]; retry?: () => void }
  | { status: "loading" }
  | { status: "missing" }
  | { status: "ready"; workspace: WorkspaceData; saved: SavedWorkspace | null; saveError?: string };

function Home() {
  const user = useUser();
  const router = useRouter();
  const id = useSearchParams().get("id");
  const [draft, setDraft] = useState<DraftDocuments>({ policies: [] });
  const [docs, setDocs] = useState<Documents | null>(null);
  const [view, setView] = useState<View>({ status: "idle" });
  const needsSignIn = accountsEnabled && user === null;
  const savedId = view.status === "ready" ? view.saved?.id : undefined;

  // A saved company opened from its link: wait until Firebase knows who is reading
  useEffect(() => {
    if (!id || user === undefined || id === savedId) return;
    let cancelled = false;
    loadWorkspace(id)
      .then((saved) => {
        if (cancelled) return;
        setView(saved ? { status: "ready", workspace: saved, saved } : { status: "missing" });
        if (saved) document.title = `OrgFlow, ${saved.company}`;
      })
      .catch(() => !cancelled && setView({ status: "error", message: "OrgFlow couldn't load this company. Try again.", problems: [] }));
    return () => {
      cancelled = true;
    };
  }, [id, user, savedId]);

  async function analyze(d: Documents, sample: boolean) {
    let owner = user ?? null;
    if (!sample && accountsEnabled && !owner) {
      try {
        owner = await signIn();
      } catch (e) {
        setView({ status: "error", message: signInMessage(e), problems: [] });
        return;
      }
    }
    setDocs(d);
    setView({ status: "analyzing", step: "organization" });
    let workspace: WorkspaceData;
    try {
      const analysis = await runAnalysis(d, (step) => setView({ status: "analyzing", step }));
      workspace = {
        ...analysis,
        company: analysis.organization.company,
        documents: { orgChart: d.orgChart.name, policies: d.policies.map((p) => p.name) },
        built: {},
        analyzedAt: new Date().toISOString(),
        sample,
      };
    } catch (e) {
      const err = e as AnalysisError;
      setView({ status: "error", message: err.message, problems: err.problems ?? [], retry: () => analyze(d, sample) });
      return;
    }
    document.title = `OrgFlow, ${workspace.company}`;
    if (!owner) {
      setView({ status: "ready", workspace, saved: null });
      return;
    }
    try {
      const newId = await saveWorkspace(workspace, owner.uid);
      setView({ status: "ready", workspace, saved: { ...workspace, id: newId, owner: owner.uid, shared: false } });
      window.history.replaceState(null, "", `/?id=${newId}`);
    } catch {
      setView({ status: "ready", workspace, saved: null, saveError: "OrgFlow couldn't save this company. You can still work with it here." });
    }
  }

  function onBuilt(built: Record<string, BuiltWorkflow>) {
    if (savedId) {
      saveBuilt(savedId, built).then(
        () => setView((v) => (v.status === "ready" && v.saved?.id === savedId ? { ...v, saveError: undefined } : v)),
        () =>
          setView((v) =>
            v.status === "ready" && v.saved?.id === savedId
              ? { ...v, saveError: "The latest workflows aren't saved yet. They'll be saved with the next one you build." }
              : v,
          ),
      );
    }
    setView((v) =>
      v.status === "ready"
        ? { ...v, workspace: { ...v.workspace, built }, saved: v.saved ? { ...v.saved, built } : null }
        : v,
    );
  }

  function onCases(cases: CaseRecord[]) {
    if (savedId) saveCases(savedId, cases).catch(() => undefined);
    setView((v) => (v.status === "ready" ? { ...v, workspace: { ...v.workspace, cases } } : v));
  }

  function onDecisions(decisions: Decision[]) {
    if (savedId) saveDecisions(savedId, decisions).catch(() => undefined);
    setView((v) => (v.status === "ready" ? { ...v, workspace: { ...v.workspace, decisions } } : v));
  }

  function startOver() {
    setView({ status: "idle" });
    window.history.replaceState(null, "", "/");
  }

  if (view.status === "ready") {
    const isOwner = Boolean(view.saved && user && view.saved.owner === user.uid);
    const editable = !view.saved || isOwner;
    return (
      <CompanyConsole
        key={view.saved?.id ?? view.workspace.analyzedAt}
        workspace={view.workspace}
        docs={docs}
        onDocs={setDocs}
        editable={editable}
        onBuilt={onBuilt}
        onCases={onCases}
        onDecisions={onDecisions}
        onNew={startOver}
        notice={
          (!view.saved || view.saveError) && (
            <p role="status" className="rounded-xl border border-ai/20 bg-ai-soft px-4 py-3 text-sm text-ai print:hidden">
              {view.saveError ??
                (accountsEnabled ? "This isn't saved. Sign in before your next analysis to keep it and share it." : "This isn't saved.")}
            </p>
          )
        }
        ownerActions={isOwner && view.saved ? <OwnerActions workspace={view.saved} onDeleted={() => router.push("/companies")} /> : undefined}
      />
    );
  }

  if (view.status === "loading" || (id && view.status === "idle"))
    return (
      <Shell current="new" onNew={startOver}>
        <Working label="Opening the company" />
      </Shell>
    );
  if (view.status === "missing")
    return (
      <Shell current="new" onNew={startOver}>
        <div className="flex flex-col gap-4">
          <h1 className="text-3xl font-semibold tracking-tight">This company isn&apos;t available</h1>
          <p className="max-w-prose text-lg text-muted">
            It may have been deleted, or its owner stopped sharing it. {user ? "" : "If it's yours, sign in to open it."}
          </p>
        </div>
      </Shell>
    );

  return (
    <Shell current="new" onNew={startOver}>
      <main className="grid max-w-6xl gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
        <div className="flex flex-col gap-8">
          <div className="flex flex-col gap-4">
            <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              Stop requests from getting stuck between departments
            </h1>
            <p className="max-w-xl text-lg leading-relaxed text-muted">
              Upload your org chart and policies. OrgFlow maps how work moves from department to department, finds where
              your own rules leave a request with no one to approve it, and builds linked workflows that route the rest
              on their own.
            </p>
          </div>
          {view.status === "analyzing" ? (
            <Progress step={view.step} />
          ) : (
            <UploadStep docs={draft} onDocs={setDraft} onRun={analyze} busy={false} needsSignIn={needsSignIn} />
          )}
          {view.status === "error" && <ErrorNote message={view.message} problems={view.problems} onRetry={view.retry} />}
        </div>
        <aside className="card flex h-fit flex-col gap-6 p-6">
          <h2 className="text-lg font-semibold">What you get</h2>
          <ul className="flex flex-col gap-5">
            {LOOKS_FOR.map((item, i) => {
              const Icon = [BuildingIcon, MapIcon, FlowIcon, AlertIcon][i] ?? FlowIcon;
              return (
                <li key={item.title} className="flex gap-3">
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                      i === 3 ? "bg-alert-soft text-alert" : "bg-ai-soft text-ai"
                    }`}
                  >
                    <Icon />
                  </span>
                  <span className="flex flex-col gap-0.5">
                    <span className="font-medium">{item.title}</span>
                    <span className="text-sm leading-relaxed text-muted">{item.text}</span>
                  </span>
                </li>
              );
            })}
          </ul>
          <div className="flex flex-col gap-2 border-t border-line pt-5 text-sm text-muted">
            <div className="flex gap-2">
              <Tag kind="gemini" />
              <Tag kind="rules" />
            </div>
            <p>Gemini reads the documents and designs. Plain code checks every quote and runs every case.</p>
            <p>OrgFlow runs on Gemini 3.8 Flash, Google ADK, Cloud Run, Firebase Authentication, Firestore and Firebase Hosting.</p>
          </div>
        </aside>
      </main>
    </Shell>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<Working label="Loading" />}>
      <Home />
    </Suspense>
  );
}
