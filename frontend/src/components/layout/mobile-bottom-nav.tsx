import { Link } from "react-router-dom";
import { useLocation } from "react-router-dom";
import { Home, Users, MessageSquare, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { useBotBox } from "@/components/conversations/bot-box-provider";

const navItems = [
  { label: "Home", href: "/dashboard", icon: Home },
  { label: "Members", href: "/members", icon: Users },
  { label: "AI Chat", href: "/conversations", icon: MessageSquare },
];

export function MobileBottomNav() {
  const { pathname } = useLocation();
  const { open: openBotBox } = useBotBox();

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-background/90 backdrop-blur-xl border-t border-border/50 safe-area-bottom"
      role="navigation"
      aria-label="Mobile navigation"
    >
      <div className="flex items-center justify-around h-16 px-2">
        {navItems.map((item) => {
          const active = pathname.startsWith(item.href);
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
              {/* Active pill background */}
              {active && (
                <div className="absolute inset-x-2 inset-y-0.5 rounded-xl bg-gradient-to-b from-(--brand-accent)/15 to-(--brand-primary)/10" />
              )}

              <div className="relative">
                <div
                  className={cn(
                    "flex items-center justify-center rounded-lg transition-all duration-200",
                    active
                      ? "h-7 w-7 bg-gradient-to-br from-(--brand-accent) to-(--brand-primary) shadow-sm"
                      : ""
                  )}
                >
                  <Icon className={cn("h-5 w-5", active ? "text-white" : "")} />
                </div>
              </div>
              <span
                className={cn(
                  "text-[10px] truncate relative",
                  active
                    ? "font-bold text-(--brand-primary) dark:text-(--brand-accent)"
                    : "font-medium"
                )}
              >
                {item.label}
              </span>
            </Link>
          );
        })}

        {/* AI Assistant button */}
        <button
          onClick={openBotBox}
          aria-label="AI Assistant"
          className={cn(
            "relative flex flex-col items-center justify-center gap-1 min-w-0 flex-1 py-1.5 rounded-xl transition-all duration-200 text-muted-foreground/70 active:text-foreground"
          )}
        >
          <div className="relative">
            <div className="flex items-center justify-center rounded-lg h-7 w-7">
              <Bot className="h-5 w-5" />
            </div>
          </div>
          <span className="text-[10px] truncate font-medium">Assistant</span>
        </button>
      </div>
    </nav>
  );
}
