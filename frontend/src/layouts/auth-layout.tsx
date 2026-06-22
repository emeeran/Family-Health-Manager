import { Outlet } from "react-router-dom";
import { DawnstarLogo } from "@/components/shared/dawnstar-logo";

export function AuthLayout() {
  return (
    <div className="min-h-screen grid md:grid-cols-2">
      {/* Branded left panel */}
      <div className="hidden md:flex flex-col justify-between bg-[#0a1628] p-10 text-white">
        <div className="flex items-center gap-0">
          <div className="flex flex-col leading-none">
            <span className="text-2xl font-extrabold tracking-tight text-white">DAWNSTAR</span>
            <span className="text-xs font-semibold tracking-widest text-amber-400 mt-0.5">
              Family Health Keeper
            </span>
          </div>
          <DawnstarLogo variant="white" className="h-10 w-10 ml-0.5 -mb-1.5" />
        </div>

        <div className="space-y-6">
          <h2 className="text-3xl font-bold leading-tight">
            Your family&apos;s health,
            <br />
            organized in one place.
          </h2>
          <p className="text-white/60 text-sm leading-relaxed max-w-sm">
            Track medical records, manage medications, set reminders, and get AI-powered health
            insights for your entire household.
          </p>
          <div className="grid grid-cols-3 gap-4 pt-2">
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <p className="text-2xl font-bold text-amber-400">360</p>
              <p className="text-xs text-white/50 mt-0.5">Health View</p>
            </div>
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <p className="text-2xl font-bold text-amber-400">AI</p>
              <p className="text-xs text-white/50 mt-0.5">Powered</p>
            </div>
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <p className="text-2xl font-bold text-amber-400">24/7</p>
              <p className="text-xs text-white/50 mt-0.5">Monitoring</p>
            </div>
          </div>
        </div>

        <p className="text-xs text-white/30">
          &copy; {new Date().getFullYear()} DAWNSTAR. Secure &amp; private.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center p-6 bg-background">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="flex md:hidden items-center justify-center gap-0 mb-8">
            <div className="flex flex-col leading-none">
              <span className="text-xl font-extrabold tracking-tight text-foreground">
                DAWNSTAR
              </span>
              <span className="text-[11px] font-semibold tracking-widest text-amber-600 mt-0.5">
                Family Health Keeper
              </span>
            </div>
            <DawnstarLogo variant="gradient" className="h-8 w-8 ml-0.5 -mb-1" />
          </div>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
