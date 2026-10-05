"use client";

import { useId, useState } from "react";
import { loadSampleDocuments, SAMPLE_FILES } from "@/lib/api";
import type { Documents } from "@/lib/types";
import { ErrorNote, PrimaryButton } from "./Section";

export const MAX_POLICIES = 5;
const MAX_BYTES = 5 * 1024 * 1024;

export type DraftDocuments = { orgChart?: File; policies: File[] };

const size = (f: File) => `${Math.max(1, Math.round(f.size / 1024))} KB`;

function PickButton({ label, multiple, onFiles }: { label: string; multiple?: boolean; onFiles: (files: File[]) => void }) {
  const id = useId();
  return (
    <>
      <input
        id={id}
        type="file"
        accept="application/pdf"
        multiple={multiple}
        aria-label={label}
        onChange={(e) => {
          onFiles(Array.from(e.target.files ?? []));
          e.target.value = ""; // lets the same file be picked again after removing it
        }}
        className="peer sr-only"
      />
      <label
        htmlFor={id}
        className="w-fit cursor-pointer rounded-md border border-line bg-paper px-3 py-1.5 text-sm hover:border-ink peer-focus-visible:outline-2 peer-focus-visible:outline-ai"
      >
        {label}
      </label>
    </>
  );
}

/** Pick the org chart and the policies. Used to start an analysis, and to add documents back to build more. */
export function DocumentPicker({ docs, onDocs }: { docs: DraftDocuments; onDocs: (docs: DraftDocuments) => void }) {
  const [warning, setWarning] = useState<string | null>(null);

  function addPolicies(files: File[]) {
    const tooBig = files.filter((f) => f.size > MAX_BYTES);
    const room = MAX_POLICIES - docs.policies.length;
    const ok = files.filter((f) => f.size <= MAX_BYTES).slice(0, Math.max(room, 0));
    setWarning(
      tooBig.length
        ? `${tooBig.map((f) => f.name).join(", ")} is larger than 5 MB.`
        : files.length > ok.length
          ? `Up to ${MAX_POLICIES} policies at a time.`
          : null,
    );
    onDocs({ ...docs, policies: [...docs.policies, ...ok] });
  }

  return (
    <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <div className="flex flex-col gap-2 rounded-md border border-line bg-sheet p-4">
        <span className="font-medium">Organization chart</span>
        <p className="text-sm break-all text-muted">
          {docs.orgChart ? `${docs.orgChart.name}, ${size(docs.orgChart)}` : "Required. PDF, up to 5 MB."}
        </p>
        <PickButton
          label={docs.orgChart ? "Replace org chart PDF" : "Choose org chart PDF"}
          onFiles={([f]) => f && onDocs({ ...docs, orgChart: f })}
        />
      </div>
      <div className="flex flex-col gap-2 rounded-md border border-line bg-sheet p-4">
        <span className="font-medium">Policies</span>
        <p className="text-sm text-muted">
          Optional, up to {MAX_POLICIES}: purchasing, payment, leave, discounts. Departments with a policy get rules
          quoted from it.
        </p>
        {docs.policies.length > 0 && (
          <ul className="flex flex-col gap-1 text-sm">
            {docs.policies.map((p, i) => (
              <li key={`${p.name}-${i}`} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate">
                  {p.name}, {size(p)}
                </span>
                <button
                  type="button"
                  onClick={() => onDocs({ ...docs, policies: docs.policies.filter((_, j) => j !== i) })}
                  className="shrink-0 text-muted underline-offset-4 hover:underline"
                  aria-label={`Remove ${p.name}`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        {docs.policies.length < MAX_POLICIES && <PickButton label="Add policy PDFs" multiple onFiles={addPolicies} />}
        {warning && <p className="text-sm text-alert">{warning}</p>}
      </div>
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
  docs: DraftDocuments;
  onDocs: (docs: DraftDocuments) => void;
  onRun: (docs: Documents, sample: boolean) => void;
  busy: boolean;
  /** Your own documents need an account; the sample doesn't. */
  needsSignIn: boolean;
}) {
  const [error, setError] = useState<string | null>(null);

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
      <DocumentPicker docs={docs} onDocs={onDocs} />
      <div className="flex flex-wrap items-center gap-4">
        <PrimaryButton
          disabled={!docs.orgChart || busy}
          onClick={() => docs.orgChart && onRun({ orgChart: docs.orgChart, policies: docs.policies }, false)}
        >
          {needsSignIn ? "Sign in and analyze" : "Analyze the company"}
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
        The sample is a fictional company with an org chart and {SAMPLE_FILES.policies.length} policies (
        <a href={`/demo/${SAMPLE_FILES.orgChart}`} target="_blank" rel="noreferrer" className="text-ai underline underline-offset-4">
          see the org chart
        </a>
        ). It works without an account. Analyzing your own documents needs a Google sign-in, so your work is saved to
        you. The PDFs themselves are not saved.
      </p>
      {error && <ErrorNote message={error} />}
    </div>
  );
}
