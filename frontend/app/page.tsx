
"use client";

import { useMemo, useState, type FormEvent } from "react";

type Page =
  | "Overview"
  | "Tenders"
  | "My Bids"
  | "Suppliers"
  | "Price Intelligence"
  | "Risk & Compliance"
  | "AI Assistant"
  | "Audit Trail";

type Tender = {
  id: string;
  title: string;
  buyer: string;
  category: string;
  value: number;
  deadline: string;
  bids: number;
  status: "Open" | "Closing soon" | "Under review";
};

const initialTenders: Tender[] = [
  { id: "TND-1048", title: "Industrial safety equipment supply", buyer: "Maharashtra Industrial Development Corp.", category: "Industrial", value: 2480000, deadline: "22 Oct 2026", bids: 8, status: "Open" },
  { id: "TND-1042", title: "IT hardware and workstation refresh", buyer: "Pune Smart City Development Corp.", category: "Technology", value: 1820000, deadline: "24 Oct 2026", bids: 5, status: "Open" },
  { id: "TND-1039", title: "Solar streetlight maintenance", buyer: "Municipal Council", category: "Energy", value: 1260000, deadline: "26 Oct 2026", bids: 12, status: "Closing soon" },
  { id: "TND-1027", title: "Office furniture procurement", buyer: "Public Works Division", category: "Facilities", value: 840000, deadline: "29 Oct 2026", bids: 4, status: "Open" },
  { id: "TND-1018", title: "Water quality testing services", buyer: "Regional Water Authority", category: "Services", value: 690000, deadline: "31 Oct 2026", bids: 7, status: "Under review" },
];

const suppliers = [
  { name: "Apex Industrial Solutions", category: "Industrial supplies", score: 96, delivery: "98%", risk: "Low", initials: "AI" },
  { name: "Vertex Technologies", category: "IT & electronics", score: 91, delivery: "94%", risk: "Low", initials: "VT" },
  { name: "GreenGrid Energy Co.", category: "Renewable energy", score: 84, delivery: "89%", risk: "Medium", initials: "GG" },
];

const nav: { label: Page; icon: string; group: string }[] = [
  { label: "Overview", icon: "◫", group: "WORKSPACE" },
  { label: "Tenders", icon: "▤", group: "WORKSPACE" },
  { label: "My Bids", icon: "↗", group: "WORKSPACE" },
  { label: "Suppliers", icon: "♙", group: "INTELLIGENCE" },
  { label: "Price Intelligence", icon: "⌁", group: "INTELLIGENCE" },
  { label: "Risk & Compliance", icon: "◇", group: "INTELLIGENCE" },
  { label: "AI Assistant", icon: "✳", group: "TOOLS" },
  { label: "Audit Trail", icon: "☷", group: "TOOLS" },
];

const titles: Record<Page, string> = {
  Overview: "Procurement overview",
  Tenders: "Tender marketplace",
  "My Bids": "My bid workspace",
  Suppliers: "Supplier intelligence",
  "Price Intelligence": "Price intelligence",
  "Risk & Compliance": "Risk & compliance",
  "AI Assistant": "Your AI copilot",
  "Audit Trail": "Audit trail",
};

const money = (n: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(n);

export default function HomePage() {
  const [active, setActive] = useState<Page>("Overview");
  const [tenders, setTenders] = useState(initialTenders);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All");
  const [showCreate, setShowCreate] = useState(false);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [toast, setToast] = useState("");
  const [title, setTitle] = useState("");
  const [buyer, setBuyer] = useState("");
  const [category, setCategory] = useState("Technology");
  const [value, setValue] = useState("");
  const [deadline, setDeadline] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");

  function notify(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 3000);
  }

  const filtered = useMemo(() => tenders.filter((t) => {
    const text = `${t.id} ${t.title} ${t.buyer} ${t.category}`.toLowerCase();
    const matchesSearch = text.includes(search.toLowerCase());
    const matchesFilter = filter === "All" || t.status === filter;
    return matchesSearch && matchesFilter;
  }), [tenders, search, filter]);

  function createTender(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const newTender: Tender = {
      id: `DRAFT-${Date.now().toString().slice(-5)}`,
      title,
      buyer: buyer || "Buyer not specified",
      category,
      value: Number(value) || 0,
      deadline: deadline
        ? new Date(`${deadline}T12:00:00`).toLocaleDateString("en-GB", {
            day: "2-digit", month: "short", year: "numeric",
          })
        : "Not set",
      bids: 0,
      status: "Open",
    };
    setTenders((current) => [newTender, ...current]);
    setShowCreate(false);
    setActive("Tenders");
    setTitle("");
    setBuyer("");
    setValue("");
    setDeadline("");
    notify("Draft added to this browser preview.");
  }

  function choosePage(page: Page) {
    setActive(page);
    setMobileMenu(false);
  }

  return (
    <main className="app-shell">
      {mobileMenu && <button className="mobile-scrim" onClick={() => setMobileMenu(false)} aria-label="Close menu" />}

      <aside className={`sidebar ${mobileMenu ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-logo">B<span>↗</span></div>
          <div><strong>BidSynq</strong><small>PROCUREMENT INTELLIGENCE</small></div>
          <button className="mobile-close" onClick={() => setMobileMenu(false)}>×</button>
        </div>

        <div className="workspace-card">
          <div className="avatar">SN</div>
          <div><strong>My workspace</strong><small>Procurement team</small></div>
          <span>⌄</span>
        </div>

        <nav className="side-nav">
          {(["WORKSPACE", "INTELLIGENCE", "TOOLS"] as const).map((group) => (
            <div className="nav-group" key={group}>
              <p>{group}</p>
              {nav.filter((item) => item.group === group).map((item) => (
                <button
                  key={item.label}
                  onClick={() => choosePage(item.label)}
                  className={`nav-link ${active === item.label ? "active" : ""}`}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span>{item.label}</span>
                  {item.label === "Risk & Compliance" && <i className="nav-count">3</i>}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="upgrade-card">
            <span className="upgrade-symbol">✦</span>
            <strong>Procurement, made smarter</strong>
            <p>Organize opportunities and review supplier intelligence in one place.</p>
            <button onClick={() => choosePage("AI Assistant")}>Explore AI tools →</button>
          </div>
          <div className="user-card">
            <div className="avatar">SN</div>
            <div><strong>Workspace admin</strong><small>BidSynq account</small></div>
          </div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumbs">
            <button className="menu-toggle" onClick={() => setMobileMenu(true)}>☰</button>
            <span>Workspace</span><b>/</b><strong>{active}</strong>
          </div>
          <div className="topbar-right">
            <label className="global-search">
              <span>⌕</span>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tenders..." />
              <kbd>⌕</kbd>
            </label>
            <button className="icon-button" onClick={() => notify("You are all caught up.")} aria-label="Notifications">♧</button>
            <div className="avatar top-avatar">SN</div>
          </div>
        </header>

        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><i /> PROCUREMENT WORKSPACE <span>/</span> OCT 2026</div>
              <h1>{titles[active]}</h1>
              <p>Discover opportunities, manage bids, and make informed procurement decisions.</p>
            </div>
            <div className="heading-actions">
              <button className="btn btn-secondary" onClick={() => notify("Export will be available when connected to your backend.")}>↓ Export</button>
              <button className="btn btn-primary" onClick={() => setShowCreate(true)}>＋ Create tender</button>
            </div>
          </div>

          {active === "Overview" && <>
            <section className="hero-banner">
              <div className="hero-copy">
                <span className="hero-tag">YOUR PROCUREMENT COMMAND CENTER</span>
                <h2>Better decisions start here<span>.</span></h2>
                <p>Keep tenders, supplier performance, bids, and risk signals in one organized workspace.</p>
                <button className="hero-button" onClick={() => choosePage("Tenders")}>Explore opportunities <span>→</span></button>
              </div>
              <div className="hero-art"><div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" /><div className="hero-core">B<span>↗</span></div><div className="float-chip chip-one">✦ Intelligence</div><div className="float-chip chip-two">↗ Opportunities</div></div>
            </section>

            <div className="section-heading">
              <div><h2>Workspace at a glance</h2><p>Example indicators for your procurement activity</p></div>
              <span className="demo-label"><i /> Demo data</span>
            </div>

            <div className="stats-grid">
              <StatCard label="Active tenders" value="24" change="+12.5%" icon="▤" tone="purple" />
              <StatCard label="Bids submitted" value="18" change="+8.2%" icon="↗" tone="blue" />
              <StatCard label="Supplier score" value="92.4" change="+3.1 pts" icon="♙" tone="green" />
              <StatCard label="Risk alerts" value="03" change="Needs review" icon="◇" tone="amber" />
            </div>

            <div className="content-grid">
              <section className="panel">
                <div className="panel-heading">
                  <div><h2>Trending opportunities</h2><p>Review current tender listings</p></div>
                  <button className="text-button" onClick={() => choosePage("Tenders")}>View all →</button>
                </div>
                <TenderTable tenders={filtered.slice(0, 4)} onOpen={() => choosePage("Tenders")} />
              </section>
              <section className="panel">
                <div className="panel-heading"><div><h2>Recent activity</h2><p>Sample workspace events</p></div></div>
                <div className="activity-list">
                  <Activity icon="✓" tone="green" title="Bid submitted" detail="IT hardware refresh" time="12 min ago" />
                  <Activity icon="✦" tone="purple" title="Risk review completed" detail="Supplier evaluation" time="48 min ago" />
                  <Activity icon="＋" tone="blue" title="New tender matched" detail="Industrial equipment" time="2 hours ago" />
                  <Activity icon="◇" tone="amber" title="Compliance check needed" detail="Solar maintenance tender" time="Yesterday" />
                </div>
                <button className="text-button" onClick={() => choosePage("Audit Trail")}>Open audit trail →</button>
              </section>
            </div>
          </>}

          {active === "Tenders" && <section className="panel full-panel">
            <div className="panel-heading">
              <div><h2>All opportunities</h2><p>Search, filter, and review tender records</p></div>
              <button className="btn btn-primary" onClick={() => setShowCreate(true)}>＋ New tender</button>
            </div>
            <div className="table-filters">
              <label className="filter-search">⌕ <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by title, buyer or ID" /></label>
              <select value={filter} onChange={(e) => setFilter(e.target.value)}>
                <option>All</option><option>Open</option><option>Closing soon</option><option>Under review</option>
              </select>
            </div>
            <TenderTable tenders={filtered} onOpen={(t) => notify(`${t.id} selected. Connect tender detail endpoint to view full records.`)} />
            <p className="demo-note">Demo records only. Creating a tender adds it to the current page state, not the server database.</p>
          </section>}

          {active === "My Bids" && <section className="panel full-panel">
            <div className="panel-heading"><div><h2>Bid tracking</h2><p>Monitor submissions and next steps</p></div></div>
            <div className="stats-grid small-stats">
              <StatCard label="Submitted" value="18" icon="↗" tone="blue" />
              <StatCard label="Under evaluation" value="06" icon="◷" tone="purple" />
              <StatCard label="Awarded" value="04" icon="✓" tone="green" />
              <StatCard label="Drafts" value="03" icon="▤" tone="amber" />
            </div>
            <TenderTable tenders={tenders.slice(0, 4)} onOpen={(t) => notify(`Bid workspace for ${t.id} needs your bid API connection.`)} />
            <p className="demo-note">Bid counts and states are placeholders until loaded from your account.</p>
          </section>}

          {active === "Suppliers" && <section className="full-panel">
            <div className="section-heading"><div><h2>Supplier directory</h2><p>Example supplier performance profiles</p></div><span className="demo-label">Demo profiles</span></div>
            <div className="supplier-grid">
              {suppliers.map((s) => <article className="supplier-card" key={s.name}>
                <div className="supplier-card-top"><div className="supplier-avatar">{s.initials}</div><span className={`risk-pill ${s.risk.toLowerCase()}`}>{s.risk} risk</span></div>
                <h3>{s.name}</h3><p>{s.category}</p>
                <div className="supplier-metrics"><div><strong>{s.score}<small>/100</small></strong><span>Trust score</span></div><div><strong>{s.delivery}</strong><span>On-time delivery</span></div></div>
                <div className="score-track"><i style={{ width: `${s.score}%` }} /></div>
                <button className="text-button" onClick={() => notify(`${s.name}: connect your supplier detail API to view verified records.`)}>View profile →</button>
              </article>)}
            </div>
          </section>}

          {active === "Price Intelligence" && <section className="content-grid">
            <div className="panel price-panel"><div className="panel-heading"><div><h2>Price benchmark overview</h2><p>Illustrative category comparison</p></div><span className="demo-label">Sample</span></div>
              {[
                { name: "IT equipment", price: "₹18.2L", width: "74%", label: "Market estimate" },
                { name: "Industrial supplies", price: "₹24.8L", width: "92%", label: "Market estimate" },
                { name: "Renewable energy", price: "₹12.6L", width: "58%", label: "Market estimate" },
                { name: "Facilities", price: "₹8.4L", width: "42%", label: "Market estimate" },
              ].map((p) => <div className="price-row" key={p.name}><div><strong>{p.name}</strong><span>{p.label}</span></div><strong>{p.price}</strong><div className="price-track"><i style={{ width: p.width }} /></div></div>)}
              <p className="demo-note">These figures are examples, not verified market prices or AI-generated estimates.</p>
            </div>
            <div className="panel"><h2>Before you compare prices</h2><div className="check-list"><p>✓ Compare equivalent specifications</p><p>✓ Include taxes, shipping, and installation</p><p>✓ Check delivery dates and warranty</p><p>✓ Verify vendor quotations and source dates</p></div></div>
          </section>}

          {active === "Risk & Compliance" && <section className="panel full-panel">
            <div className="panel-heading"><div><h2>Risk review queue</h2><p>Sample signals to investigate before making a decision</p></div><span className="risk-pill medium">3 items</span></div>
            <RiskRow level="High" title="Missing compliance documentation" detail="Confirm required certificates before evaluation." date="22 Oct" />
            <RiskRow level="Medium" title="Supplier delivery performance" detail="Review delivery history and supporting evidence." date="24 Oct" />
            <RiskRow level="Medium" title="Tender deadline approaching" detail="Check that all mandatory bid documents are ready." date="26 Oct" />
            <p className="demo-note">Sample risk items only. Do not use these as actual compliance findings.</p>
          </section>}

          {active === "AI Assistant" && <section className="content-grid assistant-layout">
            <div className="panel assistant-panel">
              <div className="assistant-icon">✳</div><span className="eyebrow">BIDSYNQ INTELLIGENCE</span>
              <h2>Your procurement copilot</h2>
              <p>Ask for help with tender preparation, supplier comparisons, evaluation criteria, and risk checklists.</p>
              <div className="suggestions">
                {["What should I check before submitting a bid?", "How can I compare supplier quotations?", "Create a tender evaluation checklist."].map((q) => <button key={q} onClick={() => setQuestion(q)}>{q} <span>↗</span></button>)}
              </div>
              <form className="assistant-form" onSubmit={(e) => { e.preventDefault(); if (question.trim()) setAnswer("This frontend preview is not connected to an AI model. Your question was: " + question); }}>
                <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about tenders, bids, suppliers..." />
                <button className="btn btn-primary">Ask AI ↗</button>
              </form>
              {answer && <div className="answer-box"><strong>Preview response</strong><p>{answer}</p></div>}
              <p className="demo-note">Connect this interface to your backend assistant endpoint for real AI responses.</p>
            </div>
            <div className="panel"><h2>Suggested workflows</h2><Activity icon="▤" tone="purple" title="Tender analysis" detail="Extract requirements and deadlines" time="Workflow" /><Activity icon="⇄" tone="blue" title="Supplier comparison" detail="Build a structured comparison table" time="Workflow" /><Activity icon="◇" tone="amber" title="Risk checklist" detail="Identify items that need verification" time="Workflow" /></div>
          </section>}

          {active === "Audit Trail" && <section className="panel full-panel">
            <div className="panel-heading"><div><h2>Activity history</h2><p>Illustrative events for the workspace</p></div><button className="btn btn-secondary" onClick={() => notify("Export requires backend audit records.")}>↓ Export log</button></div>
            <div className="audit-list">
              {[
                ["Bid submitted", "TND-1042", "Today · 12:14", "Success"],
                ["Risk review completed", "GreenGrid Energy Co.", "Today · 11:38", "Completed"],
                ["Tender opportunity matched", "TND-1048", "Today · 10:26", "New"],
                ["Supplier profile reviewed", "Apex Industrial Solutions", "Yesterday · 16:40", "Completed"],
              ].map((row) => <div className="audit-row" key={row[0]}><div><strong>{row[0]}</strong><small>{row[1]}</small></div><span>{row[2]}</span><i>{row[3]}</i></div>)}
            </div>
            <p className="demo-note">For compliance use, load audit events from the server and record authenticated user actions.</p>
          </section>}

          <footer className="page-footer"><span>© 2026 BidSynq</span><span><i /> Procurement intelligence workspace <b>·</b> Preview mode</span></footer>
        </div>
      </section>

      {showCreate && <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowCreate(false); }}>
        <form className="create-modal" onSubmit={createTender}>
          <div className="modal-header"><div><span className="eyebrow">WORKSPACE ACTION</span><h2>Create tender draft</h2><p>Add the basic details for a procurement opportunity.</p></div><button type="button" className="modal-close" onClick={() => setShowCreate(false)}>×</button></div>
          <label>Tender title<input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Office equipment procurement" /></label>
          <label>Buyer / organization<input value={buyer} onChange={(e) => setBuyer(e.target.value)} placeholder="Organization name" /></label>
          <label>Category<select value={category} onChange={(e) => setCategory(e.target.value)}><option>Technology</option><option>Industrial</option><option>Energy</option><option>Facilities</option><option>Services</option></select></label>
          <label>Estimated value (INR)<input type="number" min="0" value={value} onChange={(e) => setValue(e.target.value)} placeholder="500000" /></label>
          <label>Deadline<input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
          <p className="demo-note">This creates a local preview record only; it does not save to your database.</p>
          <div className="modal-actions"><button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button><button className="btn btn-primary">Save draft →</button></div>
        </form>
      </div>}

      {toast && <div className="toast" role="status"><span>✓</span>{toast}<button onClick={() => setToast("")}>×</button></div>}
    </main>
  );
}

function StatCard({ label, value, change, icon, tone }: { label: string; value: string; change?: string; icon: string; tone: string }) {
  return <article className="stat-card"><div className="stat-top"><span>{label}</span><span className={`stat-icon ${tone}`}>{icon}</span></div><div className="stat-value">{value}</div><div className="stat-change">{change && <span>↗ </span>}{change || "Workspace metric"}</div><div className="mini-bars"><i/><i/><i/><i/><i/><i/><i/><i/></div></article>;
}

function TenderTable({ tenders, onOpen }: { tenders: Tender[]; onOpen: (t: Tender) => void }) {
  return <div className="table-wrap"><table className="tender-table"><thead><tr><th>TENDER / BUYER</th><th>CATEGORY</th><th>EST. VALUE</th><th>BIDS</th><th>DEADLINE</th><th>STATUS</th><th /></tr></thead><tbody>{tenders.map((t) => <tr key={t.id}><td><button className="tender-link" onClick={() => onOpen(t)}><strong>{t.title}</strong><small>{t.id} · {t.buyer}</small></button></td><td><span className="category-chip">{t.category}</span></td><td className="value-cell">{money(t.value)}</td><td>{t.bids}</td><td>{t.deadline}</td><td><span className={`status-pill ${t.status === "Closing soon" ? "warning" : t.status === "Under review" ? "review" : "open"}`}><i/>{t.status}</span></td><td><button className="row-action" onClick={() => onOpen(t)} aria-label={`Open ${t.id}`}>↗</button></td></tr>)}</tbody></table>{tenders.length === 0 && <div className="empty-state">No tenders match your search. Try another term or status.</div>}</div>;
}

function Activity({ icon, tone, title, detail, time }: { icon: string; tone: string; title: string; detail: string; time: string }) {
  return <div className="activity-item"><span className={`activity-icon ${tone}`}>{icon}</span><div className="activity-copy"><strong>{title}</strong><p>{detail}</p><small>{time}</small></div></div>;
}

function RiskRow({ level, title, detail, date }: { level: string; title: string; detail: string; date: string }) {
  return <div className="risk-row"><span className={`risk-level ${level.toLowerCase()}`}>{level}</span><div><strong>{title}</strong><p>{detail}</p></div><span className="risk-date">{date}</span><button className="row-action" aria-label={`Review ${title}`}>↗</button></div>;
}
