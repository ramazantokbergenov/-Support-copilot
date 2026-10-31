import { Clock3, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState, PageHeading, StatusBadge } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";
import { formatDate } from "../lib/format";

export function HistoryPage() {
  const { tickets, loading, error, refresh } = useWorkspace();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const history = useMemo(() => tickets
    .filter((ticket) => `${ticket.ticket_id} ${ticket.player_id} ${ticket.category ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()))
    .filter((ticket) => filter === "all" || ticket.status === filter)
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)), [tickets, query, filter]);
  return (
    <>
      <PageHeading eyebrow="ЖУРНАЛ ОБРАЩЕНИЙ" title="History" description="Хронология поступивших обращений и их текущие статусы." />
      <div className="notice-banner"><Clock3 size={16} /><span>Список обращений и их текущие статусы загружаются из Backend. События конкретного обращения доступны в его карточке.</span></div>
      {loading && tickets.length === 0 ? <section className="panel"><LoadingState label="Загружаем историю" /></section> : error && tickets.length === 0 ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}
      <section className="panel list-panel">
        <div className="list-panel-toolbar">
          <label className="filter-search"><Search size={16} /><input onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по истории..." value={query} /></label>
          <label className="filter-control"><select aria-label="Фильтр истории по статусу" onChange={(event) => setFilter(event.target.value)} value={filter}><option value="all">Все статусы</option><option value="Approved">Одобрено</option><option value="Closed">Закрыто</option><option value="Escalated">Эскалация</option><option value="Needs Review">На проверке</option><option value="Processing">В работе</option><option value="New">Новое</option></select></label>
        </div>
        {loading && tickets.length === 0 ? null : error && tickets.length === 0 ? null : history.length ? <div className="history-table">{history.map((ticket) => (
          <Link className="history-entry" key={ticket.ticket_id} to={`/tickets/${encodeURIComponent(ticket.ticket_id)}`}>
            <span className="history-entry-icon"><Clock3 size={15} /></span><span className="history-entry-main"><strong>{ticket.ticket_id} · {ticket.category || "Без категории"}</strong><small>Игрок {ticket.player_id}</small><small>Создано · {formatDate(ticket.created_at)}</small></span><StatusBadge status={ticket.status} /><span className="history-date">{formatDate(ticket.created_at)}</span>
          </Link>
        ))}</div> : <div className="table-empty"><div className="empty-icon"><Clock3 size={18} /></div><strong>{tickets.length ? "Записей не найдено" : "История пока пуста"}</strong><span>Здесь отображаются обращения, полученные из Backend.</span></div>}
      </section>
    </>
  );
}
