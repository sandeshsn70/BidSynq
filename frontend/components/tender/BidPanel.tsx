"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { BidDetailOut, BidCreate, TenderOut } from "@/lib/types";
import { dateTime, money } from "@/lib/format";
import { Empty, Loading, Notice, Panel, Pill } from "../ui";

const BLANK = { price: "", delivery_days: "", validity_days: "30", requirement_match: "100", mandatory_met: true, compliance_notes: "" };

function SupplierBid({ tender, bids, reload }: { tender: TenderOut; bids: BidDetailOut[]; reload: () => void }) {
  const mine = bids[0];
  const [f, setF] = useState(BLANK);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);
  const canRevise = tender.tender_type === "reverse_auction";
  const set = (k: keyof typeof BLANK, v: string | boolean) => setF((s) => ({ ...s, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(""); setDone("");
    const body: BidCreate = {
      price: Number(f.price), delivery_days: Number(f.delivery_days), validity_days: Number(f.validity_days),
      requirement_match: Number(f.requirement_match), mandatory_met: f.mandatory_met, compliance_notes: f.compliance_notes,
    };
    if (!(body.price > 0) || !(body.delivery_days >= 1)) { setError("Enter a price above zero and delivery time of at least 1 day."); return; }
    setBusy(true);
    try {
      if (mine) await api.reviseBid(tender.id, body); else await api.submitBid(tender.id, body);
      setDone(mine ? "Your bid was lowered." : "Your bid was submitted.");
      setF(BLANK);
      reload();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  return (
    <>
      {done && <Notice kind="success">{done}</Notice>}
      {mine && (
        <Panel title="Your bid" subtitle={`Submitted ${dateTime(mine.created_at)}`}>
          <dl className="kv">
            <dt>Price</dt><dd>{money(mine.price)}</dd>
            <dt>Delivery</dt><dd>{mine.delivery_days} days</dd>
            <dt>Valid for</dt><dd>{mine.validity_days} days</dd>
            <dt>Requirement match</dt><dd>{mine.requirement_match}% (self-declared)</dd>
            <dt>Mandatory requirements</dt><dd>{mine.mandatory_met ? "Declared met" : "Declared NOT met"}</dd>
            {mine.compliance_notes && <><dt>Notes</dt><dd>{mine.compliance_notes}</dd></>}
          </dl>
        </Panel>
      )}
      {tender.bidding_open && (!mine || canRevise) ? (
        <Panel title={mine ? "Lower your bid" : "Submit your bid"}
          subtitle={tender.tender_type === "sealed" ? "Sealed bid: nobody sees it until bidding closes. You can only bid once." : canRevise ? "Reverse auction: each revision must be lower than your current price." : "You can submit one bid per tender."}>
          {error && <Notice kind="error">{error}</Notice>}
          <form onSubmit={submit}>
            <div className="form-grid">
              <label className="field"><span>Total price (INR){mine ? ` - below ${money(mine.price)}` : ""}</span>
                <input type="number" required min={0.01} step="any" value={f.price} onChange={(e) => set("price", e.target.value)} /></label>
              <label className="field"><span>Delivery time (days)</span>
                <input type="number" required min={1} max={3650} step={1} value={f.delivery_days} onChange={(e) => set("delivery_days", e.target.value)} /></label>
              <label className="field"><span>Bid valid for (days)</span>
                <input type="number" required min={1} max={365} step={1} value={f.validity_days} onChange={(e) => set("validity_days", e.target.value)} /></label>
              <label className="field"><span>Requirement match (%)</span>
                <input type="number" required min={0} max={100} step="any" value={f.requirement_match} onChange={(e) => set("requirement_match", e.target.value)} />
                <small>Your honest self-assessment; the buyer will verify it.</small></label>
              <label className="check field full"><span><input type="checkbox" checked={f.mandatory_met} onChange={(e) => set("mandatory_met", e.target.checked)} />{" "}
                I confirm we meet all mandatory requirements</span></label>
              <label className="field full"><span>Compliance notes</span>
                <textarea maxLength={5000} value={f.compliance_notes} onChange={(e) => set("compliance_notes", e.target.value)} /></label>
            </div>
            <div className="form-actions"><button className="btn btn-primary" disabled={busy}>{busy ? "Sending..." : mine ? "Submit lower price" : "Submit bid"}</button></div>
          </form>
        </Panel>
      ) : !mine ? (
        <Notice kind="info">{tender.bidding_open ? "" : "Bidding on this tender is closed."}</Notice>
      ) : null}
    </>
  );
}

export default function BidPanel({ tender, role, refreshKey = 0 }: { tender: TenderOut; role: string; refreshKey?: number }) {
  const [bids, setBids] = useState<BidDetailOut[] | null>(null);
  const [error, setError] = useState("");
  const [locked, setLocked] = useState(false);

  const load = useCallback(() => {
    setError(""); setLocked(false);
    api.listBids(tender.id).then(setBids).catch((e: Error & { status?: number }) => {
      if (e.status === 403 && /sealed/i.test(e.message)) { setLocked(true); setBids([]); } else setError(e.message);
    });
  }, [tender.id]);
  useEffect(() => { load(); }, [load, refreshKey, tender.status]);

  if (error) return <Notice kind="error">{error}</Notice>;
  if (bids === null) return <Loading />;
  if (role === "supplier") return <SupplierBid tender={tender} bids={bids} reload={load} />;

  if (locked) return <Notice kind="info">This is a sealed-bid tender. Bids stay hidden from everyone, including you, until bidding closes.</Notice>;
  return (
    <Panel title={`Bids received (${bids.length})`} subtitle="Lowest price first. Requirement match is self-declared by suppliers.">
      {bids.length === 0 ? <Empty>No bids yet.</Empty> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Supplier</th><th className="num">Price</th><th className="num">Delivery</th><th className="num">Match</th><th>Mandatory</th><th>Submitted</th></tr></thead>
          <tbody>
            {bids.map((b) => (
              <tr key={b.id}>
                <td>{b.supplier_company || b.supplier_name || `Supplier #${b.supplier_id}`}{b.compliance_notes && <small>{b.compliance_notes}</small>}</td>
                <td className="num">{money(b.price)}</td><td className="num">{b.delivery_days} d</td>
                <td className="num">{b.requirement_match}%</td>
                <td><Pill value={b.mandatory_met ? "met" : "not met"} tone={b.mandatory_met ? "good" : "bad"} /></td>
                <td>{dateTime(b.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </Panel>
  );
}
