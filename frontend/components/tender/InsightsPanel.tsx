"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PriceOut, SimilarOut } from "@/lib/types";
import { label, money } from "@/lib/format";
import { Empty, Loading, Notice, Panel, Pill } from "../ui";

export default function InsightsPanel({ tenderId }: { tenderId: number }) {
  const [price, setPrice] = useState<PriceOut | null>(null);
  const [similar, setSimilar] = useState<SimilarOut | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setPrice(null); setSimilar(null); setError("");
    Promise.all([api.priceIntelligence(tenderId), api.similar(tenderId)])
      .then(([p, s]) => { if (!cancelled) { setPrice(p); setSimilar(s); } })
      .catch((e: Error) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [tenderId]);

  if (error) return <Notice kind="error">{error}</Notice>;
  if (!price || !similar) return <Loading />;
  return (
    <div className="grid-2">
      <Panel title="Price estimate" subtitle="Based on past bids on this platform - not market prices.">
        {price.predicted_total_price == null ? <Empty>{price.explanation}</Empty> : (
          <dl className="kv">
            <dt>Estimated total</dt><dd><strong>{money(price.predicted_total_price)}</strong></dd>
            {price.suggested_range && <><dt>Indicative range</dt><dd>{money(price.suggested_range.low)} - {money(price.suggested_range.high)}</dd></>}
            <dt>Method</dt><dd>{price.model ? label(price.model) : "-"} ({label(price.source)})</dd>
            <dt>Evidence</dt><dd>{price.training_samples} past bids, {price.same_category_samples} in this category</dd>
          </dl>
        )}
        <p className="muted">{price.explanation}</p>
        <p className="muted">{price.disclaimer}</p>
      </Panel>
      <Panel title="Similar past tenders" subtitle={similar.method}>
        {similar.matches.length === 0 ? <Empty>No similar closed tenders yet.</Empty> : (
          <ul style={{ paddingLeft: 18, margin: 0 }}>
            {similar.matches.map((m) => <li key={m.tender_id ?? m.title}>{m.title} <small className="muted">({m.category}, qty {m.quantity})</small> <Pill value={`${Math.round(m.similarity * 100)}% match`} tone="low" /></li>)}
          </ul>
        )}
        <p className="muted">{similar.note}</p>
      </Panel>
    </div>
  );
}
