import { useAppConfig } from "@/hooks/useAppConfig";
import {
  usePollerStatus,
  useStartPoller,
  useStopPoller,
  usePollerLogs,
  useClearPollerLogs,
} from "@/hooks/usePoller";
import { InfoRow, PollerStatusBadge } from "@/components/admin/shared";
import { cn } from "@/lib/utils";

export function Polling() {
  const { data: config } = useAppConfig({ refetchInterval: 5_000 });
  const { data: pollerProcess } = usePollerStatus();
  const { mutate: startPoller, isPending: isStarting } = useStartPoller();
  const { mutate: stopPoller, isPending: isStopping } = useStopPoller();
  const { data: logLines = [] } = usePollerLogs(true);
  const { mutate: clearLogs, isPending: isClearing } = useClearPollerLogs();

  return (
    <div className="max-w-xl space-y-6">
      {/* Process control */}
      <section>
        <div className="mb-3">
          <h2 className="text-base font-semibold text-foreground">Poller</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Polls the M365 mailbox for new claim emails on each interval.
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card px-4">
          <div className="flex items-center justify-between gap-4 py-4">
            <div className="flex items-center gap-2.5">
              <span
                className={cn(
                  "inline-block h-2.5 w-2.5 rounded-full",
                  pollerProcess?.running ? "bg-green-500" : "bg-zinc-500"
                )}
              />
              <span className="text-sm font-medium text-foreground">
                {pollerProcess?.running
                  ? `Running${pollerProcess.pid ? ` · PID ${pollerProcess.pid}` : ""}`
                  : "Stopped"}
              </span>
            </div>
            {pollerProcess?.running ? (
              <button
                onClick={() => stopPoller()}
                disabled={isStopping}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  "bg-red-600/15 text-red-400 ring-1 ring-red-600/30 hover:bg-red-600/25",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
              >
                {isStopping ? "Stopping…" : "Stop"}
              </button>
            ) : (
              <button
                onClick={() => startPoller()}
                disabled={isStarting}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  "bg-green-600/15 text-green-400 ring-1 ring-green-600/30 hover:bg-green-600/25",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
              >
                {isStarting ? "Starting…" : "Start"}
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Status */}
      <section>
        <div className="mb-3">
          <h2 className="text-base font-semibold text-foreground">Status</h2>
        </div>
        <div className="rounded-lg border border-border bg-card px-4">
          <InfoRow
            label="Poll status"
            value={<PollerStatusBadge status={config?.poller_status ?? null} />}
          />
          <InfoRow
            label="Last heartbeat"
            value={
              config?.last_heartbeat
                ? new Date(config.last_heartbeat).toLocaleString(undefined, {
                    dateStyle: "short",
                    timeStyle: "medium",
                  })
                : null
            }
          />
          <InfoRow
            label="Last run"
            value={
              config?.last_run_at
                ? new Date(config.last_run_at).toLocaleString(undefined, {
                    dateStyle: "short",
                    timeStyle: "medium",
                  })
                : null
            }
          />
          {config?.last_error && (
            <InfoRow
              label="Last error"
              value={
                <span className="text-red-400 font-mono text-xs">
                  {config.last_error}
                </span>
              }
            />
          )}
        </div>
      </section>

      {/* Log viewer */}
      <section>
        <div className="flex items-center justify-between mb-1.5">
          <p className="text-xs text-muted-foreground">
            Log output — last 200 lines, refreshes every 5s
          </p>
          <button
            onClick={() => clearLogs()}
            disabled={isClearing || logLines.length === 0}
            className={cn(
              "rounded px-2 py-0.5 text-xs font-medium transition-colors",
              "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800",
              "disabled:cursor-not-allowed disabled:opacity-40"
            )}
          >
            {isClearing ? "Clearing…" : "Clear"}
          </button>
        </div>
        <pre
          className={cn(
            "h-96 overflow-y-auto rounded-lg border border-border bg-zinc-950",
            "px-3 py-2.5 text-[11px] leading-relaxed font-mono text-zinc-300",
            "whitespace-pre-wrap break-all"
          )}
        >
          {logLines.length === 0 ? (
            <span className="text-zinc-600">
              No log output yet. Start the poller to see activity.
            </span>
          ) : (
            logLines.join("\n")
          )}
        </pre>
      </section>
    </div>
  );
}
