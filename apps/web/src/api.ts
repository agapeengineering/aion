export class ApiError extends Error {
  constructor(
    public code: string,
    public retry = 0,
    public status = 0,
    public current?: unknown,
  ) {
    super(code);
  }
}
export type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
};
export type Transport = <T>(path: string, options?: RequestOptions) => Promise<T>;
export const request: Transport = async <T>(path: string, options: RequestOptions = {}) => {
  const response = await fetch(`/api/v1${path}`, {
    method: options.method ?? 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    throw new ApiError(
      value?.error?.code ?? 'unavailable',
      Number(response.headers.get('Retry-After')) || 0,
      response.status,
      value?.current,
    );
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
};
export function api<T>(path: string, body?: unknown, csrf?: string): Promise<T> {
  return request<T>(path, {
    method: body === undefined ? 'GET' : 'POST',
    body,
    headers: csrf ? { 'X-CSRF-Token': csrf } : undefined,
  });
}
