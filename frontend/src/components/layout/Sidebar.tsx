import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  Settings,
  Activity,
  Radio,
  FlaskConical,
  ChevronLeft,
  ChevronRight,
  Inbox,
  History,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useInboxCount } from "@/hooks/useInbox";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/claims", icon: FileText, label: "Claims" },
  { to: "/inbox", icon: Inbox, label: "Inbox" },
];

const adminItems = [
  { to: "/admin/settings", icon: Settings, label: "Settings" },
  { to: "/admin/polling", icon: Radio, label: "Polling" },
  { to: "/admin/testing", icon: FlaskConical, label: "Testing" },
  { to: "/admin/email-history", icon: History, label: "Email History" },
];

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { data: inboxCountData } = useInboxCount();
  const inboxCount = inboxCountData?.count ?? 0;

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 h-full bg-background border-r border-border flex flex-col z-30 transition-all duration-200",
        collapsed ? "w-14" : "w-56"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-3 border-b border-border">
        {!collapsed && (
          <span className="text-sm font-semibold text-foreground tracking-wide">
            CatPro Claims
          </span>
        )}
        <button
          onClick={onToggle}
          className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-3 px-2.5 py-2 rounded-md text-sm transition-colors",
                isActive
                  ? "bg-primary/10 text-primary border-l-2 border-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              )
            }
          >
            <Icon size={18} />
            {!collapsed && <span>{label}</span>}
            {/* Inbox badge — amber work-queue indicator, not an error */}
            {to === "/inbox" && !collapsed && inboxCount > 0 && (
              <span className={cn(
                "ml-auto flex h-5 min-w-[1.25rem] items-center justify-center",
                "rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white tabular-nums"
              )}>
                {inboxCount > 99 ? "99+" : inboxCount}
              </span>
            )}
            {to === "/inbox" && collapsed && inboxCount > 0 && (
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-amber-500" />
            )}
          </NavLink>
        ))}

        {/* Admin section */}
        <div className="pt-4">
          {!collapsed && (
            <p className="px-2.5 pb-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Admin
            </p>
          )}
          {adminItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-2.5 py-2 rounded-md text-sm transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary border-l-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                )
              }
            >
              <Icon size={18} />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Footer */}
      <div className="px-2 py-3 border-t border-border">
        <NavLink
          to="/health"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 px-2.5 py-2 rounded-md text-sm transition-colors",
              isActive
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            )
          }
        >
          <Activity size={18} />
          {!collapsed && <span>System Health</span>}
        </NavLink>
      </div>
    </aside>
  );
}
