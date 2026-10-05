import { Fragment } from "react";
import { flowLanes } from "@/lib/chain";
import type { BuiltWorkflow, DepartmentMap as Map_, Organization, WorkflowCandidate } from "@/lib/types";
import { Quote } from "./Quote";

export const departmentAnchor = (name: string) => `dept-${encodeURIComponent(name).replace(/%/g, "")}`;

function DepartmentNode({
  name,
  org,
  planned,
  built,
}: {
  name: string;
  org: Organization;
  planned: number;
  built: number;
}) {
  const head = org.roles.find((r) => r.id === org.departments.find((d) => d.name === name)?.head_role_id);
  return (
    <a
      href={`#${departmentAnchor(name)}`}
      className={`flex min-w-0 flex-col rounded-md border-2 bg-sheet px-3 py-2 hover:bg-paper sm:w-44 ${
        built > 0 ? "border-ink" : "border-dashed border-line"
      }`}
    >
      <span className="font-semibold break-words">{name}</span>
      {head && <span className="truncate text-xs text-muted">{head.title}</span>}
      <span className="mt-1 text-xs tabular-nums text-muted">
        {built > 0 ? `${built} of ${planned} built` : `${planned} planned`}
      </span>
    </a>
  );
}

function Arrow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 py-1 pl-4 sm:w-32 sm:flex-col sm:items-stretch sm:gap-1 sm:px-2 sm:py-0" aria-hidden>
      <span className="text-rule sm:hidden">↓</span>
      <span className="text-xs leading-tight text-rule sm:text-center">{label}</span>
      <span className="relative hidden h-px bg-rule sm:block">
        <span className="absolute -top-[5px] -right-1 text-[10px] leading-none text-rule">▶</span>
      </span>
    </div>
  );
}

/** Departments as boxes and handoffs as arrows, laid out as the paths work takes through the company. */
export function DepartmentMap({
  map,
  org,
  plan,
  built,
}: {
  map: Map_;
  org: Organization;
  plan: WorkflowCandidate[];
  built: Record<string, BuiltWorkflow>;
}) {
  const names = map.departments.map((d) => d.name);
  const { lanes, alone } = flowLanes(map.handoffs, names);
  const count = (name: string) => {
    const mine = plan.filter((w) => w.department === name);
    return { planned: mine.length, built: mine.filter((w) => built[w.id]).length };
  };
  const node = (name: string) => <DepartmentNode name={name} org={org} {...count(name)} />;

  return (
    <div className="flex flex-col gap-6">
      {lanes.length > 0 ? (
        <ol className="flex flex-col gap-5" aria-label="How work moves between departments">
          {lanes.map((lane, i) => (
            <li key={i} className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:gap-y-3">
              {node(lane[0].from)}
              {lane.map((h) => (
                <Fragment key={`${h.from}-${h.to}`}>
                  <span className="sr-only">
                    hands {h.what} to {h.to}
                  </span>
                  <Arrow label={h.what} />
                  {node(h.to)}
                </Fragment>
              ))}
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-muted">The documents don&apos;t say how work passes between departments.</p>
      )}
      {alone.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">No handoffs found for</p>
          <div className="flex flex-wrap gap-3">
            {alone.map((name) => (
              <Fragment key={name}>{node(name)}</Fragment>
            ))}
          </div>
        </div>
      )}
      {map.handoffs.length > 0 && (
        <details className="group">
          <summary className="w-fit cursor-pointer text-sm text-ai underline underline-offset-4">
            The passages behind these handoffs
          </summary>
          <ul className="mt-4 flex flex-col gap-4">
            {map.handoffs.map((h) => (
              <li key={`${h.from}-${h.to}`} className="flex flex-col gap-2">
                <p className="text-sm font-medium">
                  {h.from} → {h.to}: {h.what}
                </p>
                <Quote text={h.evidence.quote} doc={h.evidence.doc} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
