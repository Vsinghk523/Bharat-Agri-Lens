export interface SttRequest {
  audio_b64: string;
  language?: string;
}

export interface SttResponse {
  transcript: string;
  language: string;
  provider: 'bhashini' | 'mock';
}

export interface TtsRequest {
  text: string;
  language?: string;
  gender?: 'female' | 'male';
}

export interface TtsResponse {
  audio_b64: string;
  mime_type: string;
  language: string;
  provider: 'bhashini' | 'mock';
}
