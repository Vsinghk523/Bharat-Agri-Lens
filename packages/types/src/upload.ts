export interface PresignRequest {
  image_name: string;
  mime_type: string;
  size_bytes: number;
}

export interface PresignResponse {
  image_id: string;
  upload_url: string;
  storage_location: string;
  expires_in_seconds: number;
}

export interface ImageUploadRead {
  image_id: string;
  user_id: string;
  image_name: string;
  image_file_type: string;
  storage_location: string;
  size_bytes: number | null;
  mime_type: string | null;
  moderation_status: string;
  status: string;
  add_date: string;
}
