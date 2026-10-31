import { Bell, BrainCircuit, Database, Globe2, LockKeyhole, Server, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { PageHeading } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";
import { useAuth } from "../context/AuthContext";
import { getHealth } from "../lib/api";

function SettingRow({ icon: Icon, title, detail, value, disabled = false }: { icon: LucideIcon; title: string; detail: string; value: string; disabled?: boolean }) {
  return <div className={`setting-row${disabled ? " setting-disabled" : ""}`}><span className="setting-icon"><Icon size={16} /></span><span className="setting-copy"><strong>{title}</strong><small>{detail}</small></span><span className="setting-value">{value}</span></div>;
}

export function SettingsPage() {
  const { totalCount } = useWorkspace();
  const { enabled: authEnabled, session } = useAuth();
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal).then(() => setBackendOnline(true)).catch(() => {
      if (!controller.signal.aborted) setBackendOnline(false);
    });
    return () => controller.abort();
  }, []);
  return (
    <>
      <PageHeading eyebrow="НАСТРОЙКИ РАБОЧЕГО ПРОСТРАНСТВА" title="Settings" description="Состояние и доступные параметры Support Copilot." />
      <div className="settings-layout">
        <section className="panel settings-section"><div className="panel-header"><div className="panel-title"><Settings2 size={16} /><span>Общие</span></div></div>
          <SettingRow icon={Globe2} title="Язык интерфейса" detail="Текущая локализация интерфейса" value="Русский" />
          <SettingRow icon={Bell} title="Уведомления" detail="Отдельный канал уведомлений не настроен" value="Не настроено" disabled />
          <SettingRow icon={LockKeyhole} title="Управление доступом" detail={authEnabled ? "Supabase Auth session" : "Supabase Auth не сконфигурирован"} value={authEnabled ? (session ? "Вход выполнен" : "Требуется вход") : "Локальный API"} disabled={!authEnabled} />
        </section>
        <section className="panel settings-section"><div className="panel-header"><div className="panel-title"><BrainCircuit size={16} /><span>AI и обработка</span></div></div>
          <SettingRow icon={BrainCircuit} title="Анализ обращений" detail="Запускается оператором из карточки обращения" value={backendOnline ? "API доступен" : backendOnline === false ? "API недоступен" : "Проверяем API"} disabled={backendOnline === false} />
          <SettingRow icon={Database} title="База правил" detail="Поиск по активным источникам Backend" value={backendOnline ? "API доступен" : backendOnline === false ? "API недоступен" : "Проверяем API"} disabled={backendOnline === false} />
          <SettingRow icon={Bell} title="Автоматическая отправка ответов" detail="Ответ игроку автоматически не отправляется" value="Отключена" />
        </section>
        <section className="panel settings-section system-settings"><div className="panel-header"><div className="panel-title"><Server size={16} /><span>Система</span></div></div>
          <SettingRow icon={Server} title="Backend API" detail="Состояние health endpoint" value={backendOnline ? "Подключён" : backendOnline === false ? "Недоступен" : "Проверяем"} disabled={backendOnline === false} />
          <SettingRow icon={Database} title="Обращения" detail="Общий count, полученный от Backend" value={`${totalCount} обращений`} />
          <div className="settings-footnote">Секреты LLM и service-role остаются на сервере. Публичный интерфейс использует только Supabase anon key и короткоживущую Auth session.</div>
        </section>
      </div>
    </>
  );
}
