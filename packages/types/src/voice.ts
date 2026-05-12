export interface SttRequest {
  audio_b64: string;
  language?: string;
}

export interface SttResponse {
  transcript: string;
  language: string;
  provider: 'bhashini' | 'mock';
  /**
   * How the API normalised the audio before forwarding to Bhashini.
   *  - passthrough_wav: input was already RIFF/WAVE.
   *  - converted: ffmpeg transcoded to 16 kHz mono PCM.
   *  - passthrough_no_ffmpeg / passthrough_failed: forwarded raw bytes.
   */
  audio_conversion:
    | 'passthrough_wav'
    | 'converted'
    | 'passthrough_no_ffmpeg'
    | 'passthrough_failed';
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
