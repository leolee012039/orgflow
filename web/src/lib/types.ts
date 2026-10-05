// Mirrors api/schemas.py. The API adds origin and latency_ms to each AI stage.

export type Origin = "live" | "repaired" | "fixture";
export type WithMeta<T> = T & { origin: Origin; latency_ms: number };

export interface Evidence {
  doc: string;
  quote: string;
}

export interface Department {
  name: string;
  head_role_id: string;
}

export interface Role {
  id: string;
  title: string;
  department: string | null;
  reports_to: string | null;
  responsibilities: string[];
}

export interface Relationship {
  from: string;
  to: string;
  description: string;
  evidence: Evidence;
}

export interface Organization {
  company: string;
  departments: Department[];
  roles: Role[];
  relationships: Relationship[];
}

export interface Opportunity {
  id: string;
  name: string;
  departments: string[];
  manual_handoffs: number;
  impact: "HIGH" | "MEDIUM" | "LOW";
  why: string;
  executable: boolean;
  evidence: Evidence[];
}

export interface Rule {
  id: string;
  when: { field: string; op: "<" | "<=" | ">" | ">=" | "=="; value: number | string };
  source: string;
}

export type StepType = "approval" | "ai_review" | "task" | "notification";

export interface Step {
  id: string;
  type: StepType;
  actor: string;
  only_if?: string | null;
  check?: string | null;
  on_fail?: string | null;
}

export interface Workflow {
  workflow_name: string;
  opportunity_id: string;
  required_fields: string[];
  rules: Rule[];
  steps: Step[];
  unresolved_actors: string[];
  explanation: string;
}

/** An approver the policy requires that the organization does not provide. */
export interface Gap {
  actor: string;
  /** missing: the org chart never mentions it. possible_match: it does, but no role matched. */
  status: "missing" | "possible_match";
  step_id: string | null;
  policy_quote: string | null;
}

export type StepResult = "PASSED" | "SKIPPED" | "DONE" | "RETURNED" | "HUMAN_REVIEW";

export interface StepTrace {
  step_id: string;
  type: string;
  actor: string;
  result: StepResult;
  reason: string;
  rule_id?: string | null;
  source?: string | null;
}

export interface Trace {
  request_id: string;
  status: "COMPLETED" | "RETURNED" | "NEEDS_HUMAN_REVIEW";
  steps: StepTrace[];
  metrics: { manual_handoffs_before: number; human_approvals: number; ai_checks: number };
}

export interface PurchaseRequest {
  request_id: string;
  requester: string;
  department: string;
  item: string;
  estimated_cost: number;
  business_justification: string;
}

export interface Documents {
  orgChart: File;
  policy: File;
}
