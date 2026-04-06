import { z } from "zod";

export const EmailActionSchema = z.object({
  id: z.number().int(),
  action_type: z.string(),
  actor: z.string(),
  details: z.record(z.string(), z.unknown()).nullable(),
  created_at: z.string(),
});

export const InboxEntrySchema = z.object({
  id: z.number().int(),
  subject: z.string().nullable(),
  sender: z.string().nullable(),
  received_at: z.string().nullable(),
  processed_at: z.string(),
  status: z.string(),
  triage_status: z.string(),
  dry_run: z.boolean().default(false),
  error_message: z.string().nullable(),
  error_traceback: z.string().nullish(),
  error_phase: z.string().nullish(),
  insured_name: z.string().nullable(),
});

export const InboxCountSchema = z.object({ count: z.number().int() });

export const InboxResponseSchema = z.object({
  items: z.array(InboxEntrySchema),
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
});

export const EmailLogStatsSchema = z.object({
  total: z.number().int(),
  success: z.number().int(),
  dry_run: z.number().int(),
  skipped: z.number().int(),
  error: z.number().int(),
  // needs_review intentionally absent — use useInboxCount() for that
});

export const EmailLogEntrySchema = z.object({
  id: z.number().int(),
  subject: z.string().nullable(),
  sender: z.string().nullable(),
  received_at: z.string().nullable(),
  processed_at: z.string(),
  status: z.string(),
  triage_status: z.string(),
  dry_run: z.boolean().default(false),
  claim_id: z.string().nullable(),
  error_message: z.string().nullable(),
  error_traceback: z.string().nullish(),
  error_phase: z.string().nullish(),
  insured_name: z.string().nullable(),
  body_text: z.string().nullish(),
});

export const EmailLogDetailSchema = EmailLogEntrySchema.extend({
  actions: z.array(EmailActionSchema).default([]),
});

export const EmailLogResponseSchema = z.object({
  items: z.array(EmailLogEntrySchema),
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
  stats: EmailLogStatsSchema,
});

// Types
export type TriageAction = "flag_review" | "dismiss" | "approve";
export type EmailAction = z.infer<typeof EmailActionSchema>;
export type InboxEntry = z.infer<typeof InboxEntrySchema>;
export type InboxResponse = z.infer<typeof InboxResponseSchema>;
export type EmailLogEntry = z.infer<typeof EmailLogEntrySchema>;
export type EmailLogDetail = z.infer<typeof EmailLogDetailSchema>;
export type EmailLogResponse = z.infer<typeof EmailLogResponseSchema>;
export type EmailLogStats = z.infer<typeof EmailLogStatsSchema>;
