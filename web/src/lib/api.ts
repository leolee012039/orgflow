import { idToken } from "./firebase";
import type {
  BuiltWorkflow,
  CaseRequest,
  ChainTrace,
  DepartmentMap,
  Documents,
  Organization,
  Trace,
  WithMeta,
  Workflow,
  WorkflowCandidate,
  WorkflowPlan,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");

/** An API error with the guard's findings, when the service sends them. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly problems: string[] = [],
  ) {
    super(message);
  }
}

async function post<T>(path: string, body: FormData | object): Promise<T> {
  const isForm = body instanceof FormData;
  const headers: Record<string, string> = isForm ? {} : { "Content-Type": "application/json" };
  const token = await idToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      body: isForm ? body : JSON.stringify(body),
      headers,
    });
  } catch {
    throw new ApiError("Can't reach the OrgFlow service. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = undefined;
    }
    if (typeof detail === "string") throw new ApiError(detail);
    if (detail && typeof detail === "object" && "message" in detail) {
      const d = detail as { message: string; problems?: string[] };
      throw new ApiError(d.message, d.problems ?? []);
    }
    throw new ApiError(`The OrgFlow service returned an error (${res.status}). Try again.`);
  }
  return res.json() as Promise<T>;
}

function documentsForm(docs: Documents, fields: Record<string, unknown> = {}): FormData {
  const form = new FormData();
  form.append("org_chart", docs.orgChart);
  for (const policy of docs.policies) form.append("policies", policy);
  for (const [key, value] of Object.entries(fields)) form.append(key, JSON.stringify(value));
  return form;
}

export const api = {
  analyze: (docs: Documents) => post<WithMeta<Organization>>("/api/analyze", documentsForm(docs)),

  map: (docs: Documents, organization: Organization) =>
    post<WithMeta<DepartmentMap>>("/api/map", documentsForm(docs, { organization })),

  plan: (docs: Documents, organization: Organization, departmentMap: DepartmentMap) =>
    post<WithMeta<WorkflowPlan>>("/api/plan", documentsForm(docs, { organization, department_map: departmentMap })),

  build: (docs: Documents, organization: Organization, planned: WorkflowCandidate, upstream: Workflow | null) =>
    post<BuiltWorkflow>("/api/build", documentsForm(docs, { organization, planned, upstream })),

  run: (workflow: Workflow, organization: Organization, request: CaseRequest, manualHandoffs: number) =>
    post<Trace>("/api/run", { workflow, organization, request, manual_handoffs_before: manualHandoffs }),

  runChain: (
    workflows: Workflow[],
    organization: Organization,
    startId: string,
    request: CaseRequest,
    handoffsBefore: Record<string, number>,
  ) =>
    post<ChainTrace>("/api/run_chain", {
      workflows,
      organization,
      start_id: startId,
      request,
      handoffs_before: handoffsBefore,
    }),
};

export type AnalysisStep = "organization" | "departments" | "plan";

/** A failed analysis, with the step it stopped at. */
export class AnalysisError extends ApiError {
  constructor(
    readonly step: AnalysisStep,
    cause: unknown,
  ) {
    super((cause as Error).message, cause instanceof ApiError ? cause.problems : []);
  }
}

export interface Analysis {
  organization: WithMeta<Organization>;
  departmentMap: WithMeta<DepartmentMap>;
  plan: WithMeta<WorkflowPlan>;
}

/** The three reading stages in a row: the organization, the department map, then each department's plan. */
export async function runAnalysis(docs: Documents, onStep: (step: AnalysisStep) => void): Promise<Analysis> {
  let step: AnalysisStep = "organization";
  try {
    onStep(step);
    const organization = await api.analyze(docs);
    onStep((step = "departments"));
    const departmentMap = await api.map(docs, organization);
    onStep((step = "plan"));
    const plan = await api.plan(docs, organization, departmentMap);
    return { organization, departmentMap, plan };
  } catch (e) {
    throw new AnalysisError(step, e);
  }
}

export const SAMPLE_FILES = {
  orgChart: "NovaGear_Organization_Chart.pdf",
  policies: [
    "NovaGear_Purchasing_Policy.pdf",
    "NovaGear_Procurement_Payment_Procedures.pdf",
    "NovaGear_Sales_Discount_Policy.pdf",
  ],
};

export async function loadSampleDocuments(): Promise<Documents> {
  const fetchPdf = async (name: string) => {
    const res = await fetch(`/demo/${name}`);
    if (!res.ok) throw new Error("The sample documents could not be loaded. Reload the page and try again.");
    return new File([await res.blob()], name, { type: "application/pdf" });
  };
  const [orgChart, ...policies] = await Promise.all([SAMPLE_FILES.orgChart, ...SAMPLE_FILES.policies].map(fetchPdf));
  return { orgChart, policies };
}
