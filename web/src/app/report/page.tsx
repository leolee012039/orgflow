"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { Report } from "@/components/Report";
import { OwnerActions, PrintButton } from "@/components/ReportActions";
import { ErrorNote, Working } from "@/components/Section";
import { loadCheck, type SavedCheck } from "@/lib/audits";
import { useUser } from "@/lib/firebase";

type State =
  | { status: "loading" }
  | { status: "done"; check: SavedCheck }
  | { status: "missing" }
  | { status: "error"; message: string };

function SavedReport() {
  const id = useSearchParams().get("id");
  const user = useUser();
  const router = useRouter();
  const [loaded, setState] = useState<State>({ status: "loading" });
  const state: State = id ? loaded : { status: "missing" };

  useEffect(() => {
    if (user === undefined || !id) return; // wait until Firebase knows who is reading
    let cancelled = false;
    loadCheck(id)
      .then((check) => !cancelled && setState(check ? { status: "done", check } : { status: "missing" }))
      .catch(() => !cancelled && setState({ status: "error", message: "OrgFlow couldn't load this report. Try again." }));
    return () => {
      cancelled = true;
    };
  }, [id, user]);

  const company = state.status === "done" ? state.check.company : null;
  useEffect(() => {
    // The saved PDF takes its file name from the page title
    if (company) document.title = `OrgFlow health check, ${company}`;
  }, [company]);

  if (state.status === "loading") return <Working label="Opening the report" />;
  if (state.status === "error") return <ErrorNote message={state.message} />;
  if (state.status === "missing")
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-3xl font-semibold tracking-tight">This report isn&apos;t available</h1>
        <p className="max-w-prose text-lg text-muted">
          It may have been deleted, or its owner stopped sharing it.{" "}
          {user ? "" : "If it's yours, sign in to open it."}
        </p>
        <Link href="/" className="w-fit font-medium text-ai underline underline-offset-4">
          Run a health check
        </Link>
      </div>
    );

  const isOwner = user?.uid === state.check.owner;
  return (
    <Report
      check={state.check}
      actions={isOwner ? <OwnerActions check={state.check} onDeleted={() => router.push("/audits")} /> : <PrintButton />}
    />
  );
}

export default function ReportPage() {
  return (
    <>
      <AppHeader />
      <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
        <div className="max-w-4xl">
          <Suspense fallback={<Working label="Opening the report" />}>
            <SavedReport />
          </Suspense>
        </div>
      </main>
    </>
  );
}
