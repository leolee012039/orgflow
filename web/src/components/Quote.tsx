const DOC_NAMES: Record<string, string> = {
  policy: "Purchasing policy",
  org_chart: "Organization chart",
};

/** A passage copied from the company's documents, set like the document itself. */
export function Quote({ text, doc }: { text: string; doc?: string }) {
  return (
    <figure className="border-l-2 border-line pl-4">
      <blockquote className="font-serif text-[1.02rem] leading-relaxed text-ink">{text}</blockquote>
      {doc && <figcaption className="mt-1 text-xs text-muted">{DOC_NAMES[doc] ?? doc}</figcaption>}
    </figure>
  );
}
