import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/utils";

interface TopBarProps {
  title: string;
  healthStatus?: string | null;
  lastProcessedAt?: string | null;
}

export function TopBar({ title, healthStatus, lastProcessedAt }: TopBarProps) {
  const isOk = healthStatus === "ok";
  const isDegraded = healthStatus === "degraded";

  return (
    <header className="h-14 border-b border-border flex items-center justify-between px-6">
      <h1 className="text-base font-semibold text-foreground">{title}</h1>
      <div className="flex items-center gap-3">
        {healthStatus && (
          <div className="flex items-center gap-2 text-xs">
            <span
              className={cn(
                "w-2 h-2 rounded-full",
                isOk && "bg-success",
                isDegraded && "bg-warning",
                !isOk && !isDegraded && "bg-muted-foreground"
              )}
            />
            <span className={cn(
              "font-medium",
              isOk && "text-success",
              isDegraded && "text-warning",
              !isOk && !isDegraded && "text-muted-foreground"
            )}>
              Poller {healthStatus === "ok" ? "OK" : healthStatus === "degraded" ? "STALE" : "Unknown"}
            </span>
          </div>
        )}
        {lastProcessedAt && (
          <span className="text-xs text-muted-foreground">
            Updated {timeAgo(lastProcessedAt)}
          </span>
        )}
      </div>
    </header>
  );
}
