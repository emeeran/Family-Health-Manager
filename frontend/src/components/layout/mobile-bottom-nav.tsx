import { Link, useLocation } from "react-router-dom";
import { Home, Users, Stethoscope, ClipboardList, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Home", href: "/", icon: Home },
  { label: "People", href: "/people", icon: Users },
  { label: "Providers", href: "/providers", icon: Stethoscope },
  { label: "Records", href: "/records", icon: ClipboardList },
  { label: "Chat", href: "/chat", icon: MessageSquare },
];

export function MobileBottomNav() {
  const { pathname } = useLocation();

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-background/80 backdrop-blur-xl border-t border-border/50 safe-area-bottom"
      role="navigation"
      aria-label="Mobile navigation"
    >
      <div className="flex items-center justify-around h-16 px-2">
        {navItems.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              to={item.href}
              aria-current={active ? "page" : undefined}
              aria-label={item.label}
              className={cn(
                "relative flex flex-col items-center justify-center gap-1 min-w-0 flex-1 py-1.5 rounded-xl transition-all duration-200",
                active ? "" : "text-muted-foreground/70 active:text-foreground"
              )}
            >
              <div className="relative" style={active ? { transform: "scale(1.05)" } : undefined}>
                <Icon className={cn("h-5 w-5", active ? "text-[var(--brand-accent)]" : "")} />
              </div>
              {active && <div className="h-[3px] w-[3px] rounded-full bg-[var(--brand-accent)]" />}
              <span
                className={cn(
                  "text-[10px] truncate relative",
                  active ? "font-bold text-[var(--brand-accent)]" : "font-medium"
                )}
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
