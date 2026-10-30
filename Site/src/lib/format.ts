import type { TicketPriority, TicketStatus } from "../types";

export const statusLabels: Record<TicketStatus, string> = {
  New: "Новое",
  Processing: "В работе",
  "Needs Review": "На проверке",
  Approved: "Одобрено",
  Escalated: "Эскалация",
  Closed: "Закрыто",
};

export const priorityLabels: Record<TicketPriority, string> = {
  Low: "Низкий",
  Normal: "Обычный",
  High: "Высокий",
  Urgent: "Срочный",
};

export function formatDate(value: string, withTime = true) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Дата неизвестна";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export function isEscalated(
  status: TicketStatus,
  escalationRequired: boolean | null,
) {
  return status === "Escalated" || escalationRequired === true;
}
