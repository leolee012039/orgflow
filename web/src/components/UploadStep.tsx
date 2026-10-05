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
      <p className="text-sm text-muted">
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
        View the NovaGear sample
      </a>
    </div>
  );
}

export function UploadStep({
  docs,
  onDocs,
  onRead,
  busy,
}: {
  docs: Partial<Documents>;
  onDocs: (docs: Partial<Documents>) => void;
  onRead: (docs: Documents) => void;
  busy: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const ready = docs.orgChart && docs.policy;

  async function loadSample() {
    setError(null);
    try {
      const sample = await loadSampleDocuments();
      onDocs(sample);
      onRead(sample);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-prose text-lg leading-relaxed">
        Add an organization chart and a policy. OrgFlow reads both, finds the work worth automating, and builds a
        workflow that runs on the company&apos;s own rules.
      </p>
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
        <PrimaryButton disabled={!ready || busy} onClick={() => ready && onRead(docs as Documents)}>
          Read documents
        </PrimaryButton>
        <button
          type="button"
          disabled={busy}
          onClick={loadSample}
          className="rounded-md border border-ink px-5 py-2.5 font-medium hover:bg-sheet disabled:cursor-not-allowed disabled:opacity-50"
        >
          Use the NovaGear sample
        </button>
      </div>
      {error && <ErrorNote message={error} />}
    </div>
  );
}
