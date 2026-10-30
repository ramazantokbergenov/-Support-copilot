import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { WorkspaceProvider } from "./context/WorkspaceContext";
import { AnalysisDetailPage } from "./pages/AnalysisDetailPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { DraftsPage } from "./pages/DraftsPage";
import { EscalationsPage } from "./pages/EscalationsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { OverviewPage } from "./pages/OverviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TeamPage } from "./pages/TeamPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { TicketsPage } from "./pages/TicketsPage";

function NotFound() {
  return (
    <section className="panel not-found">
      <span className="not-found-code">404</span>
      <h2>Страница не найдена</h2>
      <p>Проверьте адрес или вернитесь к обзору.</p>
      <a className="button button-primary" href="/">Вернуться в Overview</a>
    </section>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <WorkspaceProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="tickets" element={<TicketsPage />} />
            <Route path="tickets/:ticketId" element={<TicketDetailPage />} />
            <Route path="analysis" element={<AnalysisPage />} />
            <Route path="analysis/:ticketId" element={<AnalysisDetailPage />} />
            <Route path="knowledge" element={<KnowledgePage />} />
            <Route path="drafts" element={<DraftsPage />} />
            <Route path="escalations" element={<EscalationsPage />} />
            <Route path="history" element={<HistoryPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="team" element={<TeamPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="not-found" element={<NotFound />} />
            <Route path="*" element={<Navigate replace to="/not-found" />} />
          </Route>
        </Routes>
      </WorkspaceProvider>
    </BrowserRouter>
  );
}
