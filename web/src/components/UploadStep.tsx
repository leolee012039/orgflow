"use client";

import { useId, useState } from "react";
import { loadSampleDocuments } from "@/lib/api";
import { DEFAULT_SAMPLE, SAMPLES } from "@/lib/samples";
import type { Documents } from "@/lib/types";
import { BuildingIcon, FileIcon, SparkIcon, UploadIcon } from "./Icons";
import { ErrorNote, primaryClass, secondaryClass } from "./Section";

export const MAX_POLICIES = 5;
const MAX_BYTES = 5 * 1024 * 1024;

export type DraftDocuments = { orgChart?: File; policies: File[] };

const size = (f: File) => `${Math.max(1, Math.round(f.size / 1024))} KB`;
const isPdf = (f: File) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");

/** Why a file can't be used, said when it is picked rather than after signing in and uploading. */
function refusal(f: File): string | null {
  if (!isPdf(f)) return `${f.name} isn't a PDF. Choose a .pdf file.`;
  if (f.size > MAX_BYTES) return `${f.name} is larger than 5 MB. Choose a smaller PDF.`;
  return null;
}

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
        className="inline-flex w-fit cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-sheet px-3 py-1.5 text-sm font-medium shadow-[0_1px_2px_rgb(22_26_35/0.05)] hover:border-faint peer-focus-visible:outline-2 peer-focus-visible:outline-ai"
      >
        <UploadIcon width="15" height="15" className="text-muted" />
        {label}
      </label>
    </>
  );
}

/** Pick the org chart and the policies. Used to start an analysis, and to add documents back to build more. */
export function DocumentPicker({ docs, onDocs }: { docs: DraftDocuments; onDocs: (docs: DraftDocuments) => void }) {
  const [warning, setWarning] = useState<string | null>(null);

  function addPolicies(files: File[]) {
    const refused = files.map(refusal).filter((r): r is string => r !== null);
    const room = MAX_POLICIES - docs.policies.length;
    const usable = files.filter((f) => refusal(f) === null);
    const ok = usable.slice(0, Math.max(room, 0));
    setWarning(refused.length ? refused.join(" ") : usable.length > ok.length ? `Up to ${MAX_POLICIES} policies at a time.` : null);
    onDocs({ ...docs, policies: [...docs.policies, ...ok] });
  }

  function setOrgChart(f: File) {
    const refused = refusal(f);
    setWarning(refused);
    if (!refused) onDocs({ ...docs, orgChart: f });
  }

  return (
    <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <div className="card flex flex-col gap-2.5 p-5">
        <span className="flex items-center gap-2.5 font-semibold">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-ai-soft text-ai">
            <BuildingIcon />
          </span>
          Organization chart
        </span>
        <p className="text-sm break-all text-muted">
          {docs.orgChart ? `${docs.orgChart.name}, ${size(docs.orgChart)}` : "Required. PDF, up to 5 MB."}
        </p>
        <PickButton
          label={docs.orgChart ? "Replace org chart PDF" : "Choose org chart PDF"}
          onFiles={([f]) => f && setOrgChart(f)}
        />
      </div>
      <div className="card flex flex-col gap-2.5 p-5">
        <span className="flex items-center gap-2.5 font-semibold">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-rule-soft text-rule">
            <FileIcon />
          </span>
          Policies
        </span>
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
      </div>
      {warning && (
        <p role="alert" className="text-sm text-alert sm:col-span-2">
          {warning}
        </p>
      )}
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
  /** sampleId: a sample company, which opens from its saved reading; null: the visitor's own documents */
  onRun: (docs: Documents, sampleId: string | null) => void;
  busy: boolean;
  /** Your own documents need an account; the samples don't. */
  needsSignIn: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const others = SAMPLES.filter((s) => s.id !== DEFAULT_SAMPLE.id);

  async function runSample(id: string) {
    setError(null);
    try {
      const sample = await loadSampleDocuments(id);
      onDocs(sample);
      onRun(sample, id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <DocumentPicker docs={docs} onDocs={onDocs} />
      <div className="flex flex-wrap items-center gap-4">
        {/* Until a file is chosen, the sample is the thing to try */}
        <button
          type="button"
          disabled={!docs.orgChart || busy}
          onClick={() => docs.orgChart && onRun({ orgChart: docs.orgChart, policies: docs.policies }, null)}
          className={docs.orgChart ? primaryClass : secondaryClass}
        >
          {needsSignIn ? "Sign in and analyze" : "Analyze the company"}
        </button>
        {!docs.orgChart && <span className="text-sm text-muted sm:order-last">Choose an org chart PDF to analyze your own company.</span>}
        <button
          type="button"
          disabled={busy}
          onClick={() => runSample(DEFAULT_SAMPLE.id)}
          className={docs.orgChart ? secondaryClass : primaryClass}
        >
          <SparkIcon />
          Try the NovaGear sample
        </button>
      </div>
      {others.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Samples from across Asia-Pacific</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Samples from across Asia-Pacific">
            {others.map((s) => (
              <button
                key={s.id}
                type="button"
                disabled={busy}
                onClick={() => runSample(s.id)}
                title={`${s.company}: ${s.industry}, documents in ${s.language}`}
                aria-label={`Open the ${s.market} sample, ${s.company}, ${s.industry}, documents in ${s.language}`}
                className="flex flex-col rounded-lg border border-line bg-sheet px-3 py-2 text-left text-sm shadow-[0_1px_2px_rgb(22_26_35/0.04)] hover:border-ai disabled:opacity-60"
              >
                <span className="font-medium">{s.market}</span>
                <span className="text-xs text-muted">{s.industry}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      <p className="text-sm text-muted">
        Each sample is a fictional company with an org chart and its policies, in its own language and currency (
        <a href={`/demo/${DEFAULT_SAMPLE.orgChart}`} target="_blank" rel="noreferrer" className="font-medium text-ai hover:underline">
          see NovaGear&apos;s org chart
        </a>
        ). They work without an account and open at once: Gemini&apos;s reading of each was checked and saved. Your own
        documents are read live, which takes about a minute, and need a Google sign-in so your work is saved to you.
        The PDFs themselves are not saved.
      </p>
      {error && <ErrorNote message={error} />}
    </div>
  );
}
