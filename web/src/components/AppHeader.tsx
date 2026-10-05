"use client";

import Link from "next/link";
import { useState } from "react";
import { accountsEnabled, signIn, signInMessage, signOut, useUser } from "@/lib/firebase";

export function AppHeader() {
  const user = useUser();
  const [error, setError] = useState<string | null>(null);

  async function startSignIn() {
    setError(null);
    try {
      await signIn();
    } catch (e) {
      setError(signInMessage(e));
    }
  }

  return (
    <header className="border-b border-ink print:hidden">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-5 py-4 sm:px-8">
        <Link href="/" className="text-xl font-semibold tracking-tight">
          OrgFlow
        </Link>
        {accountsEnabled && (
          <nav aria-label="Account" className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            {user && (
              <Link href="/audits" className="font-medium underline-offset-4 hover:underline">
                My health checks
              </Link>
            )}
            {user && <span className="max-w-[14rem] truncate text-muted">{user.displayName ?? user.email}</span>}
            {user && (
              <button type="button" onClick={() => signOut()} className="underline-offset-4 hover:underline">
                Sign out
              </button>
            )}
            {user === null && (
              <button
                type="button"
                onClick={startSignIn}
                className="rounded-md border border-ink px-3 py-1.5 font-medium hover:bg-sheet"
              >
                Sign in with Google
              </button>
            )}
          </nav>
        )}
      </div>
      {error && (
        <p role="alert" className="mx-auto max-w-6xl px-5 pb-3 text-sm text-alert sm:px-8">
          {error}
        </p>
      )}
    </header>
  );
}
