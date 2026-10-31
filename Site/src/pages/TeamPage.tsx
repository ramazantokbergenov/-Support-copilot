import { LockKeyhole } from "lucide-react";
import { EmptyState, PageHeading } from "../components/UI";

export function TeamPage() {
  return (
    <>
      <PageHeading eyebrow="УЧАСТНИКИ РАБОЧЕГО ПРОСТРАНСТВА" title="Team" description="Управление операторами и доступом к данным поддержки." />
      <div className="notice-banner warning-banner"><LockKeyhole size={16} /><span>Доступ к API проверяется через Supabase Auth. Управление списком операторов и назначениями не входит в текущий API.</span></div>
      <section className="panel unavailable-panel">
        <EmptyState icon="users" title="Список операторов недоступен" description="Операторские роли проверяются Backend из operator_profiles. Endpoint для просмотра команды и назначения обращений пока не реализован." />
        <div className="integration-checklist"><div><span className="check-muted">—</span><span>Единый вход и управление сессиями</span><small>Supabase Auth</small></div><div><span className="check-muted">—</span><span>Роли и права доступа</span><small>Проверяются Backend</small></div><div><span className="check-muted">—</span><span>Назначение обращений операторам</span><small>Endpoint отсутствует</small></div></div>
      </section>
    </>
  );
}
