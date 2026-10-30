import { ArrowRight, Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState, PageHeading, StatusBadge } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";
import { formatDate } from "../lib/format";

export function AnalysisPage() {
  const { tickets, loading, error, refresh } = useWorkspace();
  const [query, setQuery] = useState("");
  const filtered = useMemo(
    () => tickets.filter((ticket) =>
      `${ticket.ticket_id} ${ticket.player_id} ${ticket.category ?? ""}`
        .toLowerCase().includes(query.trim().toLowerCase()),
    ),
    [tickets, query],
  );
  const analyzed = tickets.filter((ticket) => ticket.confidence !== null).length;

  return (
    <>
      <PageHeading eyebrow="ПРОВЕРКА РЕЗУЛЬТАТОВ" title="AI Analysis" description="Обзор обращений. Подробный результат AI появится после подключения backend." />
      <div className="notice-banner warning-banner"><Sparkles size={16} /><span><strong>Автономный режим.</strong> AI-анализ отключён; система не создаёт фиктивные классификации и рекомендации.</span></div>
      {loading && tickets.length === 0 ? <section className="panel"><LoadingState label="Загружаем очередь анализа" /></section> : error && tickets.length === 0 ? <ErrorState message={error} onRetry={() => void refresh()} /> : null}
      <section className="panel list-panel">
        <div className="list-panel-toolbar">
          <label className="filter-search"><Search size={16} /><input onChange={(event) => setQuery(event.target.value)} placeholder="Найти обращение..." value={query} /></label>
          <span className="table-caption-inline">Сохранённый анализ: {analyzed}</span>
        </div>
        {loading && tickets.length === 0 ? null : error && tickets.length === 0 ? null : filtered.length ? (
          <div className="analysis-ticket-list">
            {filtered.map((ticket) => (
              <Link className="analysis-ticket-row" key={ticket.ticket_id} to={`/analysis/${encodeURIComponent(ticket.ticket_id)}`}>
                <span className="analysis-ticket-icon"><Sparkles size={16} /></span>
                <span className="analysis-ticket-info"><strong>{ticket.ticket_id} <small>· Игрок {ticket.player_id}</small></strong><span>{ticket.category || "Категория не определена"} · {formatDate(ticket.created_at)}</span></span>
                {ticket.confidence === null ? <span className="badge badge-neutral">Нет анализа</span> : <span className="confidence-label">{Math.round(ticket.confidence * 100)}% уверенности</span>}
                <StatusBadge status={ticket.status} /><ArrowRight size={15} className="muted" />
              </Link>
            ))}
          </div>
        ) : (
          <div className="table-empty"><div className="empty-icon"><Sparkles size={18} /></div><strong>{tickets.length ? "Обращений не найдено" : "Нет обращений для анализа"}</strong><span>{tickets.length ? "Измените поисковый запрос." : "Создайте обращение; открыть этот раздел с результатами AI можно после подключения backend."}</span></div>
        )}
      </section>
    </>
  );
}
