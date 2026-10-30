import { ArrowUpRight, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { formatDate } from "../lib/format";
import type { TicketSummary } from "../types";
import { PriorityBadge, StatusBadge } from "./UI";

export function TicketTable({
  tickets,
  emptyTitle = "Обращений пока нет",
  emptyDescription = "Когда появятся обращения, они будут отображаться здесь.",
}: {
  tickets: TicketSummary[];
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (!tickets.length) {
    return (
      <div className="table-empty">
        <div className="empty-icon"><Search size={18} /></div>
        <strong>{emptyTitle}</strong>
        <span>{emptyDescription}</span>
      </div>
    );
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>ОБРАЩЕНИЕ</th><th>КАТЕГОРИЯ</th><th>ПРИОРИТЕТ</th><th>СТАТУС</th><th>СОЗДАНО</th><th><span className="sr-only">Открыть</span></th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.ticket_id}>
              <td>
                <Link className="ticket-cell-link" to={`/tickets/${encodeURIComponent(ticket.ticket_id)}`}>
                  <strong className="ticket-id-cell">{ticket.ticket_id}</strong>
                  <span>Игрок · {ticket.player_id}</span>
                </Link>
              </td>
              <td>{ticket.category || <span className="muted">Не определена</span>}</td>
              <td><PriorityBadge priority={ticket.priority} /></td>
              <td><StatusBadge status={ticket.status} /></td>
              <td className="date-cell">{formatDate(ticket.created_at)}</td>
              <td><Link aria-label={`Открыть ${ticket.ticket_id}`} className="table-open" to={`/tickets/${encodeURIComponent(ticket.ticket_id)}`}><ArrowUpRight size={16} /></Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
