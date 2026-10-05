import type { Organization, Rule, StepType } from "./types";

export const money = (n: number) => `USD ${n.toLocaleString("en-US")}`;

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
