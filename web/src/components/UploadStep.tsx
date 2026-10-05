"use client";

import { useId, useState } from "react";
import { loadSampleDocuments } from "@/lib/api";
import type { Documents } from "@/lib/types";
import { ErrorNote, PrimaryButton } from "./Section";

function FilePicker({
  label,
  file,
  onFile,
  sample,
}: {
  label: string;
  file: File | null;
  onFile: (f: File | null) => void;
  sample: string;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-2 rounded-md border border-line bg-sheet p-4">
      <span className="font-medium">{label}</span>
      <p className="text-sm break-all text-muted">
        {file ? `${file.name}, ${Math.max(1, Math.round(file.size / 1024))} KB` : "PDF, up to 5 MB"}
      </p>
      <input
        id={id}
        type="file"
        accept="application/pdf"
        aria-label={`${label} PDF`}
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        className="peer sr-only"
      />
      <label
        htmlFor={id}
        className="w-fit cursor-pointer rounded-md border border-line bg-paper px-3 py-1.5 text-sm hover:border-ink peer-focus-visible:outline-2 peer-focus-visible:outline-ai"
      >
        {file ? "Replace PDF" : "Choose PDF"}
      </label>
      <a href={sample} target="_blank" rel="noreferrer" className="text-sm text-ai underline underline-offset-4">
        See the NovaGear example
      </a>
    </div>
  );
}

export function UploadStep({
  docs,
  onDocs,
  onRun,
  busy,
  needsSignIn,
}: {
  docs: Partial<Documents>;
  onDocs: (docs: Partial<Documents>) => void;
  onRun: (docs: Documents, sample: boolean) => void;
  busy: boolean;
  /** Your own documents need an account; the sample doesn't. */
  needsSignIn: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const ready = docs.orgChart && docs.policy;

  async function runSample() {
    setError(null);
    try {
      const sample = await loadSampleDocuments();
      onDocs(sample);
      onRun(sample, true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <FilePicker
          label="Organization chart"
          file={docs.orgChart ?? null}
          onFile={(f) => onDocs({ ...docs, orgChart: f ?? undefined })}
          sample="/demo/NovaGear_Organization_Chart.pdf"
        />
        <FilePicker
          label="Policy"
          file={docs.policy ?? null}
          onFile={(f) => onDocs({ ...docs, policy: f ?? undefined })}
          sample="/demo/NovaGear_Purchasing_Policy.pdf"
        />
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <PrimaryButton disabled={!ready || busy} onClick={() => ready && onRun(docs as Documents, false)}>
          {needsSignIn ? "Sign in and run health check" : "Run health check"}
        </PrimaryButton>
        <button
          type="button"
          disabled={busy}
          onClick={runSample}
          className="rounded-md border border-ink px-5 py-2.5 font-medium hover:bg-sheet disabled:cursor-not-allowed disabled:opacity-50"
        >
          Try the NovaGear sample
        </button>
      </div>
      <p className="text-sm text-muted">
        The sample works without an account. Checking your own documents needs a Google sign-in, so your reports are
        saved to you. The PDFs themselves are not saved.
      </p>
      {error && <ErrorNote message={error} />}
    </div>
  );
}
