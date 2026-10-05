"use client";

import { createContext, useContext } from "react";
import type { AmountGap, BuiltWorkflow, Decision, Gap, Organization } from "./types";

/** The head of the requester's own department, whoever submits the case. */
export const REQUESTER_MANAGER = "requester.manager";

export interface DecisionsValue {
  decisions: Decision[];
  /** Missing when this viewer can't change decisions (a shared company, the printed report) */
  decide?: (decision: Decision) => void;
  undo?: (decision: Decision) => void;
}

/** What people settled for this company: who approves in place of a missing approver,
 * and which level owns an exact amount the policy leaves open. */
export const Decisions = createContext<DecisionsValue>({ decisions: [] });
export const useDecisions = () => useContext(Decisions);

const key = (d: Decision) =>
  d.kind === "approver" ? `approver|${d.workflow_id}|${d.actor.toLowerCase()}` : `amount|${d.workflow_id}|${d.field}|${d.amount}`;

export const withDecision = (decisions: Decision[], decision: Decision) => [
  ...decisions.filter((d) => key(d) !== key(decision)),
  decision,
];
export const withoutDecision = (decisions: Decision[], decision: Decision) =>
  decisions.filter((d) => key(d) !== key(decision));

export function approverDecision(decisions: Decision[], workflowId: string, actor: string) {
  return decisions.find(
    (d): d is Extract<Decision, { kind: "approver" }> =>
      d.kind === "approver" && d.workflow_id === workflowId && d.actor.toLowerCase() === actor.toLowerCase(),
  );
}

export function amountDecision(decisions: Decision[], workflowId: string, gap: AmountGap) {
  return decisions.find(
    (d): d is Extract<Decision, { kind: "amount" }> =>
      d.kind === "amount" && d.workflow_id === workflowId && d.field === gap.field && d.amount === gap.amount,
  );
}

const gapOpen = (decisions: Decision[], wf: BuiltWorkflow) => (g: Gap) =>
  !approverDecision(decisions, wf.opportunity_id, g.actor);
const amountOpen = (decisions: Decision[], wf: BuiltWorkflow) => (g: AmountGap) =>
  !amountDecision(decisions, wf.opportunity_id, g);

/** The decisions that settle a problem these workflows have now. Older ones (from before a
 * rebuild, or for a company's other chains) stay saved but aren't sent with a case. */
export function activeDecisions(decisions: Decision[], workflows: BuiltWorkflow[]): Decision[] {
  return decisions.filter((d) => {
    const wf = workflows.find((w) => w.opportunity_id === d.workflow_id);
    if (!wf) return false;
    return d.kind === "approver"
      ? wf.gaps.some((g) => g.actor.toLowerCase() === d.actor.toLowerCase())
      : (wf.amount_gaps ?? []).some((g) => g.field === d.field && g.amount === d.amount);
  });
}

/** Places this workflow still stops a case, after the decisions people made. */
export function openProblems(wf: BuiltWorkflow, decisions: Decision[]): number {
  return wf.gaps.filter(gapOpen(decisions, wf)).length + (wf.amount_gaps ?? []).filter(amountOpen(decisions, wf)).length;
}

/** Problems people have settled with a decision. */
export function settledProblems(wf: BuiltWorkflow, decisions: Decision[]): number {
  return wf.gaps.length + (wf.amount_gaps?.length ?? 0) - openProblems(wf, decisions);
}

/** Who a decision names, in words. */
export function standInName(roleId: string, org: Organization): string {
  if (roleId === REQUESTER_MANAGER) return "the requester's department head";
  return org.roles.find((r) => r.id === roleId)?.title ?? roleId;
}

export const decidedOn = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
