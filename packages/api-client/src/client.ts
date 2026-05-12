import type {
  ChatMessageRead,
  ChatSessionRead,
  DiagnosticCreate,
  DiagnosticRead,
  DownloadUrlResponse,
  FeedbackCreate,
  FollowupRead,
  OtpRequest,
  OtpRequestResponse,
  OtpVerify,
  PresignRequest,
  PresignResponse,
  TokenPair,
  UserRead,
  UserUpdate,
} from '@bal/types';

export interface ApiClientOptions {
  baseUrl: string;
  getAccessToken?: () => string | null;
}

class HttpError extends Error {
  constructor(public status: number, public payload: unknown, message?: string) {
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

  return {
    auth: {
      requestOtp: (payload: OtpRequest) =>
        f<OtpRequestResponse>('POST', '/auth/otp/request', payload),
      verifyOtp: (payload: OtpVerify) => f<TokenPair>('POST', '/auth/otp/verify', payload),
    },
    users: {
      get: (userId: string) => f<UserRead>('GET', `/users/${userId}`),
      list: (limit = 50, offset = 0) =>
        f<UserRead[]>('GET', `/users?limit=${limit}&offset=${offset}`),
      update: (userId: string, payload: UserUpdate) =>
        f<UserRead>('PATCH', `/users/${userId}`, payload),
      softDelete: (userId: string) => f<void>('DELETE', `/users/${userId}`),
      purge: (userId: string) => f<void>('DELETE', `/users/${userId}/purge`),
    },
    uploads: {
      presign: (payload: PresignRequest) =>
        f<PresignResponse>('POST', '/uploads/presign', payload),
      get: (imageId: string) => f<unknown>('GET', `/uploads/${imageId}`),
      getDownloadUrl: (imageId: string) =>
        f<DownloadUrlResponse>('GET', `/uploads/${imageId}/url`),
      list: (limit = 50, offset = 0) =>
        f<unknown[]>('GET', `/uploads?limit=${limit}&offset=${offset}`),
      softDelete: (imageId: string) => f<void>('DELETE', `/uploads/${imageId}`),
    },
    diagnostics: {
      create: (payload: DiagnosticCreate) => f<DiagnosticRead>('POST', '/diagnostics', payload),
      get: (id: string) => f<DiagnosticRead>('GET', `/diagnostics/${id}`),
      list: (limit = 50, offset = 0) =>
        f<DiagnosticRead[]>('GET', `/diagnostics?limit=${limit}&offset=${offset}`),
      update: (id: string, payload: Partial<DiagnosticRead>) =>
        f<DiagnosticRead>('PATCH', `/diagnostics/${id}`, payload),
      softDelete: (id: string) => f<void>('DELETE', `/diagnostics/${id}`),
      submitFeedback: (id: string, payload: FeedbackCreate) =>
        f<void>('POST', `/diagnostics/${id}/feedback`, payload),
      listFollowups: (id: string) => f<FollowupRead[]>('GET', `/diagnostics/${id}/followups`),
      markFollowupClicked: (id: string) =>
        f<void>('POST', `/diagnostics/followups/${id}/click`),
    },
    chat: {
      createSession: (payload: { title?: string; language?: string }) =>
        f<ChatSessionRead>('POST', '/chat/sessions', payload),
      listSessions: () => f<ChatSessionRead[]>('GET', '/chat/sessions'),
      listMessages: (sessionId: string) =>
        f<ChatMessageRead[]>('GET', `/chat/sessions/${sessionId}/messages`),
      postMessage: (payload: {
        session_id: string;
        role?: string;
        language?: string;
        content_text?: string;
        audio_blob_url?: string;
      }) => f<ChatMessageRead>('POST', '/chat/messages', payload),
      softDeleteSession: (sessionId: string) =>
        f<void>('DELETE', `/chat/sessions/${sessionId}`),
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
