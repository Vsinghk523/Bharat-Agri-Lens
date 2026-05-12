import { createApiClient } from '@bal/api-client';

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api';

export const api = createApiClient({
  baseUrl,
  getAccessToken: () => localStorage.getItem('bal_access_token'),
});
