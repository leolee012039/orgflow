"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { Report } from "@/components/Report";
import { PrintButton } from "@/components/ReportActions";
import { ErrorNote, Tag, Working } from "@/components/Section";
import { UploadStep } from "@/components/UploadStep";
import { CheckError, runHealthCheck, type CheckStep } from "@/lib/api";
import { saveCheck, type HealthCheck } from "@/lib/audits";
import { accountsEnabled, signIn, signInMessage, useUser } from "@/lib/firebase";
import type { Documents } from "@/lib/types";

type State =
  | { status: "idle" }
  | { status: "running"; step: CheckStep }
  | { status: "error"; message: string; problems: string[]; retry?: () => void }
  | { status: "done"; check: HealthCheck; saveError?: string };

const STEPS: { id: CheckStep; label: string }[] = [
  { id: "organization", label: "Reading how the company is organized" },
  { id: "opportunities", label: "Finding work worth automating" },
  { id: "workflow", label: "Checking the policy against the organization" },
];

function Progress({ step }: { step: CheckStep }) {
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
      <p className="text-sm text-muted">Usually 20 to 40 seconds. Long documents take up to a minute.</p>
    </ol>
  );
}

const LOOKS_FOR = [
  {
    title: "Approvers who don't exist",
    text: "The policy requires a role, such as a Director, that the org chart doesn't have. Every such request would stall.",
  },
  {
    title: "Amounts no rule covers",
    text: "One level says under 100,000 and the next says over 100,000. Exactly 100,000 has no approver.",
  },
  {
    title: "Work worth automating",
    text: "Gemini ranks repetitive, rule-based work and builds the top one into a workflow you can try.",
  },
];

export default function Home() {
  const user = useUser();
  const router = useRouter();
  const [docs, setDocs] = useState<Partial<Documents>>({});
  const [state, setState] = useState<State>({ status: "idle" });
  const needsSignIn = accountsEnabled && user === null;

  async function run(d: Documents, sample: boolean) {
    let owner = user ?? null;
    if (!sample && accountsEnabled && !owner) {
      try {
        owner = await signIn();
      } catch (e) {
        setState({ status: "error", message: signInMessage(e), problems: [] });
        return;
      }
    }
    setState({ status: "running", step: "organization" });
    let check: HealthCheck;
    try {
      check = await runHealthCheck(d, sample, (step) => setState({ status: "running", step }));
    } catch (e) {
      const err = e as CheckError;
      setState({ status: "error", message: err.message, problems: err.problems ?? [], retry: () => run(d, sample) });
      return;
    }
    if (owner) {
      try {
        router.push(`/report?id=${await saveCheck(check, owner.uid)}`);
        return;
      } catch {
        setState({ status: "done", check, saveError: "OrgFlow couldn't save this report. You can still read it here." });
        return;
      }
    }
    setState({ status: "done", check });
  }

  return (
    <>
      <AppHeader />
      <div className="mx-auto max-w-6xl px-5 sm:px-8">
        {state.status === "done" ? (
          <main className="flex max-w-4xl flex-col gap-6 py-10">
            <p role="status" className="rounded-md border border-line bg-sheet px-4 py-3 text-sm print:hidden">
              {state.saveError ??
                (accountsEnabled
                  ? "This report isn't saved. Sign in before your next health check to keep reports and share them."
                  : "This report isn't saved.")}
            </p>
            <Report
              check={state.check}
              actions={
                <div className="flex flex-wrap gap-3">
                  <PrintButton />
                  <button
                    type="button"
                    onClick={() => setState({ status: "idle" })}
                    className="rounded-md border border-line px-4 py-2 font-medium hover:border-ink"
                  >
                    Run another health check
                  </button>
                </div>
              }
            />
          </main>
        ) : (
          <main className="grid gap-12 py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
            <div className="flex flex-col gap-8">
              <div className="flex flex-col gap-4">
                <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
                  Find where your policy can&apos;t run in your organization
                </h1>
                <p className="max-w-xl text-lg leading-relaxed text-muted">
                  Upload an org chart and a policy. OrgFlow reports every place a request would get stuck, with the
                  lines that prove it, then builds a workflow for the parts that can run.
                </p>
              </div>
              {state.status === "running" ? (
                <Progress step={state.step} />
              ) : (
                <UploadStep docs={docs} onDocs={setDocs} onRun={run} busy={false} needsSignIn={needsSignIn} />
              )}
              {state.status === "error" && (
                <ErrorNote message={state.message} problems={state.problems} onRetry={state.retry} />
              )}
            </div>
            <aside className="flex flex-col gap-6 lg:border-l lg:border-line lg:pl-10">
              <h2 className="text-lg font-semibold">What the health check looks for</h2>
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
                <p>Gemini reads the documents. Plain code checks every quote and finds every problem.</p>
              </div>
            </aside>
          </main>
        )}
        <footer className="border-t border-line py-8 text-sm text-muted print:hidden">
          OrgFlow runs on Gemini 3.8 Flash, Google ADK, Cloud Run, Firebase Authentication, Firestore and Firebase
          Hosting.
        </footer>
      </div>
    </>
  );
}
