"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TenderCreate, TenderOut } from "@/lib/types";
import { dateTime, label, tenderTypeLabel } from "@/lib/format";
import { Loading, Notice, PageHeading, Panel, Pill } from "@/components/ui";
import TenderForm from "@/components/TenderForm";
import BidPanel from "@/components/tender/BidPanel";
import RankingPanel from "@/components/tender/RankingPanel";
import AssistantPanel from "@/components/tender/AssistantPanel";
import RiskPanel from "@/components/tender/RiskPanel";
import InsightsPanel from "@/components/tender/InsightsPanel";

type Tab = "overview" | "bids" | "documents" | "insights" | "risk";

export default function TenderDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { user } = useAuth();
  const [tender, setTender] = useState<TenderOut | null>(null);
  const [bidCount, setBidCount] = useState(0);
  const [tab, setTab] = useState<Tab>("overview");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!Number.isInteger(id) || id < 1) { setError("Invalid tender."); return; }
    api.getTender(id).then(setTender).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const isManager = user?.role === "admin" || (user?.role === "buyer" && tender?.buyer_id === user.id);
  useEffect(() => {
    if (!tender || !isManager) return;
    // Sealed tenders refuse to list bids while open; treat that as "unknown", which keeps the form permissive.
    api.listBids(tender.id).then((b) => setBidCount(b.length)).catch(() => setBidCount(0));
  }, [tender, isManager]);

  if (error) return <Notice kind="error">{error} <Link href="/tenders">Back to tenders</Link></Notice>;
  if (!tender || !user) return <Loading />;

  async function changeStatus(status: "closed" | "cancelled") {
    const text = status === "closed" ? "Close bidding now? Suppliers will no longer be able to bid." : "Cancel this tender? This cannot be undone.";
    if (!window.confirm(text)) return;
    setError(""); setBusy(true);
    try { setTender(await api.setTenderStatus(id, status)); setNotice(status === "closed" ? "Tender closed." : "Tender cancelled."); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function save(values: TenderCreate) {
    const { tender_type, ...editable } = values;
    setTender(await api.updateTender(id, editable));
    setEditing(false);
    setNotice("Tender updated.");
  }

  const tabs: { key: Tab; text: string; show: boolean }[] = [
    { key: "overview", text: "Overview", show: true },
    { key: "bids", text: user.role === "supplier" ? "My bid" : "Bids & ranking", show: user.role !== "supplier" || tender.status !== "cancelled" },
    { key: "documents", text: "Documents & Q&A", show: true },
    { key: "insights", text: "Price insights", show: true },
    { key: "risk", text: "Risk", show: isManager },
  ];
  const bidsClosed = !tender.bidding_open;

  return (
    <>
      <PageHeading title={tender.title} subtitle={`${tender.category} · ${tenderTypeLabel[tender.tender_type] ?? tender.tender_type}`}
        actions={<><Pill value={tender.status} />{tender.status === "open" && !tender.bidding_open && <Pill value="deadline passed" tone="warn" />}</>} />
      {notice && <Notice kind="success">{notice}</Notice>}
      <div className="tabs" role="tablist">
        {tabs.filter((t) => t.show).map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>{t.text}</button>
        ))}
      </div>

      {tab === "overview" && (editing ? (
        <Panel title="Edit tender"><TenderForm tender={tender} hasBids={bidCount > 0} submitLabel="Save changes" onSubmit={save} />
          <div className="form-actions"><button className="btn" onClick={() => setEditing(false)}>Cancel</button></div></Panel>
      ) : (
        <Panel title="Details" actions={isManager && tender.status === "open" && (
          <div className="heading-actions">
            <button className="btn btn-small" onClick={() => setEditing(true)}>Edit</button>
            <button className="btn btn-small" disabled={busy} onClick={() => changeStatus("closed")}>Close bidding</button>
            <button className="btn btn-danger btn-small" disabled={busy} onClick={() => changeStatus("cancelled")}>Cancel tender</button>
          </div>)}>
          <dl className="kv">
            <dt>Deadline</dt><dd>{dateTime(tender.deadline)}</dd>
            <dt>Quantity</dt><dd>{tender.quantity.toLocaleString("en-IN")}</dd>
            <dt>Description</dt><dd style={{ whiteSpace: "pre-wrap" }}>{tender.description || "-"}</dd>
            <dt>Mandatory requirements</dt><dd style={{ whiteSpace: "pre-wrap" }}>{tender.mandatory_requirements || "None listed"}</dd>
            <dt>Scoring weights</dt><dd>Price {(tender.w_price * 100).toFixed(0)}% · Delivery {(tender.w_delivery * 100).toFixed(0)}% · Trust {(tender.w_trust * 100).toFixed(0)}% · Requirement match {(tender.w_match * 100).toFixed(0)}%</dd>
            {tender.tender_type === "reverse_auction" && <><dt>Anti-sniping</dt><dd>{tender.anti_sniping ? "On - late bids extend the deadline by 2 minutes" : "Off"}</dd></>}
            {tender.tender_type === "sealed" && <><dt>Sealed bids</dt><dd>Hidden from everyone but the bidder until bidding closes</dd></>}
            <dt>Published</dt><dd>{dateTime(tender.created_at)}</dd>
          </dl>
        </Panel>
      ))}

      {tab === "bids" && (
        <>
          <BidPanel tender={tender} role={user.role} />
          {isManager && (bidsClosed ? <RankingPanel tender={tender} /> : <Notice kind="info">The ranking becomes available once bidding closes ({label(tender.status)}, deadline {dateTime(tender.deadline)}).</Notice>)}
        </>
      )}
      {tab === "documents" && <AssistantPanel tenderId={id} canManage={Boolean(isManager)} hasRequirements={Boolean(tender.mandatory_requirements.trim())} />}
      {tab === "insights" && <InsightsPanel tenderId={id} />}
      {tab === "risk" && isManager && (tender.tender_type === "sealed" && !bidsClosed
        ? <Notice kind="info">Risk scans for sealed tenders unlock after bidding closes, so sealed bids stay confidential.</Notice>
        : <RiskPanel tenderId={id} isAdmin={user.role === "admin"} />)}
    </>
  );
}
