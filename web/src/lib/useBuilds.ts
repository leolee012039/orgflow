"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { buildOrder, upstreamOf } from "./chain";
import type { BuiltWorkflow, Documents, Organization, WorkflowCandidate } from "./types";

export type BuildState = { status: "building" } | { status: "error"; message: string; problems: string[] };

/** Building one company's workflows, one at a time or every linked one at once.
 *
 * Mount it once per company (the page keys the console by company): it keeps the built workflows in a ref
 * so parallel builds see each other's results, and drops builds that finish after the company is closed.
 */
export function useBuilds({
  org,
  candidates,
  initial,
  docs,
  onBuilt,
}: {
  org: Organization;
  candidates: WorkflowCandidate[];
  initial: Record<string, BuiltWorkflow>;
  docs: Documents | null;
  onBuilt: (built: Record<string, BuiltWorkflow>) => void;
}) {
  const [states, setStates] = useState<Record<string, BuildState>>({});
  const builtRef = useRef(initial);
  const gone = useRef(false);
  useEffect(() => {
    gone.current = false;
    return () => {
      gone.current = true;
    };
  }, []);

  async function build(c: WorkflowCandidate): Promise<boolean> {
    if (!docs) return false;
    const upstream = upstreamOf(c, candidates, builtRef.current);
    setStates((s) => ({ ...s, [c.id]: { status: "building" } }));
    try {
      const result = await api.build(docs, org, c, upstream ? builtRef.current[upstream.id] ?? null : null);
      if (gone.current) return false;
      builtRef.current = { ...builtRef.current, [c.id]: result };
      onBuilt(builtRef.current);
      setStates((s) => Object.fromEntries(Object.entries(s).filter(([key]) => key !== c.id)));
      return true;
    } catch (e) {
      if (gone.current) return false;
      setStates((s) => ({
        ...s,
        [c.id]: { status: "error", message: (e as Error).message, problems: e instanceof ApiError ? e.problems : [] },
      }));
      return false;
    }
  }

  async function buildAll() {
    // Upstream first: a workflow is built once its upstream is built, side by side with others that are ready
    const upstreamBuilt = (c: WorkflowCandidate) => {
      const up = upstreamOf(c, candidates, builtRef.current);
      return !up || Boolean(builtRef.current[up.id]);
    };
    let pending = buildOrder(candidates, builtRef.current);
    while (pending.length && !gone.current) {
      const ready = pending.filter(upstreamBuilt);
      if (!ready.length) break;
      await Promise.all(ready.map(build));
      pending = pending.filter((c) => !ready.includes(c));
      // A workflow whose upstream failed can't be built against it; the rest carry on
      pending = pending.filter((c) => {
        const up = upstreamOf(c, candidates, builtRef.current);
        return !up || builtRef.current[up.id] || pending.includes(up);
      });
    }
  }

  return { states, build, buildAll, busy: Object.values(states).some((s) => s.status === "building") };
}
