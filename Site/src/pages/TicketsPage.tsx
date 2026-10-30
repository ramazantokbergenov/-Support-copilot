import { ArrowDownWideNarrow, Filter, RotateCw, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { TicketTable } from "../components/TicketTable";
import { ErrorState, LoadingState, PageHeading } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";

export function TicketsPage() {
  const { tickets, loading, error, refresh } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [priority, setPriority] = useState(params.get("priority") ?? "");
  const [category, setCategory] = useState(params.get("category") ?? "");
  const [sort, setSort] = useState("newest");

  useEffect(() => {
    setQuery(params.get("q") ?? "");
    setStatus(params.get("status") ?? "");
    setPriority(params.get("priority") ?? "");
    setCategory(params.get("category") ?? "");
  }, [params]);

  const categories = [...new Set(tickets.map((ticket) => ticket.category).filter((value): value is string => Boolean(value)))].sort();
  if (loading && tickets.length === 0) {
    return <><PageHeading eyebrow="ОЧЕРЕДЬ ПОДДЕРЖКИ" title="Обращения" description="Загружаем локальные обращения." /><section className="panel"><LoadingState label="Загружаем очередь" /></section></>;
  }
  if (error && tickets.length === 0) {
    return <><PageHeading eyebrow="ОЧЕРЕДЬ ПОДДЕРЖКИ" title="Обращения" description="Поиск, фильтрация и управление обращениями игроков." /><ErrorState message={error} onRetry={() => void refresh()} /></>;
  }
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return tickets
      .filter((ticket) => {
        const searchable = `${ticket.ticket_id} ${ticket.player_id} ${ticket.category ?? ""}`.toLocaleLowerCase();
        return (
          (!normalized || searchable.includes(normalized)) &&
          (!status || ticket.status === status) &&
          (!priority || ticket.priority === priority) &&
          (!category || ticket.category === category)
        );
      })
      .sort((a, b) =>
        sort === "oldest"
          ? Date.parse(a.created_at) - Date.parse(b.created_at)
          : Date.parse(b.created_at) - Date.parse(a.created_at),
      );
  }, [tickets, query, status, priority, category, sort]);

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
    setParams({});
  }

  return (
    <>
      <PageHeading eyebrow="ОЧЕРЕДЬ ПОДДЕРЖКИ" title="Обращения" description="Поиск, фильтрация и управление обращениями игроков." actions={<button className="button button-secondary" onClick={() => void refresh()} type="button"><RotateCw size={15} /> Обновить</button>} />
      <section className="panel ticket-workspace">
        <div className="ticket-toolbar">
          <label className="filter-search">
            <Search size={16} />
            <input onChange={(event) => { setQuery(event.target.value); updateParams({ q: event.target.value }); }} placeholder="Поиск по ID, игроку или категории" value={query} />
          </label>
          <div className="filters">
            <label className="filter-control"><Filter size={14} /><select aria-label="Фильтр по статусу" onChange={(event) => { setStatus(event.target.value); updateParams({ status: event.target.value }); }} value={status}><option value="">Все статусы</option><option value="New">Новое</option><option value="Processing">В работе</option><option value="Needs Review">На проверке</option><option value="Escalated">Эскалация</option><option value="Approved">Одобрено</option><option value="Closed">Закрыто</option></select></label>
            <label className="filter-control"><select aria-label="Фильтр по приоритету" onChange={(event) => { setPriority(event.target.value); updateParams({ priority: event.target.value }); }} value={priority}><option value="">Все приоритеты</option><option value="Low">Низкий</option><option value="Normal">Обычный</option><option value="High">Высокий</option><option value="Urgent">Срочный</option></select></label>
            <label className="filter-control"><select aria-label="Фильтр по категории" onChange={(event) => { setCategory(event.target.value); updateParams({ category: event.target.value }); }} value={category}><option value="">Все категории</option>{categories.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
            <label className="filter-control"><ArrowDownWideNarrow size={14} /><select aria-label="Сортировка" onChange={(event) => setSort(event.target.value)} value={sort}><option value="newest">Сначала новые</option><option value="oldest">Сначала старые</option></select></label>
            {(query || status || priority || category) && <button className="filter-reset" onClick={reset} type="button"><X size={14} /> Сбросить</button>}
          </div>
        </div>
        <div className="table-caption"><span>{loading ? "Обновление..." : `Обращений: ${filtered.length}`}</span><span>Локальные данные · без демо-обращений</span></div>
        {error ? <div className="inline-error padded-error" role="alert">{error}<button className="text-button" onClick={() => void refresh()} type="button">Повторить</button></div> : null}
        <TicketTable emptyTitle={tickets.length ? "Ничего не найдено" : "Очередь пока пуста"} emptyDescription={tickets.length ? "Измените запрос или сбросьте фильтры." : "Создайте первое обращение, чтобы начать работу."} tickets={filtered} />
      </section>
    </>
  );
}
