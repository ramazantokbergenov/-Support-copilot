import { AlertTriangle, Check, Clipboard, FileText, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useToast } from "../components/AppShell";
import { ErrorState, LoadingState, PageHeading, StatusBadge } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";
import { getTicket } from "../lib/localWorkspace";
import { formatDate } from "../lib/format";
import type { TicketDetail } from "../types";

function localKey(ticketId: string) {
  return `sc-draft:${ticketId}`;
}

export function DraftsPage() {
  const { tickets, loading: ticketsLoading, error: ticketsError, refresh } = useWorkspace();
  const notify = useToast();
  const candidates = useMemo(() => [...tickets], [tickets]);
  const [selectedId, setSelectedId] = useState("");
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [reviewed, setReviewed] = useState(false);

  useEffect(() => {
    if (!selectedId && candidates[0]) setSelectedId(candidates[0].ticket_id);
    if (selectedId && !candidates.some((item) => item.ticket_id === selectedId)) {
      setSelectedId(candidates[0]?.ticket_id ?? "");
    }
  }, [candidates, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setTicket(null);
      setDraft("");
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getTicket(selectedId, controller.signal).then((value) => {
      setTicket(value);
      let localDraft = "";
      let localReviewed = false;
      try {
        localDraft = window.localStorage.getItem(localKey(selectedId)) ?? "";
        localReviewed = window.localStorage.getItem(`sc-reviewed:${selectedId}`) === "true";
      } catch {
        setError("Локальное хранилище недоступно; черновик нельзя загрузить с этого устройства.");
      }
      setDraft(localDraft || value.draft_reply || "");
      setReviewed(localReviewed);
      setSaved(Boolean(localDraft));
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить черновик.");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [selectedId]);

  async function copyDraft() {
    try {
      await navigator.clipboard.writeText(draft);
      notify("Черновик скопирован.");
    } catch {
      notify("Браузер не разрешил доступ к буферу обмена.", "error");
    }
  }

  function saveDraft() {
    if (!ticket) return;
    try {
      window.localStorage.setItem(localKey(ticket.ticket_id), draft);
      setSaved(true);
      notify("Черновик сохранён в этом браузере.");
    } catch {
      notify("Не удалось сохранить черновик в локальном хранилище.", "error");
    }
  }

  function toggleReviewed() {
    if (!ticket) return;
    const next = !reviewed;
    try {
      window.localStorage.setItem(`sc-reviewed:${ticket.ticket_id}`, String(next));
      setReviewed(next);
      notify(next ? "Отметка сохранена локально." : "Отметка снята.");
    } catch {
      notify("Не удалось сохранить отметку проверки.", "error");
    }
  }

  return (
    <>
      <PageHeading eyebrow="ОТВЕТЫ ДЛЯ ПРОВЕРКИ" title="Response Drafts" description="Редактируйте и проверяйте черновики перед ручной отправкой игроку." />
      {ticketsLoading && candidates.length === 0 ? <section className="panel"><LoadingState label="Загружаем черновики" /></section> : ticketsError && candidates.length === 0 ? <ErrorState message={ticketsError} onRetry={() => void refresh()} /> : candidates.length === 0 ? (
        <div className="panel"><div className="table-empty"><div className="empty-icon"><FileText size={18} /></div><strong>Черновиков пока нет</strong><span>Создайте черновик вручную для обращения. AI-генерация и отправка ответа отключены.</span><Link className="button button-secondary" to="/tickets">К обращениям</Link></div></div>
      ) : (
        <div className="drafts-layout">
          <aside className="panel draft-list-panel">
            <div className="panel-header"><div className="panel-title"><FileText size={16} /><span>Черновики</span></div><span className="title-count">{candidates.length}</span></div>
            <div className="draft-ticket-list">
              {candidates.map((item) => (
                <button className={`draft-ticket${selectedId === item.ticket_id ? " selected" : ""}`} key={item.ticket_id} onClick={() => setSelectedId(item.ticket_id)} type="button">
                  <span><strong>{item.ticket_id}</strong><small>Игрок · {item.player_id}</small><small>{formatDate(item.created_at)}</small></span><StatusBadge status={item.status} />
                </button>
              ))}
            </div>
          </aside>
          <section className="panel draft-editor-panel">
            {!ticket ? <div className="table-empty"><strong>{loading ? "Загрузка..." : "Выберите обращение"}</strong></div> : (
              <>
                <div className="panel-header draft-editor-head">
                  <div><div className="panel-title"><span>Черновик ответа</span></div><span className="draft-subtitle">#{ticket.ticket_id} · Игрок {ticket.player_id}</span></div>
                  {reviewed ? <span className="reviewed-badge"><Check size={14} /> Проверено</span> : <span className="badge badge-neutral">Ожидает проверки</span>}
                </div>
                <div className="draft-editor-content">
                  {error && <ErrorState message={error} />}
                  <div className="draft-meta-grid">
                    <div><span>Язык ответа</span><strong>{ticket.ai_analysis?.language || "Не определён анализом"}</strong></div>
                    <div><span>Основание</span><strong>{ticket.ai_analysis?.summary || "Сводка анализа недоступна"}</strong></div>
                    <div><span>Источник текста</span><strong>{ticket.draft_reply ? "Черновик обращения" : draft ? "Черновик оператора" : "Не сформирован"}</strong></div>
                  </div>
                  <div className="draft-rationale">
                    <div><span className="micro-label">ПРОВЕРЕННЫЕ ОСНОВАНИЯ</span><ul>{ticket.ai_analysis?.verified_system_data?.length ? ticket.ai_analysis.verified_system_data.map((item, index) => <li key={`${item}-${index}`}>{item}</li>) : <li className="muted">Подтверждённые системные данные отсутствуют.</li>}</ul></div>
                    <div><span className="micro-label">ПРАВИЛА</span>{ticket.matched_rules.length ? ticket.matched_rules.map((rule) => <a href={rule.source_url} key={`${rule.document_name}-${rule.rule_id}`} rel="noreferrer" target="_blank">{rule.rule_id} · {rule.document_name}</a>) : <p className="muted">Ссылки на правила не найдены.</p>}</div>
                  </div>
                  {ticket.ai_analysis?.unknowns?.length ? <div className="draft-warning"><AlertTriangle size={15} /><span><strong>Есть неподтверждённые сведения.</strong> Не представляйте их как установленные факты: {ticket.ai_analysis.unknowns.join(" ")}</span></div> : null}
                  {ticket.ai_analysis?.escalation_required && <div className="draft-warning"><AlertTriangle size={15} /><span><strong>Рекомендуется эскалация.</strong> {ticket.ai_analysis.escalation_reason || "Причина не указана."}</span></div>}
                  <label className="field-label draft-text-label">Текст ответа<textarea aria-label="Редактор текста ответа" onChange={(event) => { setDraft(event.target.value); setSaved(false); }} placeholder="Черновик ещё не сформирован. Запустите AI-анализ для обращения." rows={10} value={draft} /></label>
                  <div className="draft-save-state">{saved ? <><Check size={13} /> Сохранено локально</> : <><Save size={13} /> Изменения не сохранены</>}<span>Локально · backend не поддерживает сохранение черновика</span></div>
                  <div className="draft-actions">
                    <button className="button button-secondary" disabled={!draft} onClick={() => void copyDraft()} type="button"><Clipboard size={14} /> Копировать</button>
                    <button className="button button-secondary" disabled={!draft} onClick={saveDraft} type="button"><Save size={14} /> Сохранить изменения</button>
                    <button className={`button ${reviewed ? "button-secondary" : "button-primary"}`} onClick={toggleReviewed} type="button">{reviewed ? <Check size={14} /> : <Check size={14} />}{reviewed ? "Снять проверку" : "Отметить проверенным"}</button>
                  </div>
                  <p className="send-warning">Черновик и отметка проверки сохраняются только в этом браузере. AI-генерация и отправка ответа отключены.</p>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
