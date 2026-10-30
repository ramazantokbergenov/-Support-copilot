import { LockKeyhole } from "lucide-react";
import { EmptyState, PageHeading } from "../components/UI";

export function TeamPage() {
  return (
    <>
      <PageHeading eyebrow="УЧАСТНИКИ РАБОЧЕГО ПРОСТРАНСТВА" title="Team" description="Управление операторами и доступом к данным поддержки." />
      <div className="notice-banner warning-banner"><LockKeyhole size={16} /><span>Управление пользователями, ролями и авторизацией требует backend и в автономном режиме недоступно.</span></div>
      <section className="panel unavailable-panel">
        <EmptyState icon="users" title="Участники не подключены" description="Список пользователей, роли, статусы доступа и назначения операторов станут доступны после интеграции с системой идентификации." />
        <div className="integration-checklist"><div><span className="check-muted">—</span><span>Единый вход и управление сессиями</span><small>Ожидает интеграции</small></div><div><span className="check-muted">—</span><span>Роли и права доступа</span><small>Ожидает backend</small></div><div><span className="check-muted">—</span><span>Назначение обращений операторам</span><small>Ожидает backend</small></div></div>
      </section>
    </>
  );
}
