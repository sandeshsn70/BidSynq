"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { AskOut, ChecklistOut, DocumentOut } from "@/lib/types";
import { dateTime, label } from "@/lib/format";
import { Empty, Loading, Notice, Panel } from "../ui";

export default function AssistantPanel({ tenderId, canManage, hasRequirements = true }: { tenderId: number; canManage: boolean; hasRequirements?: boolean }) {
  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskOut | null>(null);
  const [checklist, setChecklist] = useState<ChecklistOut | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<"" | "upload" | "ask" | "list">("");

  const loadDocs = useCallback(() => {
    api.listDocuments(tenderId).then(setDocs).catch((e: Error) => { setDocs([]); setError(e.message); });
  }, [tenderId]);
  useEffect(() => { setAnswer(null); setChecklist(null); setError(""); setNotice(""); setDocs(null); loadDocs(); }, [tenderId, loadDocs]);

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(""); setNotice(""); setBusy("upload");
    try {
      const r = await api.uploadDocument(tenderId, file);
      setNotice(`Indexed ${r.filename}: ${r.chunks_indexed} passages created.`);
      setFile(null); (document.getElementById("doc-file") as HTMLInputElement | null)?.setAttribute("value", "");
      loadDocs();
    } catch (err) { setError((err as Error).message); } finally { setBusy(""); }
  }

  async function remove(doc: DocumentOut) {
    if (!window.confirm(`Delete ${doc.filename} and its indexed text?`)) return;
    setError(""); setNotice("");
    try { await api.deleteDocument(tenderId, doc.id); setNotice("Document deleted."); setAnswer(null); loadDocs(); }
    catch (err) { setError((err as Error).message); }
  }

  async function ask(e: FormEvent) {
    e.preventDefault();
    setError(""); setAnswer(null); setBusy("ask");
    try { setAnswer(await api.ask(tenderId, question)); } catch (err) { setError((err as Error).message); } finally { setBusy(""); }
  }

  async function runChecklist() {
    setError(""); setBusy("list");
    try { setChecklist(await api.requirementChecklist(tenderId)); } catch (err) { setError((err as Error).message); } finally { setBusy(""); }
  }

  return (
    <>
      {error && <Notice kind="error">{error}</Notice>}
      {notice && <Notice kind="success">{notice}</Notice>}
      <div className="grid-2" style={{ marginBottom: 20 }}>
        <Panel title="Tender documents" subtitle="PDF, DOCX or TXT, up to 15 MB. Scanned PDFs are not supported (no OCR).">
          {canManage && (
            <form onSubmit={upload} className="inline-form" style={{ marginBottom: 12 }}>
              <input id="doc-file" type="file" accept=".pdf,.docx,.txt" aria-label="Choose document" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <button className="btn btn-primary btn-small" disabled={!file || busy === "upload"}>{busy === "upload" ? "Indexing..." : "Upload"}</button>
            </form>
          )}
          {docs === null ? <Loading /> : docs.length === 0 ? <Empty>{canManage ? "No documents yet. Upload the tender specification to enable Q&A." : "The buyer has not uploaded documents."}</Empty> : docs.map((d) => (
            <div className="doc-row" key={d.id}>
              <div><strong>{d.filename}</strong><br /><small className="muted">{d.file_type.toUpperCase()} · {(d.file_size / 1024).toFixed(0)} KB · {dateTime(d.created_at)}</small></div>
              {canManage && <button className="btn btn-danger btn-small" onClick={() => remove(d)}>Delete</button>}
            </div>
          ))}
        </Panel>
        <Panel title="Ask the documents" subtitle="Answers use only the uploaded text and always show their sources.">
          <form onSubmit={ask}>
            <label className="field"><span>Your question</span>
              <textarea required minLength={3} maxLength={1200} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Which certificates must suppliers provide?" /></label>
            <div className="form-actions"><button className="btn btn-primary" disabled={busy === "ask" || question.trim().length < 3 || !docs?.length}>{busy === "ask" ? "Searching..." : "Find answer"}</button></div>
          </form>
        </Panel>
      </div>

      {answer && (
        <Panel title="Answer" subtitle={label(answer.mode)}>
          {answer.notice && <Notice kind="warn">{answer.notice} Showing the matching passages instead.</Notice>}
          <div className="answer">{answer.answer}</div>
          <p className="muted">{answer.disclaimer}</p>
          {answer.citations.map((c) => (
            <article className="citation" key={c.source_id}>
              <strong>[{c.source_id}] {c.filename}</strong> <span className="muted">· {c.page_number ? `page ${c.page_number}` : c.section}</span>
              <p>{c.excerpt}</p>
            </article>
          ))}
        </Panel>
      )}

      <Panel title="Mandatory-requirement evidence checklist"
        subtitle="Finds the best matching passage for each requirement line. A match is a lead, not proof of compliance."
        actions={<button className="btn btn-small" onClick={runChecklist} disabled={busy === "list" || !docs?.length || !hasRequirements}>Build checklist</button>}>
        {!hasRequirements && <Empty>This tender lists no mandatory requirements.</Empty>}
        {checklist && checklist.checklist.length === 0 && <Empty>No requirement lines to check.</Empty>}
        {checklist?.checklist.map((item, i) => (
          <div key={i} className="doc-row" style={{ alignItems: "flex-start" }}>
            <div><strong>{item.requirement}</strong>
              {item.evidence ? <p className="muted" style={{ margin: "4px 0 0" }}>{item.evidence.filename}{item.evidence.page_number ? ` · page ${item.evidence.page_number}` : ""}: {item.evidence.excerpt}</p> : <p className="muted" style={{ margin: "4px 0 0" }}>No matching passage found.</p>}</div>
            <span className={`pill ${item.evidence_found ? "good" : "warn"}`}>{item.evidence_found ? "Evidence found" : "No evidence"}</span>
          </div>
        ))}
        {checklist && <p className="muted">{checklist.note}</p>}
      </Panel>
    </>
  );
}
