import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/utils";

interface ModeChipProps {
  label: string;
  tooltip: string;
  color: "amber" | "violet";
}

function ModeChip({ label, tooltip, color }: ModeChipProps) {
  return (
    <div className="relative group">
      <span
        className={cn(
          "inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider cursor-default select-none",
          color === "amber"
            ? "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30"
            : "bg-violet-500/15 text-violet-400 ring-1 ring-violet-500/30"
        )}
      >
        {label}
      </span>
      {/* Tooltip */}
      <div
        className={cn(
          "absolute right-0 top-full mt-2 z-50 w-56 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2.5 shadow-xl",
          "text-xs text-zinc-200 leading-relaxed",
          "opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-150"
        )}
      >
        {tooltip}
        <div className="absolute -top-1.5 right-3 w-3 h-3 rotate-45 border-l border-t border-zinc-700 bg-zinc-900" />
      </div>
    </div>
  );
}

interface TopBarProps {
  title: string;
  healthStatus?: string | null;
  lastProcessedAt?: string | null;
  dryRun?: boolean;
  testMode?: boolean;
}

export function TopBar({
  title,
  healthStatus,
  lastProcessedAt,
  dryRun,
  testMode,
}: TopBarProps) {
  const isOk = healthStatus === "ok";
  const isDegraded = healthStatus === "degraded";

  return (
    <header className="h-14 border-b border-border flex items-center justify-between px-6">
      <h1 className="text-base font-semibold text-foreground">{title}</h1>
      <div className="flex items-center gap-3">
        {/* Mode indicators */}
        {testMode && (
          <ModeChip
            label="TEST"
            color="violet"
            tooltip="Test Mode is on — claims are routed to Bob TEST (adjuster 342436) and the TEST branch instead of real IDs."
          />
        )}
        {dryRun && (
          <ModeChip
            label="DRY RUN"
            color="amber"
            tooltip="Dry Run is on — the full pipeline runs but the final POST to FileTrac is skipped. No billable claim is created."
          />
        )}

        {/* Health indicator */}
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
            <span
              className={cn(
                "font-medium",
                isOk && "text-success",
                isDegraded && "text-warning",
                !isOk && !isDegraded && "text-muted-foreground"
              )}
            >
              Poller{" "}
              {healthStatus === "ok"
                ? "OK"
                : healthStatus === "degraded"
                  ? "STALE"
                  : "Unknown"}
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
