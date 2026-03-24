import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { MainLayout } from "@/components/layout";
import {
  VoiceRxSettingsPage,
  VoiceRxDashboard,
  VoiceRxRunList,
  VoiceRxRunDetail,
} from "@/features/voiceRx";
import {
  KairaBotSettingsPage,
  TagManagementPage,
} from "@/features/kairaBotSettings";
import {
  EvalDashboard,
  EvalRunList,
  EvalRunDetail,
  EvalThreadDetailV2,
  EvalAdversarialDetailV2,
  EvalLogs,
} from "@/features/evalRuns";
import { LoginPage, SignupPage, AuthGuard, AdminGuard } from "@/features/auth";
import { AdminUsersPage } from "@/features/admin";
import {
  InsideSalesListing,
  InsideSalesEvaluators,
  InsideSalesRunList,
  InsideSalesRunDetail,
  InsideSalesDashboard,
  InsideSalesCallDetail,
} from "@/features/insideSales";
import { HomePage } from "./pages/HomePage";
import { ListingPage } from "./pages/ListingPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { KairaBotHomePage } from "./pages/kaira";
import { routes } from "@/config/routes";

const GuidePage = lazy(() => import("@/features/guide"));

export function Router() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes — login + signup */}
        <Route path={routes.login} element={<LoginPage />} />
        <Route path={routes.signup} element={<SignupPage />} />

        {/* Guide — full-page layout, lazy-loaded, behind auth */}
        <Route
          path={routes.guide}
          element={
            <AuthGuard>
              <Suspense fallback={null}>
                <GuidePage />
              </Suspense>
            </AuthGuard>
          }
        />

        {/* Protected routes — wrapped with AuthGuard + MainLayout */}
        <Route
          element={
            <AuthGuard>
              <MainLayout />
            </AuthGuard>
          }
        >
          {/* Voice Rx routes */}
          <Route
            path={routes.voiceRx.home}
            element={<Navigate to={routes.voiceRx.dashboard} replace />}
          />
          <Route path={routes.voiceRx.upload} element={<HomePage />} />
          <Route path="/listing/:id" element={<ListingPage />} />
          <Route
            path={routes.voiceRx.dashboard}
            element={<VoiceRxDashboard />}
          />
          <Route path="/runs/:runId" element={<VoiceRxRunDetail />} />
          <Route path={routes.voiceRx.runs} element={<VoiceRxRunList />} />
          <Route path={routes.voiceRx.logs} element={<EvalLogs />} />
          <Route
            path={routes.voiceRx.settings}
            element={<VoiceRxSettingsPage />}
          />

          {/* Kaira Bot routes */}
          <Route
            path={routes.kaira.home}
            element={<Navigate to={routes.kaira.dashboard} replace />}
          />
          <Route path="/kaira/chat/:chatId" element={<KairaBotHomePage />} />
          <Route path={routes.kaira.chat} element={<KairaBotHomePage />} />
          <Route
            path={routes.kaira.settings}
            element={<KairaBotSettingsPage />}
          />
          <Route
            path={routes.kaira.settingsTags}
            element={<TagManagementPage />}
          />

          {/* Kaira Evals routes */}
          <Route path={routes.kaira.dashboard} element={<EvalDashboard />} />
          <Route path={routes.kaira.runs} element={<EvalRunList />} />
          <Route path="/kaira/runs/:runId" element={<EvalRunDetail />} />
          <Route
            path="/kaira/runs/:runId/adversarial/:evalId"
            element={<EvalAdversarialDetailV2 />}
          />
          <Route
            path="/kaira/threads/:threadId"
            element={<EvalThreadDetailV2 />}
          />
          <Route path={routes.kaira.logs} element={<EvalLogs />} />

          {/* Inside Sales routes */}
          <Route path={routes.insideSales.listing} element={<InsideSalesListing />} />
          <Route path={routes.insideSales.evaluators} element={<InsideSalesEvaluators />} />
          <Route path="/inside-sales/evaluators/:id" element={<InsideSalesEvaluators />} />
          <Route path={routes.insideSales.runs} element={<InsideSalesRunList />} />
          <Route path="/inside-sales/runs/:runId" element={<InsideSalesRunDetail />} />
          <Route path="/inside-sales/runs/:runId/calls/:callId" element={<InsideSalesRunDetail />} />
          <Route path="/inside-sales/calls/:activityId" element={<InsideSalesCallDetail />} />
          <Route path={routes.insideSales.dashboard} element={<InsideSalesDashboard />} />
          <Route path={routes.insideSales.logs} element={<EvalLogs />} />
          <Route path={routes.insideSales.settings} element={<InsideSalesDashboard />} />

          {/* Admin routes */}
          <Route
            path={routes.adminUsers}
            element={
              <AdminGuard>
                <AdminUsersPage />
              </AdminGuard>
            }
          />

          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
