import { createApiClient } from '@bal/api-client';
import { getAccessToken } from './auth';

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api';

export const api = createApiClient({
  baseUrl,
  getAccessToken,
});
