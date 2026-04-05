import { useState, useEffect } from "react";
import { useAppConfig, useUpdateAppConfig } from "@/hooks/useAppConfig";
import {
  usePollerStatus,
  useStartPoller,
  useStopPoller,
  usePollerLogs,
  useClearPollerLogs,
} from "@/hooks/usePoller";
import { InfoRow, PollerStatusBadge } from "@/components/admin/shared";
import { SectionHeading } from "@/components/ui";
import { cn } from "@/lib/utils";

export function Polling() {
  const { data: config } = useAppConfig({ refetchInterval: 5_000 });
  const { data: pollerProcess } = usePollerStatus();
  const { mutate: startPoller, isPending: isStarting } = useStartPoller();
  const { mutate: stopPoller, isPending: isStopping } = useStopPoller();
  const { data: logLines = [] } = usePollerLogs(true);
  const { mutate: clearLogs, isPending: isClearing } = useClearPollerLogs();
  const { mutate: updateConfig, isPending: isSaving } = useUpdateAppConfig();

  const [intervalInput, setIntervalInput] = useState<string>("");
  const [intervalSaved, setIntervalSaved] = useState(false);

  // Sync input when config loads (only on first load)
  useEffect(() => {
    if (config?.poll_interval_seconds !== undefined && intervalInput === "") {
      setIntervalInput(String(config.poll_interval_seconds));
    }
  }, [config?.poll_interval_seconds, intervalInput]);

  function handleSaveInterval() {
    const value = parseInt(intervalInput, 10);
    if (isNaN(value) || value < 10) return;
    updateConfig(
      { poll_interval_seconds: value },
      {
        onSuccess: () => {
          setIntervalSaved(true);
          setTimeout(() => setIntervalSaved(false), 2000);
        },
      }
    );
  }

  const intervalValue = parseInt(intervalInput, 10);
  const intervalValid = !isNaN(intervalValue) && intervalValue >= 10;
  const intervalChanged = intervalValid && intervalValue !== config?.poll_interval_seconds;

  return (
    <div className="max-w-xl space-y-6">
      {/* Process control */}
      <section>
        <SectionHeading title="Poller" description="Polls the M365 mailbox for new claim emails on each interval." />
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

      {/* Configuration */}
      <section>
        <SectionHeading title="Configuration" description="Changes apply immediately — no restart required." />
        <div className="rounded-lg border border-border bg-card px-4">
          <div className="flex items-center justify-between gap-4 py-4">
            <div className="space-y-0.5">
              <p className="text-sm font-medium text-foreground">Poll interval</p>
              <p className="text-xs text-muted-foreground">Seconds between each mailbox check (minimum 10)</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <input
                type="number"
                min={10}
                value={intervalInput}
                onChange={(e) => setIntervalInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSaveInterval()}
                className={cn(
                  "w-20 rounded-md border bg-zinc-900 px-2.5 py-1.5 text-sm text-right tabular-nums",
                  "text-foreground placeholder:text-muted-foreground",
                  "focus:outline-none focus:ring-1 focus:ring-blue-500",
                  !isNaN(intervalValue) && intervalValue < 10
                    ? "border-red-500/60"
                    : "border-border"
                )}
              />
              <span className="text-xs text-muted-foreground">s</span>
              <button
                onClick={handleSaveInterval}
                disabled={isSaving || !intervalChanged}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  intervalSaved
                    ? "bg-green-600/15 text-green-400 ring-1 ring-green-600/30"
                    : intervalChanged
                    ? "bg-blue-600/15 text-blue-400 ring-1 ring-blue-600/30 hover:bg-blue-600/25"
                    : "bg-zinc-800 text-zinc-500 ring-1 ring-zinc-700",
                  "disabled:cursor-default"
                )}
              >
                {isSaving ? "Saving…" : intervalSaved ? "Saved" : intervalChanged ? "Save" : "Current"}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Status */}
      <section>
        <SectionHeading title="Status" />
        <div className="rounded-lg border border-border bg-card px-4">
          <InfoRow
            label="Poll status"
            value={<PollerStatusBadge status={config?.poller_status ?? null} />}
          />
          <InfoRow
            label="Poll interval"
            value={
              config?.poll_interval_seconds != null
                ? `${config.poll_interval_seconds}s`
                : null
            }
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
            Log output — last 200 lines
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
