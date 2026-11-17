/**
 * The API is deployed separately from the SPA (Vercel frontend + Render/HF
 * backend), so its origin comes from `VITE_API_BASE_URL`. Previously this file
 * hardcoded one Hugging Face Space, which made every other deployment fail.
 *
 * Local development: set `VITE_API_BASE_URL=http://localhost:8000` in `.env.local`.
 * Same-origin deployments: leave it empty.
 */
const configuredBase = (import.meta.env.VITE_API_BASE_URL ?? '').trim();

export const API_BASE_URL = configuredBase.replace(/\/+$/, '');

const GUEST_KEY = 'minerakshak_guest_id';
const TOKEN_KEY = 'minerakshak_auth_token';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

let guestId = '';

const newGuestId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
};

/**
 * Identity of this browser while the app has no sign-in. The API uses it to
 * keep each reviewer's conversations separate; it is replaced by an account id
 * when authentication is added back.
 */
export const getGuestId = () => {
  if (guestId) return guestId;
  try {
    guestId = localStorage.getItem(GUEST_KEY) || newGuestId();
    localStorage.setItem(GUEST_KEY, guestId);
  } catch {
    // Storage can be blocked (private mode); the id then lasts for this page view.
    guestId = newGuestId();
  }
  return guestId;
};

export const getAuthToken = () => localStorage.getItem(TOKEN_KEY);

export const setAuthToken = (token: string | null) => {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
};

const errorMessage = async (response: Response) => {
  try {
    const data = await response.json();
    return data.detail || data.error || data.response || `Request failed (${response.status}).`;
  } catch {
    return `Request failed (${response.status}).`;
  }
};

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('X-Guest-Id', getGuestId());
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError('Unable to reach the server. Check your connection and try again.');
  }

  if (!response.ok) {
    const message = await errorMessage(response);
    if (response.status === 401 && token) {
      setAuthToken(null);
      window.dispatchEvent(new Event('minerakshak:unauthorized'));
    }
    throw new ApiError(message, response.status);
  }
  return response;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  return response.json() as Promise<T>;
}
