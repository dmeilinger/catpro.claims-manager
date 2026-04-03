import { useState, useEffect } from "react";
import { useAppConfig, useUpdateAppConfig } from "@/hooks/useAppConfig";
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

export function Settings() {
  const { data: config, isLoading } = useAppConfig();
  const { mutate: updateConfig, isPending: isSaving } = useUpdateAppConfig();

  const [form, setForm] = useState<Partial<AppConfig>>({});
  const [saved, setSaved] = useState(false);

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
