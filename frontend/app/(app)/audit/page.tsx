"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuditPageOut, VerifyOut } from "@/lib/types";
import { dateTime } from "@/lib/format";
import { Empty, Loading, Notice, PageHeading, Panel, Pill } from "@/components/ui";

const PAGE = 50;

export default function AuditPage() {
  const { user } = useAuth();
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<AuditPageOut | null>(null);
  const [verify, setVerify] = useState<VerifyOut | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setPage(null); setError("");
    api.auditLogs(PAGE, offset).then(setPage).catch((e: Error) => setError(e.message));
  }, [offset]);
  useEffect(() => { if (user && user.role !== "supplier") load(); }, [load, user]);

  async function runVerify() {
    setBusy(true); setError("");
    try { setVerify(await api.verifyAudit()); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (user?.role === "supplier") return <Notice kind="info">The audit trail is available to buyers and administrators.</Notice>;
  return (
    <>
      <PageHeading title="Audit trail" subtitle={user?.role === "admin" ? "Every recorded action, hash-chained." : "Actions on your tenders and by you."}
        actions={user?.role === "admin" && <button className="btn btn-primary" onClick={runVerify} disabled={busy}>{busy ? "Verifying..." : "Verify integrity"}</button>} />
      {verify && (
        <Notice kind={verify.valid ? "success" : "error"}>
          {verify.valid ? `Chain intact: ${verify.checked_entries} entries verified.` : `Chain BROKEN at entry #${verify.broken_at_id} (${verify.reason}).`}
          {verify.head_hash && <div className="hash">Head hash: {verify.head_hash}</div>}
          <div style={{ marginTop: 6 }}>{verify.note}</div>
        </Notice>
      )}
      {error && <Notice kind="error">{error}</Notice>}
      <Panel>
        {!page && !error ? <Loading /> : page && page.items.length === 0 ? <Empty>{offset ? "No more entries." : "No audit entries yet."}</Empty> : page && (
          <div className="table-wrap"><table>
            <thead><tr><th>#</th><th>When</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
            <tbody>{page.items.map((i) => (
              <tr key={i.id}>
                <td>{i.id}</td><td>{dateTime(i.created_at)}</td>
                <td><Pill value={i.action} tone="low" /><small>actor {i.actor_id ?? "system"}</small></td>
                <td>{i.entity_type} {i.entity_id}</td>
                <td><details><summary>View</summary><pre className="evidence">{JSON.stringify(i.details, null, 2)}</pre><div className="hash">hash {i.entry_hash}</div></details></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
        <div className="form-actions">
          <button className="btn btn-small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</button>
          <button className="btn btn-small" disabled={!page || page.items.length < PAGE} onClick={() => setOffset(offset + PAGE)}>Older</button>
        </div>
      </Panel>
    </>
  );
}
