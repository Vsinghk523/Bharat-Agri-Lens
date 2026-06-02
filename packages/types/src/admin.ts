export interface LabellingQueueItem {
  diagnostic_id: string;
  image_id: string | null;
  /** Presigned URL the reviewer uses to inspect the original image. */
  image_url: string | null;
  storage_location: string | null;
  predicted_plant: string | null;
  predicted_disease: string | null;
  predicted_infection_type: string | null;
  confidence_score: string | number | null;
  user_feedback: string;
  language_used: string | null;
  add_date: string;
  modify_date: string;
  /** Reviewer's authoritative re-label. Null until an admin has PATCHed. */
  correct_plant: string | null;
  correct_disease: string | null;
  correct_infection_type: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  /** Provenance of the prediction. Lets the UI badge llm_fallback rows. */
  prediction_source: 'plantvit' | 'llm_fallback' | 'mock';
}

/** Which review bucket to fetch from /admin/labelling-queue. */
export type LabellingQueueSource = 'flagged' | 'llm_gold';

/** One row of GET /admin/llm-fallback-summary. */
export interface LlmFallbackSummaryRow {
  plant_classification: string;
  total_count: number;
  feedback_correct: number;
  feedback_incorrect: number;
  feedback_partial: number;
  feedback_none: number;
  latest_seen: string;
  sample_diagnostic_ids: string[];
}

export interface LlmFallbackSummaryResponse {
  items: LlmFallbackSummaryRow[];
  window_days: number;
  total_fallback_rows: number;
}

export interface LabellingQueueResponse {
  items: LabellingQueueItem[];
  total: number;
  limit: number;
  offset: number;
}

/** PATCH body for /admin/labelling-queue/{id}. Omit a field to keep it. */
export interface ReviewerCorrection {
  correct_plant?: string | null;
  correct_disease?: string | null;
  correct_infection_type?: string | null;
}
