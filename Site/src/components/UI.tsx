import type { ReactNode } from "react";
import {
  AlertCircle,
  BarChart3,
  BookOpen,
  Inbox,
  LoaderCircle,
  Search,
  Sparkles,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { TicketPriority, TicketStatus } from "../types";
import { priorityLabels, statusLabels } from "../lib/format";

export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}

export function SectionHeading({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        <h2>{title}</h2>
        {detail && <span>{detail}</span>}
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  icon = "inbox",
  title,
  description,
  action,
}: {
  icon?: "inbox" | "search" | "book" | "chart" | "users" | "sparkles";
  title: string;
  description: string;
  action?: ReactNode;
}) {
  const Icon =
    icon === "search"
      ? Search
      : icon === "sparkles"
          ? Sparkles
        : icon === "book"
            ? BookOpen
          : icon === "chart"
              ? BarChart3
            : icon === "users"
                ? Users
                : Inbox;
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon size={19} strokeWidth={1.7} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`badge status-badge status-${statusClass(status)}`}>
      <span className="badge-dot" />
      {statusLabels[status]}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  return (
    <span className={`badge priority-badge priority-${priority.toLowerCase()}`}>
      <span className="badge-dot" />
      {priorityLabels[priority]}
    </span>
  );
}

function statusClass(status: TicketStatus) {
  return {
    New: "new",
    Processing: "processing",
    "Needs Review": "review",
    Approved: "approved",
    Escalated: "escalated",
    Closed: "closed",
  }[status];
}

export function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  accent = false,
}: {
  label: string;
  value: number | string;
  detail: string;
  icon: LucideIcon;
  accent?: boolean;
}) {
  return (
    <article className={`metric-card${accent ? " metric-accent" : ""}`}>
      <div className="metric-top">
        <span>{label}</span>
        <span className="metric-icon">
          <Icon size={16} strokeWidth={1.7} />
        </span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
    </article>
  );
}

export function LoadingState({ label = "Загружаем данные" }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <img className="loading-brand-mark" src="/branding/support-copilot-icon.svg" alt="" />
      <LoaderCircle className="spin" size={18} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={18} />
      <span>{message}</span>
      {onRetry && (
        <button className="button button-quiet" onClick={onRetry} type="button">
          Повторить
        </button>
      )}
    </div>
  );
}

export function IconButton({
  label,
  children,
  onClick,
  className = "",
  type = "button",
}: {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  className?: string;
  type?: "button" | "submit";
}) {
  return (
    <button
      aria-label={label}
      className={`icon-button ${className}`}
      onClick={onClick}
      type={type}
      title={label}
    >
      {children}
    </button>
  );
}
