"use client";

import { useState, type FormEvent } from "react";
import type { TenderCreate, TenderOut } from "@/lib/types";
import { isoToLocalInput, localInputToIso } from "@/lib/format";
import { Notice } from "./ui";

type Values = TenderCreate;

function initial(t?: TenderOut): Values {
  const defaultDeadline = isoToLocalInput(new Date(Date.now() + 7 * 864e5).toISOString());
  return t
    ? { title: t.title, description: t.description, category: t.category, quantity: t.quantity,
        tender_type: t.tender_type as Values["tender_type"], deadline: isoToLocalInput(t.deadline),
        mandatory_requirements: t.mandatory_requirements, w_price: t.w_price, w_delivery: t.w_delivery,
        w_trust: t.w_trust, w_match: t.w_match, anti_sniping: t.anti_sniping }
    : { title: "", description: "", category: "General", quantity: 1, tender_type: "rfq", deadline: defaultDeadline,
        mandatory_requirements: "", w_price: 0.35, w_delivery: 0.2, w_trust: 0.25, w_match: 0.2, anti_sniping: true };
}

/** Create/edit form. ``deadline`` is held as a local datetime-local string and converted to ISO on submit. */
export default function TenderForm({ tender, hasBids = false, submitLabel, onSubmit }: {
  tender?: TenderOut; hasBids?: boolean; submitLabel: string; onSubmit: (values: TenderCreate) => Promise<void>;
}) {
  const [v, setV] = useState<Values>(() => initial(tender));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const editing = Boolean(tender);
  const frozen = editing && hasBids;
  const total = v.w_price + v.w_delivery + v.w_trust + v.w_match;
  const set = <K extends keyof Values>(key: K, value: Values[K]) => setV((s) => ({ ...s, [key]: value }));
  const num = (value: string) => (value === "" ? 0 : Number(value));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (Math.abs(total - 1) > 0.001) { setError(`Scoring weights must add up to 1.00 (currently ${total.toFixed(2)}).`); return; }
    setBusy(true);
    try {
      await onSubmit({ ...v, deadline: localInputToIso(v.deadline) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      {error && <Notice kind="error">{error}</Notice>}
      {frozen && <Notice kind="info">Bids have been submitted, so quantity, requirements and scoring weights are locked. The deadline can only be extended.</Notice>}
      <div className="form-grid">
        <label className="field full"><span>Title</span>
          <input required minLength={4} maxLength={200} value={v.title} onChange={(e) => set("title", e.target.value)} /></label>
        <label className="field"><span>Category</span>
          <input required maxLength={100} value={v.category} onChange={(e) => set("category", e.target.value)} />
          <small>Used to find similar tenders and price history.</small></label>
        <label className="field"><span>Quantity</span>
          <input type="number" required min={1} step={1} disabled={frozen} value={v.quantity} onChange={(e) => set("quantity", Math.max(1, Math.floor(num(e.target.value))))} /></label>
        <label className="field"><span>Tender type</span>
          <select disabled={editing} value={v.tender_type} onChange={(e) => set("tender_type", e.target.value as Values["tender_type"])}>
            <option value="rfq">RFQ - open quotes</option>
            <option value="sealed">Sealed bid - hidden until closed</option>
            <option value="reverse_auction">Reverse auction - suppliers may lower prices</option>
          </select>{editing && <small>The type cannot change after creation.</small>}</label>
        <label className="field"><span>Bid deadline (your local time)</span>
          <input type="datetime-local" required value={v.deadline} onChange={(e) => set("deadline", e.target.value)} /></label>
        <label className="field full"><span>Description</span>
          <textarea maxLength={10000} value={v.description} onChange={(e) => set("description", e.target.value)} /></label>
        <label className="field full"><span>Mandatory requirements</span>
          <textarea maxLength={5000} disabled={frozen} value={v.mandatory_requirements} onChange={(e) => set("mandatory_requirements", e.target.value)} />
          <small>One requirement per line. The assistant looks for evidence of each one in your uploaded documents.</small></label>
        <fieldset className="field full" style={{ border: 0, padding: 0, margin: 0 }} disabled={frozen}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>Scoring weights (must total 1.00 - now {total.toFixed(2)})</span>
          <div className="form-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", marginTop: 6 }}>
            {([["w_price", "Price"], ["w_delivery", "Delivery"], ["w_trust", "Supplier trust"], ["w_match", "Requirement match"]] as const).map(([key, text]) => (
              <label className="field" key={key}><span>{text}</span>
                <input type="number" min={0} max={1} step={0.05} value={v[key]} onChange={(e) => set(key, num(e.target.value))} /></label>
            ))}
          </div>
        </fieldset>
        {v.tender_type === "reverse_auction" && (
          <label className="check field full"><span><input type="checkbox" checked={v.anti_sniping} onChange={(e) => set("anti_sniping", e.target.checked)} />{" "}
            Extend the deadline by 2 minutes when a bid arrives in the last 2 minutes</span></label>
        )}
      </div>
      <div className="form-actions"><button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : submitLabel}</button></div>
    </form>
  );
}
