import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Check,
  Download,
  FileImage,
  FileText,
  MessageSquareText,
  Play,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorState, LoadingState, PriorityBadge, StatusBadge } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";
import { attachmentUrl, getAttachment, getTicket, updateTicketStatus } from "../lib/localWorkspace";
import { formatBytes, formatDate } from "../lib/format";
import { useToast } from "../components/AppShell";
import type { AiAnalysis, TicketAttachment, TicketDetail, TicketStatus } from "../types";

const statuses: TicketStatus[] = ["New", "Processing", "Needs Review", "Approved", "Escalated", "Closed"];

function FactList({ items, empty }: { items: string[]; empty: string }) {
  return items.length ? (
    <ul className="fact-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
  ) : <p className="muted small-copy">{empty}</p>;
}

function AnalysisPanel({
  ticket,
}: {
  ticket: TicketDetail;
}) {
  const result = ticket.ai_analysis;
  return (
    <aside className="panel detail-panel detail-analysis">
      <div className="panel-header">
        <div className="panel-title"><Sparkles size={16} /><span>AI Analysis</span></div>
        <span className="ai-chip">OFFLINE</span>
      </div>
      {!result ? (
        <div className="analysis-empty">
          <div className="empty-icon"><Sparkles size={18} /></div>
          <strong>AI-анализ отключён</strong>
          <p>Без backend анализ не запускается. Подключите его, чтобы получить результат; демонстрационные выводы не создаются.</p>
          <button className="button button-secondary button-wide" disabled type="button">
            <Play size={14} /> Недоступно офлайн
          </button>
        </div>
      ) : (
        <AnalysisContent result={result} ticket={ticket} />
      )}
    </aside>
  );
}

function AnalysisContent({ result, ticket }: { result: AiAnalysis; ticket: TicketDetail }) {
  const rules = result.matched_rules?.length ? result.matched_rules : ticket.matched_rules;
  return (
    <div className="analysis-content">
      <div className="confidence-card">
        <div><span className="micro-label">УВЕРЕННОСТЬ АНАЛИЗА</span><strong>{Math.round(result.confidence * 100)}%</strong></div>
        <div className="confidence-track"><i style={{ width: `${Math.round(result.confidence * 100)}%` }} /></div>
        <p>Эвристическая оценка, не вероятность. Проверьте выводы вручную.</p>
      </div>
      <div className="analysis-section">
        <span className="micro-label">КЛАССИФИКАЦИЯ</span>
        <div className="classification">{result.category}</div>
        <p>{result.category_reason}</p>
      </div>
      <div className="analysis-section">
        <span className="micro-label">УТВЕРЖДЕНИЯ ИГРОКА</span>
        <FactList empty="Утверждения не извлечены." items={result.player_claims ?? []} />
      </div>
      <div className="analysis-section evidence-unknown">
        <span className="micro-label">НЕИЗВЕСТНЫЕ ФАКТЫ</span>
        <FactList empty="Неизвестные сведения не указаны." items={result.unknowns ?? []} />
      </div>
      <div className="analysis-section">
        <span className="micro-label">ДАННЫЕ ИЗ ВЛОЖЕНИЙ</span>
        {result.attachments?.length ? result.attachments.map((file) => (
          <div className="evidence-file" key={file.attachment_id}>
            <FileText size={14} /><span>{file.filename}</span>
            <strong>{file.inspected ? "проверено" : "не изучено"}</strong>
          </div>
        )) : <p className="muted small-copy">Нет данных о вложениях.</p>}
      </div>
      <div className="analysis-section evidence-verified">
        <span className="micro-label">ПОДТВЕРЖДЁННЫЕ ДАННЫЕ</span>
        <FactList empty="Подтверждённые системные данные отсутствуют." items={result.verified_system_data ?? []} />
      </div>
      <div className="analysis-section">
        <span className="micro-label">ПРАВИЛА GRAND MOBILE</span>
        {rules.length ? rules.map((rule) => (
          <a className="matched-rule" href={rule.source_url} key={`${rule.document_name}-${rule.rule_id}`} rel="noreferrer" target="_blank">
            <span><strong>{rule.rule_id}</strong><small>{rule.document_name} · {rule.rule_title}</small></span><ArrowUpRight size={14} />
          </a>
        )) : <p className="muted small-copy">Совпадений в загруженной базе нет.</p>}
      </div>
      {result.escalation_required && (
        <div className="escalation-warning">
          <AlertTriangle size={15} /><div><strong>Рекомендуется эскалация</strong><p>{result.escalation_reason || "Причина не указана."}</p></div>
        </div>
      )}
    </div>
  );
}

export function TicketDetailPage() {
  const { ticketId = "" } = useParams();
  const { refresh } = useWorkspace();
  const notify = useToast();
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingStatus, setSavingStatus] = useState(false);
  const [note, setNote] = useState("");
  const [previewAttachment, setPreviewAttachment] = useState<TicketAttachment | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getTicket(ticketId, controller.signal)
      .then(setTicket)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить обращение.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [ticketId]);

  useEffect(() => {
    try {
      setNote(window.localStorage.getItem(`sc-note:${ticketId}`) ?? "");
    } catch {
      setNote("");
    }
  }, [ticketId]);

  async function changeStatus(status: TicketStatus) {
    if (!ticket) return;
    setSavingStatus(true);
    try {
      await updateTicketStatus(ticket.ticket_id, status);
      setTicket({ ...ticket, status });
      await refresh();
      notify("Статус обращения обновлён.");
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "Не удалось изменить статус.", "error");
    } finally {
      setSavingStatus(false);
    }
  }

  function saveNote() {
    try {
      window.localStorage.setItem(`sc-note:${ticketId}`, note);
      notify("Заметка сохранена только в этом браузере.");
    } catch {
      notify("Не удалось сохранить заметку в локальном хранилище.", "error");
    }
  }

  function closePreview() {
    setPreviewAttachment(null);
  }

  if (loading) return <LoadingState label="Загружаем обращение" />;
  if (error || !ticket) return <ErrorState message={error ?? "Обращение не найдено."} />;

  return (
    <>
      <div className="detail-topline">
        <Link className="back-link" to="/tickets"><ArrowLeft size={15} /> К обращениям</Link>
        <div className="detail-toolbar">
          <span className="ticket-number">#{ticket.ticket_id}</span>
          <StatusBadge status={ticket.status} />
          <PriorityBadge priority={ticket.priority} />
          <label className="status-select">
            <span className="sr-only">Изменить статус обращения</span>
            <select disabled={savingStatus} onChange={(event) => void changeStatus(event.target.value as TicketStatus)} value={ticket.status}>
              {statuses.map((status) => <option key={status} value={status}>{status}</option>)}
            </select>
          </label>
        </div>
      </div>
      <div className="ticket-detail-grid">
        <aside className="panel detail-panel detail-sidebar">
          <div className="panel-header"><div className="panel-title"><span>Сведения</span></div></div>
          <div className="detail-info">
            <div className="player-card">
              <span className="player-avatar">{ticket.player_id.slice(0, 2).toUpperCase()}</span>
              <div><strong>Игрок</strong><span>{ticket.player_id}</span></div>
            </div>
            <div className="info-item"><span>Категория</span><strong>{ticket.category || "Не определена"}</strong></div>
            <div className="info-item"><span>Приоритет</span><PriorityBadge priority={ticket.priority} /></div>
            <div className="info-item"><span>Создано</span><strong>{formatDate(ticket.created_at)}</strong></div>
            <div className="info-item"><span>Ответственный</span><strong className="muted">Назначение недоступно</strong></div>
          </div>
          <div className="detail-section-block">
            <div className="subsection-title">Хронология</div>
            <div className="timeline">
              <span className="timeline-point" />
              <div><strong>Обращение создано</strong><small>{formatDate(ticket.created_at)}</small></div>
            </div>
            <p className="integration-note">Журнал последующих изменений пока не предоставляется API.</p>
          </div>
          {ticket.escalation_required && (
            <div className="risk-card"><AlertTriangle size={15} /><div><strong>Нужна проверка</strong><span>{ticket.escalation_reason || "Причина не указана."}</span></div></div>
          )}
        </aside>

        <section className="panel detail-panel detail-conversation">
          <div className="panel-header">
            <div className="panel-title"><MessageSquareText size={16} /><span>Переписка</span></div>
            <span className="message-date">{formatDate(ticket.created_at)}</span>
          </div>
          <div className="conversation-body">
            <div className="message-header"><span className="player-avatar message-avatar">{ticket.player_id.slice(0, 2).toUpperCase()}</span><div><strong>{ticket.player_id}</strong><small>Игрок · входящее сообщение</small></div><time>{formatDate(ticket.created_at)}</time></div>
            <div className="player-message">{ticket.message}</div>
            {ticket.attachments.length > 0 && (
              <div className="attachment-section">
                <div className="subsection-title">Вложения · {ticket.attachments.length}</div>
                <div className="attachment-list">{ticket.attachments.map((attachment) => (
                  <button className="attachment-item attachment-button" key={attachment.attachment_id} onClick={() => setPreviewAttachment(attachment)} type="button">
                    <span className="attachment-icon">{attachment.content_type.startsWith("image/") ? <FileImage size={16} /> : <FileText size={16} />}</span>
                    <span className="attachment-copy"><strong>{attachment.filename}</strong><small>{formatBytes(attachment.size_bytes)} · {attachment.content_type}</small></span>
                    <ArrowUpRight size={14} />
                  </button>
                ))}</div>
                <p className="integration-note">Изображения, PDF и текст открываются в окне предпросмотра; остальные форматы можно скачать.</p>
              </div>
            )}
          </div>
          <div className="note-composer">
            <div className="composer-heading"><span><ShieldCheck size={14} /> Внутренняя заметка</span><span>Только в этом браузере</span></div>
            <textarea aria-label="Внутренняя заметка" onChange={(event) => setNote(event.target.value)} placeholder="Добавьте заметку для себя..." rows={3} value={note} />
            <div className="composer-actions"><span>Не отправляется игроку</span><button className="button button-secondary" onClick={saveNote} type="button"><Check size={14} /> Сохранить заметку</button></div>
          </div>
        </section>

        <AnalysisPanel ticket={ticket} />
      </div>
      {previewAttachment && (
        <AttachmentPreview
          attachment={previewAttachment}
          onClose={closePreview}
          ticketId={ticket.ticket_id}
        />
      )}
    </>
  );
}

function AttachmentPreview({
  attachment,
  ticketId,
  onClose,
}: {
  attachment: TicketAttachment;
  ticketId: string;
  onClose: () => void;
}) {
  const [preview, setPreview] = useState<{ kind: "image" | "pdf"; url: string } | { kind: "text"; text: string } | { kind: "unsupported" } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const url = attachmentUrl(ticketId, attachment.attachment_id);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setLoading(true);
    setError(null);
    setPreview(null);
    getAttachment(url, controller.signal).then(async (blob) => {
      if (attachment.content_type.startsWith("image/")) {
        objectUrl = URL.createObjectURL(blob);
        setPreview({ kind: "image", url: objectUrl });
      } else if (attachment.content_type === "application/pdf") {
        objectUrl = URL.createObjectURL(blob);
        setPreview({ kind: "pdf", url: objectUrl });
      } else if (attachment.content_type.startsWith("text/") || attachment.content_type === "application/json") {
        setPreview({ kind: "text", text: await blob.text() });
      } else {
        setPreview({ kind: "unsupported" });
      }
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : "Не удалось открыть вложение.");
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [attachment, url]);

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  return (
    <div className="dialog-backdrop preview-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section aria-label={`Предпросмотр файла ${attachment.filename}`} aria-modal="true" className="preview-dialog" role="dialog">
        <div className="dialog-header">
          <div className="preview-title"><span className="attachment-icon"><FileText size={16} /></span><span><strong>{attachment.filename}</strong><small>{formatBytes(attachment.size_bytes)} · {attachment.content_type}</small></span></div>
          <div className="preview-actions"><a className="button button-secondary" download={attachment.filename} href={url}><Download size={14} /> Скачать</a><button aria-label="Закрыть предпросмотр" className="icon-button" onClick={onClose} type="button"><X size={17} /></button></div>
        </div>
        <div className="preview-body">
          {loading ? <LoadingState label="Загружаем вложение" /> : error ? <ErrorState message={error} /> : preview?.kind === "image" ? <img alt={attachment.filename} className="preview-image" src={preview.url} /> : preview?.kind === "pdf" ? <iframe className="preview-pdf" src={preview.url} title={`Предпросмотр ${attachment.filename}`} /> : preview?.kind === "text" ? <pre className="preview-text">{preview.text}</pre> : <div className="preview-unsupported"><FileText size={22} /><strong>Предпросмотр этого формата недоступен</strong><span>Скачайте файл, чтобы открыть его в подходящем приложении.</span></div>}
        </div>
      </section>
    </div>
  );
}
