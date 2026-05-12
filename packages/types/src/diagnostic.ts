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
