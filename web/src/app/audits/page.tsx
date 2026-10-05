"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { ErrorNote, PrimaryButton, Working } from "@/components/Section";
import { listChecks, summarize, type SavedCheck } from "@/lib/audits";
import { signIn, signInMessage, useUser } from "@/lib/firebase";

const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

function Outcome({ check }: { check: SavedCheck }) {
  const { problems, toConfirm } = summarize(check);
  if (problems > 0)
    return <span className="font-medium text-alert">{problems} {problems === 1 ? "problem" : "problems"}</span>;
  if (toConfirm.length > 0) return <span className="font-medium text-rule">{toConfirm.length} to confirm</span>;
  return <span className="font-medium text-ok">No problems</span>;
}

function History() {
  const user = useUser();
  const [checks, setChecks] = useState<SavedCheck[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    listChecks(user.uid)
      .then(setChecks)
      .catch(() => setError("OrgFlow couldn't load your health checks. Try again."));
  }, [user]);

  if (user === undefined) return <Working label="Checking your sign-in" />;
  if (user === null)
    return (
      <div className="flex flex-col gap-4">
        <p className="max-w-prose text-lg text-muted">Sign in to see the health checks you have run.</p>
        <div>
          <PrimaryButton onClick={() => signIn().catch((e) => setError(signInMessage(e)))}>Sign in with Google</PrimaryButton>
        </div>
        {error && <ErrorNote message={error} />}
      </div>
    );
  if (error) return <ErrorNote message={error} />;
  if (checks === null) return <Working label="Loading your health checks" />;
  if (checks.length === 0)
    return (
      <div className="flex flex-col gap-4">
        <p className="max-w-prose text-lg text-muted">You haven&apos;t run a health check yet.</p>
        <Link href="/" className="w-fit font-medium text-ai underline underline-offset-4">
          Run your first health check
        </Link>
      </div>
    );

  return (
    <ul className="flex flex-col rounded-md border border-line bg-sheet">
      {checks.map((check) => (
        <li key={check.id} className="border-t border-line first:border-t-0">
          <Link
            href={`/report?id=${check.id}`}
            className="grid gap-x-6 gap-y-1 px-5 py-4 hover:bg-paper sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center"
          >
            <span className="flex min-w-0 flex-col">
              <span className="truncate font-medium">{check.company}</span>
              <span className="truncate text-sm text-muted">{check.documents.policy}</span>
            </span>
            <Outcome check={check} />
            <span className="text-sm text-muted tabular-nums">
              {day(check.checkedAt)}
              {check.shared ? ", shared" : ""}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function AuditsPage() {
  return (
    <>
      <AppHeader />
      <main className="mx-auto flex max-w-6xl flex-col gap-8 px-5 py-10 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h1 className="text-4xl font-semibold tracking-tight">My health checks</h1>
          <Link href="/" className="font-medium text-ai underline underline-offset-4">
            Run a new health check
          </Link>
        </div>
        <div className="max-w-4xl">
          <History />
        </div>
      </main>
    </>
  );
}
