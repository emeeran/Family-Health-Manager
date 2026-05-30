import { lazy, Suspense } from "react";
import { createBrowserRouter, redirect } from "react-router-dom";
import { isAuthenticated } from "@/lib/auth";
import { AppLayout } from "@/layouts/app-layout";
import { AuthLayout } from "@/layouts/auth-layout";

// Auth pages
const LoginPage = lazy(() => import("@/pages/login"));
const Login2FAPage = lazy(() => import("@/pages/login-2fa"));
const RegisterPage = lazy(() => import("@/pages/register"));

// App pages
const DashboardPage = lazy(() => import("@/pages/dashboard"));
const MembersPage = lazy(() => import("@/pages/members"));
const NewMemberPage = lazy(() => import("@/pages/member-new"));
const MemberDetailPage = lazy(() => import("@/pages/member-detail"));
const EditMemberPage = lazy(() => import("@/pages/member-edit"));
const MemberRecordsPage = lazy(() => import("@/pages/member-records"));
const NewRecordPage = lazy(() => import("@/pages/record-new"));
const RecordDetailPage = lazy(() => import("@/pages/record-detail"));
const EditRecordPage = lazy(() => import("@/pages/record-edit"));
const RecordBatchPage = lazy(() => import("@/pages/record-batch"));
const TimelinePage = lazy(() => import("@/pages/timeline"));
const LabRecordsPage = lazy(() => import("@/pages/lab-records"));
const MemberProvidersPage = lazy(() => import("@/pages/member-providers"));
const AIPage = lazy(() => import("@/pages/ai"));
const ProvidersPage = lazy(() => import("@/pages/providers"));
const NewProviderPage = lazy(() => import("@/pages/provider-new"));
const ProviderDetailPage = lazy(() => import("@/pages/provider-detail"));
const EditProviderPage = lazy(() => import("@/pages/provider-edit"));
const RemindersPage = lazy(() => import("@/pages/reminders"));
const NewReminderPage = lazy(() => import("@/pages/reminder-new"));
const EditReminderPage = lazy(() => import("@/pages/reminder-edit"));
const HouseholdRecordsPage = lazy(() => import("@/pages/household-records"));
const ConversationsPage = lazy(() => import("@/pages/conversations"));
const ConversationDetailPage = lazy(() => import("@/pages/conversation-detail"));
const NotificationsPage = lazy(() => import("@/pages/notifications"));
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
      <a href="/dashboard" className="text-sm text-primary hover:underline">
        Go to Dashboard
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
    path: "/",
    element: <></>,
    loader: () => {
      throw redirect("/dashboard");
    },
  },
  {
    element: <AuthLayout />,
    children: [
      { path: "login", element: withSuspense(LoginPage) },
      { path: "login/2fa", element: withSuspense(Login2FAPage) },
      { path: "register", element: withSuspense(RegisterPage) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
  {
    element: <AppLayout />,
    loader: authGuard,
    children: [
      { path: "dashboard", element: withSuspense(DashboardPage) },
      { path: "members", element: withSuspense(MembersPage) },
      { path: "members/new", element: withSuspense(NewMemberPage) },
      { path: "members/:memberId", element: withSuspense(MemberDetailPage) },
      { path: "members/:memberId/edit", element: withSuspense(EditMemberPage) },
      { path: "members/:memberId/records", element: withSuspense(MemberRecordsPage) },
      { path: "members/:memberId/records/new", element: withSuspense(NewRecordPage) },
      { path: "members/:memberId/records/batch", element: withSuspense(RecordBatchPage) },
      { path: "members/:memberId/records/:recordId", element: withSuspense(RecordDetailPage) },
      { path: "members/:memberId/records/:recordId/edit", element: withSuspense(EditRecordPage) },
      { path: "members/:memberId/timeline", element: withSuspense(TimelinePage) },
      { path: "members/:memberId/lab-records", element: withSuspense(LabRecordsPage) },
      { path: "members/:memberId/providers", element: withSuspense(MemberProvidersPage) },
      { path: "members/:memberId/ai", element: withSuspense(AIPage) },
      { path: "providers", element: withSuspense(ProvidersPage) },
      { path: "providers/new", element: withSuspense(NewProviderPage) },
      { path: "providers/:providerId", element: withSuspense(ProviderDetailPage) },
      { path: "providers/:providerId/edit", element: withSuspense(EditProviderPage) },
      { path: "reminders", element: withSuspense(RemindersPage) },
      { path: "reminders/new", element: withSuspense(NewReminderPage) },
      { path: "reminders/:reminderId/edit", element: withSuspense(EditReminderPage) },
      { path: "records", element: withSuspense(HouseholdRecordsPage) },
      { path: "conversations", element: withSuspense(ConversationsPage) },
      { path: "conversations/:conversationId", element: withSuspense(ConversationDetailPage) },
      { path: "notifications", element: withSuspense(NotificationsPage) },
      { path: "settings", element: withSuspense(SettingsPage) },
      { path: "onboarding", element: withSuspense(OnboardingPage) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
