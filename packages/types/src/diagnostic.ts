export type InfectionType =
  | 'insect_pest'
  | 'fungal'
  | 'viral'
  | 'bacterial'
  | 'nematode'
  | 'nutrient_deficiency'
  | 'abiotic_stress'
  | 'weed_competition'
  | 'unknown';

export type Severity = 'low' | 'medium' | 'high' | 'critical';

/** OOD rejection codes. Match services/inference/app/ood.py. */
export type RejectionReason =
  | 'too_blurry'
  | 'too_dark'
  | 'too_small'
  | 'not_a_plant'
  | 'non_target_plant'
  | 'low_confidence'
  | 'ambiguous';

export interface DiagnosticCreate {
  image_id: string;
  language?: string;
}

export interface DiagnosticRead {
  diagnostic_id: string;
  user_id: string;
  image_id: string | null;
  plant_classification: string | null;
  scientific_name: string | null;
  disease_name: string | null;
  pathogen_name: string | null;
  infection_type: InfectionType | string | null;
  severity: Severity | string | null;
  confidence_score: string | number | null;
  // JSONB columns: server may return either an object or an array.
  secondary_predictions: Record<string, unknown> | Record<string, unknown>[] | null;
  suggested_remedies: string | null;
  chemical_remedies: Record<string, unknown> | Record<string, unknown>[] | null;
  organic_remedies: Record<string, unknown> | Record<string, unknown>[] | null;
  preventive_measures: string | null;
  language_used: string | null;
  user_feedback: string | null;
  status: string;
  add_date: string;
  model_version: string | null;
  /** OOD-defense: non-null means the inference layer refused to diagnose. */
  rejection_reason: RejectionReason | null;
  /** Closest CLIP label when rejection_reason='non_target_plant'/etc., e.g. "Rose". */
  rejection_hint: string | null;
  /** Where this prediction came from. 'plantvit' is the specialist model;
   *  'llm_fallback' means Gemini was used because the specialist rejected;
   *  'mock' is dev-only. UI uses this to render the "Diagnosed via general AI" badge. */
  prediction_source: 'plantvit' | 'llm_fallback' | 'mock';
}

/** Treatment-cycle progress for a single diagnosis. Powers the Home
 *  page's active-issue hero "Step N of 3" indicator. ``total_steps``
 *  is 0 when no reminders were ever scheduled (viral / abiotic /
 *  low-severity / user opted out) — UI hides the indicator in that
 *  case. */
export interface TreatmentProgressRead {
  total_steps: number;
  completed_steps: number;
  current_step: number;
  next_scheduled_at: string | null;
  interval_days: number | null;
}

export interface FollowupRead {
  addnl_question_id: string;
  diagnostic_id: string;
  question_text: string;
  question_language: string | null;
  display_order: number;
  category: string | null;
  was_clicked: boolean;
  answer_cache: string | null;
}

export interface FeedbackCreate {
  verdict: 'correct' | 'incorrect' | 'partial';
  notes?: string;
}
