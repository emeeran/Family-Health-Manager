import { useState, useEffect, memo } from "react";
import { useLocation, Link } from "react-router-dom";
import {
  Home,
  Users,
  Stethoscope,
  MessageSquare,
  BellDot,
  Settings,
  FileText,
  CalendarClock,
  Sparkles,
  ClipboardList,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { useNotificationCount } from "@/hooks/use-notification-count";
import { DawnstarLogo } from "@/components/shared/dawnstar-logo";
import { ChatPopup } from "@/components/shared/chat-popup";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
}

const COLLAPSED_KEY = "sidebar-collapsed";

export const Sidebar = memo(function Sidebar() {
  const { pathname } = useLocation();
  const unreadCount = useNotificationCount();

  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(COLLAPSED_KEY) === "true";
  });

  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, String(collapsed));
  }, [collapsed]);

  const overviewNav: NavItem[] = [
    { label: "Dashboard", href: "/dashboard", icon: Home },
    { label: "Members", href: "/members", icon: Users },
  ];

  const careNav: NavItem[] = [
    { label: "Records", href: "/records", icon: ClipboardList },
    { label: "Providers", href: "/providers", icon: Stethoscope },
    { label: "Reminders", href: "/reminders", icon: CalendarClock },
    { label: "Notifications", href: "/notifications", icon: BellDot, badge: unreadCount },
  ];

  const toolsNav: NavItem[] = [
    { label: "AI Chat", href: "/conversations", icon: MessageSquare },
    { label: "Settings", href: "/settings", icon: Settings },
    { label: "Audit Log", href: "/audit", icon: FileText },
  ];

  function handleNavKeyDown(e: React.KeyboardEvent<HTMLElement>) {
    const links = Array.from(e.currentTarget.querySelectorAll<HTMLAnchorElement>("a[href]"));
    const idx = links.indexOf(document.activeElement as HTMLAnchorElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      links[(idx + 1) % links.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      links[(idx - 1 + links.length) % links.length]?.focus();
    }
  }

  return (
    <aside
      className={cn(
        "hidden md:flex flex-col transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]",
        "bg-gradient-to-b from-[var(--sidebar)] to-[var(--sidebar)]/95 border-r border-sidebar-border",
        collapsed ? "w-[58px]" : "w-52"
      )}
      role="navigation"
      aria-label="Main navigation"
    >
      {/* ── Header: Logo + toggle ── */}
      <div
        className={cn(
          "px-2 pt-4 pb-3 flex items-center",
          collapsed ? "flex-col gap-2" : "justify-between"
        )}
      >
        <Link
          to="/dashboard"
          className={cn(
            "group overflow-hidden",
            collapsed ? "mx-auto flex items-center justify-center" : "flex-1"
          )}
        >
          {!collapsed ? (
            <div className="flex items-center">
              <span className="font-extrabold text-lg tracking-tight text-foreground leading-none">
                DAWNSTAR
              </span>
              <DawnstarLogo variant="gradient" className="h-7 w-7 shrink-0 ml-0.5" />
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setCollapsed((c) => !c);
                }}
                className="ml-2 shrink-0 rounded-lg p-1.5 text-muted-foreground/60 hover:text-foreground hover:bg-muted/60 transition-all duration-200"
                aria-label="Collapse sidebar"
              >
                <PanelLeftClose className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <DawnstarLogo variant="gradient" className="h-8 w-8 shrink-0" />
          )}
          {!collapsed && (
            <span className="block text-[11px] font-bold tracking-[0.25em] text-(--brand-primary)/80 mt-0.5 ml-0.5">
              FAMILY HEALTH KEEPER
            </span>
          )}
        </Link>
        {collapsed && (
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="mx-auto rounded-lg p-1.5 text-muted-foreground/60 hover:text-foreground hover:bg-muted/60 transition-all duration-200"
            aria-label="Expand sidebar"
          >
            <PanelLeftOpen className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* ── Navigation ── */}
      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-1 space-y-3"
        onKeyDown={handleNavKeyDown}
      >
        <div>
          <SectionLabel collapsed={collapsed}>Overview</SectionLabel>
          <div className={collapsed ? "flex flex-col items-center gap-0.5" : "space-y-0.5"}>
            {overviewNav.map((item) => (
              <SidebarLink
                key={item.href}
                {...item}
                active={
                  pathname === item.href ||
                  (item.href !== "/dashboard" && pathname.startsWith(item.href))
                }
                collapsed={collapsed}
              />
            ))}
          </div>
        </div>

        <div>
          <SectionLabel collapsed={collapsed}>Care</SectionLabel>
          <div className={collapsed ? "flex flex-col items-center gap-0.5" : "space-y-0.5"}>
            {careNav.map((item) => (
              <SidebarLink
                key={item.href}
                {...item}
                active={pathname.startsWith(item.href)}
                collapsed={collapsed}
              />
            ))}
          </div>
        </div>

        <div>
          <SectionLabel collapsed={collapsed}>Tools</SectionLabel>
          <div className={collapsed ? "flex flex-col items-center gap-0.5" : "space-y-0.5"}>
            {toolsNav.map((item) => (
              <SidebarLink
                key={item.href}
                {...item}
                active={pathname.startsWith(item.href)}
                collapsed={collapsed}
              />
            ))}
          </div>
        </div>
      </nav>

      {/* ── AI Assistant button (bottom) ── */}
      <div className="px-2 pb-2">
        {collapsed ? (
          <TooltipProvider delay={300}>
            <Tooltip>
              {/* @ts-expect-error Radix TooltipTrigger supports asChild */}
              <TooltipTrigger asChild>
                <button
                  onClick={() => setChatOpen(true)}
                  className="group flex items-center justify-center w-10 h-10 rounded-lg bg-gradient-to-br from-(--brand-accent)/15 to-(--brand-primary)/10 border border-(--brand-accent)/20 hover:from-(--brand-accent)/25 hover:to-(--brand-primary)/20 hover:border-(--brand-accent)/40 transition-all duration-300"
                >
                  <Sparkles className="h-4 w-4 text-(--brand-accent)" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">AI Assistant</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : (
          <button
            onClick={() => setChatOpen(true)}
            className="group w-full text-left rounded-lg bg-gradient-to-r from-(--brand-accent)/12 via-(--brand-primary)/8 to-(--brand-accent)/12 border border-(--brand-accent)/15 px-3 py-2 hover:from-(--brand-accent)/20 hover:via-(--brand-primary)/15 hover:to-(--brand-accent)/20 hover:border-(--brand-accent)/30 transition-all duration-300"
          >
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-(--brand-accent) to-orange-600 shadow-sm shadow-(--brand-accent)/20">
                <Sparkles className="h-3.5 w-3.5 text-white" />
              </div>
              <p className="text-xs font-semibold text-foreground">AI Assistant</p>
            </div>
          </button>
        )}
      </div>

      <ChatPopup open={chatOpen} onOpenChange={setChatOpen} />
    </aside>
  );
});

/* ── Section label ── */
function SectionLabel({ collapsed, children }: { collapsed: boolean; children: React.ReactNode }) {
  if (collapsed) {
    return <div className="w-0.5 h-0.5 rounded-full bg-muted-foreground/20 mx-auto mb-0.5" />;
  }
  return (
    <div className="flex items-center gap-1.5 px-1.5 pb-1.5 pt-0.5">
      <div className="h-1.5 w-1.5 rounded-full bg-gradient-to-br from-(--brand-accent) to-(--brand-primary) opacity-60" />
      <span className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-muted-foreground/60 select-none">
        {children}
      </span>
      <div className="flex-1 h-px bg-gradient-to-r from-border to-transparent" />
    </div>
  );
}

/* ── Nav link ── */
const SidebarLink = memo(function SidebarLink({
  label,
  href,
  icon: Icon,
  active,
  badge,
  collapsed,
}: NavItem & { active: boolean; collapsed: boolean }) {
  const link = (
    <Link
      to={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex items-center gap-2.5 rounded-lg transition-all duration-200",
        collapsed ? "justify-center w-10 h-10 mx-auto" : "px-2.5 py-2",
        active
          ? "bg-gradient-to-r from-(--brand-primary)/15 to-(--brand-accent)/10 text-(--brand-primary) dark:text-(--brand-accent) shadow-sm"
          : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
      )}
    >
      {/* Active icon background */}
      <div
        className={cn(
          "flex items-center justify-center rounded-lg transition-all duration-200",
          active
            ? "h-7 w-7 bg-gradient-to-br from-(--brand-accent) to-(--brand-primary) shadow-sm shadow-(--brand-accent)/20"
            : "h-7 w-7 bg-transparent group-hover:bg-muted/30",
          !collapsed && !active && "group-hover:bg-muted/30"
        )}
      >
        <Icon className={cn("h-4 w-4 shrink-0", active ? "text-white" : "")} />
      </div>

      {!collapsed && (
        <span
          className={cn(
            "text-sm truncate transition-all duration-200",
            active ? "font-bold" : "font-medium"
          )}
        >
          {label}
        </span>
      )}

      {/* Badge — expanded */}
      {!collapsed && badge !== undefined && badge > 0 && (
        <span className="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full bg-(--brand-accent) px-1 text-[11px] font-bold text-white shadow-sm">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
      {/* Badge — collapsed */}
      {collapsed && badge !== undefined && badge > 0 && (
        <span className="absolute -top-1 -right-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-(--brand-accent) px-1 text-[8px] font-bold text-white">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </Link>
  );

  if (!collapsed) return link;

  return (
    <TooltipProvider delay={300}>
      <Tooltip>
        <TooltipTrigger>{link}</TooltipTrigger>
        <TooltipContent side="right" className="font-medium">
          {label}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
});
