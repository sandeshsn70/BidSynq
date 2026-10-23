"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { MyBidOut, TrustOut } from "@/lib/types";
import { dateTime, label, money } from "@/lib/format";
import { Empty, Loading, Notice, PageHeading, Panel, Pill, ScoreBar } from "@/components/ui";

export default function MyBidsPage() {
  const { user } = useAuth();
  const [bids, setBids] = useState<MyBidOut[] | null>(null);
  const [trust, setTrust] = useState<TrustOut | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user?.role !== "supplier") return;
    Promise.all([api.myBids(), api.myTrust()])
      .then(([b, t]) => { setBids(b); setTrust(t); })
      .catch((e: Error) => setError(e.message));
  }, [user?.role]);

  if (user && user.role !== "supplier") return <Notice kind="info">This page is for supplier accounts.</Notice>;
  return (
    <>
      <PageHeading title="My bids & trust" subtitle="Everything you have bid on, and how buyers' feedback shapes your trust score." />
      {error && <Notice kind="error">{error}</Notice>}
      {!bids && !error && <Loading />}
      {trust && (
        <Panel title="Your trust score" subtitle="Advisory. Calculated from buyer-recorded delivery outcomes.">
          <div className="inline-form"><strong style={{ fontSize: 28 }}>{trust.score}</strong><span>/ 100 · {label(trust.confidence)} · {trust.observations} outcomes</span></div>
          <ScoreBar value={trust.score} />
          <p className="muted">{trust.explanation}</p>
          {trust.recent_outcomes.length > 0 && (
            <div className="table-wrap"><table><thead><tr><th>Tender</th><th className="num">Quality</th><th>On time</th><th className="num">Issues</th><th>Recorded</th></tr></thead>
              <tbody>{trust.recent_outcomes.map((o) => (
                <tr key={`${o.tender_id}`}><td><Link href={`/tenders/${o.tender_id}`}>#{o.tender_id}</Link></td><td className="num">{o.quality_score}/5</td><td>{o.on_time ? "Yes" : "No"}</td><td className="num">{o.issue_count}</td><td>{dateTime(o.created_at)}</td></tr>
              ))}</tbody></table></div>
          )}
        </Panel>
      )}
      {bids && (
        <Panel title={`Bids (${bids.length})`}>
          {bids.length === 0 ? <Empty>You have not bid on any tender yet. <Link href="/tenders">Browse open tenders</Link>.</Empty> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Tender</th><th className="num">Your price</th><th className="num">Delivery</th><th>Deadline</th><th>Status</th></tr></thead>
              <tbody>{bids.map((b) => (
                <tr key={b.id}>
                  <td><Link href={`/tenders/${b.tender_id}`}>{b.tender_title}</Link><small>{label(b.tender_type)}</small></td>
                  <td className="num">{money(b.price)}</td><td className="num">{b.delivery_days} d</td>
                  <td>{dateTime(b.tender_deadline)}</td><td><Pill value={b.bidding_open ? "open" : b.tender_status === "open" ? "closed" : b.tender_status} /></td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </Panel>
      )}
    </>
  );
}
