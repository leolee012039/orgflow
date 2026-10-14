"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { buildOrder, upstreamOf, upstreamOptions } from "./chain";
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
  // How each workflow's last build failed: "transient" (unreachable, busy, Gemini didn't answer) may pass a moment
  // later; "lasting" (a sign-in, a limit, documents that fail the checks) won't, so the automatic second pass
  // leaves it and keeps its first error
  const failures = useRef(new Map<string, "transient" | "lasting">());
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
      failures.current.delete(c.id);
      onBuilt(builtRef.current);
      setStates((s) => Object.fromEntries(Object.entries(s).filter(([key]) => key !== c.id)));
      return true;
    } catch (e) {
      if (gone.current) return false;
      failures.current.set(c.id, e instanceof ApiError && e.transient ? "transient" : "lasting");
      setStates((s) => ({
        ...s,
        [c.id]: { status: "error", message: (e as Error).message, problems: e instanceof ApiError ? e.problems : [] },
      }));
      return false;
    }
  }

  async function buildAll() {
    // Upstream first: a workflow is built once every workflow it may start from has been tried and one is built,
    // side by side with a few others that are ready. Waiting for all of them builds it against the first in plan
    // order, whichever finished first, as the samples' saved workflows were built (ISSUES.md #31)
    async function pass(skipLasting: boolean) {
      let pending = buildOrder(candidates, builtRef.current).filter(
        (c) => !skipLasting || failures.current.get(c.id) !== "lasting",
      );
      const ready = (c: WorkflowCandidate) => {
        const options = upstreamOptions(c, candidates);
        return !options.length || (options.some((w) => builtRef.current[w.id]) && !options.some((w) => pending.includes(w)));
      };
      while (pending.length && !gone.current) {
        const batch = pending.filter(ready).slice(0, BUILD_AT_ONCE);
        if (!batch.length) break;
        await Promise.all(batch.map(build));
        pending = pending.filter((c) => !batch.includes(c));
        // A workflow none of whose upstreams can be built any more can't be built; the rest carry on
        pending = pending.filter((c) => {
          const options = upstreamOptions(c, candidates);
          return !options.length || options.some((w) => builtRef.current[w.id] || pending.includes(w));
        });
      }
    }
    await pass(false); // pressing the button tries everything not built, whatever failed before
    // When Gemini is busy or slow, a few builds fail; a second pass a little later usually builds them
    // (ISSUES.md #27), so nobody has to know to press the button again. The page stays busy while it waits.
    // Only when a build failed in a way that may pass now, and only those (with what waits on them) are tried
    // again (ISSUES.md #30)
    const unbuilt = buildOrder(candidates, builtRef.current);
    if (!gone.current && unbuilt.some((c) => failures.current.get(c.id) === "transient")) {
      setRetrying(true);
      try {
        await new Promise((resolve) => setTimeout(resolve, RETRY_AFTER_MS));
        await pass(true);
      } finally {
        if (!gone.current) setRetrying(false);
      }
    }
  }

  const building = Object.values(states).some((s) => s.status === "building");
  return { states, build, buildAll, busy: building || retrying };
}
