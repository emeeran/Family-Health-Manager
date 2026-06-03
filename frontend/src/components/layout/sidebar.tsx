import { useState, useEffect, memo } from "react";
import { useLocation, Link } from "react-router-dom";
import {
  Home,
  Users,
  Stethoscope,
  ClipboardList,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { DawnstarLogo } from "@/components/shared/dawnstar-logo";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const COLLAPSED_KEY = "sidebar-collapsed";

const navItems: NavItem[] = [
  { label: "Home", href: "/", icon: Home },
  { label: "People", href: "/people", icon: Users },
  { label: "Providers", href: "/providers", icon: Stethoscope },
  { label: "Records", href: "/records", icon: ClipboardList },
  { label: "Chat", href: "/chat", icon: MessageSquare },
];

export const Sidebar = memo(function Sidebar() {
  const { pathname } = useLocation();

  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(COLLAPSED_KEY) === "true";
  });

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, String(collapsed));
  }, [collapsed]);

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

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
      {/* Header: Logo + toggle */}
      <div
        className={cn(
          "px-2 pt-4 pb-3 flex items-center border-b border-border/50",
          collapsed ? "flex-col gap-2" : "justify-between"
        )}
      >
        <Link
          to="/"
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

      {/* Navigation */}
      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-1"
        onKeyDown={handleNavKeyDown}
      >
        <div className={collapsed ? "flex flex-col items-center gap-0.5" : "space-y-0.5"}>
          {navItems.map((item) => (
            <SidebarLink
              key={item.href}
              {...item}
              active={isActive(item.href)}
              collapsed={collapsed}
            />
          ))}
        </div>
      </nav>
    </aside>
  );
});

/* ── Nav link ── */
const SidebarLink = memo(function SidebarLink({
  label,
  href,
  icon: Icon,
  active,
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
          ? "bg-primary/10 text-primary font-semibold"
          : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {active && (
        <div className="absolute left-0 top-1/4 bottom-1/4 w-[3px] rounded-full bg-gradient-to-b from-[var(--brand-accent)] to-[var(--brand-primary)]" />
      )}
      {!collapsed && <span className="text-sm truncate">{label}</span>}
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
