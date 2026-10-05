"use client";

import { useRef, useState, type RefObject } from "react";
import { OpportunityList } from "@/components/OpportunityList";
import { OrgView } from "@/components/OrgView";
import { RunPanel } from "@/components/RunPanel";
import { ErrorNote, OriginNote, Section, Tag, Working } from "@/components/Section";
import { StepRail, type RailState } from "@/components/StepRail";
import { UploadStep } from "@/components/UploadStep";
import { WorkflowView } from "@/components/WorkflowView";
import { api, ApiError } from "@/lib/api";
import type { Documents, Opportunity, Organization, PurchaseRequest, Trace, WithMeta, WorkflowResult } from "@/lib/types";

type Stage<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; data: T }
  | { status: "error"; error: string; problems: string[] };

const IDLE = { status: "idle" } as const;
const LOADING = { status: "loading" } as const;
const failed = (e: unknown) =>
  ({ status: "error", error: (e as Error).message, problems: e instanceof ApiError ? e.problems : [] }) as const;

function railState(stage: Stage<unknown>, previousDone: boolean): RailState {
  if (stage.status === "done") return "done";
  if (stage.status === "loading" || stage.status === "error" || previousDone) return "current";
  return "upcoming";
}

function reveal(ref: RefObject<HTMLElement | null>) {
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  requestAnimationFrame(() => ref.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" }));
}

export default function Home() {
  const [docs, setDocs] = useState<Partial<Documents>>({});
  const [org, setOrg] = useState<Stage<WithMeta<Organization>>>(IDLE);
  const [opps, setOpps] = useState<Stage<WithMeta<{ opportunities: Opportunity[] }>>>(IDLE);
  const [chosen, setChosen] = useState<Opportunity | null>(null);
  const [workflow, setWorkflow] = useState<Stage<WithMeta<WorkflowResult>>>(IDLE);
  const [run, setRun] = useState<Stage<Trace>>(IDLE);
  const [lastRequest, setLastRequest] = useState<PurchaseRequest | null>(null);
  const [runKey, setRunKey] = useState(0);

  const understandRef = useRef<HTMLElement>(null);
  const recommendRef = useRef<HTMLElement>(null);
  const generateRef = useRef<HTMLElement>(null);
  const runRef = useRef<HTMLElement>(null);

  async function findOpportunities(d: Documents, organization: Organization) {
    setOpps(LOADING);
    reveal(recommendRef);
    try {
      setOpps({ status: "done", data: await api.opportunities(d, organization) });
    } catch (e) {
      setOpps(failed(e));
    }
  }

  async function readDocuments(d: Documents) {
    setOrg(LOADING);
    setOpps(IDLE);
    setChosen(null);
    setWorkflow(IDLE);
    setRun(IDLE);
    reveal(understandRef);
    let organization: WithMeta<Organization>;
    try {
      organization = await api.analyze(d);
    } catch (e) {
      setOrg(failed(e));
      return;
    }
    setOrg({ status: "done", data: organization });
    await findOpportunities(d, organization);
  }

  async function buildWorkflow(opportunity: Opportunity) {
    if (org.status !== "done" || !docs.orgChart || !docs.policy) return;
    setChosen(opportunity);
    setWorkflow(LOADING);
    setRun(IDLE);
    reveal(generateRef);
    try {
      setWorkflow({
        status: "done",
        data: await api.workflow({ orgChart: docs.orgChart, policy: docs.policy }, org.data, opportunity),
      });
      reveal(generateRef);
    } catch (e) {
      setWorkflow(failed(e));
    }
  }

  async function runRequest(request: PurchaseRequest) {
    if (org.status !== "done" || workflow.status !== "done") return;
    setRun(LOADING);
    setLastRequest(request);
    try {
      const trace = await api.run(workflow.data, org.data, request, chosen?.manual_handoffs ?? 4);
      setRunKey((k) => k + 1);
      setRun({ status: "done", data: trace });
    } catch (e) {
      setRun(failed(e));
    }
  }

  const docsReady = Boolean(docs.orgChart && docs.policy);
  const rail = [
    { id: "upload", label: "Upload", state: org.status !== "idle" ? "done" : "current" },
    { id: "understand", label: "Understand", state: railState(org, org.status !== "idle") },
    { id: "recommend", label: "Recommend", state: railState(opps, org.status === "done") },
    { id: "generate", label: "Generate", state: railState(workflow, opps.status === "done") },
    { id: "run", label: "Run", state: railState(run, workflow.status === "done") },
  ] satisfies { id: string; label: string; state: RailState }[];

  return (
    <div className="mx-auto flex max-w-6xl flex-col px-5 sm:px-8">
      <header className="flex flex-col gap-4 border-b border-ink py-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-2">
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">OrgFlow</h1>
            <p className="max-w-xl text-lg text-muted">
              Find where your written rules can&apos;t run in your organization, with the lines that prove it. Then
              automate the parts that can.
            </p>
          </div>
          <div className="flex max-w-md flex-col gap-2 text-sm text-muted">
            <div className="flex gap-2">
              <Tag kind="gemini" />
              <Tag kind="rules" />
            </div>
            <p>Gemini reads the documents and designs the workflow. Plain code applies the rules, so a request always gets the same answer.</p>
          </div>
        </div>
      </header>

      <div className="grid gap-x-12 py-8 lg:grid-cols-[11rem_minmax(0,1fr)]">
        <aside className="mb-4 min-w-0 lg:mb-0">
          <StepRail steps={rail} />
        </aside>

        <main className="min-w-0 max-w-3xl">
          <Section id="upload" step={1} title="Upload company documents">
            <UploadStep docs={docs} onDocs={setDocs} onRead={readDocuments} busy={org.status === "loading"} />
          </Section>

          {org.status !== "idle" && (
            <Section id="understand" step={2} title="How the company is organized" sectionRef={understandRef} tags={<Tag kind="gemini" />}>
              {org.status === "loading" && <Working label="Gemini is reading both documents" />}
              {org.status === "error" && (
                <ErrorNote
                  message={org.error}
                  problems={org.problems}
                  onRetry={docsReady ? () => readDocuments(docs as Documents) : undefined}
                />
              )}
              {org.status === "done" && (
                <>
                  <OrgView org={org.data} />
                  <OriginNote origin={org.data.origin} latencyMs={org.data.latency_ms} />
                </>
              )}
            </Section>
          )}

          {opps.status !== "idle" && (
            <Section id="recommend" step={3} title="What to automate" sectionRef={recommendRef} tags={<Tag kind="gemini" />}>
              {opps.status === "loading" && <Working label="Gemini is looking for repetitive, rule-based work" />}
              {opps.status === "error" && org.status === "done" && (
                <ErrorNote
                  message={opps.error}
                  problems={opps.problems}
                  onRetry={() => findOpportunities(docs as Documents, org.data)}
                />
              )}
              {opps.status === "done" && (
                <>
                  <OpportunityList
                    opportunities={opps.data.opportunities}
                    onBuild={buildWorkflow}
                    busy={workflow.status === "loading"}
                  />
                  <OriginNote origin={opps.data.origin} latencyMs={opps.data.latency_ms} />
                </>
              )}
            </Section>
          )}

          {workflow.status !== "idle" && (
            <Section
              id="generate"
              step={4}
              title={workflow.status === "done" ? workflow.data.workflow_name : "Workflow"}
              sectionRef={generateRef}
              tags={
                <>
                  <Tag kind="gemini" />
                  <Tag kind="rules" />
                </>
              }
            >
              {workflow.status === "loading" && <Working label="Gemini is turning the policy into steps and rules" />}
              {workflow.status === "error" && chosen && (
                <ErrorNote message={workflow.error} problems={workflow.problems} onRetry={() => buildWorkflow(chosen)} />
              )}
              {workflow.status === "done" && org.status === "done" && (
                <>
                  <WorkflowView
                    workflow={workflow.data}
                    gaps={workflow.data.gaps ?? []}
                    amountGaps={workflow.data.amount_gaps ?? []}
                    org={org.data}
                  />
                  <OriginNote origin={workflow.data.origin} latencyMs={workflow.data.latency_ms} />
                </>
              )}
            </Section>
          )}

          {workflow.status === "done" && org.status === "done" && (
            <Section
              id="run"
              step={5}
              title="Run a request"
              sectionRef={runRef}
              tags={
                <>
                  <Tag kind="rules" />
                  <Tag kind="gemini" />
                </>
              }
            >
              <div className="flex flex-col gap-6">
                <p className="max-w-prose text-lg leading-relaxed">
                  Submit a purchase request. The rules engine walks it through the workflow; Gemini only checks that the
                  required information makes sense.
                </p>
                {run.status === "error" && <ErrorNote message={run.error} />}
                {run.status === "loading" && <Working label="Running the request" />}
                <RunPanel
                  org={org.data}
                  workflow={workflow.data}
                  boundaries={(workflow.data.amount_gaps ?? []).map((g) => g.amount)}
                  trace={run.status === "done" ? run.data : null}
                  runKey={runKey}
                  lastRequest={lastRequest}
                  busy={run.status === "loading"}
                  onRun={runRequest}
                />
              </div>
            </Section>
          )}
        </main>
      </div>

      <footer className="border-t border-line py-8 text-sm text-muted">
        NovaGear Inc. is a fictional company created for this demo. OrgFlow runs on Gemini 3.8 Flash, Google ADK, Cloud
        Run and Firebase Hosting.
      </footer>
    </div>
  );
}
