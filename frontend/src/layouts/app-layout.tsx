import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { MobileBottomNav } from "@/components/layout/mobile-bottom-nav";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ErrorBoundary } from "@/components/shared/error-boundary";
import { OfflineBanner } from "@/components/shared/offline-banner";
import { RecordQuickViewProvider } from "@/components/records/record-quick-view-provider";
import { RecordQuickView } from "@/components/records/record-quick-view";
import { UniversalQuickAdd } from "@/components/shared/universal-quick-add";

export function AppLayout() {
  return (
    <TooltipProvider>
      <RecordQuickViewProvider>
        <OfflineBanner />
        <div className="flex h-screen overflow-hidden">
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:p-4 focus:bg-primary focus:text-primary-foreground focus:border focus:rounded-lg focus:top-2 focus:left-2 focus:shadow-lg"
          >
            Skip to main content
          </a>
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <Header />
            <main
              id="main-content"
              className="relative flex-1 overflow-y-auto overflow-x-hidden p-3 md:p-5 pb-20 md:pb-5 animate-page-enter"
            >
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </main>
          </div>
        </div>
        <Toaster />
        <MobileBottomNav />
        <RecordQuickView />
        <UniversalQuickAdd />
      </RecordQuickViewProvider>
    </TooltipProvider>
  );
}
