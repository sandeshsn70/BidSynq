import type { ReactNode } from "react";
import { label } from "@/lib/format";

export function PageHeading({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}

export function Notice({ kind, children }: { kind: "error" | "success" | "info" | "warn"; children: ReactNode }) {
  return <div className={`notice ${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

export function Loading({ text = "Loading..." }: { text?: string }) {
  return <div className="loading" role="status"><span className="spinner" aria-hidden />{text}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}

export function Pill({ value, tone }: { value: string; tone?: string }) {
  return <span className={`pill ${tone ?? value}`}>{label(value)}</span>;
}

export function StatCard({ name, value }: { name: string; value: number | string }) {
  return <div className="stat-card"><span>{name}</span><strong>{value}</strong></div>;
}

export function Panel({ title, subtitle, actions, children }: { title?: string; subtitle?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      {title && (
        <div className="panel-heading">
          <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function ScoreBar({ value }: { value: number }) {
  const width = Math.max(0, Math.min(100, value));
  return <div className="score-bar" aria-hidden><i style={{ width: `${width}%` }} /></div>;
}
