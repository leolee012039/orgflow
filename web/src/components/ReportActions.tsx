"use client";

import { useState } from "react";
import { deleteCheck, setShared, type SavedCheck } from "@/lib/audits";

const buttonClass = "rounded-md border border-line px-4 py-2 font-medium hover:border-ink disabled:opacity-50";

/** The browser's print dialog, where "Save as PDF" is one of the printers. */
export function PrintButton() {
  return (
    <button type="button" onClick={() => window.print()} className={buttonClass}>
      Save as PDF
    </button>
  );
}

/** Owner-only controls for a saved report: share a read-only link, or delete it. */
export function OwnerActions({ check, onDeleted }: { check: SavedCheck; onDeleted: () => void }) {
  const [shared, setSharedState] = useState(check.shared);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const link = typeof window === "undefined" ? "" : `${window.location.origin}/report?id=${check.id}`;

  async function toggleShare() {
    setBusy(true);
    setNote(null);
    try {
      await setShared(check.id, !shared);
      setSharedState(!shared);
      setNote(shared ? "The link no longer works for anyone but you." : null);
    } catch {
      setNote("OrgFlow couldn't change sharing. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(link);
      setNote("Link copied.");
    } catch {
      setNote(`Copy this link: ${link}`);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete the health check for ${check.company}? This can't be undone.`)) return;
    setBusy(true);
    try {
      await deleteCheck(check.id);
      onDeleted();
    } catch {
      setNote("OrgFlow couldn't delete this report. Try again.");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-3">
        <PrintButton />
        <button type="button" onClick={toggleShare} disabled={busy} className={buttonClass} aria-pressed={shared}>
          {shared ? "Stop sharing" : "Share a read-only link"}
        </button>
        {shared && (
          <button type="button" onClick={copyLink} className={buttonClass}>
            Copy link
          </button>
        )}
        <button type="button" onClick={remove} disabled={busy} className={`${buttonClass} text-alert`}>
          Delete
        </button>
      </div>
      {shared && <p className="text-sm text-muted">Anyone with the link can read this report. They can&apos;t change it.</p>}
      {note && (
        <p role="status" className="text-sm">
          {note}
        </p>
      )}
    </div>
  );
}
