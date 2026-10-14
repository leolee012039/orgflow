"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { CompanyConsole } from "@/components/console/CompanyConsole";
import { Shell } from "@/components/console/Shell";
import { AlertIcon, BuildingIcon, FlowIcon, MapIcon } from "@/components/Icons";
import { OwnerActions } from "@/components/ReportActions";
import { ErrorNote, Tag, Working } from "@/components/Section";
import { UploadStep, type DraftDocuments } from "@/components/UploadStep";
import { AnalysisError, loadSampleDocuments, runAnalysis, type AnalysisStep } from "@/lib/api";
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

function Progress({ step, sample }: { step: AnalysisStep; sample: boolean }) {
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
      <p className="text-sm text-muted">
        {sample
          ? "Opening the saved sample: it takes a second or two."
          : "Usually 30 to 45 seconds. Long documents take up to two minutes."}
      </p>
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
  | { status: "analyzing"; step: AnalysisStep; sample: boolean }
  | { status: "error"; message: string; problems: string[]; retry?: () => void }
  | { status: "loading" }
  | { status: "missing" }
  | { status: "ready"; workspace: WorkspaceData; saved: SavedWorkspace | null; saveError?: string };

// An analysis that isn't saved to an account (the sample, or when saving failed) is kept for this
// browser tab, so a reload or the back button doesn't lose it. New analysis clears it.
const UNSAVED_KEY = "orgflow.unsaved";

function readUnsaved(): WorkspaceData | null {
  try {
    const raw = sessionStorage.getItem(UNSAVED_KEY);
    const workspace = raw ? (JSON.parse(raw) as WorkspaceData) : null;
    return workspace?.organization && workspace.departmentMap && workspace.plan ? workspace : null;
  } catch {
    return null; // storage refused, or something else wrote there
  }
}

function writeUnsaved(workspace: WorkspaceData | null) {
  try {
    if (workspace) sessionStorage.setItem(UNSAVED_KEY, JSON.stringify(workspace));
    else sessionStorage.removeItem(UNSAVED_KEY);
  } catch {
    // A private window may refuse storage: the analysis still works, it just won't survive a reload
  }
}

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

  useEffect(() => {
    if (id) return;
    const unsaved = readUnsaved();
    if (!unsaved) return;
    let cancelled = false;
    // The sample's documents come back too, so its workflows can still be built
    // If they fail to load, the console says so where the builds would be
    const sampleDocs = unsaved.sample
      ? loadSampleDocuments(unsaved.sampleId).catch((e) => {
          console.warn("The sample's documents didn't load:", e);
          return null;
        })
      : Promise.resolve(null);
    sampleDocs.then((d) => {
      if (cancelled) return;
      if (d) setDocs(d);
      setView((v) => (v.status === "idle" ? { status: "ready", workspace: unsaved, saved: null } : v));
      document.title = `OrgFlow, ${unsaved.company}`;
    });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (view.status === "ready") writeUnsaved(view.saved ? null : view.workspace);
  }, [view]);

  /** sampleId: one of the sample companies, which open from their saved reading without an account */
  async function analyze(d: Documents, sampleId: string | null) {
    const sample = sampleId !== null;
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
    setView({ status: "analyzing", step: "organization", sample });
    let workspace: WorkspaceData;
    try {
      const analysis = await runAnalysis(d, (step) => setView({ status: "analyzing", step, sample }));
      workspace = {
        ...analysis,
        company: analysis.organization.company,
        documents: { orgChart: d.orgChart.name, policies: d.policies.map((p) => p.name) },
        built: {},
        analyzedAt: new Date().toISOString(),
        sample,
        ...(sampleId ? { sampleId } : {}),
      };
    } catch (e) {
      const err = e as AnalysisError;
      setView({ status: "error", message: err.message, problems: err.problems ?? [], retry: () => analyze(d, sampleId) });
      return;
    }
    document.title = `OrgFlow, ${workspace.company}`;
    window.scrollTo({ top: 0 }); // on a phone the button that started it is far down the page
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

  // Only the owner's changes are saved: a shared company opened by its link is read-only
  const ownsSaved = view.status === "ready" && Boolean(view.saved && user && view.saved.owner === user.uid);

  /** Save in the background and say so when it fails: every save writes the whole list, so the next change
   * saves this one too. */
  function save(saving: Promise<unknown>, what: string) {
    saving.then(
      () => setView((v) => (v.status === "ready" && v.saved?.id === savedId ? { ...v, saveError: undefined } : v)),
      () =>
        setView((v) =>
          v.status === "ready" && v.saved?.id === savedId
            ? { ...v, saveError: `The latest ${what} aren't saved yet. They'll be saved with your next change.` }
            : v,
        ),
    );
  }

  function onBuilt(built: Record<string, BuiltWorkflow>) {
    if (savedId && ownsSaved) save(saveBuilt(savedId, built), "workflows");
    setView((v) =>
      v.status === "ready"
        ? { ...v, workspace: { ...v.workspace, built }, saved: v.saved ? { ...v.saved, built } : null }
        : v,
    );
  }

  function onCases(cases: CaseRecord[]) {
    if (savedId && ownsSaved) save(saveCases(savedId, cases), "cases");
    setView((v) => (v.status === "ready" ? { ...v, workspace: { ...v.workspace, cases } } : v));
  }

  function onDecisions(decisions: Decision[]) {
    if (savedId && ownsSaved) save(saveDecisions(savedId, decisions), "decisions");
    setView((v) => (v.status === "ready" ? { ...v, workspace: { ...v.workspace, decisions } } : v));
  }

  function startOver() {
    writeUnsaved(null);
    // A sample puts its own PDFs in the picker; a new analysis starts without them
    setDraft({ policies: [] });
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
                (view.workspace.sample
                  ? accountsEnabled
                    ? "This is the sample company. Sign in to analyze your own documents and save them."
                    : "This is the sample company."
                  : accountsEnabled
                    ? "This isn't saved to an account: it stays in this tab until you start a new analysis. Sign in before your next analysis to keep it and share it."
                    : "This isn't saved to an account: it stays in this tab until you start a new analysis.")}
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
            <Progress step={view.step} sample={view.sample} />
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
