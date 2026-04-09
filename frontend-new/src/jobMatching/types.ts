// ─── API response shape ───────────────────────────────────────────────────────

/** Raw document returned by GET /jobs. Fields match the Zambia jobs DB. */
export interface JobApiDocument {
  uuid?: string;
  opportunity_title?: string;
  employer?: string;
  category?: string;
  contract_type?: string;
  location?: string;
  city?: string;
  province?: string;
  posted_date?: string;
  closing_date?: string;
  URL?: string;
  source_platform?: string;
  attributes?: Record<string, string>;
}

export interface JobsApiMeta {
  limit: number;
  next_cursor: string | null;
  has_more: boolean;
  total: number | null;
}

export interface JobsApiResponse {
  data: JobApiDocument[];
  meta: JobsApiMeta;
}

// ─── UI row shape ─────────────────────────────────────────────────────────────

/** Raw document returned by GET /jobs/matched. Fields match the matching service response, enriched with job details. */
export interface MatchedJobApiDocument {
  uuid?: string;
  opportunity_title?: string;
  location?: string;
  contract_type?: string;
  URL?: string;
  final_score?: number;
  justification?: string;
  rank?: number;
  // Enriched from the jobs collection
  employer?: string;
  category?: string;
  posted_date?: string;
}

/** Normalised row used by the table and detail modal. */
export interface JobRow {
  id: string;
  jobTitle: string;
  company: string;
  category: string;
  contractType: string;
  location: string;
  posted: string;
  jobUrl?: string;
  skills?: string[];
  /** Match score (0–100), only set for the Matched For You tab */
  matchScore?: number;
}

// ─── Filter state ─────────────────────────────────────────────────────────────

export interface JobFilters {
  search: string;
  category: string;
  contractType: string;
  location: string;
}
