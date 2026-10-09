// Mirrors api/schemas.py. The API adds origin and latency_ms to each AI stage.

export type Origin = "live" | "repaired" | "saved" | "fixture";
export type WithMeta<T> = T & { origin: Origin; latency_ms: number };

export interface Evidence {
  doc: string;
  quote: string;
}

export interface Department {
  name: string;
  head_role_id: string | null;
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

/** What a department does and how work moves between departments. */
export interface DepartmentProfile {
  name: string;
  summary: string;
  work: { task: string; evidence: Evidence }[];
}

export interface Handoff {
  from: string;
  to: string;
  what: string;
  evidence: Evidence;
}

export interface DepartmentMap {
  departments: DepartmentProfile[];
  handoffs: Handoff[];
}

/** A workflow one department could automate, before it is built. */
export interface WorkflowCandidate {
  id: string;
  department: string;
  name: string;
  trigger: string;
  starts_from: string | null;
  hands_to: string | null;
  output: string;
  /** policy: rules written in a policy. org_chart: only responsibilities describe it. */
  basis: "policy" | "org_chart";
  why: string;
  manual_handoffs: number;
  evidence: Evidence[];
}

export interface WorkflowPlan {
  workflows: WorkflowCandidate[];
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
  /** A second rule that must also hold, for a range of amounts. */
  also_if?: string | null;
  check?: string | null;
  on_fail?: string | null;
}

export interface FormField {
  name: string;
  label: string;
  type: "text" | "number" | "date" | "choice";
  options: string[];
}

/** One approval level of the policy, with the amounts it states at each end. */
export interface AmountTier {
  field: string;
  min: number | null;
  max: number | null;
  source: string;
}

export interface Workflow {
  workflow_name: string;
  opportunity_id: string;
  department: string;
  /** Empty: the original NovaGear purchase request form. */
  fields: FormField[];
  required_fields: string[];
  rules: Rule[];
  steps: Step[];
  unresolved_actors: string[];
  amount_tiers?: AmountTier[];
  starts_from: string | null;
  hands_to: string | null;
  output: string;
  explanation: string;
  /** Set by code: the built workflow this one receives cases from */
  upstream_id?: string | null;
}

/** An approver the policy requires that the organization does not provide. */
export interface Gap {
  actor: string;
  /** missing: the org chart never mentions it. possible_match: it does, but no role matched. */
  status: "missing" | "possible_match";
  step_id: string | null;
  policy_quote: string | null;
}

/** A number where one level ends and the next begins, and the wording leaves it in no level or in both. */
export interface AmountGap {
  /** unclear: one side's wording says both, like 「逾150萬元以上」 */
  kind: "gap" | "overlap" | "unclear";
  field: string;
  amount: number;
  /** passage of the level that ends at this number */
  below: string;
  /** passage of the level that starts at this number */
  above: string;
  /** For "unclear": the passage that words the amount both ways */
  unclear_side?: "below" | "above";
}

/** amount_levels_unchecked: the policy's amount levels didn't pass the checks, so exact amounts weren't looked at */
export type BuiltWorkflow = WithMeta<
  Workflow & { gaps: Gap[]; amount_gaps: AmountGap[]; amount_levels_unchecked?: boolean }
>;

export type StepResult = "PASSED" | "SKIPPED" | "DONE" | "RETURNED" | "HUMAN_REVIEW";

export interface StepTrace {
  step_id: string;
  type: string;
  actor: string;
  result: StepResult;
  reason: string;
  rule_id?: string | null;
  source?: string | null;
  /** The approver the policy names, when a person chose this step's role to stand in for it */
  stands_in_for?: string | null;
}

export type TraceStatus = "COMPLETED" | "RETURNED" | "NEEDS_HUMAN_REVIEW";

export interface Trace {
  request_id: string;
  status: TraceStatus;
  steps: StepTrace[];
  /** ai_checks: checks Gemini answered; code_checks: checks plain code made instead (absent in cases saved before 9 Oct) */
  metrics: { manual_handoffs_before: number; human_approvals: number; ai_checks: number; code_checks?: number };
}

export interface ChainLeg {
  workflow_id: string;
  workflow_name: string;
  department: string;
  trace: Trace;
}

export interface ChainTrace {
  request_id: string;
  status: TraceStatus;
  legs: ChainLeg[];
  /** The department the last workflow hands to, when nothing is built there yet. */
  waiting_for: string | null;
}

/** What starts a workflow: who, from which department, plus the workflow's own fields. */
export type CaseRequest = { request_id: string; requester: string; department: string } & Record<
  string,
  string | number
>;

/** A case run across departments, kept in the company's case list. */
export interface CaseRecord {
  id: string;
  at: string;
  startId: string;
  request: CaseRequest;
  trace: ChainTrace;
}

/** A person settles, once, what the documents leave open; every case after follows it. */
export type Decision =
  | {
      kind: "approver";
      workflow_id: string;
      /** The approver the policy names, which the org chart doesn't have */
      actor: string;
      /** The role that approves instead, or "requester.manager" */
      role_id: string;
      decided_at: string;
    }
  | {
      kind: "amount";
      workflow_id: string;
      field: string;
      amount: number;
      /** below: the level that ends at the amount owns it. above: the level that starts there. */
      level: "below" | "above";
      decided_at: string;
    };

export interface Documents {
  orgChart: File;
  policies: File[];
}
