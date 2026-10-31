import { AlertTriangle, ArrowLeft, FileSearch, History, Play, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useToast } from "../components/AppShell";
import { ErrorState, LoadingState, PageHeading } from "../components/UI";
import { analyzeTicket, getTicket } from "../lib/api";
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
  const notify = useToast();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
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

  async function runAnalysis() {
    if (!ticket || analyzing) return;
    setAnalyzing(true);
    setError(null);
    try {
      await analyzeTicket(ticket.ticket_id);
      setTicket(await getTicket(ticket.ticket_id));
      notify("AI-анализ завершён. Проверьте выводы и источники.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось выполнить AI-анализ.");
    } finally {
      setAnalyzing(false);
    }
  }

  if (loading) return <LoadingState label="Загружаем результат анализа" />;
  if (error && !ticket) return <ErrorState message={error} />;
  if (!ticket) return <ErrorState message="Обращение не найдено." />;
  const result = ticket.ai_analysis;
  const humanReviewRequired = result?.human_review_required ?? result?.escalation_required ?? ticket.escalation_required;

  return (
    <>
      <Link className="back-link analysis-back" to="/analysis"><ArrowLeft size={15} /> К очереди анализа</Link>
      <PageHeading
        eyebrow={`ОБРАЩЕНИЕ ${ticket.ticket_id}`}
        title="Результат анализа"
        description={ticket.message}
        actions={<button className="button button-secondary" disabled={analyzing} onClick={() => void runAnalysis()} type="button"><Play size={14} /> {analyzing ? "Анализируем..." : result ? "Повторить анализ" : "Анализировать"}</button>}
      />
      {error && <ErrorState message={error} onRetry={() => void runAnalysis()} />}
      {!result ? (
        <div className="panel"><div className="table-empty"><div className="empty-icon"><Sparkles size={18} /></div><strong>Анализ ещё не запускался</strong><span>Запустите анализ, чтобы получить structured выводы и verified rule references.</span><Link className="button button-secondary" to={`/tickets/${encodeURIComponent(ticket.ticket_id)}`}>Открыть обращение</Link></div></div>
      ) : (
        <>
          <div className="analysis-summary-grid">
            <article className="summary-tile"><span className="summary-tile-icon"><Sparkles size={16} /></span><small>КАТЕГОРИЯ · ЯЗЫК · ПРИОРИТЕТ</small><strong>{result.category}</strong><p>{result.category_reason}</p><p>{result.language} · {result.priority || ticket.priority}</p><p>{result.summary}</p></article>
            <article className="summary-tile"><span className="summary-tile-icon"><ShieldCheck size={16} /></span><small>УВЕРЕННОСТЬ</small><strong>{Math.round(result.confidence * 100)}%</strong><p>Оценка модели. Решение принимает оператор.</p></article>
            <article className={`summary-tile${humanReviewRequired ? " tile-warning" : ""}`}><span className="summary-tile-icon">{humanReviewRequired ? <AlertTriangle size={16} /> : <ShieldCheck size={16} />}</span><small>РЕШЕНИЕ</small><strong>{humanReviewRequired ? "Требуется проверка" : "Проверить оператором"}</strong><p>{result.escalation_reasons?.join(" ") || result.escalation_reason || "Решение остаётся за оператором."}</p></article>
          </div>
          <div className="analysis-detail-layout">
            <div className="analysis-evidence-column">
              <article className="panel analysis-result-card">
                <div className="panel-header"><div className="panel-title"><FileSearch size={16} /><span>Извлечение и доказательства</span></div></div>
                <FactGroup title="Утверждения игрока" items={result.player_claims} />
                <FactGroup title="Предоставленные доказательства" items={(result.provided_evidence ?? result.attachments).map((file) => `${file.filename} · ${file.content_type} · ${file.size_bytes} bytes · content not inspected`)} tone="fact-amber" />
                <FactGroup title="Подтверждённые системные данные" items={result.verified_system_data} tone="fact-green" />
                <FactGroup title="Неизвестные сведения" items={result.unknowns} tone="fact-red" />
                <FactGroup title="Вопросы для уточнения" items={result.missing_information_questions ?? []} />
                {humanReviewRequired && <FactGroup title="Причины проверки оператором" items={result.escalation_reasons?.length ? result.escalation_reasons : result.escalation_reason ? [result.escalation_reason] : []} tone="fact-red" />}
              </article>
              <article className="panel analysis-result-card">
                <div className="panel-header"><div className="panel-title"><History size={16} /><span>История анализа</span></div></div>
                <div className="history-limitation"><History size={16} /><span>История действий оператора доступна в карточке обращения. Здесь указано время создания тикета.</span></div>
                <div className="analysis-current"><span className="timeline-point" /><span><strong>Обращение создано</strong><small>{formatDate(ticket.created_at)}</small></span></div>
              </article>
            </div>
            <aside className="panel analysis-rules-card">
              <div className="panel-header"><div className="panel-title"><FileSearch size={16} /><span>Knowledge retrieval</span></div></div>
              {result.matched_rules.length ? result.matched_rules.map((rule) => (
                <article className="retrieved-rule" key={`${rule.document_name}-${rule.rule_id}`}>
                  <div className="rule-kicker">{rule.document_name} · {rule.rule_id}</div><h3>{rule.rule_title}</h3><p>{rule.rule_text}</p>
                  <div className="rule-meta"><span>{rule.version_or_date || "Версия не указана"}</span><a href={rule.source_url} rel="noreferrer" target="_blank">Оригинальный источник <span>↗</span></a></div>
                </article>
              )) : <div className="compact-empty">Проверенные совпадающие правила не найдены. Цитаты не сгенерированы.</div>}
              <div className="retrieval-disclaimer">Показываются только retrieved rule references из активных версий источников.</div>
            </aside>
          </div>
        </>
      )}
    </>
  );
}
