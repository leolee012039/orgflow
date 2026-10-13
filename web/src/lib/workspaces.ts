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
import type { Analysis } from "./api";
import { db } from "./firebase";
import { openProblems } from "./decisions";
import type { BuiltWorkflow, CaseRecord, Decision } from "./types";

/** One company's analysis and the workflows built from it. The PDFs are not kept. */
export interface Workspace extends Analysis {
  company: string;
  documents: { orgChart: string; policies: string[] };
  /** Built workflows by planned workflow id */
  built: Record<string, BuiltWorkflow>;
  /** Cases run across departments, newest first */
  cases?: CaseRecord[];
  /** What people settled where the documents leave a case with no approver */
  decisions?: Decision[];
  analyzedAt: string;
  sample: boolean;
  /** Which sample company (web/src/lib/samples.json); absent on an analysis kept from before there were several */
  sampleId?: string;
}

export interface SavedWorkspace extends Workspace {
  id: string;
  owner: string;
  shared: boolean;
}

const workspaces = () => collection(db(), "workspaces");

// Firestore rejects undefined fields; a JSON round trip drops them
const plain = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export async function saveWorkspace(workspace: Workspace, owner: string): Promise<string> {
  const ref = await addDoc(workspaces(), {
    ...plain(workspace),
    owner,
    shared: false,
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  });
  return ref.id;
}

export const saveBuilt = (id: string, built: Record<string, BuiltWorkflow>) =>
  updateDoc(doc(db(), "workspaces", id), { built: plain(built), updatedAt: serverTimestamp() });

export const MAX_CASES = 30;

export const saveDecisions = (id: string, decisions: Decision[]) =>
  updateDoc(doc(db(), "workspaces", id), { decisions: plain(decisions), updatedAt: serverTimestamp() });

export const saveCases = (id: string, cases: CaseRecord[]) =>
  updateDoc(doc(db(), "workspaces", id), { cases: plain(cases.slice(0, MAX_CASES)), updatedAt: serverTimestamp() });

/** The saved workspace, or null when it doesn't exist or this viewer may not see it. */
export async function loadWorkspace(id: string): Promise<SavedWorkspace | null> {
  try {
    const snap = await getDoc(doc(db(), "workspaces", id));
    return snap.exists() ? ({ ...(snap.data() as Omit<SavedWorkspace, "id">), id: snap.id } as SavedWorkspace) : null;
  } catch (e) {
    if ((e as { code?: string }).code === "permission-denied") return null;
    throw e;
  }
}

export async function listWorkspaces(owner: string): Promise<SavedWorkspace[]> {
  const snap = await getDocs(query(workspaces(), where("owner", "==", owner), limit(100)));
  return snap.docs
    .map((d) => ({ ...(d.data() as Omit<SavedWorkspace, "id">), id: d.id }) as SavedWorkspace)
    .sort((a, b) => b.analyzedAt.localeCompare(a.analyzedAt));
}

export const setShared = (id: string, shared: boolean) =>
  updateDoc(doc(db(), "workspaces", id), { shared, updatedAt: serverTimestamp() });
export const deleteWorkspace = (id: string) => deleteDoc(doc(db(), "workspaces", id));

/** Places the built workflows still stop a case, after the decisions people made. */
export function findings(built: Record<string, BuiltWorkflow>, decisions: Decision[] = []) {
  return { problems: Object.values(built).reduce((n, w) => n + openProblems(w, decisions), 0) };
}
