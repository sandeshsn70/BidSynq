"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { SupplierOutcomeIn, RankingOut, TenderOut, TrustOut } from "@/lib/types";
import { label } from "@/lib/format";
import { Empty, Loading, Notice, Panel, Pill, ScoreBar } from "../ui";

function OutcomeForm({ tenderId, supplierId, onSaved }: { tenderId: number; supplierId: number; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ quality: "4", onTime: true, issues: "0", notes: "" });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(""); setBusy(true);
    const body: SupplierOutcomeIn = { supplier_id: supplierId, quality_score: Number(f.quality), on_time: f.onTime, issue_count: Number(f.issues), notes: f.notes };
    try { await api.recordOutcome(tenderId, body); setDone(true); setOpen(false); onSaved(); }
    catch (err) { setError((err as Error).message); if (/already recorded/i.test((err as Error).message)) setDone(true); }
    finally { setBusy(false); }
  }

  if (done) return <small>Outcome recorded</small>;
  if (!open) return <button className="link-button" onClick={() => setOpen(true)}>Record delivery outcome</button>;
  return (
    <form onSubmit={submit} style={{ marginTop: 8, display: "grid", gap: 8, maxWidth: 360 }}>
      {error && <Notice kind="error">{error}</Notice>}
      <label className="field"><span>Quality (1-5)</span><input type="number" min={1} max={5} step={0.5} required value={f.quality} onChange={(e) => setF({ ...f, quality: e.target.value })} /></label>
      <label className="check"><input type="checkbox" checked={f.onTime} onChange={(e) => setF({ ...f, onTime: e.target.checked })} /> Delivered on time</label>
      <label className="field"><span>Issues found</span><input type="number" min={0} max={100} step={1} required value={f.issues} onChange={(e) => setF({ ...f, issues: e.target.value })} /></label>
      <label className="field"><span>Private note</span><textarea maxLength={2000} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
      <div className="inline-form"><button className="btn btn-primary btn-small" disabled={busy}>Save outcome</button><button type="button" className="btn btn-small" onClick={() => setOpen(false)}>Cancel</button></div>
    </form>
  );
}

function TrustLine({ supplierId }: { supplierId: number }) {
  const [trust, setTrust] = useState<TrustOut | null>(null);
  useEffect(() => { api.supplierTrust(supplierId).then(setTrust).catch(() => setTrust(null)); }, [supplierId]);
  return trust ? <small>Trust {trust.score}/100 · {label(trust.confidence)} ({trust.observations} past outcomes)</small> : null;
}

export default function RankingPanel({ tender }: { tender: TenderOut }) {
  const [data, setData] = useState<RankingOut | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => { api.ranking(tender.id).then(setData).catch((e: Error) => setError(e.message)); }, [tender.id]);
  useEffect(() => { load(); }, [load]);

  const closedForOutcomes = tender.status === "closed" || tender.status === "awarded";
  if (error) return <Notice kind="info">{error}</Notice>;
  if (!data) return <Loading />;
  return (
    <Panel title="Explainable bid ranking" subtitle="Advisory only. You decide who wins.">
      <p className="muted">{data.method}</p>
      <p className="muted">Weights - {Object.entries(data.weights).map(([k, w]) => `${label(k)} ${(w * 100).toFixed(0)}%`).join(" · ")}</p>
      {data.ranking.length === 0 ? <Empty>No bids to rank.</Empty> : (
        <div className="table-wrap"><table>
          <thead><tr><th>#</th><th>Supplier</th><th>Score</th><th>Why</th></tr></thead>
          <tbody>
            {data.ranking.map((r, i) => (
              <tr key={r.bid_id ?? i}>
                <td>{i + 1}</td>
                <td>{r.supplier_company || `Supplier #${r.supplier_id}`}{r.supplier_id != null && <><br /><TrustLine supplierId={r.supplier_id} /></>}
                  {closedForOutcomes && r.supplier_id != null && <div><OutcomeForm tenderId={tender.id} supplierId={r.supplier_id} onSaved={() => undefined} /></div>}</td>
                <td style={{ minWidth: 110 }}><strong>{r.score.toFixed(1)}</strong><ScoreBar value={r.score} />{!r.eligible && <Pill value="ineligible" tone="bad" />}</td>
                <td>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>{(r.explanation ?? []).map((line, j) => <li key={j}>{line}</li>)}</ul>
                  <small>{r.reason_codes.map(label).join(" · ")}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
      <p className="muted">{data.note}</p>
    </Panel>
  );
}
