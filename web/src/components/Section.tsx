"use client";

import { useEffect, useState, type ReactNode, type Ref } from "react";
import { seconds } from "@/lib/format";
import type { Origin } from "@/lib/types";

export function Section({
  id,
  step,
  title,
  tags,
  sectionRef,
  children,
}: {
  id: string;
  step: number;
  title: string;
  tags?: ReactNode;
  sectionRef?: Ref<HTMLElement>;
  children: ReactNode;
}) {
  return (
    <section id={id} ref={sectionRef} aria-labelledby={`${id}-title`} className="scroll-mt-8 border-t border-line py-12 first:border-t-0 first:pt-4">
      <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full border border-ink text-sm font-medium tabular-nums">
          {step}
        </span>
        <h2 id={`${id}-title`} className="text-2xl font-semibold tracking-tight text-balance">
          {title}
        </h2>
        {tags && <div className="flex flex-wrap gap-2">{tags}</div>}
      </div>
      {children}
    </section>
  );
}

/** Who produced this part of the screen. */
export function Tag({ kind }: { kind: "gemini" | "rules" }) {
  const gemini = kind === "gemini";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
        gemini ? "bg-ai-soft text-ai" : "bg-rule-soft text-rule"
      }`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${gemini ? "bg-ai" : "bg-rule"}`} />
      {gemini ? "Gemini" : "Rules engine"}
    </span>
  );
}

/** Shown while Gemini works: what it is doing and for how long. */
export function Working({ label }: { label: string }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => setElapsed(Date.now() - start), 250);
    return () => clearInterval(timer);
  }, []);
  return (
    <p role="status" className="flex items-center gap-3 text-ai">
      <span aria-hidden className="working-dot h-2.5 w-2.5 rounded-full bg-ai" />
      <span>{label}</span>
      <span className="tabular-nums text-muted">{Math.floor(elapsed / 1000)} s</span>
    </p>
  );
}

export function ErrorNote({
  message,
  problems = [],
  onRetry,
}: {
  message: string;
  problems?: string[];
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-md border border-alert bg-alert-soft px-4 py-3 text-alert">
      <p>{message}</p>
      {problems.length > 0 && (
        <div className="flex flex-col gap-1 text-sm text-ink">
          <p className="font-medium">What the checks found</p>
          <ul className="list-disc pl-5">
            {problems.slice(0, 3).map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {onRetry && (
        <button type="button" onClick={onRetry} className="w-fit font-medium underline underline-offset-4">
          Try again
        </button>
      )}
    </div>
  );
}

/** Honest provenance for each AI answer. */
export function OriginNote({ origin, latencyMs }: { origin: Origin; latencyMs: number }) {
  const text =
    origin === "fixture"
      ? "Gemini didn't return a usable answer in time, so this is a saved, prevalidated result."
      : origin === "repaired"
        ? `Gemini answered in ${seconds(latencyMs)}, after one correction requested by the checks.`
        : `Gemini answered in ${seconds(latencyMs)}. Every item passed the checks.`;
  return <p className="mt-6 text-sm text-muted">{text}</p>;
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="rounded-md bg-ink px-5 py-2.5 font-medium text-sheet transition-colors hover:bg-ai disabled:cursor-not-allowed disabled:bg-line disabled:text-muted"
    >
      {children}
    </button>
  );
}
