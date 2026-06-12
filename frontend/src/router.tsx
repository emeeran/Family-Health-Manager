import { lazy, Suspense } from "react";
import { createBrowserRouter, redirect } from "react-router-dom";
import { isAuthenticated } from "@/lib/auth";
import { AppLayout } from "@/layouts/app-layout";
import { AuthLayout } from "@/layouts/auth-layout";

// Auth pages
const LoginPage = lazy(() => import("@/pages/login"));
const Login2FAPage = lazy(() => import("@/pages/login-2fa"));
const RegisterPage = lazy(() => import("@/pages/register"));

// Primary pages
const HomePage = lazy(() => import("@/pages/home"));
const PeoplePage = lazy(() => import("@/pages/people"));
const ProvidersPage = lazy(() => import("@/pages/providers"));
const ChatPage = lazy(() => import("@/pages/chat"));

// AI Tools pages
const AiToolsHubPage = lazy(() => import("@/pages/ai-tools/ai-tools-hub"));
const AiToolsChatPage = lazy(() => import("@/pages/ai-tools/chat"));
const AiToolsInsightsPage = lazy(() => import("@/pages/ai-tools/insights"));
const AiToolsPreConsultPage = lazy(() => import("@/pages/ai-tools/pre-consultation"));
const AiToolsDrugInteractionsPage = lazy(() => import("@/pages/ai-tools/drug-interactions"));
const AiToolsSummariesPage = lazy(() => import("@/pages/ai-tools/summaries"));
const AiToolsSmartEntryPage = lazy(() => import("@/pages/ai-tools/smart-entry"));
const AiToolsDocumentExtractionPage = lazy(() => import("@/pages/ai-tools/document-extraction"));

// Member pages (kept for deep linking)
const NewMemberPage = lazy(() => import("@/pages/member-new"));
const MemberDetailPage = lazy(() => import("@/pages/member-detail"));
const EditMemberPage = lazy(() => import("@/pages/member-edit"));

// Record pages
const NewRecordPage = lazy(() => import("@/pages/record-new"));
const RecordDetailPage = lazy(() => import("@/pages/record-detail"));
const EditRecordPage = lazy(() => import("@/pages/record-edit"));
const RecordBatchPage = lazy(() => import("@/pages/record-batch"));
const HouseholdRecordsPage = lazy(() => import("@/pages/household-records"));

// Provider pages (kept for deep linking)
const NewProviderPage = lazy(() => import("@/pages/provider-new"));
const ProviderDetailPage = lazy(() => import("@/pages/provider-detail"));
const EditProviderPage = lazy(() => import("@/pages/provider-edit"));

// Reminder pages (kept for deep linking)
const NewReminderPage = lazy(() => import("@/pages/reminder-new"));
const EditReminderPage = lazy(() => import("@/pages/reminder-edit"));

// Other pages
const SettingsPage = lazy(() => import("@/pages/settings"));
const OnboardingPage = lazy(() => import("@/pages/onboarding"));

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

function withSuspense(Component: React.LazyExoticComponent<React.ComponentType>) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <p className="text-6xl font-bold text-muted-foreground/30 mb-4">404</p>
      <p className="text-lg font-medium mb-2">Page not found</p>
      <p className="text-sm text-muted-foreground mb-6">
        The page you're looking for doesn't exist.
      </p>
      <a href="/" className="text-sm text-primary hover:underline">
        Go Home
      </a>
    </div>
  );
}

function authGuard() {
  if (!isAuthenticated()) throw redirect("/login");
  return null;
}

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    loader: authGuard,
    children: [
      // ── Primary routes ──
      { index: true, element: withSuspense(HomePage) },
      { path: "people", element: withSuspense(PeoplePage) },
      { path: "providers", element: withSuspense(ProvidersPage) },
      { path: "records", element: withSuspense(HouseholdRecordsPage) },
      { path: "chat", element: withSuspense(ChatPage) },

      // ── AI Tools ──
      { path: "ai-tools", element: withSuspense(AiToolsHubPage) },
      { path: "ai-tools/chat", element: withSuspense(AiToolsChatPage) },
      { path: "ai-tools/insights", element: withSuspense(AiToolsInsightsPage) },
      { path: "ai-tools/pre-consultation", element: withSuspense(AiToolsPreConsultPage) },
      { path: "ai-tools/drug-interactions", element: withSuspense(AiToolsDrugInteractionsPage) },
      { path: "ai-tools/summaries", element: withSuspense(AiToolsSummariesPage) },
      { path: "ai-tools/smart-entry", element: withSuspense(AiToolsSmartEntryPage) },
      {
        path: "ai-tools/document-extraction",
        element: withSuspense(AiToolsDocumentExtractionPage),
      },

      // ── People / Member sub-routes ──
      { path: "people/new", element: withSuspense(NewMemberPage) },
      { path: "people/:memberId", element: withSuspense(MemberDetailPage) },
      { path: "people/:memberId/edit", element: withSuspense(EditMemberPage) },
      {
        path: "people/:memberId/records",
        loader: ({ params }: { params: { memberId?: string } }) => {
          throw redirect(`/people/${params.memberId}?tab=records`);
        },
      },
      { path: "people/:memberId/records/new", element: withSuspense(NewRecordPage) },
      { path: "people/:memberId/records/batch", element: withSuspense(RecordBatchPage) },
      { path: "people/:memberId/records/:recordId", element: withSuspense(RecordDetailPage) },
      {
        path: "people/:memberId/records/:recordId/edit",
        element: withSuspense(EditRecordPage),
      },

      // ── Provider sub-routes (deep-link) ──
      { path: "providers/new", element: withSuspense(NewProviderPage) },
      { path: "providers/:providerId", element: withSuspense(ProviderDetailPage) },
      { path: "providers/:providerId/edit", element: withSuspense(EditProviderPage) },

      // ── Reminder sub-routes (deep-link) ──
      { path: "reminders/new", element: withSuspense(NewReminderPage) },
      { path: "reminders/:reminderId/edit", element: withSuspense(EditReminderPage) },

      // ── Other ──
      { path: "settings", element: withSuspense(SettingsPage) },
      { path: "onboarding", element: withSuspense(OnboardingPage) },

      // ── Backwards-compat redirects ──
      {
        path: "dashboard",
        loader: () => {
          throw redirect("/");
        },
      },
      {
        path: "members",
        loader: () => {
          throw redirect("/people");
        },
      },
      {
        path: "members/new",
        loader: () => {
          throw redirect("/people/new");
        },
      },
      {
        path: "members/:memberId",
        loader: ({ params }: { params: { memberId?: string } }) => {
          throw redirect(`/people/${params.memberId}`);
        },
      },
      {
        path: "members/:memberId/edit",
        loader: ({ params }: { params: { memberId?: string } }) => {
          throw redirect(`/people/${params.memberId}/edit`);
        },
      },
      {
        path: "members/:memberId/assistant",
        loader: ({ params }: { params: { memberId?: string } }) => {
          throw redirect(`/ai-tools?memberId=${params.memberId}`);
        },
      },
      {
        path: "members/:memberId/records/new",
        loader: ({ params }: { params: { memberId?: string } }) => {
          throw redirect(`/people/${params.memberId}/records/new`);
        },
      },
      {
        path: "members/:memberId/records/batch",
        loader: ({ params }: { params: { memberId?: string } }) => {
          throw redirect(`/people/${params.memberId}/records/batch`);
        },
      },
      {
        path: "members/:memberId/records/:recordId",
        loader: ({ params }: { params: { memberId?: string; recordId?: string } }) => {
          throw redirect(`/people/${params.memberId}/records/${params.recordId}`);
        },
      },
      {
        path: "members/:memberId/records/:recordId/edit",
        loader: ({ params }: { params: { memberId?: string; recordId?: string } }) => {
          throw redirect(`/people/${params.memberId}/records/${params.recordId}/edit`);
        },
      },
      {
        path: "conversations",
        loader: () => {
          throw redirect("/chat");
        },
      },
      {
        path: "conversations/:conversationId",
        loader: ({ params }: { params: { conversationId?: string } }) => {
          throw redirect(`/chat?conversationId=${params.conversationId}`);
        },
      },

      // ── Catch all ──
      { path: "*", element: <NotFoundPage /> },
    ],
  },
  {
    element: <AuthLayout />,
    children: [
      { path: "login", element: withSuspense(LoginPage) },
      { path: "login/2fa", element: withSuspense(Login2FAPage) },
      { path: "register", element: withSuspense(RegisterPage) },
    ],
  },
]);
