"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { accountsEnabled, signIn, signInMessage, signOut, useUser } from "@/lib/firebase";

export type Section = "overview" | "workflows" | "cases" | "documents";

export const SECTIONS: { id: Section; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "workflows", label: "Workflows" },
  { id: "cases", label: "Cases" },
  { id: "documents", label: "Documents" },
];

function NavItem({
  active,
  onClick,
  href,
  children,
  badge,
}: {
  active?: boolean;
  onClick?: () => void;
  href?: string;
  children: ReactNode;
  badge?: ReactNode;
}) {
  const className = `flex shrink-0 items-center justify-between gap-3 rounded-md px-3 py-2 text-left whitespace-nowrap ${
    active ? "bg-ink font-medium text-sheet" : "text-ink hover:bg-line/50"
  }`;
  const inner = (
    <>
      <span>{children}</span>
      {badge}
    </>
  );
  return href ? (
    <Link href={href} className={className} aria-current={active ? "page" : undefined}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={className} aria-current={active ? "page" : undefined}>
      {inner}
    </button>
  );
}

function Account() {
  const user = useUser();
  const [error, setError] = useState<string | null>(null);
  if (!accountsEnabled) return null;
  return (
    <div className="flex flex-col gap-2 text-sm">
      {user ? (
        <>
          <span className="truncate text-muted">{user.displayName ?? user.email}</span>
          <button type="button" onClick={() => signOut()} className="w-fit underline-offset-4 hover:underline">
            Sign out
          </button>
        </>
      ) : user === null ? (
        <button
          type="button"
          onClick={() => signIn().catch((e) => setError(signInMessage(e)))}
          className="w-fit rounded-md border border-ink px-3 py-1.5 font-medium hover:bg-sheet"
        >
          Sign in with Google
        </button>
      ) : null}
      {error && (
        <p role="alert" className="text-alert">
          {error}
        </p>
      )}
    </div>
  );
}

/** The console: a sidebar with the open company's sections, plus new analysis and the company list. */
export function Shell({
  company,
  section,
  onSection,
  badges = {},
  current,
  onNew,
  children,
}: {
  /** The open company, if any */
  company?: string;
  section?: Section;
  onSection?: (s: Section) => void;
  badges?: Partial<Record<Section, ReactNode>>;
  /** Which global page is showing when no company is open */
  current?: "new" | "companies";
  onNew?: () => void;
  children: ReactNode;
}) {
  const user = useUser();
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="border-b border-ink bg-paper print:hidden lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between gap-4 px-5 py-4 lg:py-6">
          <Link href="/" className="text-xl font-semibold tracking-tight">
            OrgFlow
          </Link>
          <div className="lg:hidden">
            <Account />
          </div>
        </div>
        <nav aria-label="Console" className="flex flex-col gap-4 px-3 pb-3 lg:flex-1 lg:overflow-y-auto lg:pb-6">
          {company && section && onSection && (
            <div className="flex flex-col gap-1">
              <p className="truncate px-3 pb-1 text-sm font-semibold" title={company}>
                {company}
              </p>
              <div className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
                {SECTIONS.map((s) => (
                  <NavItem key={s.id} active={section === s.id} onClick={() => onSection(s.id)} badge={badges[s.id]}>
                    {s.label}
                  </NavItem>
                ))}
              </div>
            </div>
          )}
          <div className="flex gap-1 overflow-x-auto border-t border-line pt-3 lg:flex-col lg:overflow-visible">
            {onNew ? (
              <NavItem active={current === "new"} onClick={onNew}>
                New analysis
              </NavItem>
            ) : (
              <NavItem active={current === "new"} href="/">
                New analysis
              </NavItem>
            )}
            {user && (
              <NavItem active={current === "companies"} href="/companies">
                My companies
              </NavItem>
            )}
          </div>
        </nav>
        <div className="hidden border-t border-line px-5 py-5 lg:block">
          <Account />
        </div>
      </aside>
      <div className="min-w-0 px-5 py-8 sm:px-8 lg:px-10">{children}</div>
    </div>
  );
}
