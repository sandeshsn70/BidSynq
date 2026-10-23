"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { RiskAlertOut } from "@/lib/types";
import { Empty, Loading, Notice, PageHeading, Panel } from "@/components/ui";
import { AlertCard } from "@/components/tender/RiskPanel";

type Filter = "open" | "reviewed" | "dismissed" | "all";

export default function RiskPage() {
  const { user } = useAuth();
  const [filter, setFilter] = useState<Filter>("open");
  const [alerts, setAlerts] = useState<RiskAlertOut[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setAlerts(null); setError("");
    api.riskAlerts(filter).then(setAlerts).catch((e: Error) => setError(e.message));
  }, [filter]);
  useEffect(() => { if (user && user.role !== "supplier") load(); }, [load, user]);

  if (user?.role === "supplier") return <Notice kind="info">Risk alerts are only available to buyers and administrators.</Notice>;
  const isAdmin = user?.role === "admin";
  return (
    <>
      <PageHeading title="Risk alerts" subtitle="Signals for human review. They are not evidence of fraud or collusion." />
      {!isAdmin && <Notice kind="info">Alerts are reviewed by a platform administrator so the review is independent of the buyer. Run scans from a tender&apos;s Risk tab.</Notice>}
      <Panel actions={
        <select aria-label="Filter alerts" value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
          <option value="open">Open</option><option value="reviewed">Reviewed</option><option value="dismissed">Dismissed</option><option value="all">All</option>
        </select>}>
        {error && <Notice kind="error">{error}</Notice>}
        {alerts === null && !error ? <Loading /> : alerts && alerts.length === 0 ? <Empty>No {filter === "all" ? "" : filter} alerts.</Empty> :
          alerts?.map((a) => (
            <div key={a.id}><small className="muted">Tender <Link href={`/tenders/${a.tender_id}`}>#{a.tender_id}</Link></small>
              <AlertCard alert={a} isAdmin={Boolean(isAdmin)} onChanged={load} /></div>
          ))}
      </Panel>
    </>
  );
}
