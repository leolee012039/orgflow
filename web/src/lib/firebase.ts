"use client";

import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";
import { useEffect, useState } from "react";

// The web config is public by design; Firestore rules decide who reads what.
const config = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

export const accountsEnabled = Boolean(config.apiKey && config.projectId);

function app(): FirebaseApp {
  return getApps()[0] ?? initializeApp(config);
}

export const auth = () => getAuth(app());
export const db = (): Firestore => getFirestore(app());

/** The signed-in user; undefined while Firebase is still finding out. */
export function useUser(): User | null | undefined {
  const [user, setUser] = useState<User | null | undefined>(accountsEnabled ? undefined : null);
  useEffect(() => (accountsEnabled ? onAuthStateChanged(auth(), setUser) : undefined), []);
  return user;
}

export async function signIn(): Promise<User> {
  const result = await signInWithPopup(auth(), new GoogleAuthProvider());
  return result.user;
}

export const signOut = () => firebaseSignOut(auth());

/** The current user's ID token for the OrgFlow API, or null when nobody is signed in. */
export async function idToken(): Promise<string | null> {
  if (!accountsEnabled) return null;
  const user = auth().currentUser;
  return user ? user.getIdToken() : null;
}

/** A sign-in failure in words a person can act on. */
export function signInMessage(e: unknown): string {
  const code = (e as { code?: string }).code ?? "";
  if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") return "Sign-in was cancelled.";
  if (code === "auth/popup-blocked") return "Your browser blocked the sign-in window. Allow pop-ups for this site and try again.";
  if (code === "auth/operation-not-allowed" || code === "auth/configuration-not-found")
    return "Google sign-in isn't switched on for OrgFlow yet.";
  return "Sign-in didn't work. Try again.";
}
