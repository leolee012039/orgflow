import type { Organization, Role } from "@/lib/types";
import { Quote } from "./Quote";

function RoleBox({ role, lead }: { role: Role; lead?: boolean }) {
  return (
    <div
      className={`rounded-md border px-3 py-2 ${lead ? "border-ink bg-sheet font-medium" : "border-line bg-sheet text-ink"}`}
      title={role.responsibilities.join(" ")}
    >
      {role.title}
    </div>
  );
}

export function OrgView({ org }: { org: Organization }) {
  const top = org.roles.filter((r) => !r.reports_to);
  const departmentRoles = org.roles.filter((r) => r.department);
  const executive = top.length === 1 ? "1 chief executive" : `${top.length} top roles`;

  return (
    <div className="flex flex-col gap-8">
      <p className="text-lg">
        {org.company} has {executive}, {org.departments.length} departments and {departmentRoles.length} department
        roles.
      </p>

      <div className="overflow-x-auto">
        <div className="flex min-w-[36rem] flex-col items-center gap-4">
          <div className="flex gap-3">
            {top.map((r) => (
              <RoleBox key={r.id} role={r} lead />
            ))}
          </div>
          <div aria-hidden className="h-4 w-px bg-ink" />
          <ul className="grid w-full gap-3" style={{ gridTemplateColumns: `repeat(${org.departments.length}, minmax(0, 1fr))` }}>
            {org.departments.map((dept) => {
              const head = org.roles.find((r) => r.id === dept.head_role_id);
              const team = org.roles.filter((r) => r.department === dept.name && r.id !== dept.head_role_id);
              return (
                <li key={dept.name} className="flex flex-col gap-2 border-t-2 border-ink pt-3">
                  <span className="text-sm text-muted">{dept.name}</span>
                  {head && <RoleBox role={head} lead />}
                  {team.map((r) => (
                    <RoleBox key={r.id} role={r} />
                  ))}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {org.relationships.length > 0 && (
        <div className="flex flex-col gap-4">
          <h3 className="font-semibold">Handoffs stated in the documents</h3>
          <ul className="flex flex-col gap-5">
            {org.relationships.map((rel, i) => (
              <li key={i} className="flex flex-col gap-2">
                <p>
                  <span className="font-medium">
                    {rel.from} to {rel.to}.
                  </span>{" "}
                  {rel.description}
                </p>
                <Quote text={rel.evidence.quote} doc={rel.evidence.doc} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
