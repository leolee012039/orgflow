import type { FormField, Organization, Rule, StepType, Workflow } from "./types";

export const money = (n: number, currency = "USD") => `${currency} ${n.toLocaleString("en-US")}`;

/** The policy's currency, read from the passages its rules quote. */
export function currencyOf(rules: Rule[]): string {
  return rules.some((r) => /新[臺台]幣|元|NT\$/.test(r.source)) ? "NT$" : "USD";
}

/** The original NovaGear purchase request form, for workflows built without their own fields. */
export const LEGACY_FIELDS: FormField[] = [
  { name: "item", label: "Requested Item", type: "text", options: [] },
  { name: "estimated_cost", label: "Estimated Cost", type: "number", options: [] },
  { name: "business_justification", label: "Business Justification", type: "text", options: [] },
];

export const fieldsOf = (wf: Workflow): FormField[] => (wf.fields?.length ? wf.fields : LEGACY_FIELDS);

export function fieldLabel(wf: Workflow, name: string): string {
  if (name === "requester") return "Requester";
  if (name === "department") return "Department";
  return fieldsOf(wf).find((f) => f.name === name)?.label ?? name.replace(/_/g, " ");
}

const isPercent = (field: FormField | undefined) =>
  Boolean(field && (/percent/i.test(field.name) || /%|percent/i.test(field.label)));

/** A number as the policy writes it: a percentage, an amount in the policy's currency, or a plain number. */
export function formatValue(wf: Workflow, name: string, value: unknown): string {
  const field = fieldsOf(wf).find((f) => f.name === name);
  const n = typeof value === "number" ? value : Number(value);
  if (value === "" || value === undefined || value === null || Number.isNaN(n) || field?.type !== "number")
    return String(value ?? "");
  if (isPercent(field)) return `${n}%`;
  const moneyRule = wf.rules.some((r) => r.when.field === name) || /cost|price|amount|payment/i.test(name);
  return moneyRule ? money(n, currencyOf(wf.rules)) : n.toLocaleString("en-US");
}

/** Values worth trying for a number field: below, between and above the thresholds, and every gap. */
export function tryValues(wf: Workflow, name: string, gaps: number[] = []): number[] {
  const t = [
    ...new Set(
      wf.rules
        .filter((r) => r.when.field === name)
        .map((r) => Number(r.when.value))
        .filter((v) => Number.isFinite(v) && v > 0),
    ),
  ].sort((a, b) => a - b);
  if (t.length === 0) return gaps;
  const between = t.slice(1).map((v, i) => Math.round((v + t[i]) / 2));
  const round = (v: number) => (v >= 100 ? Math.round(v / 50) * 50 : Math.round(v));
  return [...new Set([round(t[0] / 2), ...between.map(round), round(t[t.length - 1] * 1.5), ...gaps])].sort(
    (a, b) => a - b,
  );
}

const OPERATORS: Record<string, string> = { "<": "<", "<=": "≤", ">": ">", ">=": "≥", "==": "=" };

export function ruleExpression(rule: Rule, wf?: Workflow): string {
  const value =
    typeof rule.when.value === "number" && wf ? formatValue(wf, rule.when.field, rule.when.value) : String(rule.when.value);
  const field = wf ? fieldLabel(wf, rule.when.field) : rule.when.field;
  return `${field} ${OPERATORS[rule.when.op] ?? rule.when.op} ${value}`;
}

export function actorName(actor: string, org: Organization | null): string {
  if (actor === "requester") return "Requester";
  if (actor === "requester.manager") return "Requester's manager";
  if (actor === "orgflow_ai") return "Gemini";
  const role = org?.roles.find((r) => r.id === actor || r.title.toLowerCase() === actor.toLowerCase());
  return role?.title ?? actor;
}

export const STEP_KIND: Record<StepType, string> = {
  ai_review: "AI check",
  approval: "Approval",
  task: "Task",
  notification: "Notification",
};

/** A document id as the person uploaded it: org_chart, policy_1 ... */
export function documentName(doc: string, documents?: { orgChart: string; policies: string[] }): string {
  if (doc === "org_chart") return documents?.orgChart ?? "Organization chart";
  const n = /^policy_(\d+)$/.exec(doc);
  if (n) return documents?.policies[Number(n[1]) - 1] ?? `Policy ${n[1]}`;
  if (doc === "policy") return documents?.policies.length === 1 ? documents.policies[0] : "One of the policies";
  return doc;
}

export const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`;
