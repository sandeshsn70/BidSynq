"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TenderOut } from "@/lib/types";
import AssistantPanel from "@/components/tender/AssistantPanel";
import { Empty, Loading, Notice, PageHeading, Panel } from "@/components/ui";

export default function AssistantPage() {
  const { user } = useAuth();
  const [tenders, setTenders] = useState<TenderOut[] | null>(null);
  const [tenderId, setTenderId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.listTenders("all")
      .then((rows) => { setTenders(rows); if (rows.length) setTenderId(String(rows[0].id)); })
      .catch((e: Error) => setError(e.message));
  }, []);

  const selected = tenders?.find((t) => String(t.id) === tenderId);
  const canManage = Boolean(selected && user && (user.role === "admin" || (user.role === "buyer" && selected.buyer_id === user.id)));
  return (
    <>
      <PageHeading title="Tender assistant" subtitle="Ask questions about a tender's documents and see exactly which passages the answer comes from." />
      {error && <Notice kind="error">{error}</Notice>}
      {!tenders && !error && <Loading />}
      {tenders && tenders.length === 0 && <Empty>No tenders available yet.</Empty>}
      {tenders && tenders.length > 0 && (
        <>
          <Panel>
            <label className="field"><span>Tender</span>
              <select value={tenderId} onChange={(e) => setTenderId(e.target.value)}>
                {tenders.map((t) => <option key={t.id} value={t.id}>#{t.id} · {t.title} ({t.status})</option>)}
              </select></label>
          </Panel>
          {selected && <AssistantPanel key={selected.id} tenderId={selected.id} canManage={canManage} hasRequirements={Boolean(selected.mandatory_requirements.trim())} />}
        </>
      )}
    </>
  );
}
