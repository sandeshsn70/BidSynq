"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TenderOut, TenderStatusFilter } from "@/lib/types";
import { Empty, Loading, Notice, PageHeading, Panel, Pill } from "@/components/ui";
import { dateTime, tenderTypeLabel } from "@/lib/format";

const FILTERS: TenderStatusFilter[] = ["open", "closed", "awarded", "cancelled", "all"];

export default function TendersPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<TenderStatusFilter>("open");
  const [search, setSearch] = useState("");
  const [tenders, setTenders] = useState<TenderOut[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setTenders(null);
    setError("");
    api.listTenders(status)
      .then((rows) => { if (!cancelled) setTenders(rows); })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [status]);

  const needle = search.trim().toLowerCase();
  const rows = (tenders ?? []).filter((t) => !needle || `${t.title} ${t.category} ${t.description}`.toLowerCase().includes(needle));
  const canCreate = user?.role === "buyer" || user?.role === "admin";

  return (
    <>
      <PageHeading title="Tenders" subtitle={user?.role === "buyer" ? "Tenders you published." : "Browse tenders and open one to see details."}
        actions={canCreate && <Link className="btn btn-primary" href="/tenders/new">Create tender</Link>} />
      <Panel>
        <div className="inline-form" style={{ marginBottom: 16 }}>
          <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value as TenderStatusFilter)}>
            {FILTERS.map((f) => <option key={f} value={f}>{f === "all" ? "All statuses" : f[0].toUpperCase() + f.slice(1)}</option>)}
          </select>
          <input aria-label="Search tenders" placeholder="Search title or category" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {error && <Notice kind="error">{error}</Notice>}
        {tenders === null && !error && <Loading />}
        {tenders !== null && rows.length === 0 && <Empty>{tenders.length ? "No tenders match your search." : "No tenders found for this filter."}</Empty>}
        {rows.length > 0 && (
          <div className="table-wrap"><table>
            <thead><tr><th>Tender</th><th>Type</th><th className="num">Quantity</th><th>Deadline</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td><Link href={`/tenders/${t.id}`}>{t.title}</Link><small>{t.category}</small></td>
                  <td>{tenderTypeLabel[t.tender_type] ?? t.tender_type}</td>
                  <td className="num">{t.quantity.toLocaleString("en-IN")}</td>
                  <td>{dateTime(t.deadline)}</td>
                  <td><Pill value={t.status} />{t.status === "open" && !t.bidding_open && <small>deadline passed</small>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Panel>
    </>
  );
}
