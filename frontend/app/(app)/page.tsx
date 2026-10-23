"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DashboardOut, TenderOut } from "@/lib/types";
import { Empty, Loading, Notice, PageHeading, Panel, Pill, StatCard } from "@/components/ui";
import { dateTime } from "@/lib/format";

export default function DashboardPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<DashboardOut | null>(null);
  const [tenders, setTenders] = useState<TenderOut[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.dashboard(), api.listTenders("open")])
      .then(([s, t]) => { if (!cancelled) { setSummary(s); setTenders(t); } })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, []);

  if (!user) return null;
  const isSupplier = user.role === "supplier";
  return (
    <>
      <PageHeading
        title={`Welcome, ${user.name.split(" ")[0]}`}
        subtitle={isSupplier ? "Find open tenders and track your bids." : "Manage your tenders, review bids and monitor risk."}
        actions={!isSupplier && <Link className="btn btn-primary" href="/tenders/new">Create tender</Link>}
      />
      {error && <Notice kind="error">{error}</Notice>}
      {!summary && !error && <Loading />}
      {summary && (
        <div className="stats-grid">
          {isSupplier ? (
            <>
              <StatCard name="Open tenders" value={summary.open_tenders} />
              <StatCard name="Bids I submitted" value={summary.submitted_bids ?? 0} />
            </>
          ) : (
            <>
              <StatCard name={user.role === "admin" ? "All tenders" : "My tenders"} value={summary.tenders ?? 0} />
              <StatCard name="Open tenders" value={summary.open_tenders} />
              <StatCard name="Bids received" value={summary.bids_received ?? 0} />
              <StatCard name="Open risk alerts" value={summary.open_risk_alerts ?? 0} />
            </>
          )}
        </div>
      )}
      <Panel title="Open tenders" subtitle="Most recent first" actions={<Link href="/tenders">View all</Link>}>
        {tenders === null && !error ? <Loading /> : tenders && tenders.length === 0 ? (
          <Empty>{isSupplier ? "No tenders are open right now. Check back soon." : "You have no open tenders. Create one to start receiving bids."}</Empty>
        ) : (
          <div className="table-wrap"><table>
            <thead><tr><th>Tender</th><th>Category</th><th>Deadline</th><th>Status</th></tr></thead>
            <tbody>
              {(tenders ?? []).slice(0, 6).map((t) => (
                <tr key={t.id}>
                  <td><Link href={`/tenders/${t.id}`}>{t.title}</Link></td>
                  <td>{t.category}</td><td>{dateTime(t.deadline)}</td>
                  <td><Pill value={t.bidding_open ? "open" : "closed"} /></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Panel>
    </>
  );
}
