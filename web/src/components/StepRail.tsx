export type RailState = "done" | "current" | "upcoming";

export function StepRail({ steps }: { steps: { id: string; label: string; state: RailState }[] }) {
  return (
    <nav aria-label="Progress" className="lg:sticky lg:top-8">
      <ol className="flex gap-4 overflow-x-auto pb-2 text-sm lg:flex-col lg:gap-1 lg:overflow-visible lg:pb-0">
        {steps.map((step, i) => (
          <li key={step.id} className="shrink-0">
            <a
              href={`#${step.id}`}
              aria-current={step.state === "current" ? "step" : undefined}
              className={`flex items-center gap-3 rounded-md py-1.5 lg:px-2 ${
                step.state === "upcoming" ? "text-muted" : "text-ink"
              } ${step.state === "current" ? "font-semibold" : ""}`}
            >
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full border text-xs tabular-nums ${
                  step.state === "done"
                    ? "border-ink bg-ink text-sheet"
                    : step.state === "current"
                      ? "border-ink"
                      : "border-line"
                }`}
              >
                {step.state === "done" ? "✓" : i + 1}
              </span>
              {step.label}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
