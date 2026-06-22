import { useState, useEffect } from "react";
import { useLocation, Link, useNavigate } from "react-router-dom";
import { ChevronRight, LogOut, Search, Settings, Bell } from "lucide-react";
import useSWR from "swr";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { MobileSidebar } from "./mobile-sidebar";
import { GlobalSearch } from "@/components/shared/global-search";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { clearToken } from "@/lib/auth";
import { getMe } from "@/lib/api/auth";
import { mutate } from "swr";
import { UUID_RE } from "@/lib/utils";
import { getMember } from "@/lib/api/members";
import { getProvider } from "@/lib/api/providers";
import { useNotifications } from "@/hooks/use-notifications";

const STATIC_LABELS: Record<string, string> = {
  home: "Home",
  people: "People",
  records: "Records",
  chat: "Chat",
  new: "New",
  edit: "Edit",
  providers: "Providers",
  reminders: "Reminders",
  settings: "Settings",
  onboarding: "Onboarding",
};

function useBreadcrumbLabel(segment: string, parentSegment: string | undefined) {
  const isUuid = UUID_RE.test(segment);

  const { data } = useSWR(
    isUuid ? `breadcrumb-${segment}` : null,
    async () => {
      try {
        if (parentSegment === "members" || parentSegment === "people") {
          const m = await getMember(segment);
          return `${m.first_name} ${m.last_name}`;
        }
        if (parentSegment === "providers") {
          const p = await getProvider(segment);
          return p.name;
        }
      } catch {
        // API call failed — fall back to shortened UUID
      }
      return segment.slice(0, 8) + "...";
    },
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  );

  return STATIC_LABELS[segment] || data || segment;
}

function Breadcrumb() {
  const { pathname } = useLocation();
  const segments = pathname.split("/").filter(Boolean);

  return (
    <nav className="flex-1 flex items-center gap-0.5 text-sm text-muted-foreground overflow-x-auto scrollbar-none">
      {segments.map((segment, i) => {
        const href = "/" + segments.slice(0, i + 1).join("/");
        const isLast = i === segments.length - 1;
        const parent = i > 0 ? segments[i - 1] : undefined;
        return (
          <BreadcrumbItem
            key={href}
            segment={segment}
            href={href}
            isLast={isLast}
            parent={parent}
          />
        );
      })}
    </nav>
  );
}

function BreadcrumbItem({
  segment,
  href,
  isLast,
  parent,
}: {
  segment: string;
  href: string;
  isLast: boolean;
  parent: string | undefined;
}) {
  const label = useBreadcrumbLabel(segment, parent);
  return (
    <span className="flex items-center gap-0.5 shrink-0">
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/30" />
      {isLast ? (
        <span className="text-foreground font-semibold px-1">{label}</span>
      ) : (
        <Link to={href} className="px-1 hover:text-foreground transition-colors">
          {label}
        </Link>
      )}
    </span>
  );
}

export function Header() {
  const [searchOpen, setSearchOpen] = useState(false);
  const _navigate = useNavigate();

  const { data: user } = useSWR(
    "current-user",
    async () => {
      try {
        return await getMe();
      } catch {
        return null;
      }
    },
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  );

  const initials = user?.username ? user.username.slice(0, 2).toUpperCase() : "U";
  const { unreadCount } = useNotifications();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <>
      <header className="flex h-13 items-center gap-3 border-b bg-background/80 backdrop-blur-lg px-4 md:px-6 sticky top-0 z-30">
        <MobileSidebar />
        <Breadcrumb />
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => setSearchOpen(true)}
            className="hidden md:inline-flex items-center gap-2 rounded-lg border border-border/60 bg-background/50 px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted/50 hover:text-foreground hover:border-border transition-all duration-200"
            aria-label="Open search"
          >
            <Search className="h-3.5 w-3.5" />
            <span className="text-xs">Search</span>
            <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-0.5 rounded border bg-muted px-1 font-mono text-[10px] font-medium text-muted-foreground">
              <span className="text-xs">⌘</span>K
            </kbd>
          </button>
          <button
            onClick={() => setSearchOpen(true)}
            className="md:hidden rounded-lg p-2 text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors"
            aria-label="Open search"
          >
            <Search className="h-4 w-4" />
          </button>
          <button
            className="relative rounded-lg p-2 text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors"
            aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
            onClick={() => {
              // Notifications are shown via toast/toaster; bell is visual indicator only
            }}
          >
            <Bell className="h-4 w-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-(--brand-accent) px-1 text-[11px] font-bold text-white ring-2 ring-background">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>
          <ThemeToggle />
          <DropdownMenu>
            <DropdownMenuTrigger className="focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-full">
              <div className="relative">
                <Avatar className="h-8 w-8 ring-2 ring-background transition-shadow hover:shadow-md">
                  <AvatarFallback className="text-[11px] bg-gradient-to-br from-(--brand-accent) to-(--brand-primary) text-white font-bold">
                    {initials}
                  </AvatarFallback>
                </Avatar>
                <div className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-background" />
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <div className="px-2 py-1.5">
                <p className="text-sm font-medium">{user?.username || "User"}</p>
                <p className="text-xs text-muted-foreground">Family Admin</p>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                render={<Link to="/settings" className="flex items-center gap-2 cursor-pointer" />}
              >
                <Settings className="h-4 w-4" />
                Settings
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 text-destructive focus:text-destructive"
                  onClick={() => {
                    mutate(() => true, undefined, { revalidate: false });
                    clearToken();
                  }}
                >
                  <LogOut className="h-4 w-4" />
                  Sign Out
                </button>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>
      <GlobalSearch open={searchOpen} onOpenChange={setSearchOpen} />
    </>
  );
}
