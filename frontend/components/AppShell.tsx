"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { Loading } from "./ui";

const NAV: { href: string; text: string; roles: string[] }[] = [
  { href: "/", text: "Dashboard", roles: ["buyer", "supplier", "admin"] },
  { href: "/tenders", text: "Tenders", roles: ["buyer", "supplier", "admin"] },
  { href: "/bids", text: "My bids & trust", roles: ["supplier"] },
  { href: "/assistant", text: "Tender assistant", roles: ["buyer", "supplier", "admin"] },
  { href: "/risk", text: "Risk alerts", roles: ["buyer", "admin"] },
  { href: "/audit", text: "Audit trail", roles: ["buyer", "admin"] },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, signOut } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  if (loading) return <div className="auth-wrap"><Loading text="Signing you in..." /></div>;
  if (!user) return <div className="auth-wrap"><Loading text="Redirecting to sign in..." /></div>;

  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <div className="app-shell">
      <button className={`scrim ${open ? "open" : ""}`} aria-label="Close menu" onClick={() => setOpen(false)} />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand"><span className="brand-logo">B</span><span>BidSynq<small>PROCUREMENT</small></span></div>
        <nav className="side-nav" aria-label="Main">
          {NAV.filter((item) => item.roles.includes(user.role)).map((item) => (
            <Link key={item.href} href={item.href} className={`nav-link ${active(item.href) ? "active" : ""}`}
              aria-current={active(item.href) ? "page" : undefined} onClick={() => setOpen(false)}>
              {item.text}
            </Link>
          ))}
        </nav>
        <div className="sidebar-user">
          <div><strong>{user.name}</strong><small>{user.email}</small><br /><small>{user.role}{user.company_name ? ` · ${user.company_name}` : ""}</small></div>
          <button className="btn btn-small" onClick={signOut}>Sign out</button>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <button className="menu-toggle" aria-label="Open menu" onClick={() => setOpen(true)}>☰</button>
          <strong>BidSynq</strong>
          <span />
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
