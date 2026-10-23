"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth";
import { Notice } from "@/components/ui";

export default function LoginPage() {
  const { signIn, loading, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await signIn(email.trim(), password);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading || user) return null;
  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="brand"><span className="brand-logo">B</span><span>BidSynq<small>PROCUREMENT</small></span></div>
        <h1>Sign in</h1>
        <p className="muted">Welcome back. Use the account you registered with.</p>
        <form onSubmit={submit}>
          {error && <Notice kind="error">{error}</Notice>}
          <label className="field"><span>Email</span>
            <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field"><span>Password</span>
            <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</button>
        </form>
        <p className="auth-foot">New here? <Link href="/register">Create an account</Link></p>
      </div>
    </div>
  );
}
