import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { useHealth } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

const pageTitles: Record<string, string> = {
  "/": "Dashboard",
  "/claims": "Claims",
  "/settings/adjusters": "Adjusters",
  "/health": "System Health",
};

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const { data: health } = useHealth();

  const title = pageTitles[location.pathname] || "CatPro Claims";

  return (
    <div className="min-h-screen bg-background">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <div
        className={cn(
          "transition-all duration-200",
          collapsed ? "ml-14" : "ml-56"
        )}
      >
        <TopBar
          title={title}
          healthStatus={health?.status}
          lastProcessedAt={health?.last_processed_at}
        />
        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
