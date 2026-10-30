import { Bell, BrainCircuit, Database, Globe2, LockKeyhole, Server, Settings2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PageHeading } from "../components/UI";
import { useWorkspace } from "../context/WorkspaceContext";

function SettingRow({ icon: Icon, title, detail, value, disabled = false }: { icon: LucideIcon; title: string; detail: string; value: string; disabled?: boolean }) {
  return <div className={`setting-row${disabled ? " setting-disabled" : ""}`}><span className="setting-icon"><Icon size={16} /></span><span className="setting-copy"><strong>{title}</strong><small>{detail}</small></span><span className="setting-value">{value}</span></div>;
}

export function SettingsPage() {
  const { tickets } = useWorkspace();
  return (
    <>
      <PageHeading eyebrow="НАСТРОЙКИ РАБОЧЕГО ПРОСТРАНСТВА" title="Settings" description="Состояние и доступные параметры Support Copilot." />
      <div className="settings-layout">
        <section className="panel settings-section"><div className="panel-header"><div className="panel-title"><Settings2 size={16} /><span>Общие</span></div></div>
          <SettingRow icon={Globe2} title="Язык интерфейса" detail="Текущая локализация интерфейса" value="Русский" />
          <SettingRow icon={Bell} title="Уведомления" detail="Уведомления недоступны без backend" value="Не подключено" disabled />
          <SettingRow icon={LockKeyhole} title="Управление доступом" detail="Аутентификация и роли в backend не реализованы" value="Не подключено" disabled />
        </section>
        <section className="panel settings-section"><div className="panel-header"><div className="panel-title"><BrainCircuit size={16} /><span>AI и обработка</span></div></div>
          <SettingRow icon={BrainCircuit} title="Анализ обращений" detail="AI-анализ требует backend" value="Недоступен офлайн" disabled />
          <SettingRow icon={Database} title="База правил" detail="Загрузка правил требует backend" value="Недоступна офлайн" disabled />
          <SettingRow icon={Bell} title="Автоматическая отправка ответов" detail="Ответ игроку автоматически не отправляется" value="Отключена" />
        </section>
        <section className="panel settings-section system-settings"><div className="panel-header"><div className="panel-title"><Server size={16} /><span>Система</span></div></div>
          <SettingRow icon={Server} title="Backend API" detail="Временно отключён; обращения хранятся в браузере" value="Автономный режим" />
          <SettingRow icon={Database} title="Локальные данные" detail="Обращения сохранены в хранилище этого браузера" value={`${tickets.length} обращений`} />
          <div className="settings-footnote">Локальные данные доступны только в текущем браузере и не синхронизируются с другими устройствами. Очищение данных сайта удалит обращения.</div>
        </section>
      </div>
    </>
  );
}
