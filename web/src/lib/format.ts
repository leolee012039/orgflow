import type { Organization, Rule, StepType } from "./types";

export const money = (n: number, currency = "USD") => `${currency} ${n.toLocaleString("en-US")}`;

/** The policy's currency, read from the passages its rules quote. */
export function currencyOf(rules: Rule[]): string {
  return rules.some((r) => /新[臺台]幣|元|NT\$/.test(r.source)) ? "NT$" : "USD";
}

/** Amounts worth trying: below, between and above the policy's thresholds. */
export function tryAmounts(rules: Rule[]): number[] {
  const t = [...new Set(rules.map((r) => Number(r.when.value)).filter((v) => Number.isFinite(v) && v > 0))].sort(
    (a, b) => a - b,
  );
  if (t.length === 0) return [];
  const between = t.slice(1).map((v, i) => Math.round((v + t[i]) / 2));
  return [Math.round(t[0] / 2), ...between, Math.round(t[t.length - 1] * 1.5)];
}

const OPERATORS: Record<string, string> = { "<": "<", "<=": "≤", ">": ">", ">=": "≥", "==": "=" };

export function ruleExpression(rule: Rule): string {
  const value = typeof rule.when.value === "number" ? rule.when.value.toLocaleString("en-US") : rule.when.value;
  return `${rule.when.field} ${OPERATORS[rule.when.op] ?? rule.when.op} ${value}`;
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

export const FIELD_LABELS: Record<string, string> = {
  requester: "requester",
  department: "department",
  item: "item",
  estimated_cost: "estimated cost",
  business_justification: "business justification",
};

export const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`;
