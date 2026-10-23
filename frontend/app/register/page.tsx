"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Notice } from "@/components/ui";

export default function RegisterPage() {
  const { signIn, loading, user } = useAuth();
  const [form, setForm] = useState({ name: "", email: "", password: "", company_name: "", role: "supplier" as "buyer" | "supplier" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form, value: string) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.register({ ...form, email: form.email.trim(), name: form.name.trim(), company_name: form.company_name.trim() });
      await signIn(form.email.trim(), form.password);
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
        <h1>Create your account</h1>
        <p className="muted">Buyers publish tenders; suppliers submit bids. Administrator accounts are created by the platform owner.</p>
        <form onSubmit={submit}>
          {error && <Notice kind="error">{error}</Notice>}
          <label className="field"><span>Full name</span>
            <input required minLength={2} maxLength={120} autoComplete="name" value={form.name} onChange={(e) => set("name", e.target.value)} /></label>
          <label className="field"><span>Company</span>
            <input maxLength={180} autoComplete="organization" value={form.company_name} onChange={(e) => set("company_name", e.target.value)} /></label>
          <label className="field"><span>I am a</span>
            <select value={form.role} onChange={(e) => set("role", e.target.value)}>
              <option value="supplier">Supplier - I want to bid on tenders</option>
              <option value="buyer">Buyer - I want to publish tenders</option>
            </select></label>
          <label className="field"><span>Email</span>
            <input type="email" required autoComplete="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></label>
          <label className="field"><span>Password</span>
            <input type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={form.password} onChange={(e) => set("password", e.target.value)} />
            <small>At least 8 characters.</small></label>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Creating account..." : "Create account"}</button>
        </form>
        <p className="auth-foot">Already registered? <Link href="/login">Sign in</Link></p>
      </div>
    </div>
  );
}
