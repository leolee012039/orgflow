import list from "./samples.json";

/** A fictional company whose documents Gemini read once; the reading was checked and saved (api/fixtures/<id>/).
 * scripts/save_sample.py writes samples.json; the API knows the same documents by their fingerprints. */
export type Sample = {
  id: string;
  company: string;
  market: string;
  industry: string;
  language: string;
  /** Paths under /demo/: the org chart, then the policies in the order the API knows them */
  orgChart: string;
  policies: string[];
  /** Example answers for its case forms, in its own language: "workflow id.field" or "field" */
  examples?: Record<string, string>;
};

// TypeScript reads each sample's examples as its own shape; samples.json is written by scripts/save_sample.py
// and checked against the API's fixtures by tests/test_samples.py
export const SAMPLES = list as unknown as Sample[];
/** The sample the page offers first, the one the demo video walks through */
export const DEFAULT_SAMPLE = SAMPLES[0];

export const sampleById = (id?: string): Sample => SAMPLES.find((s) => s.id === id) ?? DEFAULT_SAMPLE;
export const sampleFiles = (s: Sample): string[] => [s.orgChart, ...s.policies];
export const fileName = (path: string): string => path.split("/").pop() ?? path;
