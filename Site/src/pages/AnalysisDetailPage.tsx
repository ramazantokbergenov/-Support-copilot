import { ArrowLeft, AlertTriangle, FileSearch, History, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PageHeading, LoadingState, ErrorState } from "../components/UI";
import { getTicket } from "../lib/localWorkspace";
import { formatDate } from "../lib/format";
import type { TicketDetail } from "../types";

function FactGroup({ title, items, tone }: { title: string; items: string[]; tone?: string }) {
  return (
    <section className={`analysis-result-section${tone ? ` ${tone}` : ""}`}>
      <h3>{title}<span>{items.length}</span></h3>
      {items.length ? <ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="muted">Нет данных в результате анализа.</p>}
    </section>
  );
}

export function AnalysisDetailPage() {
  const { ticketId = "" } = useParams();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getTicket(ticketId, controller.signal).then(setTicket).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить результат.");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [ticketId]);

  if (loading) return <LoadingState label="Загружаем результат анализа" />;
  if (error || !ticket) return <ErrorState message={error ?? "Обращение не найдено."} />;
  const result = ticket.ai_analysis;

  return (
    <>
      <Link className="back-link analysis-back" to="/analysis"><ArrowLeft size={15} /> К очереди анализа</Link>
      <PageHeading eyebrow={`ОБРАЩЕНИЕ ${ticket.ticket_id}`} title="Результат анализа" description={ticket.message} />
      {!result ? (
        <div className="panel"><div className="table-empty"><div className="empty-icon"><Sparkles size={18} /></div><strong>AI-анализ отключён</strong><span>Подключите backend, чтобы запускать AI-анализ. Сейчас система не генерирует фиктивные результаты.</span><Link className="button button-primary" to={`/tickets/${encodeURIComponent(ticket.ticket_id)}`}>Открыть обращение</Link></div></div>
      ) : (
        <>
          <div className="analysis-summary-grid">
            <article className="summary-tile"><span className="summary-tile-icon"><Sparkles size={16} /></span><small>КАТЕГОРИЯ</small><strong>{result.category}</strong><p>{result.category_reason}</p></article>
            <article className="summary-tile"><span className="summary-tile-icon"><ShieldCheck size={16} /></span><small>УВЕРЕННОСТЬ</small><strong>{Math.round(result.confidence * 100)}%</strong><p>Эвристическая оценка, а не вероятность.</p></article>
            <article className={`summary-tile${result.escalation_required ? " tile-warning" : ""}`}><span className="summary-tile-icon">{result.escalation_required ? <AlertTriangle size={16} /> : <ShieldCheck size={16} />}</span><small>РЕКОМЕНДАЦИЯ</small><strong>{result.escalation_required ? "Эскалировать" : "Проверить оператором"}</strong><p>{result.escalation_reason || "Решение за оператором; автоматической отправки нет."}</p></article>
          </div>
          <div className="analysis-detail-layout">
            <div className="analysis-evidence-column">
              <article className="panel analysis-result-card">
                <div className="panel-header"><div className="panel-title"><FileSearch size={16} /><span>Извлечение и доказательства</span></div></div>
                <FactGroup title="Утверждения игрока" items={result.player_claims} />
                <FactGroup title="Данные из вложений" items={result.attachments.map((file) => `${file.filename} · ${file.inspected ? "содержимое проверено" : "содержимое не изучено"}`)} tone="fact-amber" />
                <FactGroup title="Подтверждённые системные данные" items={result.verified_system_data} tone="fact-green" />
                <FactGroup title="Неизвестные сведения" items={result.unknowns} tone="fact-red" />
              </article>
              <article className="panel analysis-result-card">
                <div className="panel-header"><div className="panel-title"><History size={16} /><span>История анализа</span></div></div>
                <div className="history-limitation"><History size={16} /><span>API хранит текущий результат, но не предоставляет историю запусков или время анализа. Здесь показана последняя сохранённая версия без выдуманной хронологии.</span></div>
                <div className="analysis-current"><span className="timeline-point" /><span><strong>Обращение создано</strong><small>{formatDate(ticket.created_at)}</small></span></div>
              </article>
            </div>
            <aside className="panel analysis-rules-card">
              <div className="panel-header"><div className="panel-title"><FileSearch size={16} /><span>Knowledge retrieval</span></div></div>
              {result.matched_rules.length ? result.matched_rules.map((rule) => (
                <article className="retrieved-rule" key={`${rule.document_name}-${rule.rule_id}`}>
                  <div className="rule-kicker">{rule.document_name} · {rule.rule_id}</div><h3>{rule.rule_title}</h3><p>{rule.rule_text}</p>
                  <div className="rule-meta"><span>{rule.version_or_date || "Версия не указана"}</span><a href={rule.source_url} rel="noreferrer" target="_blank">Источник <span>↗</span></a></div>
                </article>
              )) : <div className="compact-empty">Проверенные совпадающие правила не найдены.</div>}
              <div className="retrieval-disclaimer">Правила загружаются из базы проекта. Не добавляйте неподтверждённые материалы.</div>
            </aside>
          </div>
        </>
      )}
    </>
  );
}
