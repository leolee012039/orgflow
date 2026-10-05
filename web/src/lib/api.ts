import type { Documents, Opportunity, Organization, PurchaseRequest, Trace, WithMeta, Workflow } from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");

async function post<T>(path: string, body: FormData | object): Promise<T> {
  const isForm = body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      body: isForm ? body : JSON.stringify(body),
      headers: isForm ? undefined : { "Content-Type": "application/json" },
    });
  } catch {
    throw new Error("Can't reach the OrgFlow service. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = undefined;
    }
    throw new Error(
      typeof detail === "string" ? detail : `The OrgFlow service returned an error (${res.status}). Try again.`,
    );
  }
  return res.json() as Promise<T>;
}

function documentsForm(docs: Documents, fields: Record<string, unknown> = {}): FormData {
  const form = new FormData();
  form.append("org_chart", docs.orgChart);
  form.append("policy", docs.policy);
  for (const [key, value] of Object.entries(fields)) form.append(key, JSON.stringify(value));
  return form;
}

export const api = {
  analyze: (docs: Documents) => post<WithMeta<Organization>>("/api/analyze", documentsForm(docs)),

  opportunities: (docs: Documents, organization: Organization) =>
    post<WithMeta<{ opportunities: Opportunity[] }>>("/api/opportunities", documentsForm(docs, { organization })),

  workflow: (docs: Documents, organization: Organization, opportunity: Opportunity) =>
    post<WithMeta<Workflow>>("/api/workflow", documentsForm(docs, { organization, opportunity })),

  run: (workflow: Workflow, organization: Organization, request: PurchaseRequest, manualHandoffs: number) =>
    post<Trace>("/api/run", { workflow, organization, request, manual_handoffs_before: manualHandoffs }),
};

export async function loadSampleDocuments(): Promise<Documents> {
  const fetchPdf = async (name: string) => {
    const res = await fetch(`/demo/${name}`);
    if (!res.ok) throw new Error("The sample documents could not be loaded. Reload the page and try again.");
    return new File([await res.blob()], name, { type: "application/pdf" });
  };
  const [orgChart, policy] = await Promise.all([
    fetchPdf("NovaGear_Organization_Chart.pdf"),
    fetchPdf("NovaGear_Purchasing_Policy.pdf"),
  ]);
  return { orgChart, policy };
}
