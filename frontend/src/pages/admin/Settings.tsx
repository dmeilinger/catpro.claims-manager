import { useState, useEffect } from "react";
import { useAppConfig, useUpdateAppConfig } from "@/hooks/useAppConfig";
import { Toggle, SettingRow } from "@/components/admin/shared";
import { cn } from "@/lib/utils";

export function AdminSettings() {
  const { data: config, isLoading } = useAppConfig();
  const { mutate: updateConfig, isPending: isSaving } = useUpdateAppConfig();

  const [dryRun, setDryRun] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (config) setDryRun(config.dry_run);
  }, [config]);

  const isDirty = config && dryRun !== config.dry_run;

  function handleSave() {
    updateConfig({ dry_run: dryRun }, {
      onSuccess: () => {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      },
    });
  }

  if (isLoading) {
    return <div className="text-muted-foreground text-sm">Loading…</div>;
  }

  return (
    <div className="max-w-xl space-y-8">
      <section>
        <div className="mb-3">
          <h2 className="text-base font-semibold text-foreground">Processing</h2>
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
              checked={dryRun}
              onChange={setDryRun}
              disabled={isSaving}
            />
          </SettingRow>
        </div>
      </section>

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
        {saved && <span className="text-xs text-green-500">Saved successfully.</span>}
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
