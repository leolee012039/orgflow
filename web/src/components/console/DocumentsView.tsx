"use client";

import { useState } from "react";
import { fileName, sampleById, sampleFiles } from "@/lib/samples";
import type { Workspace } from "@/lib/workspaces";
import type { Documents } from "@/lib/types";
import { OrgView } from "../OrgView";
import { Quote } from "../Quote";
import { OriginNote } from "../Section";
import { DocumentPicker, type DraftDocuments } from "../UploadStep";

/** What OrgFlow read: the files, the organization it found, and the passages behind each handoff. */
export function DocumentsView({
  workspace,
  docs,
  editable,
  onDocs,
}: {
  workspace: Workspace;
  docs: Documents | null;
  editable: boolean;
  onDocs: (docs: Documents) => void;
}) {
  const [draft, setDraft] = useState<DraftDocuments>({ policies: [] });
  // A sample's own files open from /demo/; the path of the one with this name, if it is one of them
  const samplePath = (name: string) => sampleFiles(sampleById(workspace.sampleId)).find((p) => fileName(p) === name);
  const files = [
    { label: "Organization chart", name: workspace.documents.orgChart },
    ...workspace.documents.policies.map((name, i) => ({ label: `Policy ${i + 1}`, name })),
  ];
  return (
    <div className="flex flex-col gap-12">
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Files</h2>
        <ul className="card divide-y divide-line overflow-hidden">
          {files.map((f) => (
            <li key={f.label} className="grid gap-1 px-5 py-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
              <span className="text-sm text-muted">{f.label}</span>
              {workspace.sample && samplePath(f.name) ? (
                <a href={`/demo/${samplePath(f.name)}`} target="_blank" rel="noreferrer" className="break-all font-medium text-ai hover:underline">
                  {f.name}
                </a>
              ) : (
                <span className="break-all">{f.name}</span>
              )}
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted">
          {docs
            ? "The PDFs are open in this session, so you can build workflows. OrgFlow doesn't save them."
            : "OrgFlow doesn't save PDFs. To build more workflows, add the same documents again."}
        </p>
        {editable && !docs && (
          <div className="card flex flex-col gap-3 p-4">
            <DocumentPicker docs={draft} onDocs={setDraft} />
            <div>
              <button
                type="button"
                disabled={!draft.orgChart}
                onClick={() => draft.orgChart && onDocs({ orgChart: draft.orgChart, policies: draft.policies })}
                className="rounded-lg bg-ai px-4 py-2 font-medium text-sheet hover:bg-ai-strong disabled:bg-line disabled:text-faint"
              >
                Use these documents
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-6">
        <h2 className="text-lg font-semibold">The organization as OrgFlow read it</h2>
        <OrgView org={workspace.organization} />
        <OriginNote origin={workspace.organization.origin} latencyMs={workspace.organization.latency_ms} />
      </section>

      {workspace.departmentMap.handoffs.length > 0 && (
        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">Handoffs between departments, with the passage that says so</h2>
          <p className="-mt-2 max-w-prose text-sm text-muted">
            These are the links on the department map. The relationships above come from reading the org chart, so the two
            lists can differ.
          </p>
          <ul className="flex flex-col gap-5">
            {workspace.departmentMap.handoffs.map((h) => (
              <li key={`${h.from}-${h.to}-${h.what}`} className="flex flex-col gap-2">
                <p className="font-medium">
                  {h.from} → {h.to}: {h.what}
                </p>
                <Quote text={h.evidence.quote} doc={h.evidence.doc} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
