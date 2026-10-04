"use client";

import { useEffect, useState } from "react";

interface HealthStatus {
  ok: boolean;
  model: string;
}

export default function Home() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ||
    "http://localhost:8000";

  const checkHealth = async () => {
    setLoading(true);
    setError(null);
    const start = performance.now();
    try {
      const res = await fetch(`${apiBase}/api/health`, {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        throw new Error(`HTTP error ${res.status}`);
      }
      const data: HealthStatus = await res.json();
      setHealth(data);
      setLatencyMs(Math.round(performance.now() - start));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to connect";
      setError(message);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
  }, [apiBase]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center">
      {/* Header */}
      <header className="w-full max-w-5xl px-6 py-8 border-b border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-blue-600 flex items-center justify-center font-bold text-white shadow-lg shadow-blue-500/30">
              OF
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              OrgFlow
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-950 border border-blue-800 text-blue-300 font-medium">
              Google Cloud AI Builder Cup 2026
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Turn organizational documents into executable, verified workflows in minutes
          </p>
        </div>

        {/* System & Health Status Indicator */}
        <div className="flex items-center gap-3 bg-slate-900 border border-slate-800 px-4 py-2.5 rounded-xl shadow-inner">
          <div className="flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                loading
                  ? "bg-amber-400 animate-pulse"
                  : health?.ok
                  ? "bg-emerald-400 shadow-[0_0_8px_#34d399]"
                  : "bg-rose-500"
              }`}
            />
            <span className="text-sm font-semibold tracking-wide">
              {loading
                ? "Connecting..."
                : health?.ok
                ? "API OK"
                : "API Disconnected"}
            </span>
          </div>
          {health?.ok && (
            <span className="text-xs text-slate-400 border-l border-slate-700 pl-3">
              Model: <code className="text-emerald-400 font-mono">{health.model}</code>
              {latencyMs !== null && ` (${latencyMs}ms)`}
            </span>
          )}
          {error && (
            <button
              onClick={checkHealth}
              className="text-xs text-rose-400 underline hover:text-rose-300 ml-2"
            >
              Retry
            </button>
          )}
        </div>
      </header>

      {/* Main Container */}
      <main className="w-full max-w-5xl px-6 py-10 flex flex-col gap-10">
        {/* Phase 0 Status Banner */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur">
          <div className="flex items-center justify-between flex-wrap gap-4 mb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">
                Environment & Deployment Status (Phase 0)
              </h2>
              <p className="text-sm text-slate-400 mt-0.5">
                Verifying end-to-end communication between Firebase Hosting and Google Cloud Run.
              </p>
            </div>
            <div className="text-xs font-mono bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-slate-300">
              API Base: {apiBase}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80">
              <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                Frontend
              </div>
              <div className="text-sm font-medium text-slate-200 mt-1">
                Next.js 15 (Static Export)
              </div>
              <div className="text-xs text-emerald-400 mt-1">✓ Ready for Firebase Hosting</div>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80">
              <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                Backend
              </div>
              <div className="text-sm font-medium text-slate-200 mt-1">
                FastAPI · Python 3.12
              </div>
              <div className="text-xs text-emerald-400 mt-1">✓ Containerized (Cloud Run)</div>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80">
              <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                Live Health Response
              </div>
              <div className="text-sm font-medium text-slate-200 mt-1">
                {loading ? (
                  <span className="text-amber-400">Pinging backend...</span>
                ) : health?.ok ? (
                  <span className="text-emerald-400 font-bold">API OK</span>
                ) : (
                  <span className="text-rose-400 font-medium">{error || "Unavailable"}</span>
                )}
              </div>
              <div className="text-xs text-slate-400 mt-1">
                {health?.model ? `Gemini target: ${health.model}` : "Awaiting response"}
              </div>
            </div>
          </div>
        </section>

        {/* 5-Step Demo Story Preview */}
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-200">
              OrgFlow Execution Pipeline (Upcoming Phases)
            </h2>
            <span className="text-xs text-slate-500 font-mono">Target: &lt; 3 min demo path</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {[
              { num: "1", title: "Upload", desc: "Org Chart & Purchasing Policy PDFs" },
              { num: "2", title: "Understand", desc: "CEO, 4 departments, 8 roles hierarchy" },
              { num: "3", title: "Recommend", desc: "3 opportunities (Purchase approval first)" },
              { num: "4", title: "Generate", desc: "Workflow steps with policy quote links" },
              { num: "5", title: "Run", desc: "USD 2,400 MacBook Pro live deterministic trace" },
            ].map((step) => (
              <div
                key={step.num}
                className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between opacity-80"
              >
                <div>
                  <span className="text-xs font-bold text-blue-400 font-mono">
                    STEP 0{step.num}
                  </span>
                  <div className="font-semibold text-slate-100 text-sm mt-1">
                    {step.title}
                  </div>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    {step.desc}
                  </p>
                </div>
                <div className="mt-3 text-[11px] font-mono text-slate-500">
                  Phase {step.num === "1" || step.num === "2" ? "2" : step.num === "3" || step.num === "4" ? "3" : "4"}
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="w-full border-t border-slate-900 py-6 mt-auto text-center text-xs text-slate-500">
        OrgFlow · Google Cloud AI Builder Cup 2026 · NovaGear Fictional Enterprise Benchmark
      </footer>
    </div>
  );
}