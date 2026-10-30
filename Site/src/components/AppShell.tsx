import {
  Activity,
  BarChart3,
  Bell,
  BookOpen,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  Inbox,
  LayoutDashboard,
  Menu,
  Plus,
  Search,
  Settings,
  ShieldAlert,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { createTicket } from "../lib/localWorkspace";
import { useWorkspace } from "../context/WorkspaceContext";
import { isEscalated } from "../lib/format";
import type { TicketPriority } from "../types";
import { IconButton } from "./UI";

type Toast = (message: string, tone?: "success" | "error") => void;
const ToastContext = createContext<Toast>(() => undefined);
export const useToast = () => useContext(ToastContext);

const primaryNavigation = [
  { label: "Overview", path: "/", icon: LayoutDashboard },
  { label: "Tickets", path: "/tickets", icon: Inbox },
  { label: "AI Analysis", path: "/analysis", icon: Sparkles },
  { label: "Knowledge Base", path: "/knowledge", icon: BookOpen },
  { label: "Response Drafts", path: "/drafts", icon: FileText },
  { label: "Escalations", path: "/escalations", icon: ShieldAlert },
  { label: "History", path: "/history", icon: Clock3 },
];

const workspaceNavigation = [
  { label: "Analytics", path: "/analytics", icon: BarChart3 },
  { label: "Team", path: "/team", icon: Users },
  { label: "Settings", path: "/settings", icon: Settings },
];

const labels: Record<string, string> = {
  "/": "Overview",
  "/tickets": "Tickets",
  "/analysis": "AI Analysis",
  "/knowledge": "Knowledge Base",
  "/drafts": "Response Drafts",
  "/escalations": "Escalations",
  "/history": "History",
  "/analytics": "Analytics",
  "/team": "Team",
  "/settings": "Settings",
};

function usePageTitle() {
  const { pathname } = useLocation();
  const { ticketId } = useParams();
  if (pathname.startsWith("/analysis/") && ticketId) return "Analysis details";
  if (ticketId) return "Ticket details";
  if (pathname.startsWith("/tickets/")) return "Ticket details";
  return labels[pathname] ?? "Overview";
}

export function AppShell() {
  const { tickets, refresh } = useWorkspace();
  const navigate = useNavigate();
  const location = useLocation();
  const title = usePageTitle();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem("sc-sidebar-collapsed") === "true";
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState<{ text: string; tone: string } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem("sc-sidebar-collapsed", String(collapsed));
    } catch {
      // The sidebar still works when browser storage is disabled.
    }
  }, [collapsed]);

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setCreateOpen(false);
        setMobileOpen(false);
      }
      if (
        event.key === "/" &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLTextAreaElement) &&
        !(event.target instanceof HTMLSelectElement) &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey
      ) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const showToast = useMemo<Toast>(
    () => (message, tone = "success") => setToast({ text: message, tone }),
    [],
  );

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate(`/tickets${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`);
  }

  return (
    <ToastContext.Provider value={showToast}>
      <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}${mobileOpen ? " mobile-nav-open" : ""}`}>
        <aside className="sidebar">
          <div className="brand-row">
            <NavLink className="brand" to="/" aria-label="Support Copilot, Overview">
              <span className="brand-mark">SC</span>
              <span className="brand-copy">
                <strong>Support Copilot</strong>
                <small>ZHS · GRAND MOBILE</small>
              </span>
            </NavLink>
            <IconButton
              className="collapse-button"
              label={collapsed ? "Развернуть меню" : "Свернуть меню"}
              onClick={() => setCollapsed((value) => !value)}
            >
              {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </IconButton>
            <IconButton
              className="mobile-close"
              label="Закрыть меню"
              onClick={() => setMobileOpen(false)}
            >
              <X size={17} />
            </IconButton>
          </div>
          <div className="workspace-label">WORKSPACE</div>
          <nav className="nav-list" aria-label="Основная навигация">
            {primaryNavigation.map(({ label, path, icon: Icon }) => (
              <NavLink
                key={path}
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                end={path === "/"}
                to={path}
                title={collapsed ? label : undefined}
              >
                <Icon size={17} strokeWidth={1.8} />
                <span>{label}</span>
                {path === "/tickets" && tickets.some((ticket) => ticket.status === "New") && (
                  <span className="nav-count">
                    {tickets.filter((ticket) => ticket.status === "New").length}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
          <div className="workspace-label secondary-label">MANAGE</div>
          <nav className="nav-list" aria-label="Управление">
            {workspaceNavigation.map(({ label, path, icon: Icon }) => (
              <NavLink
                key={path}
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                to={path}
                title={collapsed ? label : undefined}
              >
                <Icon size={17} strokeWidth={1.8} />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="connection-card is-online">
              <span className="connection-dot" />
              <span className="connection-copy">
                <strong>Автономный режим</strong>
                <small>Данные хранятся в браузере</small>
              </span>
            </div>
            <div className="profile-card">
              <span className="profile-avatar">OP</span>
              <span className="profile-copy">
                <strong>Оператор</strong>
                <small>Локальный профиль</small>
              </span>
              <ChevronDown size={15} className="profile-chevron" />
            </div>
          </div>
        </aside>
        {mobileOpen && (
          <button
            aria-label="Закрыть навигацию"
            className="mobile-backdrop"
            onClick={() => setMobileOpen(false)}
          />
        )}
        <main className="main-area">
          <header className="topbar">
            <div className="topbar-title">
              <IconButton
                className="mobile-menu"
                label="Открыть меню"
                onClick={() => setMobileOpen(true)}
              >
                <Menu size={19} />
              </IconButton>
              <div>
                <div className="breadcrumbs">
                  <span>Workspace</span><span className="breadcrumb-separator">/</span>
                  <strong>{title}</strong>
                </div>
                <h1>{title}</h1>
              </div>
            </div>
            <div className="topbar-actions">
              <form className="global-search" onSubmit={submitSearch} role="search">
                <Search size={16} />
                <input
                  aria-label="Поиск по обращениям"
                  ref={searchRef}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Найти обращение..."
                  value={query}
                />
                <kbd>/</kbd>
              </form>
              <IconButton
                className="header-notifications"
                label="Открыть эскалации"
                onClick={() => navigate("/escalations")}
              >
                <Bell size={17} />
                {tickets.some((ticket) => isEscalated(ticket.status, ticket.escalation_required)) && (
                  <span className="notification-dot" />
                )}
              </IconButton>
              <button
                className="button button-primary create-button"
                onClick={() => setCreateOpen(true)}
                type="button"
              >
                <Plus size={16} />
                <span>Новое обращение</span>
              </button>
              <IconButton
                className="refresh-button"
                label="Обновить данные"
                onClick={() => void refresh()}
              >
                <Activity size={17} />
              </IconButton>
            </div>
          </header>
          <div className="page-content"><Outlet /></div>
        </main>
      </div>
      {createOpen && (
        <CreateTicketDialog
          onClose={() => setCreateOpen(false)}
          onCreated={(ticketId) => {
            setCreateOpen(false);
            navigate(`/tickets/${encodeURIComponent(ticketId)}`);
          }}
          notify={showToast}
        />
      )}
      {toast && (
        <div className={`toast toast-${toast.tone}`} role="status">
          <span className="toast-indicator" />
          {toast.text}
        </div>
      )}
    </ToastContext.Provider>
  );
}

function CreateTicketDialog({
  onClose,
  onCreated,
  notify,
}: {
  onClose: () => void;
  onCreated: (ticketId: string) => void;
  notify: Toast;
}) {
  const [playerId, setPlayerId] = useState("");
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState<TicketPriority>("Normal");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { refresh } = useWorkspace();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const ticket = await createTicket({
        player_id: playerId.trim(),
        message: message.trim(),
        category: category.trim() || undefined,
        priority,
        attachments: [],
      });
      await refresh();
      notify("Обращение создано.");
      onCreated(ticket.ticket_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать обращение.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section aria-labelledby="create-heading" aria-modal="true" className="dialog-card" role="dialog">
        <div className="dialog-header">
          <div><span className="eyebrow">НОВОЕ ОБРАЩЕНИЕ</span><h2 id="create-heading">Создать обращение</h2></div>
          <IconButton label="Закрыть" onClick={onClose}><X size={18} /></IconButton>
        </div>
        <form className="dialog-form" onSubmit={(event) => void submit(event)}>
          <label className="field-label">ID игрока<input autoFocus maxLength={128} onChange={(event) => setPlayerId(event.target.value)} placeholder="Укажите ID игрока" required value={playerId} /></label>
          <label className="field-label">Сообщение<textarea maxLength={20000} onChange={(event) => setMessage(event.target.value)} placeholder="Текст обращения игрока" required rows={5} value={message} /></label>
          <label className="field-label">Категория <span className="muted">(необязательно)</span><input maxLength={100} onChange={(event) => setCategory(event.target.value)} placeholder="Например, техническая проблема" value={category} /></label>
          <div className="form-grid">
            <label className="field-label">Приоритет
              <select onChange={(event) => setPriority(event.target.value as TicketPriority)} value={priority}>
                <option value="Low">Низкий</option><option value="Normal">Обычный</option><option value="High">Высокий</option><option value="Urgent">Срочный</option>
              </select>
            </label>
            <label className="field-label">Вложения
              <input disabled type="file" />
            </label>
          </div>
          <p className="field-help">Загрузка файлов и AI-анализ требуют backend и временно отключены.</p>
          {error && <div className="inline-error" role="alert">{error}</div>}
          <div className="dialog-actions">
            <button className="button button-secondary" onClick={onClose} type="button">Отмена</button>
            <button className="button button-primary" disabled={saving} type="submit">{saving ? "Создаём..." : "Создать обращение"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
