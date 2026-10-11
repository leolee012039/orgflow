"use client";

import { createContext, useContext } from "react";
import { documentName } from "@/lib/format";

/** The uploaded file names, so a quote can say which document it came from. */
export const DocumentNames = createContext<{ orgChart: string; policies: string[] } | undefined>(undefined);

/** A passage copied from the company's documents, set like the document itself. */
export function Quote({ text, doc }: { text: string; doc?: string }) {
  const documents = useContext(DocumentNames);
  return (
    <figure className="break-inside-avoid border-l-2 border-line pl-4">
      <blockquote className="font-serif text-[1.02rem] leading-relaxed text-ink">{text}</blockquote>
      {doc && <figcaption className="mt-1 text-xs break-all text-muted">{documentName(doc, documents)}</figcaption>}
    </figure>
  );
}
