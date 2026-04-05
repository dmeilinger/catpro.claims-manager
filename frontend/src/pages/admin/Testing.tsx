import { useState, useEffect } from "react";
import { useAppConfig, useUpdateAppConfig } from "@/hooks/useAppConfig";
import { useSendTestEmail } from "@/hooks/usePoller";
import { Toggle, SettingRow } from "@/components/admin/shared";
import { SectionHeading } from "@/components/ui";
import { type AppConfig } from "@/schemas/claim";
import { cn } from "@/lib/utils";

export function Testing() {
  const { data: config, isLoading } = useAppConfig();
  const { mutate: updateConfig, isPending: isSaving } = useUpdateAppConfig();
  const {
    mutate: sendTestEmail,
    isPending: isSending,
    isSuccess: emailSent,
    isError: emailFailed,
    error: emailError,
  } = useSendTestEmail();

  const [form, setForm] = useState<Partial<AppConfig>>({});
  const [saved, setSaved] = useState(false);
  const [testForm, setTestForm] = useState({
    ref: "9999",
    adjuster: "Alan",
    subject: "",
  });

  useEffect(() => {
    if (config && Object.keys(form).length === 0) {
      setForm({
        test_mode: config.test_mode,
        test_adjuster_id: config.test_adjuster_id,
        test_branch_id: config.test_branch_id,
      });
    }
  }, [config, form]);

  const isDirty =
    config &&
    (form.test_mode !== config.test_mode ||
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
    return <div className="text-muted-foreground text-sm">Loading…</div>;
  }

  return (
    <div className="max-w-xl space-y-8">
      {/* Test mode */}
      <section>
        <SectionHeading title="Test Mode" description="When enabled, claims are routed to the test adjuster and test branch regardless of what the email specifies." />
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

      {/* Send test email */}
      <section>
        <SectionHeading title="Send Test Email" description="Injects a mock Acuity claim email into the mailbox for end-to-end testing." />
        <div className="rounded-lg border border-border bg-card px-4">
          <SettingRow
            label="Claim Ref"
            description="Reference number appended to TG (e.g. 9999 → TG9999)."
          >
            <input
              type="text"
              value={testForm.ref}
              onChange={(e) =>
                setTestForm((p) => ({ ...p, ref: e.target.value }))
              }
              placeholder="9999"
              className={cn(
                "w-28 rounded-md border border-input bg-background px-2.5 py-1 text-sm text-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring"
              )}
            />
          </SettingRow>
          <SettingRow
            label="Adjuster Name"
            description="Name used in the email salutation."
          >
            <input
              type="text"
              value={testForm.adjuster}
              onChange={(e) =>
                setTestForm((p) => ({ ...p, adjuster: e.target.value }))
              }
              placeholder="Alan"
              className={cn(
                "w-36 rounded-md border border-input bg-background px-2.5 py-1 text-sm text-foreground",
                "focus:outline-none focus:ring-1 focus:ring-ring"
              )}
            />
          </SettingRow>
          <SettingRow
            label="Subject"
            description="Email subject — leave blank to use TG{ref}."
          >
            <input
              type="text"
              value={testForm.subject}
              onChange={(e) =>
                setTestForm((p) => ({ ...p, subject: e.target.value }))
              }
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
            onClick={() =>
              sendTestEmail({ ...testForm, subject: testForm.subject || "" })
            }
            disabled={isSending}
            className={cn(
              "rounded-md px-4 py-2 text-sm font-medium transition-colors",
              "bg-blue-600/15 text-blue-400 ring-1 ring-blue-600/30 hover:bg-blue-600/25",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            {isSending ? "Sending…" : "Send Test Email"}
          </button>
          {emailSent && (
            <span className="text-xs text-green-500">
              Sent — check the mailbox.
            </span>
          )}
          {emailFailed && (
            <span className="text-xs text-red-400">
              {(emailError as Error)?.message ?? "Failed to send."}
            </span>
          )}
        </div>
      </section>
    </div>
  );
}
