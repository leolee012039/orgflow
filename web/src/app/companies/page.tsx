"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Shell } from "@/components/console/Shell";
import { ErrorNote, PrimaryButton, Working } from "@/components/Section";
import { signIn, signInMessage, useUser } from "@/lib/firebase";
import { findings, listWorkspaces, type SavedWorkspace } from "@/lib/workspaces";

const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

function Status({ workspace }: { workspace: SavedWorkspace }) {
  const built = Object.keys(workspace.built ?? {}).length;
  const { problems } = findings(workspace.built ?? {});
  return (
    <span className="text-sm">
      {workspace.departmentMap.departments.length} departments, {built} of {workspace.plan.workflows.length} workflows
      built
      {problems > 0 && (
        <span className="font-medium text-alert">
          , {problems} {problems === 1 ? "problem" : "problems"}
        </span>
      )}
    </span>
  );
}

function Companies() {
  const user = useUser();
  const [list, setList] = useState<SavedWorkspace[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    listWorkspaces(user.uid)
      .then(setList)
      .catch(() => setError("OrgFlow couldn't load your companies. Try again."));
  }, [user]);

  if (user === undefined) return <Working label="Checking your sign-in" />;
  if (user === null)
    return (
      <div className="flex flex-col gap-4">
        <p className="max-w-prose text-lg text-muted">Sign in to see the companies you have analyzed.</p>
        <div>
          <PrimaryButton onClick={() => signIn().catch((e) => setError(signInMessage(e)))}>Sign in with Google</PrimaryButton>
        </div>
        {error && <ErrorNote message={error} />}
      </div>
    );
  if (error) return <ErrorNote message={error} />;
  if (list === null) return <Working label="Loading your companies" />;
  if (list.length === 0)
    return (
      <div className="flex flex-col gap-4">
        <p className="max-w-prose text-lg text-muted">You haven&apos;t analyzed a company yet.</p>
        <Link href="/" className="w-fit font-medium text-ai underline underline-offset-4">
          Analyze your first company
        </Link>
      </div>
    );

  return (
    <ul className="flex flex-col rounded-md border border-line bg-sheet">
      {list.map((w) => (
        <li key={w.id} className="border-t border-line first:border-t-0">
          <Link
            href={`/?id=${w.id}`}
            className="grid gap-x-6 gap-y-1 px-5 py-4 hover:bg-paper sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
          >
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate font-medium">{w.company}</span>
              <Status workspace={w} />
            </span>
            <span className="text-sm text-muted tabular-nums">
              {day(w.analyzedAt)}
              {w.shared ? ", shared" : ""}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function CompaniesPage() {
  return (
    <Shell current="companies">
      <main className="flex max-w-5xl flex-col gap-8">
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-ink pb-6">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">My companies</h1>
          <Link href="/" className="font-medium text-ai underline underline-offset-4">
            Analyze a company
          </Link>
        </div>
        <Companies />
      </main>
    </Shell>
  );
}
