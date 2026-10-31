import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Inbox,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, MetricCard, PageHeading, SectionHeading, StatusBadge } from "../components/UI";
import { TicketTable } from "../components/TicketTable";
import { useWorkspace } from "../context/WorkspaceContext";
import { formatDate, isEscalated } from "../lib/format";
import { getHealth } from "../lib/api";

export function OverviewPage() {
  const { tickets, totalCount, loading, error, refresh } = useWorkspace();
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal).then(() => setBackendOnline(true)).catch(() => {
      if (!controller.signal.aborted) setBackendOnline(false);
    });
    return () => controller.abort();
  }, []);

  if (loading) {
    return (
      <>
        <PageHeading eyebrow="ОПЕРАЦИОННЫЙ ЦЕНТР" title="Добро пожаловать" description="Загружаем обращения из Backend." />
        <div className="metric-grid">{[1, 2, 3, 4].map((item) => <div className="metric-card skeleton-card" key={item}><span className="skeleton-line" /><span className="skeleton-value" /><span className="skeleton-line short" /></div>)}</div>
        <div className="panel"><div className="skeleton-panel"><span className="skeleton-line" /><span className="skeleton-row" /><span className="skeleton-row" /><span className="skeleton-row" /></div></div>
      </>
    );
  }
  if (error) {
    return (
      <>
        <PageHeading eyebrow="ОПЕРАЦИОННЫЙ ЦЕНТР" title="Добро пожаловать" description="Состояние обращений и инструменты поддержки в одном рабочем пространстве." />
        <ErrorState message={error} onRetry={() => void refresh()} />
      </>
    );
  }

  const newCount = tickets.filter((ticket) => ticket.status === "New").length;
  const inProgress = tickets.filter((ticket) => ticket.status === "Processing").length;
  const escalated = tickets.filter((ticket) => isEscalated(ticket.status, ticket.escalation_required)).length;
  const review = tickets.filter((ticket) => ticket.status === "Needs Review").length;
  const latest = [...tickets].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const categoryTotals = new Map<string, number>();
  tickets.forEach((ticket) => {
    if (ticket.category) categoryTotals.set(ticket.category, (categoryTotals.get(ticket.category) ?? 0) + 1);
  });
  const categories = [...categoryTotals.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);

  return (
    <>
      <PageHeading eyebrow="ОПЕРАЦИОННЫЙ ЦЕНТР" title="Добро пожаловать" description="Состояние обращений и инструменты поддержки в одном рабочем пространстве." />
      <section aria-label="Сводка обращений" className="metric-grid">
        <MetricCard accent detail="Общий count Backend" icon={Inbox} label="Всего обращений" value={totalCount} />
        <MetricCard detail="В последних 100 записях" icon={Clock3} label="Новые" value={newCount} />
        <MetricCard detail="В последних 100 записях" icon={CheckCircle2} label="В работе" value={inProgress} />
        <MetricCard detail="В последних 100 записях" icon={AlertTriangle} label="Эскалации" value={escalated} />
      </section>
      <section className="dashboard-grid">
        <article className="panel dashboard-queue">
          <div className="panel-header"><SectionHeading title="Последние обращения" detail={`${Math.min(tickets.length, 6)} из ${totalCount}`} /><Link className="text-link" to="/tickets">Все обращения <ArrowRight size={14} /></Link></div>
          <TicketTable emptyDescription="Создайте первое обращение в Backend." tickets={latest.slice(0, 6)} />
        </article>
        <div className="dashboard-side">
          <article className="panel">
            <div className="panel-header"><SectionHeading title="Категории" detail="В последних 100 записях Backend" /></div>
            {categories.length ? <div className="category-list">{categories.map(([category, count]) => (
              <div className="category-row" key={category}><span className="category-marker" /><span className="category-name">{category}</span><span className="category-count">{count}</span><span className="category-track"><i style={{ width: `${Math.max(7, (count / tickets.length) * 100)}%` }} /></span></div>
            ))}</div> : <div className="compact-empty">Распределение появится, когда у обращений будут категории.</div>}
          </article>
          <article className="panel ai-health">
            <div className="panel-header"><SectionHeading title="AI workspace" detail="Состояние обработки" /></div>
            <div className="system-card">
              <span className="system-icon"><Sparkles size={17} /></span>
              <div className="system-copy"><strong>{backendOnline ? "AI endpoint доступен" : backendOnline === false ? "Backend недоступен" : "Проверяем Backend"}</strong><span>Анализ запускается оператором из карточки обращения</span></div>
              <span className={`system-status${backendOnline ? " status-live" : ""}`}><i />{backendOnline ? "API" : backendOnline === false ? "Офлайн" : "Проверка"}</span>
            </div>
            <div className="ai-footnote">Результаты анализа и найденные правила требуют проверки оператором перед любым решением.</div>
            <Link className="text-link ai-link" to="/analysis">К очереди анализа <ArrowRight size={14} /></Link>
          </article>
        </div>
      </section>
      <section className="dashboard-bottom">
        <article className="panel">
          <div className="panel-header"><SectionHeading title="Состояние очереди" detail="В последних 100 записях Backend" /></div>
          <div className="queue-summary"><div><span className="summary-dot dot-new" /><span>Новые</span><strong>{newCount}</strong></div><div><span className="summary-dot dot-review" /><span>На проверке</span><strong>{review}</strong></div><div><span className="summary-dot dot-escalated" /><span>Эскалации</span><strong>{escalated}</strong></div></div>
        </article>
        <article className="panel activity-panel">
          <div className="panel-header"><SectionHeading title="Недавняя активность" detail="Созданные обращения" /><Link className="text-link" to="/history">История <ArrowRight size={14} /></Link></div>
          {latest.length ? <div className="activity-list">{latest.slice(0, 4).map((ticket) => (
            <Link className="activity-row" key={ticket.ticket_id} to={`/tickets/${encodeURIComponent(ticket.ticket_id)}`}><span className="activity-mark"><Inbox size={14} /></span><span className="activity-text"><strong>{ticket.ticket_id}</strong><small>Игрок · {ticket.player_id}</small></span><StatusBadge status={ticket.status} /><time>{formatDate(ticket.created_at)}</time></Link>
          ))}</div> : <div className="compact-empty">Здесь появятся обращения по мере поступления.</div>}
        </article>
      </section>
    </>
  );
}