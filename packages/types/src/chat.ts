export interface ChatSessionRead {
  session_id: string;
  user_id: string;
  title: string | null;
  language: string;
  status: string;
  add_date: string;
}

export interface ChatMessageRead {
  message_id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system' | string;
  language: string;
  content_text: string | null;
  audio_blob_url: string | null;
  transcription: string | null;
  add_date: string;
}
