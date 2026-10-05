import type { BuiltWorkflow, Handoff, WorkflowCandidate } from "./types";

type Built = Record<string, BuiltWorkflow>;

/** Built workflows in plan order. The runner picks the next workflow in the order it is sent, so the page
 * always sends this order and follows it itself. */
export function orderedBuilt(plan: WorkflowCandidate[], built: Built): BuiltWorkflow[] {
  return plan.filter((c) => built[c.id]).map((c) => built[c.id]);
}

/** The planned workflow a candidate starts from: in its starts_from department, handing to its department.
 * A built one wins, so the candidate is built against something that exists. */
export function upstreamOf(candidate: WorkflowCandidate, plan: WorkflowCandidate[], built: Built): WorkflowCandidate | null {
  if (!candidate.starts_from) return null;
  const options = plan.filter((w) => w.department === candidate.starts_from && w.hands_to === candidate.department);
  return options.find((w) => built[w.id]) ?? options[0] ?? null;
}

/** The planned workflow that picks up a candidate's result: in the department it hands to, starting from it. */
export function downstreamOf(candidate: WorkflowCandidate, plan: WorkflowCandidate[]): WorkflowCandidate | null {
  if (!candidate.hands_to) return null;
  return plan.find((w) => w.department === candidate.hands_to && w.starts_from === candidate.department) ?? null;
}

/** What "Build all" builds: each department's first workflow, the workflows they start from, and the workflows
 * that pick up their results, so every chain is complete. Upstream comes first. */
export function buildOrder(plan: WorkflowCandidate[], built: Built): WorkflowCandidate[] {
  const wanted = new Map<string, WorkflowCandidate>();
  const add = (candidate: WorkflowCandidate, seen: Set<string>) => {
    if (wanted.has(candidate.id) || seen.has(candidate.id)) return;
    seen.add(candidate.id);
    const upstream = upstreamOf(candidate, plan, built);
    if (upstream) add(upstream, seen);
    wanted.set(candidate.id, candidate);
    const downstream = downstreamOf(candidate, plan);
    if (downstream) add(downstream, seen);
  };
  const firstPerDepartment = new Map<string, WorkflowCandidate>();
  for (const w of plan) if (!firstPerDepartment.has(w.department)) firstPerDepartment.set(w.department, w);
  for (const w of firstPerDepartment.values()) add(w, new Set());
  return [...wanted.values()].filter((w) => !built[w.id]);
}

/** The built workflows a case started here passes through: each next one is the workflow built against the
 * current one (its upstream_id), first in plan order, exactly as the runner picks it. */
export function chainFrom(start: BuiltWorkflow, ordered: BuiltWorkflow[]): BuiltWorkflow[] {
  const path = [start];
  let current = start;
  while (current.hands_to) {
    const next = ordered.find((w) => w.upstream_id === current.opportunity_id);
    if (!next || path.includes(next)) break;
    path.push(next);
    current = next;
  }
  return path;
}

/** Where a case can start: built workflows that receive cases from no built workflow. The start of the longest
 * chain comes first. */
export function startPoints(plan: WorkflowCandidate[], built: Built): WorkflowCandidate[] {
  const ordered = orderedBuilt(plan, built);
  const starts = plan.filter((c) => {
    const wf = built[c.id];
    return wf && (!wf.upstream_id || !built[wf.upstream_id]);
  });
  const length = (c: WorkflowCandidate) => chainFrom(built[c.id], ordered).length;
  return starts.sort((a, b) => length(b) - length(a));
}

/** The map drawn as lanes: every path of handoffs from a department that receives nothing, plus the rest. */
export function flowLanes(handoffs: Handoff[], departments: string[]): { lanes: Handoff[][]; alone: string[] } {
  const outgoing = new Map<string, Handoff[]>();
  for (const h of handoffs) outgoing.set(h.from, [...(outgoing.get(h.from) ?? []), h]);
  const receives = new Set(handoffs.map((h) => h.to));
  const lanes: Handoff[][] = [];
  const used = new Set<Handoff>();

  const walk = (dept: string, lane: Handoff[], visited: Set<string>) => {
    const next = (outgoing.get(dept) ?? []).filter((h) => !visited.has(h.to));
    if (next.length === 0) {
      if (lane.length) lanes.push(lane);
      return;
    }
    for (const h of next) {
      used.add(h);
      walk(h.to, [...lane, h], new Set([...visited, h.to]));
    }
  };
  const sources = [...outgoing.keys()].filter((d) => !receives.has(d));
  for (const source of sources) walk(source, [], new Set([source]));
  // Handoffs inside a loop have no source; draw each on its own
  for (const h of handoffs) if (!used.has(h)) lanes.push([h]);

  const connected = new Set(handoffs.flatMap((h) => [h.from, h.to]));
  // The longest path first: it shows the most of how the company works
  return { lanes: lanes.sort((a, b) => b.length - a.length), alone: departments.filter((d) => !connected.has(d)) };
}
