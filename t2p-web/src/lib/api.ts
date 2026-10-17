import axios from 'axios';

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001';
export const AUTH_TOKEN_KEY = 't2p_access_token';
export const DEFAULT_API_TIMEOUT_MS = 30_000;
export const GENERATION_TIMEOUT_MS = 180_000;
export const AUDIT_TIMEOUT_MS = 180_000;

export const api = axios.create({
  baseURL: API_BASE,
  timeout: DEFAULT_API_TIMEOUT_MS,
});

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

interface ApiErrorPayload {
  error?: {
    message?: unknown;
  };
  detail?: unknown;
}

export const getApiErrorMessage = (
  error: unknown,
  fallback: string,
  timeoutMessage = 'The request timed out. Please try again.',
): string => {
  if (!axios.isAxiosError(error)) return fallback;

  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return timeoutMessage;
  }

  const payload = error.response?.data as ApiErrorPayload | undefined;
  const nestedMessage = payload?.error?.message;
  if (typeof nestedMessage === 'string' && nestedMessage.trim()) {
    return nestedMessage;
  }

  const detail = payload?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const detailMessage = (detail as { message?: unknown }).message;
    if (typeof detailMessage === 'string' && detailMessage.trim()) {
      return detailMessage;
    }
  }

  return fallback;
};
