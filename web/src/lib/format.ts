import type { FormField, Organization, Rule, StepType, Workflow } from "./types";

export const money = (n: number, currency = "") => (currency ? `${currency} ${n.toLocaleString("en-US")}` : n.toLocaleString("en-US"));

// How a policy writes a currency, and the name OrgFlow shows for it
const CURRENCY_NAMES: [RegExp, string][] = [
  [/新[臺台]幣|[臺台]幣|NT\$|\bNTD\b|\bTWD\b|\d\s*元/g, "NT$"],
  [/US\$|\bUSD\b/g, "USD"],
  [/S\$|\bSGD\b/g, "SGD"],
  [/A\$|\bAUD\b/g, "AUD"],
  [/HK\$|港幣|\bHKD\b/g, "HKD"],
  [/NZ\$|\bNZD\b/g, "NZD"],
  [/C\$|\bCAD\b/g, "CAD"],
  [/€|\bEUR\b/g, "EUR"],
  [/£|\bGBP\b/g, "GBP"],
  [/円|日圓|日元|\bJPY\b/g, "JPY"],
  [/人民幣|\bRMB\b|\bCNY\b/g, "CNY"],
  [/₩|\bKRW\b/g, "KRW"],
  [/\bRM\s?\d|\bMYR\b/g, "MYR"],
  [/₹|\bINR\b/g, "INR"],
  [/₱|\bPHP\b/g, "PHP"],
  [/฿|\bTHB\b/g, "THB"],
  [/\bRp\s?\d|\bIDR\b/g, "IDR"],
  [/₫|\bVND\b/g, "VND"],
];

/** The policy's currency: the one its quoted passages name most often. None found: no currency is shown,
 * rather than a guess. */
export function currencyOf(passages: string[]): string {
  let best = "";
  let most = 0;
  for (const [pattern, name] of CURRENCY_NAMES) {
    const count = passages.reduce((n, p) => n + (p.match(pattern)?.length ?? 0), 0);
    if (count > most) [best, most] = [name, count];
  }
  return best;
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
  const passages = [...wf.rules.map((r) => r.source), ...(wf.amount_tiers ?? []).map((t) => t.source)];
  return moneyRule ? money(n, currencyOf(passages)) : n.toLocaleString("en-US");
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
