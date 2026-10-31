import { ArrowDownWideNarrow, ChevronLeft, ChevronRight, Filter, RotateCw, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { TicketTable } from "../components/TicketTable";
import { ErrorState, LoadingState, PageHeading } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";
import { listTickets } from "../lib/api";
import type { TicketPriority, TicketStatus, TicketSummary } from "../types";

const PAGE_SIZE = 50;

export function TicketsPage() {
  const { tickets: workspaceTickets } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [priority, setPriority] = useState(params.get("priority") ?? "");
  const [category, setCategory] = useState(params.get("category") ?? "");
  const [sort, setSort] = useState("newest");
  const [offset, setOffset] = useState(0);
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setQuery(params.get("q") ?? "");
    setStatus(params.get("status") ?? "");
    setPriority(params.get("priority") ?? "");
    setCategory(params.get("category") ?? "");
  }, [params]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void listTickets({
        q: query.trim(),
        status: status as TicketStatus | "",
        priority: priority as TicketPriority | "",
        category,
        limit: PAGE_SIZE,
        offset,
      }, controller.signal).then((response) => {
        setTickets(response.items);
        setCount(response.count);
      }).catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить очередь.");
      }).finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    }, 220);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, status, priority, category, offset, reload]);

  const categories = [...new Set(workspaceTickets.map((ticket) => ticket.category).filter((value): value is string => Boolean(value)))].sort();
  const filtered = useMemo(() => {
    return [...tickets].sort((a, b) =>
        sort === "oldest"
          ? Date.parse(a.created_at) - Date.parse(b.created_at)
          : Date.parse(b.created_at) - Date.parse(a.created_at),
      );
  }, [tickets, sort]);

  function updateParams(next: Record<string, string>) {
    const updated = new URLSearchParams(params);
    Object.entries(next).forEach(([key, value]) => {
      if (value) updated.set(key, value);
      else updated.delete(key);
    });
    setParams(updated, { replace: true });
  }

  function reset() {
    setQuery("");
    setStatus("");
    setPriority("");
    setCategory("");
    setOffset(0);
    setParams({});
  }

  function updateFilterParams(next: Record<string, string>) {
    setOffset(0);
    updateParams(next);
  }

  return (
    <>
      <PageHeading eyebrow="ОЧЕРЕДЬ ПОДДЕРЖКИ" title="Обращения" description="Поиск, фильтрация и управление обращениями игроков." actions={<button className="button button-secondary" disabled={loading} onClick={() => setReload((value) => value + 1)} type="button"><RotateCw size={15} /> Обновить</button>} />
      <section className="panel ticket-workspace">
        <div className="ticket-toolbar">
          <label className="filter-search">
            <Search size={16} />
            <input onChange={(event) => { setQuery(event.target.value); updateFilterParams({ q: event.target.value }); }} placeholder="Поиск по ID, игроку или категории" value={query} />
          </label>
          <div className="filters">
            <label className="filter-control"><Filter size={14} /><select aria-label="Фильтр по статусу" onChange={(event) => { setStatus(event.target.value); updateFilterParams({ status: event.target.value }); }} value={status}><option value="">Все статусы</option><option value="New">Новое</option><option value="Processing">В работе</option><option value="Needs Review">На проверке</option><option value="Escalated">Эскалация</option><option value="Approved">Одобрено</option><option value="Closed">Закрыто</option></select></label>
            <label className="filter-control"><select aria-label="Фильтр по приоритету" onChange={(event) => { setPriority(event.target.value); updateFilterParams({ priority: event.target.value }); }} value={priority}><option value="">Все приоритеты</option><option value="Low">Низкий</option><option value="Normal">Обычный</option><option value="High">Высокий</option><option value="Urgent">Срочный</option></select></label>
            <label className="filter-control"><select aria-label="Фильтр по категории" onChange={(event) => { setCategory(event.target.value); updateFilterParams({ category: event.target.value }); }} value={category}><option value="">Все категории</option>{categories.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="filter-control"><ArrowDownWideNarrow size={14} /><select aria-label="Сортировка" onChange={(event) => setSort(event.target.value)} value={sort}><option value="newest">Сначала новые</option><option value="oldest">Сначала старые</option></select></label>
            {(query || status || priority || category) && <button className="filter-reset" onClick={reset} type="button"><X size={14} /> Сбросить</button>}
          </div>
        </div>
        <div className="table-caption"><span>{loading ? "Обновление..." : `Обращений: ${count}`}</span><span>Backend · страница {Math.floor(offset / PAGE_SIZE) + 1}</span></div>
        {error ? <ErrorState message={error} onRetry={() => setReload((value) => value + 1)} /> : loading && tickets.length === 0 ? <LoadingState label="Загружаем очередь" /> : <>
          <TicketTable emptyTitle={count ? "На этой странице нет обращений" : "Очередь пока пуста"} emptyDescription={count ? "Перейдите на предыдущую страницу или измените фильтры." : "Создайте первое обращение, чтобы начать работу."} tickets={filtered} />
          {count > PAGE_SIZE && <div className="list-panel-toolbar"><span className="muted">{offset + 1}–{Math.min(offset + PAGE_SIZE, count)} из {count}</span><div className="heading-actions"><button className="button button-secondary" disabled={offset === 0 || loading} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))} type="button"><ChevronLeft size={14} /> Назад</button><button className="button button-secondary" disabled={offset + PAGE_SIZE >= count || loading} onClick={() => setOffset((value) => value + PAGE_SIZE)} type="button">Далее <ChevronRight size={14} /></button></div></div>}
        </>}
      </section>
    </>
  );
}
