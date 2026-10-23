/**
 * Response types. Interface names and fields mirror the backend Pydantic schemas (app/schemas.py);
 * tests/test_frontend_contract.py fails if they drift apart.
 * A field marked "?" is one the backend may omit (it has a default / is excluded when empty).
 */

export type Role = "buyer" | "supplier" | "admin";

export interface UserOut {
  id: number;
  name: string;
  email: string;
  role: string;
  company_name: string;
}

export interface TokenOut {
  access_token: string;
  token_type?: string;
}

export interface TenderOut {
  id: number;
  buyer_id: number;
  title: string;
  description: string;
  category: string;
  quantity: number;
  tender_type: string;
  deadline: string;
  status: string;
  mandatory_requirements: string;
  w_price: number;
  w_delivery: number;
  w_trust: number;
  w_match: number;
  anti_sniping: boolean;
  created_at: string;
  bidding_open: boolean;
}

export interface BidOut {
  id: number;
  tender_id: number;
  supplier_id: number;
  price: number;
  delivery_days: number;
  validity_days: number;
  requirement_match: number;
  mandatory_met: boolean;
  compliance_notes: string;
  created_at: string;
  updated_at: string;
}

export interface BidDetailOut extends BidOut {
  supplier_name?: string | null;
  supplier_company?: string | null;
}

export interface MyBidOut extends BidOut {
  tender_title: string;
  tender_status: string;
  tender_type: string;
  tender_deadline: string;
  bidding_open: boolean;
}

export interface RankedBidOut {
  bid_id?: number | null;
  supplier_id?: number | null;
  supplier_company?: string | null;
  eligible: boolean;
  score: number;
  price_score?: number | null;
  delivery_score?: number | null;
  trust_score?: number | null;
  requirement_match?: number | null;
  reason_codes: string[];
  explanation?: string[];
}

export interface RankingOut {
  tender_id: number;
  weights: Record<string, number>;
  method: string;
  ranking: RankedBidOut[];
  note: string;
}

export interface DashboardOut {
  role: string;
  tenders?: number | null;
  open_tenders: number;
  bids_received?: number | null;
  open_risk_alerts?: number | null;
  submitted_bids?: number | null;
}

export interface DocumentOut {
  id: number;
  tender_id: number;
  filename: string;
  file_type: string;
  file_size: number;
  status: string;
  created_at: string;
}

export interface UploadOut extends DocumentOut {
  chunks_indexed: number;
}

export interface DeleteOut {
  status: string;
  document_id: number;
}

export interface CitationOut {
  source_id: string;
  document_id: number;
  filename: string;
  page_number?: number | null;
  section: string;
  excerpt: string;
  relevance_score: number;
}

export interface AskOut {
  answer: string;
  mode: string;
  citations: CitationOut[];
  disclaimer: string;
  notice?: string | null;
}

export interface ChecklistEvidenceOut {
  filename: string;
  page_number?: number | null;
  excerpt: string;
}

export interface ChecklistItemOut {
  requirement: string;
  evidence_found: boolean;
  evidence?: ChecklistEvidenceOut | null;
  review_status: string;
}

export interface ChecklistOut {
  tender_id: number;
  checklist: ChecklistItemOut[];
  note: string;
}

export interface OutcomeOut {
  id: number;
  tender_id: number;
  supplier_id: number;
  quality_score: number;
  on_time: boolean;
  issue_count: number;
  created_at: string;
  message: string;
}

export interface RecentOutcomeOut {
  tender_id: number;
  quality_score: number;
  on_time: boolean;
  issue_count: number;
  created_at: string;
}

export interface TrustOut {
  supplier_id: number;
  company_name: string;
  score: number;
  confidence: string;
  observations: number;
  components: Record<string, number | null>;
  explanation: string;
  recent_outcomes: RecentOutcomeOut[];
}

export interface SimilarMatchOut {
  tender_id?: number | null;
  title: string;
  category: string;
  quantity: number;
  similarity: number;
  status: string;
  created_at?: string | null;
}

export interface SimilarOut {
  tender_id: number;
  matches: SimilarMatchOut[];
  method: string;
  note: string;
}

export interface PriceRangeOut {
  low: number;
  high: number;
}

export interface PriceOut {
  tender_id: number;
  category: string;
  quantity: number;
  currency: string;
  predicted_total_price?: number | null;
  suggested_range?: PriceRangeOut | null;
  model?: string | null;
  training_samples: number;
  same_category_samples: number;
  source: string;
  explanation: string;
  model_note?: string | null;
  feature_importance?: string | null;
  human_review_required: boolean;
  disclaimer: string;
}

export interface RiskAlertOut {
  id: number;
  tender_id: number;
  bid_id?: number | null;
  rule_key: string;
  severity: string;
  title: string;
  explanation: string;
  evidence: Record<string, unknown>;
  status: string;
  review_note: string;
  created_at: string;
  reviewed_at?: string | null;
}

export interface ScanOut {
  tender_id: number;
  bids_checked: number;
  signals_detected: number;
  new_alerts_saved: number;
  alerts: RiskAlertOut[];
  disclaimer: string;
}

export interface ReviewOut {
  id: number;
  status: string;
  review_note: string;
  reviewed_at?: string | null;
}

export interface AuditItemOut {
  id: number;
  actor_id?: number | null;
  action: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  previous_hash: string;
  entry_hash: string;
  created_at: string;
}

export interface AuditPageOut {
  items: AuditItemOut[];
  limit: number;
  offset: number;
}

export interface VerifyOut {
  valid: boolean;
  checked_entries: number;
  head_hash?: string | null;
  last_entry_id?: number | null;
  broken_at_id?: number | null;
  reason?: string | null;
  note: string;
}

export interface HealthOut {
  status: string;
  version: string;
  database: string;
  migration_revision?: string | null;
  rag: string;
  groq_configured: boolean;
  supplier_intelligence: string;
  price_intelligence: string;
  risk_monitoring: string;
  audit_chain: string;
}

/** Request bodies (mirror TenderCreate / BidCreate / SupplierOutcomeIn / ReviewIn in the backend). */
export interface TenderCreate {
  title: string;
  description: string;
  category: string;
  quantity: number;
  tender_type: "rfq" | "sealed" | "reverse_auction";
  deadline: string;
  mandatory_requirements: string;
  w_price: number;
  w_delivery: number;
  w_trust: number;
  w_match: number;
  anti_sniping: boolean;
}

export type TenderUpdateInput = Partial<Omit<TenderCreate, "tender_type">>;

export interface BidCreate {
  price: number;
  delivery_days: number;
  validity_days: number;
  requirement_match: number;
  mandatory_met: boolean;
  compliance_notes: string;
}

export interface SupplierOutcomeIn {
  supplier_id: number;
  quality_score: number;
  on_time: boolean;
  issue_count: number;
  notes: string;
}

export type TenderStatusFilter = "open" | "closed" | "awarded" | "cancelled" | "all";
