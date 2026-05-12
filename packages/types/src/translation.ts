export interface TranslateRequest {
  text: string;
  source_language?: string;
  target_language: string;
}

export interface TranslateResponse {
  text: string;
  source_language: string;
  target_language: string;
  /** "bhashini" when calling the real service, "mock" otherwise. */
  provider: 'bhashini' | 'mock';
}
