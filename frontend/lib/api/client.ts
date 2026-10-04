import type { components } from "./schema";

export type Schemas = components["schemas"];

// The custom exception-handler error shape (app/main.py, Phase 2/6/11) —
// not reflected in the generated OpenAPI schema since FastAPI doesn't know
// about hand-written exception handlers, so this is typed by hand against
// the real, verified backend response shape.
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.status = status;
    this.code = body.error.code;
    this.requestId = body.error.request_id;
  }
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

interface RequestOptions {
  method?: string;
  query?: Record<string, string | undefined>;
  body?: unknown;
  isFormData?: boolean;
  skipAuth?: boolean;
}

function buildUrl(path: string, query?: Record<string, string | undefined>): string {
  const url = new URL(API_BASE_URL + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, value);
    }
  }
  return url.toString();
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (!options.isFormData) {
    headers["Content-Type"] = "application/json";
  }
  if (!options.skipAuth && accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body: options.isFormData
      ? (options.body as FormData)
      : options.body !== undefined
        ? JSON.stringify(options.body)
        : undefined,
  });

  if (!response.ok) {
    let errorBody: ApiErrorBody;
    try {
      errorBody = await response.json();
    } catch {
      errorBody = {
        error: { code: "UNKNOWN", message: response.statusText, request_id: "unknown" },
      };
    }
    // Every response the backend returns for a non-2xx status follows the
    // {"error": {...}} shape (Phase 2's global exception handlers) — the
    // one exception is a raw 401 from the bearer-auth dependency itself,
    // which FastAPI's default HTTPException path still routes through the
    // same handler (see app/main.py's handle_http_exception), so this
    // shape is safe to assume unconditionally here.
    throw new ApiError(response.status, errorBody);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
