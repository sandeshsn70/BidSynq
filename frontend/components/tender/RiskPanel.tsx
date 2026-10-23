"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { RiskAlertOut } from "@/lib/types";
import { dateTime, label } from "@/lib/format";
import { Empty, Loading, Notice, Panel, Pill } from "../ui";

export function AlertCard({ alert, isAdmin, onChanged }: { alert: RiskAlertOut; isAdmin: boolean; onChanged: () => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function review(status: "reviewed" | "dismissed") {
    setError(""); setBusy(true);
    try { await api.reviewAlert(alert.id, status, note); onChanged(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <article className="citation">
      <div className="inline-form" style={{ justifyContent: "space-between" }}>
        <strong>{alert.title}</strong>
        <span><Pill value={alert.severity} /> <Pill value={alert.status} /></span>
      </div>
      <p>{alert.explanation}</p>
      <details><summary>Evidence ({label(alert.rule_key)})</summary><pre className="evidence">{JSON.stringify(alert.evidence, null, 2)}</pre></details>
      <small className="muted">Detected {dateTime(alert.created_at)}{alert.reviewed_at ? ` · reviewed ${dateTime(alert.reviewed_at)}` : ""}{alert.review_note ? ` · note: ${alert.review_note}` : ""}</small>
      {error && <Notice kind="error">{error}</Notice>}
      {isAdmin && alert.status === "open" && (
        <div className="inline-form" style={{ marginTop: 10 }}>
          <input placeholder="Review note (optional)" maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn btn-small" disabled={busy} onClick={() => review("reviewed")}>Mark reviewed</button>
          <button className="btn btn-small" disabled={busy} onClick={() => review("dismissed")}>Dismiss</button>
        </div>
      )}
    </article>
  );
}

export default function RiskPanel({ tenderId, isAdmin }: { tenderId: number; isAdmin: boolean }) {
  const [alerts, setAlerts] = useState<RiskAlertOut[] | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { api.riskAlerts("all", tenderId).then(setAlerts).catch((e: Error) => setError(e.message)); }, [tenderId]);
  useEffect(() => { load(); }, [load]);

  async function scan() {
    setError(""); setInfo(""); setBusy(true);
    try {
      const r = await api.scanRisks(tenderId);
      setAlerts(r.alerts);
      setInfo(`${r.bids_checked} bids checked, ${r.signals_detected} signals found, ${r.new_alerts_saved} new. ${r.disclaimer}`);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <Panel title="Risk signals" subtitle="Explainable checks for human review - never a finding of wrongdoing."
      actions={<button className="btn btn-primary btn-small" onClick={scan} disabled={busy}>{busy ? "Scanning..." : "Scan bids now"}</button>}>
      {error && <Notice kind="error">{error}</Notice>}
      {info && <Notice kind="info">{info}</Notice>}
      {alerts === null && !error ? <Loading /> : alerts && alerts.length === 0 ? <Empty>No risk signals saved for this tender. Run a scan once bids are in.</Empty> :
        alerts?.map((a) => <AlertCard key={a.id} alert={a} isAdmin={isAdmin} onChanged={load} />)}
    </Panel>
  );
}
