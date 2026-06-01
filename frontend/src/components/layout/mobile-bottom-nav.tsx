import { Link, useLocation } from "react-router-dom";
import { Home, Users, ClipboardList, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Home", href: "/", icon: Home },
  { label: "People", href: "/people", icon: Users },
  { label: "Records", href: "/records", icon: ClipboardList },
  { label: "Chat", href: "/chat", icon: MessageSquare },
];

export function MobileBottomNav() {
  const { pathname } = useLocation();

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-background/90 backdrop-blur-xl border-t border-border/50 safe-area-bottom"
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
              {active && (
                <div className="absolute inset-x-2 inset-y-0.5 rounded-xl bg-primary/10" />
              )}
              <div className="relative">
                <Icon className={cn("h-5 w-5", active ? "text-primary" : "")} />
              </div>
              <span
                className={cn(
                  "text-[10px] truncate relative",
                  active ? "font-bold text-primary" : "font-medium"
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
