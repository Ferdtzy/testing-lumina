/**
 * API client terpusat untuk semua komunikasi dengan backend Django.
 * Jangan sebar `fetch()` langsung di komponen — selalu lewat layer ini.
 * Setiap request otomatis menyertakan token autentikasi bila tersedia.
 */

import { getToken, clearAuth } from "./auth";

const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

const DEFAULT_TIMEOUT_MS = 60000;

interface RequestOptions extends Omit<RequestInit, "body"> {
    body?: unknown;
    /** When true, body is a FormData and Content-Type is left to the browser. */
    isFormData?: boolean;
    /** Request timeout in milliseconds. */
    timeout?: number;
}

export class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

interface ApiErrorPayload {
    detail?: string;
    non_field_errors?: string[];
    [field: string]: unknown;
}

function formatApiError(payload: ApiErrorPayload | null, fallback: string): string {
    if (!payload) return fallback;
    if (typeof payload.detail === "string" && payload.detail) return payload.detail;
    if (Array.isArray(payload.non_field_errors) && payload.non_field_errors.length) {
        return payload.non_field_errors.join(", ");
    }
    const parts: string[] = [];
    for (const [field, value] of Object.entries(payload)) {
        if (field === "detail" || field === "non_field_errors") continue;
        const label = field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
        if (Array.isArray(value)) {
            parts.push(`${label}: ${(value as string[]).join(", ")}`);
        } else if (typeof value === "string") {
            parts.push(`${label}: ${value}`);
        }
    }
    return parts.length ? parts.join("; ") : fallback;
}

function buildHeaders(headers?: HeadersInit): HeadersInit {
    const token = getToken();
    const base: Record<string, string> = {
        ...(headers as Record<string, string> | undefined),
    };
    if (token) base["Authorization"] = `Token ${token}`;
    return base;
}

async function request<T>(
    path: string,
    { body, headers, isFormData, timeout, signal, ...options }: RequestOptions = {},
): Promise<T> {
    const isBodyFormData = isFormData === true;
    const finalHeaders = buildHeaders(
        isBodyFormData
            ? headers
            : {
                "Content-Type": "application/json",
                ...headers,
            },
    );

    const controller = new AbortController();
    const abortFromCaller = () => controller.abort();
    if (signal?.aborted) controller.abort();
    else signal?.addEventListener("abort", abortFromCaller, { once: true });
    const requestTimeout = timeout ?? DEFAULT_TIMEOUT_MS;
    const timeoutId = requestTimeout > 0
        ? setTimeout(() => controller.abort(), requestTimeout)
        : undefined;

    try {
        const response = await fetch(`${API_BASE_URL}${path}`, {
            ...options,
            headers: finalHeaders,
            body:
                body === undefined
                    ? undefined
                    : isBodyFormData
                        ? (body as FormData)
                        : JSON.stringify(body),
            signal: controller.signal,
        });

        if (response.status === 401) {
            clearAuth();
            window.location.href = "/login";
            throw new ApiError("Sesi login telah berakhir.", 401);
        }

        if (!response.ok) {
            const errorData = (await response.json().catch(() => null)) as
                | ApiErrorPayload
                | null;
            throw new ApiError(
                formatApiError(errorData, `Permintaan gagal (${response.status}).`),
                response.status,
            );
        }

        if (response.status === 204) {
            return undefined as T;
        }
        return response.json() as Promise<T>;
    } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
            throw new ApiError("Permintaan timeout. Silakan coba lagi.", 408);
        }
        throw error;
    } finally {
        signal?.removeEventListener("abort", abortFromCaller);
        if (timeoutId) clearTimeout(timeoutId);
    }
}

export const api = {
    get: <T>(path: string, options?: RequestOptions) => request<T>(path, options),
    post: <T>(path: string, body: unknown = {}, options?: Omit<RequestOptions, "body">) =>
        request<T>(path, { method: "POST", body, ...options }),
    patch: <T>(path: string, body: unknown = {}, options?: Omit<RequestOptions, "body">) =>
        request<T>(path, { method: "PATCH", body, ...options }),
    delete: <T>(path: string, options?: RequestOptions) =>
        request<T>(path, { method: "DELETE", ...options }),
    uploadFile: <T>(path: string, formData: FormData, options?: Omit<RequestOptions, "body" | "isFormData">) =>
        request<T>(path, { method: "POST", body: formData, isFormData: true, ...options }),
};

export interface DocumentItem {
  id: number;
  document_name: string;
  file_type: string;
  size: number;
  file_size_mb: number;
  status: string;
  is_ocr: boolean;
  created_at: string;
}

export interface DocumentUploadResponse {
  document_id: number;
  message: string;
  status: string;
  session_id: string;
}

export const documentsApi = {
  list: () => api.get<{ results: DocumentItem[]; count: number }>("/documents/"),
  upload: (formData: FormData) => api.uploadFile<DocumentUploadResponse>("/documents/", formData),
  ingest: (id: number) => api.post(`/documents/${id}/ingest/`, {}),
  remove: (id: number) => api.delete(`/documents/${id}/delete/`),
};

export type { RequestOptions };
