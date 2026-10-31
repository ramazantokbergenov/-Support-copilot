import type {
  CreateTicketInput,
  DraftRecord,
  OperatorEvent,
  OperatorNote,
  RuleList,
  StructuredAnalysisResult,
  TicketDetail,
  TicketListResponse,
  TicketQuery,
  TicketStatus,
  TicketSummary,
} from "../types";
import { getApiBaseUrl, supabase } from "./supabase";
import { getLocalAccessToken } from "./localAuth";

export class ApiError extends Error {
  constructor(message: string, readonly status?: number, readonly code?: string) {
    super(message);
    this.name = "ApiError";
  }
}

export function getHealth(signal?: AbortSignal) {
  return apiRequest<{ status: string }>("/health", { signal });
}

const API_TIMEOUT_MS = 30_000;
const AI_TIMEOUT_MS = 120_000;

function apiBase() {
  const base = getApiBaseUrl();
  if (!base) {
    throw new ApiError("Backend не настроен. Укажите VITE_API_BASE_URL или Supabase URL.", 503, "configuration_error");
  }
  return base;
}

function isEdgeApi() {
  return apiBase().includes("/functions/v1/api");
}

async function requestHeaders(body?: BodyInit | null) {
  const headers = new Headers({ Accept: "application/json" });
  if (body && !(body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (supabase) {
    const { data, error } = await supabase.auth.getSession();
    if (error) throw new ApiError("Не удалось проверить сессию оператора.", 401, "auth_error");
    const token = data.session?.access_token;
    if (!token) throw new ApiError("Войдите в систему, чтобы продолжить.", 401, "unauthorized");
    headers.set("Authorization", `Bearer ${token}`);
    headers.set("apikey", import.meta.env.VITE_SUPABASE_ANON_KEY ?? "");
  } else {
    const token = getLocalAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = API_TIMEOUT_MS,
): Promise<T> {
  const base = apiBase();
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  options.signal?.addEventListener("abort", onAbort, { once: true });
  if (options.signal?.aborted) controller.abort();
  try {
    const headers = await requestHeaders(options.body);
    const response = await fetch(`${base}${path}`, {
      ...options,
      headers: new Headers({ ...Object.fromEntries(headers), ...Object.fromEntries(new Headers(options.headers)) }),
      signal: controller.signal,
    });
    if (!response.ok) {
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      const error = payload && typeof payload === "object" && "error" in payload
        ? (payload as { error?: { message?: string; code?: string } }).error
        : null;
      throw new ApiError(
        error?.message ?? `Запрос завершился с ошибкой (${response.status}).`,
        response.status,
        error?.code,
      );
    }
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  } catch (reason) {
    if (reason instanceof ApiError) throw reason;
    if (controller.signal.aborted) {
      if (options.signal?.aborted) throw new DOMException("Запрос отменён.", "AbortError");
      throw new ApiError("Backend отвечает слишком долго. Попробуйте ещё раз.", 408, "timeout");
    }
    throw new ApiError(reason instanceof Error ? reason.message : "Не удалось связаться с Backend.");
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener("abort", onAbort);
  }
}

export async function listTickets(
  query: TicketQuery = {},
  signal?: AbortSignal,
): Promise<TicketListResponse> {
  const parameters = new URLSearchParams();
  for (const key of ["q", "status", "priority", "category", "limit", "offset"] as const) {
    const value = query[key];
    if (value !== undefined && value !== "") parameters.set(key, String(value));
  }
  const suffix = parameters.size ? `?${parameters.toString()}` : "";
  const result = await apiRequest<TicketListResponse | TicketSummary[]>(`/tickets${suffix}`, { signal });
  if (Array.isArray(result)) {
    return { items: result, count: result.length, limit: result.length, offset: query.offset ?? 0 };
  }
  return result;
}

export function getTicket(ticketId: string, signal?: AbortSignal) {
  return apiRequest<TicketDetail>(`/tickets/${encodeURIComponent(ticketId)}`, { signal });
}

export async function getRules(query = "", signal?: AbortSignal): Promise<RuleList> {
  const params = new URLSearchParams();
  if (query.trim()) params.set(isEdgeApi() ? "query" : "query", query.trim());
  const route = isEdgeApi() ? "/rules/search" : "/rules";
  const suffix = params.size ? `?${params.toString()}` : "";
  return apiRequest<RuleList>(`${route}${suffix}`, { signal });
}

export function createTicket(input: CreateTicketInput): Promise<TicketDetail> {
  const body = new FormData();
  body.set("player_id", input.player_id);
  body.set("message", input.message);
  body.set("priority", input.priority);
  if (input.category) body.set("category", input.category);
  input.attachments.forEach((file) => body.append("attachments", file, file.name));
  return apiRequest<TicketDetail>("/tickets", {
    method: "POST",
    body,
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
}

export function updateTicketStatus(ticketId: string, status: TicketStatus) {
  return apiRequest<TicketSummary>(`/tickets/${encodeURIComponent(ticketId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function analyzeTicket(ticketId: string, signal?: AbortSignal) {
  const endpoint = isEdgeApi() ? "analyze" : "analyze-structured";
  return apiRequest<StructuredAnalysisResult>(
    `/tickets/${encodeURIComponent(ticketId)}/${endpoint}`,
    { method: "POST", signal },
    AI_TIMEOUT_MS,
  );
}

export function regenerateReply(ticketId: string, instructions?: string) {
  return apiRequest<DraftRecord>(`/tickets/${encodeURIComponent(ticketId)}/generate-reply`, {
    method: "POST",
    body: JSON.stringify(instructions ? { instructions } : {}),
  }, AI_TIMEOUT_MS);
}

export function saveDraft(ticketId: string, draftId: string | null, body: string) {
  const route = `/tickets/${encodeURIComponent(ticketId)}/drafts${draftId ? `/${encodeURIComponent(draftId)}` : ""}`;
  return apiRequest<DraftRecord>(route, {
    method: draftId ? "PUT" : "POST",
    body: JSON.stringify({ body }),
  });
}

export function recordDecision(
  ticketId: string,
  decision: string,
  draftId?: string | null,
  note?: string,
) {
  return apiRequest<{ ticket_id: string; decision: string; created_at: string }>(
    `/tickets/${encodeURIComponent(ticketId)}/decisions`,
    {
      method: "POST",
      body: JSON.stringify({ decision, ...(draftId ? { draft_id: draftId } : {}), ...(note ? { note } : {}) }),
    },
  );
}

export function saveOperatorNote(ticketId: string, body: string) {
  return apiRequest<OperatorNote>(`/tickets/${encodeURIComponent(ticketId)}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function getTicketEvents(ticketId: string, signal?: AbortSignal) {
  return apiRequest<OperatorEvent[]>(`/tickets/${encodeURIComponent(ticketId)}/events`, { signal });
}

export function attachmentUrl(ticketId: string, attachmentId: string) {
  return `${apiBase()}/tickets/${encodeURIComponent(ticketId)}/attachments/${encodeURIComponent(attachmentId)}`;
}

export async function getAttachment(url: string, signal?: AbortSignal): Promise<Blob> {
  const headers = await requestHeaders();
  const response = await fetch(url, { headers, signal });
  if (!response.ok) throw new ApiError("Не удалось загрузить вложение.", response.status);
  return response.blob();
}