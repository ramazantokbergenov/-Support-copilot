import type {
  CreateTicketInput,
  RuleList,
  TicketDetail,
  TicketStatus,
  TicketSummary,
} from "../types";

const STORAGE_KEY = "support-copilot:tickets";

export class LocalWorkspaceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LocalWorkspaceError";
  }
}

function readTickets(): TicketDetail[] {
  let serialized: string | null;
  try {
    serialized = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    throw new LocalWorkspaceError(
      "Локальное хранилище браузера недоступно. Разрешите сайту сохранять данные.",
    );
  }
  if (!serialized) return [];

  let value: unknown;
  try {
    value = JSON.parse(serialized);
  } catch {
    throw new LocalWorkspaceError(
      "Локальные данные повреждены. Очистите данные сайта в настройках браузера.",
    );
  }
  if (!Array.isArray(value) || !value.every(isTicketDetail)) {
    throw new LocalWorkspaceError(
      "Локальные данные имеют неподдерживаемый формат. Очистите данные сайта в настройках браузера.",
    );
  }
  return value;
}

function isTicketDetail(value: unknown): value is TicketDetail {
  if (typeof value !== "object" || value === null) return false;
  return (
    "ticket_id" in value &&
    typeof value.ticket_id === "string" &&
    "player_id" in value &&
    typeof value.player_id === "string" &&
    "message" in value &&
    typeof value.message === "string" &&
    "created_at" in value &&
    typeof value.created_at === "string" &&
    "status" in value &&
    ["New", "Processing", "Needs Review", "Approved", "Escalated", "Closed"].includes(
      String(value.status),
    ) &&
    "priority" in value &&
    ["Low", "Normal", "High", "Urgent"].includes(String(value.priority)) &&
    "attachments" in value &&
    Array.isArray(value.attachments) &&
    "matched_rules" in value &&
    Array.isArray(value.matched_rules)
  );
}

function writeTickets(tickets: TicketDetail[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tickets));
  } catch {
    throw new LocalWorkspaceError(
      "Не удалось сохранить обращение. Возможно, в браузере закончилось место.",
    );
  }
}

function checkAborted(signal?: AbortSignal) {
  if (signal?.aborted) {
    throw new DOMException("Запрос отменён.", "AbortError");
  }
}

export async function listTickets(signal?: AbortSignal): Promise<TicketSummary[]> {
  checkAborted(signal);
  return readTickets().map(toSummary);
}

export async function getTicket(
  ticketId: string,
  signal?: AbortSignal,
): Promise<TicketDetail> {
  checkAborted(signal);
  const ticket = readTickets().find((item) => item.ticket_id === ticketId);
  if (!ticket) {
    throw new LocalWorkspaceError("Обращение не найдено в локальном хранилище.");
  }
  return ticket;
}

export async function getRules(
  query = "",
  signal?: AbortSignal,
): Promise<RuleList> {
  checkAborted(signal);
  void query;
  return { items: [], count: 0 };
}

export async function createTicket(
  input: CreateTicketInput,
): Promise<TicketDetail> {
  if (input.attachments.length > 0) {
    throw new LocalWorkspaceError(
      "Вложения временно недоступны без backend. Удалите файлы и создайте обращение без них.",
    );
  }
  const tickets = readTickets();
  const ticket: TicketDetail = {
    ticket_id: `LOCAL-${crypto.randomUUID()}`,
    player_id: input.player_id,
    category: input.category || null,
    priority: input.priority,
    status: "New",
    confidence: null,
    escalation_required: null,
    created_at: new Date().toISOString(),
    message: input.message,
    attachments: [],
    extracted_facts: null,
    matched_rules: [],
    draft_reply: null,
    escalation_reason: null,
    ai_analysis: null,
  };
  writeTickets([ticket, ...tickets]);
  return ticket;
}

export async function updateTicketStatus(
  ticketId: string,
  status: TicketStatus,
): Promise<TicketSummary> {
  const tickets = readTickets();
  const index = tickets.findIndex((ticket) => ticket.ticket_id === ticketId);
  if (index < 0) {
    throw new LocalWorkspaceError("Обращение не найдено в локальном хранилище.");
  }
  const updated = { ...tickets[index], status };
  tickets[index] = updated;
  writeTickets(tickets);
  return toSummary(updated);
}

export async function analyzeTicket(_ticketId: string): Promise<never> {
  throw new LocalWorkspaceError(
    "AI-анализ недоступен в автономном режиме. Подключите backend, чтобы запустить анализ.",
  );
}

export function attachmentUrl(_ticketId: string, _attachmentId: string): string {
  throw new LocalWorkspaceError(
    "Вложения недоступны в автономном режиме: они хранятся на backend.",
  );
}

export async function getAttachment(
  _url: string,
  _signal?: AbortSignal,
): Promise<Blob> {
  throw new LocalWorkspaceError(
    "Вложения недоступны в автономном режиме: они хранятся на backend.",
  );
}

function toSummary(ticket: TicketDetail): TicketSummary {
  const {
    ticket_id,
    player_id,
    category,
    priority,
    status,
    confidence,
    escalation_required,
    created_at,
  } = ticket;
  return {
    ticket_id,
    player_id,
    category,
    priority,
    status,
    confidence,
    escalation_required,
    created_at,
  };
}
