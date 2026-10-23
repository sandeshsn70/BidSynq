/**
 * The single place that talks to the backend. Every request carries the stored bearer token, errors are
 * converted into readable messages, and a 401 signs the user out. No secrets live here: the base URL is public.
 */
import type {
  AskOut, AuditPageOut, BidDetailOut, BidCreate, BidOut, ChecklistOut, DashboardOut, DeleteOut, DocumentOut,
  HealthOut, MyBidOut, SupplierOutcomeIn, OutcomeOut, PriceOut, RankingOut, ReviewOut, RiskAlertOut, ScanOut,
  SimilarOut, TenderCreate, TenderOut, TenderStatusFilter, TenderUpdateInput, TokenOut, TrustOut, UploadOut,
  UserOut, VerifyOut,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const TOKEN_KEY = "bidsynq_token";
const TIMEOUT_MS = 70_000; // Render's free tier can take ~1 minute to wake up

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const tokenStore = {
  get(): string | null {
    try { return window.localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set(token: string): void {
    try { window.localStorage.setItem(TOKEN_KEY, token); } catch { /* storage blocked: session lasts until reload */ }
  },
  clear(): void {
    try { window.localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  },
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

/** Turn FastAPI's error payloads (string, or a list of validation problems) into one sentence. */
export function describeError(payload: unknown, status: number): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) => {
        const field = Array.isArray(item.loc) ? String(item.loc[item.loc.length - 1] ?? "") : "";
        const msg = (item.msg || "Invalid value").replace(/^Value error, /, "");
        return field && field !== "body" ? `${field.replace(/_/g, " ")}: ${msg}` : msg;
      })
      .join("; ");
  }
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 403) return "You do not have permission to do that.";
  if (status === 404) return "Not found.";
  if (status === 429) return "Too many attempts. Please wait a few minutes.";
  if (status >= 500) return "The server had a problem. Please try again shortly.";
  return `Request failed (${status}).`;
}

async function http<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  const headers: Record<string, string> = {};
  const token = auth ? tokenStore.get() : null;
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { method, headers, body: payload, signal: controller.signal });
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    throw new ApiError(
      aborted
        ? "The server took too long to respond. If it was idle it may still be waking up - try again in a minute."
        : "Cannot reach the server. Check your connection; if the backend was idle it may need a minute to wake up.",
      0,
    );
  } finally {
    clearTimeout(timer);
  }

  let data: unknown = null;
  try { data = await response.json(); } catch { /* empty or non-JSON body */ }
  if (!response.ok) {
    if (response.status === 401 && auth && token && onUnauthorized) onUnauthorized();
    throw new ApiError(describeError(data, response.status), response.status);
  }
  return data as T;
}

const q = (params: Record<string, string | number | undefined>): string => {
  const parts = Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
};

export const api = {
  health: () => http<HealthOut>("GET", "/health", undefined, false),

  // auth
  register: (data: { name: string; email: string; password: string; role: "buyer" | "supplier"; company_name: string }) =>
    http<UserOut>("POST", "/auth/register", data, false),
  login: (data: { email: string; password: string }) => http<TokenOut>("POST", "/auth/login", data, false),
  me: () => http<UserOut>("GET", "/auth/me"),

  dashboard: () => http<DashboardOut>("GET", "/dashboard/summary"),

  // tenders
  listTenders: (status: TenderStatusFilter = "open") => http<TenderOut[]>("GET", `/tenders${q({ status })}`),
  getTender: (id: number) => http<TenderOut>("GET", `/tenders/${id}`),
  createTender: (data: TenderCreate) => http<TenderOut>("POST", "/tenders", data),
  updateTender: (id: number, data: TenderUpdateInput) => http<TenderOut>("PATCH", `/tenders/${id}`, data),
  setTenderStatus: (id: number, status: "closed" | "cancelled") =>
    http<TenderOut>("PATCH", `/tenders/${id}/status`, { status }),

  // bids
  listBids: (tenderId: number) => http<BidDetailOut[]>("GET", `/tenders/${tenderId}/bids`),
  submitBid: (tenderId: number, data: BidCreate) => http<BidOut>("POST", `/tenders/${tenderId}/bids`, data),
  reviseBid: (tenderId: number, data: BidCreate) => http<BidOut>("PUT", `/tenders/${tenderId}/bids/me`, data),
  myBids: () => http<MyBidOut[]>("GET", "/bids/me"),
  ranking: (tenderId: number) => http<RankingOut>("GET", `/tenders/${tenderId}/ranking`),

  // documents and assistant
  listDocuments: (tenderId: number) => http<DocumentOut[]>("GET", `/tenders/${tenderId}/documents`),
  uploadDocument: (tenderId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return http<UploadOut>("POST", `/tenders/${tenderId}/documents`, form);
  },
  deleteDocument: (tenderId: number, documentId: number) =>
    http<DeleteOut>("DELETE", `/tenders/${tenderId}/documents/${documentId}`),
  ask: (tenderId: number, question: string) =>
    http<AskOut>("POST", `/tenders/${tenderId}/assistant/ask`, { question }),
  requirementChecklist: (tenderId: number) =>
    http<ChecklistOut>("GET", `/tenders/${tenderId}/assistant/requirements`),

  // supplier and price intelligence
  recordOutcome: (tenderId: number, data: SupplierOutcomeIn) =>
    http<OutcomeOut>("POST", `/tenders/${tenderId}/supplier-outcomes`, data),
  myTrust: () => http<TrustOut>("GET", "/suppliers/me/trust"),
  supplierTrust: (supplierId: number) => http<TrustOut>("GET", `/suppliers/${supplierId}/trust`),
  similar: (tenderId: number) => http<SimilarOut>("GET", `/tenders/${tenderId}/similar`),
  priceIntelligence: (tenderId: number) => http<PriceOut>("GET", `/tenders/${tenderId}/price-intelligence`),

  // risk and audit
  scanRisks: (tenderId: number) => http<ScanOut>("POST", `/tenders/${tenderId}/risk/scan`),
  riskAlerts: (status: "open" | "reviewed" | "dismissed" | "all" = "all", tenderId?: number) =>
    http<RiskAlertOut[]>("GET", `/risk/alerts${q({ status, tender_id: tenderId })}`),
  reviewAlert: (alertId: number, status: "reviewed" | "dismissed", note: string) =>
    http<ReviewOut>("PATCH", `/risk/alerts/${alertId}/review`, { status, note }),
  auditLogs: (limit = 50, offset = 0) => http<AuditPageOut>("GET", `/audit/logs${q({ limit, offset })}`),
  verifyAudit: () => http<VerifyOut>("GET", "/audit/verify"),
};
