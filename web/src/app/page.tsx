"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { OwnerActions } from "@/components/ReportActions";
import { ErrorNote, Tag, Working } from "@/components/Section";
import { UploadStep, type DraftDocuments } from "@/components/UploadStep";
import { Workspace } from "@/components/Workspace";
import { AnalysisError, runAnalysis, type AnalysisStep } from "@/lib/api";
import { accountsEnabled, signIn, signInMessage, useUser } from "@/lib/firebase";
import type { BuiltWorkflow, Documents } from "@/lib/types";
import { loadWorkspace, saveBuilt, saveWorkspace, type SavedWorkspace, type Workspace as WorkspaceData } from "@/lib/workspaces";

const STEPS: { id: AnalysisStep; label: string }[] = [
  { id: "organization", label: "Reading how the company is organized" },
  { id: "departments", label: "Mapping what each department does and hands to the others" },
  { id: "plan", label: "Planning workflows for each department" },
];

function Progress({ step }: { step: AnalysisStep }) {
  const current = STEPS.findIndex((s) => s.id === step);
  return (
    <ol className="flex flex-col gap-4 rounded-md border border-line bg-sheet p-5">
      {STEPS.map((s, i) => (
        <li key={s.id} className="flex items-center gap-3">
          <span
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs tabular-nums ${
              i < current ? "border-ink bg-ink text-sheet" : i === current ? "border-ai text-ai" : "border-line text-muted"
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
    title: "Where the rules can't run",
    text: "An approver the org chart doesn't have, or an amount no approval level covers, with the lines that prove it.",
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
    if (savedId) saveBuilt(savedId, built).catch(() => undefined);
    setView((v) =>
      v.status === "ready"
        ? { ...v, workspace: { ...v.workspace, built }, saved: v.saved ? { ...v.saved, built } : null }
        : v,
    );
  }

  if (view.status === "ready") {
    const isOwner = Boolean(view.saved && user && view.saved.owner === user.uid);
    const editable = !view.saved || isOwner;
    return (
      <main className="flex max-w-5xl flex-col gap-6 py-10">
        {(!view.saved || view.saveError) && (
          <p role="status" className="rounded-md border border-line bg-sheet px-4 py-3 text-sm print:hidden">
            {view.saveError ??
              (accountsEnabled ? "This isn't saved. Sign in before your next analysis to keep it and share it." : "This isn't saved.")}
          </p>
        )}
        <Workspace
          workspace={view.workspace}
          docs={docs}
          onDocs={setDocs}
          editable={editable}
          onBuilt={onBuilt}
          actions={
            <div className="flex flex-col gap-3">
              {isOwner && view.saved && <OwnerActions workspace={view.saved} onDeleted={() => router.push("/companies")} />}
              <button
                type="button"
                onClick={() => {
                  setView({ status: "idle" });
                  window.history.replaceState(null, "", "/");
                }}
                className="w-fit text-sm text-ai underline underline-offset-4"
              >
                Analyze another company
              </button>
            </div>
          }
        />
      </main>
    );
  }

  if (view.status === "loading" || (id && view.status === "idle"))
    return (
      <main className="py-10">
        <Working label="Opening the company" />
      </main>
    );
  if (view.status === "missing")
    return (
      <main className="flex flex-col gap-4 py-10">
        <h1 className="text-3xl font-semibold tracking-tight">This company isn&apos;t available</h1>
        <p className="max-w-prose text-lg text-muted">
          It may have been deleted, or its owner stopped sharing it. {user ? "" : "If it's yours, sign in to open it."}
        </p>
      </main>
    );

  return (
    <main className="grid gap-12 py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-4">
          <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Turn your org chart into workflows that hand off to each other
          </h1>
          <p className="max-w-xl text-lg leading-relaxed text-muted">
            Upload an org chart and your policies. OrgFlow maps what each department does and where its work goes, plans
            a workflow for each department, and builds them so a case runs from one department into the next.
          </p>
        </div>
        {view.status === "analyzing" ? (
          <Progress step={view.step} />
        ) : (
          <UploadStep docs={draft} onDocs={setDraft} onRun={analyze} busy={false} needsSignIn={needsSignIn} />
        )}
        {view.status === "error" && <ErrorNote message={view.message} problems={view.problems} onRetry={view.retry} />}
      </div>
      <aside className="flex flex-col gap-6 lg:border-l lg:border-line lg:pl-10">
        <h2 className="text-lg font-semibold">What you get</h2>
        <ul className="flex flex-col gap-5">
          {LOOKS_FOR.map((item) => (
            <li key={item.title} className="flex flex-col gap-1">
              <span className="font-medium">{item.title}</span>
              <span className="text-muted">{item.text}</span>
            </li>
          ))}
        </ul>
        <div className="flex flex-col gap-2 border-t border-line pt-5 text-sm text-muted">
          <div className="flex gap-2">
            <Tag kind="gemini" />
            <Tag kind="rules" />
          </div>
          <p>Gemini reads the documents and designs. Plain code checks every quote and runs every case.</p>
        </div>
      </aside>
    </main>
  );
}

export default function HomePage() {
  return (
    <>
      <AppHeader />
      <div className="mx-auto max-w-6xl px-5 sm:px-8">
        <Suspense fallback={<main className="py-10"><Working label="Loading" /></main>}>
          <Home />
        </Suspense>
        <footer className="border-t border-line py-8 text-sm text-muted print:hidden">
          OrgFlow runs on Gemini 3.8 Flash, Google ADK, Cloud Run, Firebase Authentication, Firestore and Firebase
          Hosting.
        </footer>
      </div>
    </>
  );
}
