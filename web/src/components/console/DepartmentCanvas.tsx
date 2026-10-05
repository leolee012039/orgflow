"use client";

import { openProblems, useDecisions } from "@/lib/decisions";
import { Fragment, useLayoutEffect, useRef } from "react";
import { flowLanes } from "@/lib/chain";
import { AlertIcon } from "../Icons";
import type { BuiltWorkflow, Decision, DepartmentMap, Handoff, Organization, WorkflowCandidate } from "@/lib/types";

/** Columns in the order work flows. Each department sits as far right as its handoffs allow, one column left of
 * the nearest department it hands to, so a short chain lines up under a long one instead of crossing it. */
export function layers(names: string[], handoffs: Handoff[]): { columns: string[][]; alone: string[] } {
  const into = new Map<string, string[]>();
  const out = new Map<string, string[]>();
  for (const h of handoffs) {
    into.set(h.to, [...(into.get(h.to) ?? []), h.from]);
    out.set(h.from, [...(out.get(h.from) ?? []), h.to]);
  }
  const connected = new Set(handoffs.flatMap((h) => [h.from, h.to]));
  const height = new Map<string, number>(); // the longest path of handoffs from here to the end
  const heightOf = (name: string, visiting: Set<string>): number => {
    if (height.has(name)) return height.get(name)!;
    if (visiting.has(name)) return 0; // a loop: stop counting
    visiting.add(name);
    const h = Math.max(0, ...(out.get(name) ?? []).map((s) => heightOf(s, visiting) + 1));
    visiting.delete(name);
    height.set(name, h);
    return h;
  };
  const placed = names.filter((n) => connected.has(n));
  const tallest = Math.max(0, ...placed.map((n) => heightOf(n, new Set())));
  const columns: string[][] = [];
  for (const name of placed) (columns[tallest - heightOf(name, new Set())] ??= []).push(name);
  // Within a column, follow the order of the departments they receive from, so lines cross less
  for (let i = 1; i < columns.length; i++) {
    const position = (n: string) => {
      const from = (into.get(n) ?? []).map((p) => columns[i - 1]?.indexOf(p) ?? -1).filter((x) => x >= 0);
      return from.length ? from.reduce((a, b) => a + b, 0) / from.length : 0;
    };
    columns[i]?.sort((a, b) => position(a) - position(b));
  }
  return { columns: columns.filter(Boolean), alone: names.filter((n) => !connected.has(n)) };
}

function status(name: string, plan: WorkflowCandidate[], built: Record<string, BuiltWorkflow>, decisions: Decision[]) {
  const mine = plan.filter((w) => w.department === name);
  const done = mine.filter((w) => built[w.id]);
  const problems = done.reduce((n, w) => n + openProblems(built[w.id], decisions), 0);
  return { planned: mine.length, built: done.length, problems };
}

const SVG_NS = "http://www.w3.org/2000/svg";

function wrap(text: string, width: number): string[] {
  const lines: string[] = [];
  for (const word of text.split(/\s+/)) {
    const last = lines[lines.length - 1];
    if (last !== undefined && (last + " " + word).length <= width) lines[lines.length - 1] = `${last} ${word}`;
    else lines.push(word);
  }
  return lines;
}

/** The company as boxes and arrows. Click a department to open it. */
export function DepartmentCanvas({
  map,
  org,
  plan,
  built,
  selected,
  onSelect,
}: {
  map: DepartmentMap;
  org: Organization;
  plan: WorkflowCandidate[];
  built: Record<string, BuiltWorkflow>;
  selected: string | null;
  onSelect: (name: string) => void;
}) {
  const { decisions } = useDecisions();
  const names = map.departments.map((d) => d.name);
  const { columns, alone } = layers(names, map.handoffs);
  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const nodes = useRef(new Map<string, HTMLElement>());
  const handoffKey = map.handoffs.map((h) => `${h.from}>${h.to}:${h.what}`).join("|");

  // Connectors are drawn from the boxes' measured positions, straight into the SVG (no re-render needed)
  useLayoutEffect(() => {
    const container = box.current;
    const layer = svg.current;
    if (!container || !layer) return;
    const draw = () => {
      const origin = container.getBoundingClientRect();
      layer.setAttribute("width", String(container.scrollWidth));
      layer.setAttribute("height", String(container.scrollHeight));
      layer.replaceChildren();
      for (const h of map.handoffs) {
        const a = nodes.current.get(h.from)?.getBoundingClientRect();
        const b = nodes.current.get(h.to)?.getBoundingClientRect();
        if (!a || !b) continue;
        const across = b.left >= a.right - 4;
        const [x1, y1, x2, y2] = across
          ? [a.right - origin.left, a.top + a.height / 2 - origin.top, b.left - origin.left, b.top + b.height / 2 - origin.top]
          : [a.left + a.width / 2 - origin.left, a.bottom - origin.top, b.left + b.width / 2 - origin.left, b.top - origin.top];
        const path = document.createElementNS(SVG_NS, "path");
        const bend = across ? `C ${x1 + (x2 - x1) / 2} ${y1}, ${x1 + (x2 - x1) / 2} ${y2},` : `C ${x1} ${y1 + (y2 - y1) / 2}, ${x2} ${y1 + (y2 - y1) / 2},`;
        path.setAttribute("d", `M ${x1} ${y1} ${bend} ${x2 - (across ? 6 : 0)} ${y2 - (across ? 0 : 6)}`);
        path.setAttribute("class", "canvas-edge");
        path.setAttribute("marker-end", "url(#canvas-arrow)");
        layer.append(path);
        // Long labels wrap to fit the space between the boxes
        const lines = wrap(h.what, 12);
        const label = document.createElementNS(SVG_NS, "text");
        label.setAttribute("text-anchor", "middle");
        label.setAttribute("class", "canvas-label");
        lines.forEach((line, i) => {
          const span = document.createElementNS(SVG_NS, "tspan");
          span.setAttribute("x", String((x1 + x2) / 2));
          span.setAttribute("y", String((y1 + y2) / 2 - 8 - (lines.length - 1 - i) * 14));
          span.textContent = line;
          label.append(span);
        });
        layer.append(label);
      }
      const defs = document.createElementNS(SVG_NS, "defs");
      defs.innerHTML =
        '<marker id="canvas-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z" class="canvas-arrowhead"/></marker>';
      layer.prepend(defs);
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(container);
    return () => observer.disconnect();
  }, [handoffKey, map.handoffs]);

  const node = (name: string) => {
    const s = status(name, plan, built, decisions);
    const head = org.roles.find((r) => r.id === org.departments.find((d) => d.name === name)?.head_role_id);
    const isSelected = selected === name;
    return (
      <button
        key={name}
        type="button"
        ref={(el) => {
          if (el) nodes.current.set(name, el);
          else nodes.current.delete(name);
        }}
        onClick={() => onSelect(name)}
        aria-pressed={isSelected}
        className={`relative z-10 flex w-full min-w-0 flex-col items-start overflow-hidden rounded-xl border bg-sheet py-2.5 pr-3 pl-4 text-left transition-[box-shadow,border-color] sm:w-40 ${
          isSelected
            ? "border-ai shadow-[0_0_0_4px_rgb(79_70_229/0.14),var(--shadow-raised)]"
            : s.built
              ? "border-line shadow-[var(--shadow-card)] hover:border-ai/50 hover:shadow-[var(--shadow-raised)]"
              : "border-dashed border-faint/60 hover:border-ai/50"
        }`}
      >
        <span
          aria-hidden
          className={`absolute inset-y-0 left-0 w-1 ${s.problems ? "bg-alert" : s.built ? "bg-ok" : "bg-line"}`}
        />
        <span className="font-semibold break-words">{name}</span>
        {head && <span className="w-full truncate text-xs text-muted">{head.title}</span>}
        <span className="mt-2 flex w-full items-center justify-between gap-2 text-xs tabular-nums">
          <span className={s.built ? "font-medium text-ok" : "text-faint"}>
            {s.built ? `${s.built} of ${s.planned} built` : `${s.planned} planned`}
          </span>
          {s.problems > 0 && (
            <span
              className="inline-flex items-center gap-0.5 rounded-full bg-alert-soft px-1.5 py-0.5 font-semibold text-alert"
              aria-label={`${s.problems} ${s.problems === 1 ? "problem" : "problems"}`}
            >
              <AlertIcon width="11" height="11" strokeWidth="2" />
              {s.problems}
            </span>
          )}
        </span>
      </button>
    );
  };

  // Phones: each path of handoffs as one line of department chips
  const lanes = flowLanes(map.handoffs, names);
  const chip = (name: string) => {
    const s = status(name, plan, built, decisions);
    return (
      <button
        type="button"
        onClick={() => onSelect(name)}
        aria-pressed={selected === name}
        className={`inline-flex items-center gap-1.5 rounded-lg border bg-sheet px-2.5 py-1 font-medium shadow-[var(--shadow-card)] ${
          selected === name ? "border-ai text-ai" : s.built ? "border-line" : "border-dashed border-faint/60"
        }`}
      >
        {name}
        {s.problems > 0 && <span className="rounded-full bg-alert-soft px-1.5 text-xs font-semibold text-alert">{s.problems}</span>}
      </button>
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <ol className="flex flex-col gap-4 sm:hidden" aria-label="Paths work takes between departments">
        {lanes.lanes.map((lane, i) => (
          <li key={i} className="flex flex-wrap items-center gap-x-2 gap-y-2">
            {chip(lane[0].from)}
            {lane.map((h) => (
              <Fragment key={`${h.from}-${h.to}-${h.what}`}>
                <span className="text-xs text-muted">→ {h.what} →</span>
                {chip(h.to)}
              </Fragment>
            ))}
          </li>
        ))}
      </ol>
      <div ref={box} className="relative hidden sm:block">
        <svg ref={svg} className="pointer-events-none absolute inset-0 overflow-visible" aria-hidden />
        <ol
          aria-label="Departments in the order work flows"
          className="relative flex flex-col gap-14 sm:flex-row sm:items-center sm:gap-16"
        >
          {columns.map((column, i) => (
            <li key={i} className="flex flex-col gap-14 sm:gap-8">
              {column.map(node)}
            </li>
          ))}
        </ol>
      </div>
      <ul className="sr-only">
        {map.handoffs.map((h) => (
          <li key={`${h.from}-${h.to}-${h.what}`}>
            {h.from} hands {h.what} to {h.to}
          </li>
        ))}
      </ul>
      {alone.length > 0 && (
        <div className="flex flex-col gap-3 border-t border-line pt-4">
          <p className="text-sm text-muted">No handoffs found for these departments</p>
          <div className="hidden flex-wrap gap-4 sm:flex">{alone.map(node)}</div>
          <div className="flex flex-wrap gap-2 sm:hidden">{alone.map(chip)}</div>
        </div>
      )}
    </div>
  );
}
