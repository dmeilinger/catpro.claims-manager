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
} from "lucide-react";
import { cn } from "@/lib/utils";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/claims", icon: FileText, label: "Claims" },
];

const adminItems = [
  { to: "/admin/settings", icon: Settings, label: "Settings" },
  { to: "/admin/polling", icon: Radio, label: "Polling" },
  { to: "/admin/testing", icon: FlaskConical, label: "Testing" },
];

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
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
