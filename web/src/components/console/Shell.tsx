"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { accountsEnabled, signIn, signInMessage, signOut, useUser } from "@/lib/firebase";
import { BuildingIcon, FileIcon, FlowIcon, Logo, MapIcon, PlayIcon, PlusIcon } from "../Icons";

export type Section = "overview" | "workflows" | "cases" | "documents";

export const SECTIONS: { id: Section; label: string; icon: typeof MapIcon }[] = [
  { id: "overview", label: "Overview", icon: MapIcon },
  { id: "workflows", label: "Workflows", icon: FlowIcon },
  { id: "cases", label: "Cases", icon: PlayIcon },
  { id: "documents", label: "Documents", icon: FileIcon },
];

function NavItem({
  active,
  onClick,
  href,
  icon: Icon,
  children,
  badge,
  compact,
}: {
  active?: boolean;
  onClick?: () => void;
  href?: string;
  icon: typeof MapIcon;
  children: ReactNode;
  badge?: ReactNode;
  /** On a phone: icon over a short label, so four sections fit in one row */
  compact?: boolean;
}) {
  const className = `flex shrink-0 items-center gap-2.5 rounded-lg px-2.5 py-2 text-left whitespace-nowrap transition-colors ${
    active ? "bg-ai-soft font-medium text-ai" : "text-muted hover:bg-line/60 hover:text-ink"
  } ${compact ? "max-lg:flex-col max-lg:gap-1 max-lg:px-1 max-lg:py-1.5 max-lg:text-xs max-lg:relative" : ""}`;
  const inner = (
    <>
      <Icon className={active ? "text-ai" : "text-faint"} />
      <span className="flex-1">{children}</span>
      {badge && <span className={compact ? "max-lg:absolute max-lg:top-0.5 max-lg:right-1" : ""}>{badge}</span>}
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

function Account({ compact }: { compact?: boolean }) {
  const user = useUser();
  const [error, setError] = useState<string | null>(null);
  if (!accountsEnabled) return null;
  if (user === undefined) return null;
  const name = user?.displayName ?? user?.email ?? "";
  return (
    <div className="flex flex-col gap-2 text-sm">
      {user ? (
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ai-soft font-semibold text-ai">
            {name.charAt(0).toUpperCase()}
          </span>
          {!compact && (
            <span className="flex min-w-0 flex-col">
              <span className="truncate font-medium">{name}</span>
              <button type="button" onClick={() => signOut()} className="w-fit text-xs text-muted hover:text-ink">
                Sign out
              </button>
            </span>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => signIn().catch((e) => setError(signInMessage(e)))}
          className="w-fit rounded-lg border border-line bg-sheet px-3 py-1.5 font-medium shadow-[0_1px_2px_rgb(22_26_35/0.05)] hover:border-faint"
        >
          Sign in with Google
        </button>
      )}
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
    <div className="min-h-screen lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]">
      <aside className="border-b border-line bg-sheet print:hidden lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between gap-4 px-5 py-4 lg:py-5">
          <Link href="/" aria-label="OrgFlow home">
            <Logo />
          </Link>
          <div className="lg:hidden">
            <Account compact />
          </div>
        </div>
        <nav aria-label="Console" className="flex flex-col gap-5 px-3 pb-3 lg:flex-1 lg:overflow-y-auto lg:pt-2 lg:pb-6">
          {company && section && onSection && (
            <div className="flex flex-col gap-1">
              <p className="flex items-center gap-2 truncate px-2.5 pb-1.5 text-xs font-medium text-faint" title={company}>
                <BuildingIcon width="14" height="14" />
                <span className="truncate">{company}</span>
              </p>
              <div className="grid grid-cols-4 gap-1 lg:flex lg:flex-col">
                {SECTIONS.map((s) => (
                  <NavItem
                    key={s.id}
                    icon={s.icon}
                    active={section === s.id}
                    onClick={() => onSection(s.id)}
                    badge={badges[s.id]}
                    compact
                  >
                    {s.label}
                  </NavItem>
                ))}
              </div>
            </div>
          )}
          <div className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible lg:border-t lg:border-line lg:pt-4">
            {onNew ? (
              <NavItem icon={PlusIcon} active={current === "new"} onClick={onNew}>
                New analysis
              </NavItem>
            ) : (
              <NavItem icon={PlusIcon} active={current === "new"} href="/">
                New analysis
              </NavItem>
            )}
            {user && (
              <NavItem icon={BuildingIcon} active={current === "companies"} href="/companies">
                My companies
              </NavItem>
            )}
          </div>
        </nav>
        <div className="hidden border-t border-line px-5 py-4 lg:block">
          <Account />
        </div>
      </aside>
      <div className="min-w-0 px-5 py-6 sm:px-8 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-[84rem]">{children}</div>
      </div>
    </div>
  );
}
