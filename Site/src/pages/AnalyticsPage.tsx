import { AlertTriangle, BarChart3, Inbox, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState, MetricCard, PageHeading } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";
import { isEscalated } from "../lib/format";

type Period = "7" | "30" | "90" | "all";

function dayKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function monthKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function weekStart(date: Date) {
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  return start;
}

export function AnalyticsPage() {
  const { tickets, loading, error, refresh } = useWorkspace();
  const [period, setPeriod] = useState<Period>("30");
  const range = useMemo(() => {
    if (period === "all") return tickets;
    const earliest = new Date();
    earliest.setHours(0, 0, 0, 0);
    earliest.setDate(earliest.getDate() - Number(period) + 1);
    return tickets.filter((ticket) => new Date(ticket.created_at) >= earliest);
  }, [tickets, period]);
  const categoryCounts = new Map<string, number>();
  const statusCounts = new Map<string, number>();
  range.forEach((ticket) => {
    const category = ticket.category || "Не определена";
    categoryCounts.set(category, (categoryCounts.get(category) ?? 0) + 1);
    statusCounts.set(ticket.status, (statusCounts.get(ticket.status) ?? 0) + 1);
  });
  const categoryRows = [...categoryCounts.entries()].sort((a, b) => b[1] - a[1]);
  const escalated = range.filter((ticket) => isEscalated(ticket.status, ticket.escalation_required)).length;
  const series = useMemo(() => {
    if (period === "all" && tickets.length === 0) return [];
    if (period === "all") {
      const firstDate = new Date(Math.min(...tickets.map((ticket) => Date.parse(ticket.created_at))));
      const cursor = new Date(firstDate.getFullYear(), firstDate.getMonth(), 1);
      const end = new Date();
      const buckets = new Map<string, number>();
      while (cursor <= end) {
        buckets.set(monthKey(cursor), 0);
        cursor.setMonth(cursor.getMonth() + 1);
      }
      range.forEach((ticket) => {
        const key = monthKey(new Date(ticket.created_at));
        if (buckets.has(key)) buckets.set(key, (buckets.get(key) ?? 0) + 1);
      });
      return [...buckets.entries()];
    }

    if (period === "90") {
      const today = new Date();
      const firstWeek = weekStart(today);
      firstWeek.setDate(firstWeek.getDate() - 12 * 7);
      const buckets = new Map<string, number>();
      for (let week = 0; week < 13; week += 1) {
        const start = new Date(firstWeek);
        start.setDate(start.getDate() + week * 7);
        buckets.set(dayKey(start), 0);
      }
      range.forEach((ticket) => {
        const key = dayKey(weekStart(new Date(ticket.created_at)));
        if (buckets.has(key)) buckets.set(key, (buckets.get(key) ?? 0) + 1);
      });
      return [...buckets.entries()];
    }

    const days = period === "7" ? 7 : 30;
    const counts = new Map<string, number>();
    for (let offset = days - 1; offset >= 0; offset--) {
      const date = new Date();
      date.setHours(0, 0, 0, 0);
      date.setDate(date.getDate() - offset);
      counts.set(dayKey(date), 0);
    }
    range.forEach((ticket) => {
      const key = dayKey(new Date(ticket.created_at));
      if (counts.has(key)) counts.set(key, (counts.get(key) ?? 0) + 1);
    });
    return [...counts.entries()];
  }, [range, period, tickets]);
  const peak = Math.max(1, ...series.map(([, count]) => count));

  return (
    <>
      <PageHeading eyebrow="ОПЕРАЦИОННЫЕ ДАННЫЕ" title="Analytics" description="Показатели рассчитаны по обращениям, сохранённым в этом браузере." actions={<label className="period-control"><span>Период</span><select onChange={(event) => setPeriod(event.target.value as Period)} value={period}><option value="7">Последние 7 дней</option><option value="30">Последние 30 дней</option><option value="90">Последние 90 дней</option><option value="all">За всё время</option></select></label>} />
      {loading ? <section className="panel analytics-empty"><LoadingState label="Загружаем данные аналитики" /></section> : error ? (
        <ErrorState message={error} onRetry={() => void refresh()} />
      ) : tickets.length === 0 ? (
        <section className="panel analytics-empty"><EmptyState icon="chart" title="Недостаточно данных" description="После поступления обращений здесь появятся реальные показатели и распределения. Выдуманные графики не используются." /></section>
      ) : (
        <>
          <section aria-label="Показатели за выбранный период" className="metric-grid analytics-metrics">
            <MetricCard accent detail={periodLabel(period)} icon={Inbox} label="Обращения" value={range.length} />
            <MetricCard detail="Созданы в выбранном периоде" icon={AlertTriangle} label="Эскалации" value={escalated} />
            <MetricCard detail="Текущая очередь" icon={BarChart3} label="В работе" value={statusCounts.get("Processing") ?? 0} />
            <MetricCard detail="Текущий локальный статус" icon={ShieldAlert} label="На проверке" value={statusCounts.get("Needs Review") ?? 0} />
          </section>
          <div className="analytics-grid">
            <section className="panel chart-panel">
              <div className="panel-header"><div><h2>Поступление обращений</h2><span>По дате создания</span></div><span className="chart-total">{range.length}</span></div>
              {series.some(([, count]) => count > 0) ? (
                <div className={`bar-chart ${series.length > 10 ? "dense-chart" : ""}`} role="img" aria-label="Количество обращений по дням">
                  {series.map(([date, count]) => <div className="bar-column" key={date} title={`${date}: ${count}`}><span className="bar-count">{count || ""}</span><div className="bar-rail"><i style={{ height: `${Math.max(count ? 8 : 0, (count / peak) * 100)}%` }} /></div><small>{new Date(`${date}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</small></div>)}
                </div>
              ) : <div className="chart-empty">За этот период новых обращений не поступало.</div>}
            </section>
            <section className="panel category-chart">
              <div className="panel-header"><div><h2>Категории</h2><span>По количеству обращений</span></div></div>
              {categoryRows.length ? <div className="category-list analytics-category-list">{categoryRows.map(([name, count]) => <div className="category-row" key={name}><span className="category-name">{name}</span><span className="category-count">{count}</span><span className="category-track"><i style={{ width: `${Math.max(4, (count / range.length) * 100)}%` }} /></span></div>)}</div> : <div className="chart-empty">Категории для периода не указаны.</div>}
            </section>
          </div>
          <section className="panel analytics-table">
            <div className="panel-header"><div><h2>Сводка по статусам</h2><span>Текущие статусы, не журнал переходов</span></div></div>
            <div className="status-summary-table">{[...statusCounts.entries()].map(([status, count]) => <div key={status}><span>{status}</span><strong>{count}</strong><span>{range.length ? `${Math.round((count / range.length) * 100)}% от выборки` : ""}</span></div>)}</div>
          </section>
          <p className="data-scope-note">Выборка: {range.length} обращений · период: {period === "all" ? "за всё время" : `последние ${period} дней`}.</p>
        </>
      )}
    </>
  );
}

function periodLabel(period: Period) {
  return period === "all" ? "За всё время" : `За ${period} дней`;
}
