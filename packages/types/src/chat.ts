export interface ChatSessionRead {
  session_id: string;
  user_id: string;
  title: string | null;
  language: string;
  status: string;
  add_date: string;
}

export interface ChatMessageCreate {
  /** Omit to have the server create a fresh session on the fly. */
  session_id?: string;
  language?: string;
  content_text: string;
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

export interface ChatExchange {
  session_id: string;
  user_message: ChatMessageRead;
  /** Null when the inference service was unreachable. */
  assistant_message: ChatMessageRead | null;
  /** Short error code when assistant_message is null. */
  error: string | null;
}
