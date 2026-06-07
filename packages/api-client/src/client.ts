import type {
  ChatExchange,
  ChatMessageCreate,
  ChatMessageRead,
  ChatSessionRead,
  ConsentAccept,
  DiagnosticCreate,
  DiagnosticRead,
  DownloadUrlResponse,
  FeedbackCreate,
  FollowupRead,
  ImageUploadRead,
  LabellingQueueItem,
  LabellingQueueResponse,
  LabellingQueueSource,
  LlmFallbackSummaryResponse,
  OtpRequest,
  ReviewerCorrection,
  OtpRequestResponse,
  OtpVerify,
  PresignRequest,
  PresignResponse,
  SttRequest,
  SttResponse,
  TokenPair,
  TranslateRequest,
  TranslateResponse,
  TtsRequest,
  TtsResponse,
  UserPreferences,
  UserRead,
  UserUpdate,
} from '@bal/types';

export interface ApiClientOptions {
  baseUrl: string;
  getAccessToken?: () => string | null;
  /**
   * Called once when the server returns 401 to a request that DID include
   * a bearer token. Use it to clear local auth state and redirect to the
   * sign-in screen. NOT invoked when the request had no Authorization
   * header (e.g. /auth/otp/verify with a wrong code) — those 401s are
   * expected user errors, not session expiry.
   */
  onUnauthorized?: (info: { path: string; method: string }) => void;
}

export class HttpError extends Error {
  constructor(
    public status: number,
    public payload: unknown,
    message?: string,
  ) {
    super(message ?? `HTTP ${status}`);
  }
}

function makeFetcher(opts: ApiClientOptions) {
  return async function fetcher<T>(
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    path: string,
    body?: unknown,
  ): Promise<T> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = opts.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    const resp = await fetch(`${opts.baseUrl}${path}`, {
      method,
      headers,
      body: body == null ? undefined : JSON.stringify(body),
    });
    if (!resp.ok) {
      if (resp.status === 401 && token && opts.onUnauthorized) {
        opts.onUnauthorized({ path, method });
      }
      let detail: unknown = undefined;
      try {
        detail = await resp.json();
      } catch {
        // ignore
      }
      throw new HttpError(resp.status, detail, `HTTP ${resp.status} ${resp.statusText}`);
    }
    if (resp.status === 204) return undefined as T;
    return (await resp.json()) as T;
  };
}

function makeMultipartUploader(opts: ApiClientOptions) {
  return async function uploader<T>(
    path: string,
    file: File,
    extraFields?: Record<string, string>,
  ): Promise<T> {
    // CRITICAL: do NOT set Content-Type here — the browser must set it
    // including the multipart boundary, and overriding it breaks the
    // parser on the server.
    const headers: Record<string, string> = {};
    const token = opts.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    const form = new FormData();
    form.append('file', file);
    for (const [k, v] of Object.entries(extraFields ?? {})) {
      form.append(k, v);
    }
    const resp = await fetch(`${opts.baseUrl}${path}`, {
      method: 'POST',
      headers,
      body: form,
    });
    if (!resp.ok) {
      if (resp.status === 401 && token && opts.onUnauthorized) {
        opts.onUnauthorized({ path, method: 'POST' });
      }
      let detail: unknown = undefined;
      try {
        detail = await resp.json();
      } catch {
        // ignore
      }
      throw new HttpError(resp.status, detail, `HTTP ${resp.status} ${resp.statusText}`);
    }
    if (resp.status === 204) return undefined as T;
    return (await resp.json()) as T;
  };
}

export function createApiClient(opts: ApiClientOptions) {
  const f = makeFetcher(opts);
  const upload = makeMultipartUploader(opts);

  return {
    auth: {
      requestOtp: (payload: OtpRequest) =>
        f<OtpRequestResponse>('POST', '/auth/otp/request', payload),
      verifyOtp: (payload: OtpVerify) => f<TokenPair>('POST', '/auth/otp/verify', payload),
      acceptConsent: (payload: ConsentAccept) => f<void>('POST', '/auth/consent', payload),
    },
    users: {
      me: () => f<UserRead>('GET', '/users/me'),
      updateMe: (payload: UserUpdate) => f<UserRead>('PATCH', '/users/me', payload),
      updateMyPreferences: (payload: Partial<UserPreferences>) =>
        f<UserPreferences>('PATCH', '/users/me/preferences', payload),
      /** Hyperlocal outbreak alerts for this user's pincode in the last 14 days. */
      myOutbreakAlerts: () =>
        f<{
          items: Array<{
            pincode: string;
            infection_type: string;
            report_count: number;
            notified_at: string;
          }>;
        }>('GET', '/users/me/outbreak-alerts'),
      get: (userId: string) => f<UserRead>('GET', `/users/${userId}`),
      update: (userId: string, payload: UserUpdate) =>
        f<UserRead>('PATCH', `/users/${userId}`, payload),
      softDelete: (userId: string) => f<void>('DELETE', `/users/${userId}`),
      purge: (userId: string) => f<void>('DELETE', `/users/${userId}/purge`),
    },
    push: {
      registerToken: (payload: { token: string; platform: 'android' | 'ios' | 'web' }) =>
        f<{ ok: boolean }>('POST', '/push/register-token', payload),
      unregisterToken: (token: string) =>
        f<void>('DELETE', `/push/register-token?token=${encodeURIComponent(token)}`),
    },
    uploads: {
      presign: (payload: PresignRequest) =>
        f<PresignResponse>('POST', '/uploads/presign', payload),
      /**
       * Upload an image directly through the API.
       *
       * Use this when the storage backend doesn't support browser-side
       * CORS-enabled PUTs (e.g. Railway T3 buckets). The API streams the
       * file to object storage server-side and returns the persisted
       * ImageUpload row, ready to feed into ``diagnostics.create``.
       */
      direct: (file: File, imageName?: string) =>
        upload<ImageUploadRead>(
          '/uploads/direct',
          file,
          imageName ? { image_name: imageName } : undefined,
        ),
      get: (imageId: string) => f<unknown>('GET', `/uploads/${imageId}`),
      getDownloadUrl: (imageId: string) =>
        f<DownloadUrlResponse>('GET', `/uploads/${imageId}/url`),
      list: (limit = 50, offset = 0) =>
        f<unknown[]>('GET', `/uploads?limit=${limit}&offset=${offset}`),
      softDelete: (imageId: string) => f<void>('DELETE', `/uploads/${imageId}`),
    },
    diagnostics: {
      create: (payload: DiagnosticCreate) => f<DiagnosticRead>('POST', '/diagnostics', payload),
      get: (id: string, language?: string) =>
        f<DiagnosticRead>(
          'GET',
          `/diagnostics/${id}${language ? `?language=${encodeURIComponent(language)}` : ''}`,
        ),
      list: (limit = 50, offset = 0, language?: string) => {
        const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
        if (language) qs.set('language', language);
        return f<DiagnosticRead[]>('GET', `/diagnostics?${qs.toString()}`);
      },
      update: (id: string, payload: Partial<DiagnosticRead>) =>
        f<DiagnosticRead>('PATCH', `/diagnostics/${id}`, payload),
      softDelete: (id: string) => f<void>('DELETE', `/diagnostics/${id}`),
      submitFeedback: (id: string, payload: FeedbackCreate) =>
        f<void>('POST', `/diagnostics/${id}/feedback`, payload),
      listFollowups: (id: string, language?: string) =>
        f<FollowupRead[]>(
          'GET',
          `/diagnostics/${id}/followups${language ? `?language=${encodeURIComponent(language)}` : ''}`,
        ),
      markFollowupClicked: (id: string) =>
        f<void>('POST', `/diagnostics/followups/${id}/click`),
      /** Cancel all pending treatment reminders for a diagnosis. Idempotent. */
      dismissReminders: (id: string) =>
        f<void>('DELETE', `/diagnostics/${id}/reminders`),
    },
    translate: (payload: TranslateRequest) =>
      f<TranslateResponse>('POST', '/translate', payload),
    admin: {
      labellingQueue: (
        limit = 50,
        offset = 0,
        source: LabellingQueueSource = 'flagged',
      ) =>
        f<LabellingQueueResponse>(
          'GET',
          `/admin/labelling-queue?source=${source}&limit=${limit}&offset=${offset}`,
        ),
      correctDiagnostic: (diagnosticId: string, payload: ReviewerCorrection) =>
        f<LabellingQueueItem>(
          'PATCH',
          `/admin/labelling-queue/${diagnosticId}`,
          payload,
        ),
      llmFallbackSummary: (days = 7, limit = 50) =>
        f<LlmFallbackSummaryResponse>(
          'GET',
          `/admin/llm-fallback-summary?days=${days}&limit=${limit}`,
        ),
    },
    voice: {
      stt: (payload: SttRequest) => f<SttResponse>('POST', '/voice/stt', payload),
      tts: (payload: TtsRequest) => f<TtsResponse>('POST', '/voice/tts', payload),
    },
    chat: {
      createSession: (payload: { title?: string; language?: string }) =>
        f<ChatSessionRead>('POST', '/chat/sessions', payload),
      listSessions: () => f<ChatSessionRead[]>('GET', '/chat/sessions'),
      listMessages: (sessionId: string) =>
        f<ChatMessageRead[]>('GET', `/chat/sessions/${sessionId}/messages`),
      /**
       * Full conversational turn: server persists the user bubble,
       * grounds in English via Bhashini, asks the inference service,
       * translates the reply back, and returns both bubbles.
       */
      postMessage: (payload: ChatMessageCreate) =>
        f<ChatExchange>('POST', '/chat/messages', payload),
      softDeleteSession: (sessionId: string) =>
        f<void>('DELETE', `/chat/sessions/${sessionId}`),
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
