import { useParams, useNavigate } from 'react-router-dom';
import { DashboardView } from '../components/DashboardView';

export function AnalyticsDashboardDetail() {
  const { dashboardId } = useParams<{ dashboardId: string }>();
  const navigate = useNavigate();

  if (!dashboardId) return null;

  return <DashboardView dashboardId={dashboardId} onBack={() => navigate(-1)} />;
}
