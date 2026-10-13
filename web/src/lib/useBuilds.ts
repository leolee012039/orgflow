"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { buildOrder, upstreamOf } from "./chain";
import type { BuiltWorkflow, Documents, Organization, WorkflowCandidate } from "./types";

export type BuildState = { status: "building" } | { status: "error"; message: string; problems: string[] };

/** "Build all" sends at most this many builds at once: more slow every Gemini answer, and one past 90 s fails. */
const BUILD_AT_ONCE = 3;
/** "Build all" tries the ones that failed once more, this long after the first pass. */
const RETRY_AFTER_MS = 5000;

/** Building one company's workflows, one at a time or every planned one at once.
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
  const [retrying, setRetrying] = useState(false);
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
    // Upstream first: a workflow is built once its upstream is built, side by side with a few others that are ready
    const upstreamBuilt = (c: WorkflowCandidate) => {
      const up = upstreamOf(c, candidates, builtRef.current);
      return !up || Boolean(builtRef.current[up.id]);
    };
    async function pass() {
      let pending = buildOrder(candidates, builtRef.current);
      while (pending.length && !gone.current) {
        const ready = pending.filter(upstreamBuilt).slice(0, BUILD_AT_ONCE);
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
    await pass();
    // When Gemini is busy or slow, a few builds fail; a second pass a little later usually builds them
    // (ISSUES.md #27), so nobody has to know to press the button again. The page stays busy while it waits.
    if (!gone.current && buildOrder(candidates, builtRef.current).length) {
      setRetrying(true);
      try {
        await new Promise((resolve) => setTimeout(resolve, RETRY_AFTER_MS));
        await pass();
      } finally {
        if (!gone.current) setRetrying(false);
      }
    }
  }

  const building = Object.values(states).some((s) => s.status === "building");
  return { states, build, buildAll, busy: building || retrying };
}
