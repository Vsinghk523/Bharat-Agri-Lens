export interface LabellingQueueItem {
  diagnostic_id: string;
  image_id: string | null;
  /** Presigned URL the reviewer can use to inspect the original image. */
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
}

export interface LabellingQueueResponse {
  items: LabellingQueueItem[];
  total: number;
  limit: number;
  offset: number;
}
