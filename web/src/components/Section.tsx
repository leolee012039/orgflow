"use client";

import { useEffect, useState, type ReactNode } from "react";
import { seconds } from "@/lib/format";
import type { Origin } from "@/lib/types";
import { AlertIcon, RuleIcon, SparkIcon } from "./Icons";

/** Who produced this part of the screen. */
export function Tag({ kind }: { kind: "gemini" | "rules" }) {
  const gemini = kind === "gemini";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
        gemini ? "bg-ai-soft text-ai" : "bg-rule-soft text-rule"
      }`}
    >
      {gemini ? <SparkIcon width="13" height="13" /> : <RuleIcon width="13" height="13" />}
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
    <p role="status" className="flex items-center gap-2.5 text-ai">
      <span aria-hidden className="working-dot h-2 w-2 rounded-full bg-ai" />
      <span>{label}</span>
      <span className="tabular-nums text-faint">{Math.floor(elapsed / 1000)} s</span>
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
    <div role="alert" className="flex gap-3 rounded-xl border border-alert/25 bg-alert-soft px-4 py-3 text-alert">
      <AlertIcon className="mt-0.5 shrink-0" />
      <div className="flex min-w-0 flex-col gap-3">
        <p>{message}</p>
        {problems.length > 0 && (
          <div className="flex flex-col gap-1 text-sm text-ink">
            <p className="font-medium">What the checks found</p>
            <ul className="list-disc pl-5">
              {problems.slice(0, 3).map((p, i) => (
                <li key={i} className="break-words">
                  {p}
                </li>
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
    </div>
  );
}

/** Honest provenance for each AI answer. */
export function OriginNote({ origin, latencyMs }: { origin: Origin; latencyMs: number }) {
  const text =
    origin === "saved"
      ? "Gemini's reading of this sample was checked and saved, so it opens at once. Your own documents are read live."
      : origin === "fixture"
      ? "Gemini didn't return a usable answer in time, so this is a saved, prevalidated result."
      : origin === "repaired"
        ? `Gemini answered in ${seconds(latencyMs)}, after one correction requested by the checks.`
        : `Gemini answered in ${seconds(latencyMs)}. Every item passed the checks.`;
  return <p className="text-xs text-faint">{text}</p>;
}

export const primaryClass =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-ai px-4 py-2 font-medium text-sheet shadow-[0_1px_2px_rgb(79_70_229/0.3)] transition-colors hover:bg-ai-strong disabled:cursor-not-allowed disabled:bg-line disabled:text-faint disabled:shadow-none";

export const secondaryClass =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-line bg-sheet px-4 py-2 font-medium text-ink shadow-[0_1px_2px_rgb(22_26_35/0.05)] transition-colors hover:border-faint disabled:cursor-not-allowed disabled:opacity-50";

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
    <button type={type} onClick={onClick} disabled={disabled} className={primaryClass}>
      {children}
    </button>
  );
}
