import { useState, useEffect } from "react";
import { useAppConfig, useUpdateAppConfig } from "@/hooks/useAppConfig";
import { usePollerStatus, useStartPoller, useStopPoller, usePollerLogs, useClearPollerLogs, useSendTestEmail } from "@/hooks/usePoller";
import { type AppConfig } from "@/schemas/claim";
import { cn } from "@/lib/utils";

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-900",
        "disabled:cursor-not-allowed disabled:opacity-40",
        checked ? "bg-blue-600" : "bg-zinc-600"
      )}
    >
      <span
        className={cn(
          "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 mt-0.5",
          checked ? "translate-x-5" : "translate-x-0.5"
        )}
      />
    </button>
  );
}

function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-4 border-b border-border last:border-0">
      <div className="space-y-0.5">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

const POLLER_STATUS_STYLES: Record<string, { dot: string; label: string }> = {
  idle:     { dot: "bg-green-500",  label: "Idle" },
  running:  { dot: "bg-amber-400",  label: "Running" },
  error:    { dot: "bg-red-500",    label: "Error" },
  disabled: { dot: "bg-zinc-500",   label: "Disabled" },
};

function PollerStatusBadge({ status }: { status: string | null }) {
  const style = status ? (POLLER_STATUS_STYLES[status] ?? { dot: "bg-zinc-500", label: status }) : { dot: "bg-zinc-600", label: "Never run" };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("inline-block h-2 w-2 rounded-full", style.dot)} />
      <span className="text-sm text-foreground">{style.label}</span>
    </span>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm text-foreground text-right max-w-xs break-words">{value ?? "—"}</span>
    </div>
  );
}

export function Settings() {
  const { data: config, isLoading } = useAppConfig({ refetchInterval: 15_000 });
  const { mutate: updateConfig, isPending: isSaving } = useUpdateAppConfig();
  const { data: pollerProcess } = usePollerStatus();
  const { mutate: startPoller, isPending: isStarting } = useStartPoller();
  const { mutate: stopPoller, isPending: isStopping } = useStopPoller();
  const { data: logLines = [] } = usePollerLogs(true);
  const { mutate: clearLogs, isPending: isClearing } = useClearPollerLogs();
  const { mutate: sendTestEmail, isPending: isSending, isSuccess: emailSent, isError: emailFailed, error: emailError } = useSendTestEmail();

  const [form, setForm] = useState<Partial<AppConfig>>({});
  const [saved, setSaved] = useState(false);
  const [testForm, setTestForm] = useState({ ref: "9999", adjuster: "Alan", subject: "" });

  // Sync form with loaded config (only on first load)
  useEffect(() => {
    if (config && Object.keys(form).length === 0) {
      setForm({
        dry_run: config.dry_run,
        test_mode: config.test_mode,
        test_adjuster_id: config.test_adjuster_id,
        test_branch_id: config.test_branch_id,
      });
    }
  }, [config, form]);

  const isDirty =
    config &&
    (form.dry_run !== config.dry_run ||
      form.test_mode !== config.test_mode ||
      form.test_adjuster_id !== config.test_adjuster_id ||
      form.test_branch_id !== config.test_branch_id);

  function handleSave() {
    updateConfig(form, {
      onSuccess: () => {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      },
    });
  }

  if (isLoading) {
    return (
      <div className="text-muted-foreground text-sm">Loading settings…</div>
    );
  }

  return (
    <div className="max-w-xl space-y-8">
      {/* Processing section */}
      <section>
        <div className="mb-3">
          <h2 className="text-base font-semibold text-foreground">
            Processing
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Controls how claims are submitted to FileTrac.
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card px-4">
          <SettingRow
            label="Dry Run"
            description="Run the full pipeline but skip the final POST to FileTrac. No billable claim is created."
          >
            <Toggle
              checked={form.dry_run ?? false}
              onChange={(v) => setForm((p) => ({ ...p, dry_run: v }))}
              disabled={isSaving}
            />
          </SettingRow>
        </div>
      </section>

      {/* Test mode section */}
      <section>
        <div className="mb-3">
          <h2 className="text-base font-semibold text-foreground">
            Test Mode
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            When enabled, claims are routed to the test adjuster and test branch
            regardless of what the email specifies.
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card px-4">
          <SettingRow
            label="Enable Test Mode"
            description="Override adjuster and branch with the test account values below."
          >
            <Toggle
              checked={form.test_mode ?? false}
              onChange={(v) => setForm((p) => ({ ...p, test_mode: v }))}
              disabled={isSaving}
            />
          </SettingRow>

          <SettingRow
            label="Test Adjuster ID"
            description="FileTrac user ID for the test adjuster (Bob TEST)."
          >
            <input
              type="text"
              value={form.test_adjuster_id ?? ""}
              onChange={(e) =>
                setForm((p) => ({ ...p, test_adjuster_id: e.target.value }))
              }
              disabled={!form.test_mode || isSaving}
              className={cn(
                "w-28 rounded-md border border-input bg-background px-2.5 py-1 text-sm text-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring",
                "disabled:cursor-not-allowed disabled:opacity-50"
              )}
            />
          </SettingRow>

          <SettingRow
            label="Test Branch ID"
            description="FileTrac branch ID for the TEST branch."
          >
            <input
              type="text"
              value={form.test_branch_id ?? ""}
              onChange={(e) =>
                setForm((p) => ({ ...p, test_branch_id: e.target.value }))
              }
              disabled={!form.test_mode || isSaving}
              className={cn(
                "w-28 rounded-md border border-input bg-background px-2.5 py-1 text-sm text-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring",
                "disabled:cursor-not-allowed disabled:opacity-50"
              )}
            />
          </SettingRow>
        </div>
      </section>

      {/* Poller section */}
      <section>
        <div className="mb-3">
          <h2 className="text-base font-semibold text-foreground">Poller</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Polls the M365 mailbox for new claim emails on each interval.
          </p>
        </div>

        {/* Process control */}
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

        {/* DB heartbeat status */}
        <div className="rounded-lg border border-border bg-card px-4 mt-3">
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

        {/* Log viewer */}
        <div className="mt-3">
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
          <pre className={cn(
            "h-64 overflow-y-auto rounded-lg border border-border bg-zinc-950",
            "px-3 py-2.5 text-[11px] leading-relaxed font-mono text-zinc-300",
            "whitespace-pre-wrap break-all"
          )}>
            {logLines.length === 0
              ? <span className="text-zinc-600">No log output yet. Start the poller to see activity.</span>
              : logLines.join("\n")}
          </pre>
        </div>
      </section>

      {/* Test Email section */}
      <section>
        <div className="mb-3">
          <h2 className="text-base font-semibold text-foreground">Send Test Email</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Injects a mock Acuity claim email into the mailbox for end-to-end testing.
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card px-4">
          <SettingRow label="Claim Ref" description="Reference number appended to TG (e.g. 9999 → TG9999).">
            <input
              type="text"
              value={testForm.ref}
              onChange={(e) => setTestForm((p) => ({ ...p, ref: e.target.value }))}
              placeholder="9999"
              className={cn(
                "w-28 rounded-md border border-input bg-background px-2.5 py-1 text-sm text-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring"
              )}
            />
          </SettingRow>
          <SettingRow label="Adjuster Name" description="Name used in the email salutation.">
            <input
              type="text"
              value={testForm.adjuster}
              onChange={(e) => setTestForm((p) => ({ ...p, adjuster: e.target.value }))}
              placeholder="Alan"
              className={cn(
                "w-36 rounded-md border border-input bg-background px-2.5 py-1 text-sm text-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring"
              )}
            />
          </SettingRow>
          <SettingRow label="Subject" description="Email subject — leave blank to use TG{ref}.">
            <input
              type="text"
              value={testForm.subject}
              onChange={(e) => setTestForm((p) => ({ ...p, subject: e.target.value }))}
              placeholder={`TG${testForm.ref}`}
              className={cn(
                "w-48 rounded-md border border-input bg-background px-2.5 py-1 text-sm text-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring"
              )}
            />
          </SettingRow>
        </div>
        <div className="flex items-center gap-3 mt-3">
          <button
            onClick={() => sendTestEmail({ ...testForm, subject: testForm.subject || "" })}
            disabled={isSending}
            className={cn(
              "rounded-md px-4 py-2 text-sm font-medium transition-colors",
              "bg-blue-600/15 text-blue-400 ring-1 ring-blue-600/30 hover:bg-blue-600/25",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            {isSending ? "Sending…" : "Send Test Email"}
          </button>
          {emailSent && <span className="text-xs text-green-500">Sent — check the mailbox.</span>}
          {emailFailed && (
            <span className="text-xs text-red-400">
              {(emailError as Error)?.message ?? "Failed to send."}
            </span>
          )}
        </div>
      </section>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={!isDirty || isSaving}
          className={cn(
            "rounded-md px-4 py-2 text-sm font-medium transition-colors",
            "bg-primary text-primary-foreground hover:bg-primary/90",
            "disabled:cursor-not-allowed disabled:opacity-50"
          )}
        >
          {isSaving ? "Saving…" : "Save Changes"}
        </button>
        {saved && (
          <span className="text-xs text-green-500">Saved successfully.</span>
        )}
        {config?.updated_at && !isDirty && !saved && (
          <span className="text-xs text-muted-foreground">
            Last saved{" "}
            {new Date(config.updated_at).toLocaleString(undefined, {
              dateStyle: "short",
              timeStyle: "short",
            })}
          </span>
        )}
      </div>
    </div>
  );
}
