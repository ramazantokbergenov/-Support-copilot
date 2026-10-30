import { AlertTriangle, ArrowUpRight, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useWorkspace } from "../context/WorkspaceContext";
import { formatDate, isEscalated } from "../lib/format";
import { getTicket } from "../lib/localWorkspace";
import {
  ErrorState,
  LoadingState,
  PageHeading,
  PriorityBadge,
  StatusBadge,
} from "../components/UI";
import type { TicketDetail } from "../types";

export function EscalationsPage() {
  const { tickets, loading, error, refresh } = useWorkspace();
  const [query, setQuery] = useState("");
  const [details, setDetails] = useState<Record<string, TicketDetail>>({});
  const [detailError, setDetailError] = useState<string | null>(null);
  const escalations = useMemo(
    () =>
      tickets
        .filter((ticket) =>
          isEscalated(ticket.status, ticket.escalation_required),
        )
        .filter((ticket) =>
          `${ticket.ticket_id} ${ticket.player_id} ${ticket.category ?? ""}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
        )
        .sort(
          (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
        ),
    [tickets, query],
  );

  useEffect(() => {
    const controller = new AbortController();
    const missing = escalations.filter((ticket) => !details[ticket.ticket_id]);
    if (missing.length) {
      void Promise.all(
        missing.map((ticket) =>
          getTicket(ticket.ticket_id, controller.signal),
        ),
      )
        .then((loaded) =>
          setDetails((current) =>
            Object.fromEntries([
              ...Object.entries(current),
              ...loaded.map((detail) => [detail.ticket_id, detail] as const),
            ]),
          ),
        )
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) {
            setDetailError(
              reason instanceof Error
                ? reason.message
                : "Не удалось загрузить причины эскалации.",
            );
          }
        });
    }
    return () => controller.abort();
  }, [escalations, details]);

  return (
    <>
      <PageHeading
        eyebrow="ЧЕЛОВЕЧЕСКАЯ ПРОВЕРКА"
        title="Escalations"
        description="Обращения, которым оператор вручную установил статус эскалации."
      />
      <div className="notice-banner warning-banner">
        <AlertTriangle size={16} />
        <span>
          AI-рекомендации отключены офлайн. Эскалируйте обращение вручную, если
          оно требует проверки.
        </span>
      </div>
      {loading && tickets.length === 0 ? (
        <section className="panel">
          <LoadingState label="Загружаем эскалации" />
        </section>
      ) : error && tickets.length === 0 ? (
        <ErrorState message={error} onRetry={() => void refresh()} />
      ) : null}
      <section className="panel list-panel">
        <div className="list-panel-toolbar">
          <label className="filter-search">
            <Search size={16} />
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Поиск по обращениям..."
              value={query}
            />
          </label>
          <span className="table-caption-inline">
            На проверке · {escalations.length}
          </span>
        </div>
        {detailError && <ErrorState message={detailError} />}
        {loading && tickets.length === 0 ? null : error && tickets.length === 0 ? null : escalations.length ? (
          <div className="escalation-list">
            {escalations.map((ticket) => (
              <article className="escalation-row" key={ticket.ticket_id}>
                <span className="escalation-icon">
                  <AlertTriangle size={17} />
                </span>
                <div className="escalation-main">
                  <Link to={`/tickets/${encodeURIComponent(ticket.ticket_id)}`}>
                    <strong>{ticket.ticket_id}</strong>
                    <ArrowUpRight size={13} />
                  </Link>
                  <span>
                    Игрок · {ticket.player_id} ·{" "}
                    {ticket.category || "Категория не определена"}
                  </span>
                  <p>
                    {details[ticket.ticket_id]?.escalation_reason ||
                      (details[ticket.ticket_id]
                        ? "Причина эскалации не указана."
                        : detailError
                          ? "Причину не удалось загрузить; откройте обращение."
                          : "Загружаем причину эскалации…")}
                  </p>
                  <small>
                    Дополнительная информация находится в локальной карточке
                    обращения.
                  </small>
                </div>
                <div className="escalation-meta">
                  <PriorityBadge priority={ticket.priority} />
                  <StatusBadge status={ticket.status} />
                  <time>{formatDate(ticket.created_at)}</time>
                  <span>Ответственный не назначен</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="table-empty">
            <div className="empty-icon">
              <AlertTriangle size={18} />
            </div>
            <strong>
              {tickets.length ? "Эскалаций не найдено" : "Эскалаций пока нет"}
            </strong>
            <span>
              {tickets.length
                ? "Ни одно локальное обращение не отмечено для эскалации."
                : "Создайте обращение и вручную измените его статус, если нужна проверка."}
            </span>
          </div>
        )}
      </section>
    </>
  );
}
