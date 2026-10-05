"use client";

import {
  addDoc,
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  limit,
  query,
  serverTimestamp,
  updateDoc,
  where,
} from "firebase/firestore";
import { db } from "./firebase";
import type { Opportunity, Organization, WithMeta, WorkflowResult } from "./types";

/** One policy health check: what Gemini read and what the checks found. The PDFs are not kept. */
export interface HealthCheck {
  company: string;
  documents: { orgChart: string; policy: string };
  organization: WithMeta<Organization>;
  opportunities: WithMeta<{ opportunities: Opportunity[] }>;
  workflow: WithMeta<WorkflowResult>;
  checkedAt: string;
  sample: boolean;
}

export interface SavedCheck extends HealthCheck {
  id: string;
  owner: string;
  shared: boolean;
}

/** What the report leads with. */
export function summarize(check: HealthCheck) {
  const gaps = check.workflow.gaps ?? [];
  const missing = gaps.filter((g) => g.status === "missing");
  const toConfirm = gaps.filter((g) => g.status === "possible_match");
  const amountGaps = check.workflow.amount_gaps ?? [];
  return { missing, toConfirm, amountGaps, problems: missing.length + amountGaps.length };
}

const audits = () => collection(db(), "audits");

export async function saveCheck(check: HealthCheck, owner: string): Promise<string> {
  // Firestore rejects undefined fields; a JSON round trip drops them
  const data = JSON.parse(JSON.stringify(check)) as HealthCheck;
  const ref = await addDoc(audits(), { ...data, owner, shared: false, createdAt: serverTimestamp() });
  return ref.id;
}

/** The saved check, or null when it doesn't exist or this viewer may not see it. */
export async function loadCheck(id: string): Promise<SavedCheck | null> {
  try {
    const snap = await getDoc(doc(db(), "audits", id));
    return snap.exists() ? ({ ...(snap.data() as Omit<SavedCheck, "id">), id: snap.id } as SavedCheck) : null;
  } catch (e) {
    if ((e as { code?: string }).code === "permission-denied") return null;
    throw e;
  }
}

export async function listChecks(owner: string): Promise<SavedCheck[]> {
  const snap = await getDocs(query(audits(), where("owner", "==", owner), limit(100)));
  return snap.docs
    .map((d) => ({ ...(d.data() as Omit<SavedCheck, "id">), id: d.id }) as SavedCheck)
    .sort((a, b) => b.checkedAt.localeCompare(a.checkedAt));
}

export const setShared = (id: string, shared: boolean) => updateDoc(doc(db(), "audits", id), { shared });
export const deleteCheck = (id: string) => deleteDoc(doc(db(), "audits", id));
