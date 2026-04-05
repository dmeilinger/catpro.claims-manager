import { z } from "zod";

export const AppConfigSchema = z.object({
  dry_run: z.boolean(),
  test_mode: z.boolean(),
  test_adjuster_id: z.string(),
  test_branch_id: z.string(),
  updated_at: z.string().nullable(),
  poller_enabled: z.boolean().default(true),
  poll_interval_seconds: z.number().int().min(10).default(60),
  poller_status: z.string().nullable().default(null),
  last_heartbeat: z.string().nullable().default(null),
  last_run_at: z.string().nullable().default(null),
  last_error: z.string().nullable().default(null),
});

export type AppConfig = z.infer<typeof AppConfigSchema>;

export const ClaimStatsSchema = z.object({
  total: z.number(),
  success: z.number(),
  error: z.number(),
  pending: z.number(),
  dry_run: z.number(),
  success_rate: z.number().nullable(),
});

export const ClaimSummarySchema = z.object({
  id: z.number(),
  subject: z.string().nullable(),
  sender: z.string().nullable(),
  received_at: z.string().nullable(),
  processed_at: z.string(),
  claim_id: z.string().nullable(),
  status: z.string(),
  dry_run: z.boolean(),
  error_message: z.string().nullable(),
  insured_first_name: z.string().nullable(),
  insured_last_name: z.string().nullable(),
  insured_name: z.string().nullable(),
});

export const ClaimListResponseSchema = z.object({
  items: z.array(ClaimSummarySchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  stats: ClaimStatsSchema,
  last_processed_at: z.string().nullable(),
});

export const ClaimDataSchema = z.object({
  insured_first_name: z.string().nullable(),
  insured_last_name: z.string().nullable(),
  insured_email: z.string().nullable(),
  insured_phone: z.string().nullable(),
  insured_cell: z.string().nullable(),
  insured_address1: z.string().nullable(),
  insured_city: z.string().nullable(),
  insured_state: z.string().nullable(),
  insured_zip: z.string().nullable(),
  secondary_insured_first: z.string().nullable(),
  secondary_insured_last: z.string().nullable(),
  policy_number: z.string().nullable(),
  policy_effective: z.string().nullable(),
  policy_expiration: z.string().nullable(),
  loss_date: z.string().nullable(),
  loss_type: z.string().nullable(),
  loss_description: z.string().nullable(),
  loss_address1: z.string().nullable(),
  loss_city: z.string().nullable(),
  loss_state: z.string().nullable(),
  loss_zip: z.string().nullable(),
  client_company_name: z.string().nullable(),
  client_claim_number: z.string().nullable(),
  agent_company: z.string().nullable(),
  agent_phone: z.string().nullable(),
  agent_email: z.string().nullable(),
  agent_address1: z.string().nullable(),
  agent_city: z.string().nullable(),
  agent_state: z.string().nullable(),
  agent_zip: z.string().nullable(),
  assigned_adjuster_name: z.string().nullable(),
});

export const ClaimDetailSchema = z.object({
  id: z.number(),
  subject: z.string().nullable(),
  sender: z.string().nullable(),
  received_at: z.string().nullable(),
  processed_at: z.string(),
  claim_id: z.string().nullable(),
  status: z.string(),
  dry_run: z.boolean(),
  error_message: z.string().nullable(),
  claim_data: ClaimDataSchema.nullable(),
  resolved_ids: z.record(z.string(), z.string().nullable()).nullable(),
  submission_payload: z.record(z.string(), z.unknown()).nullable(),
});

export const TrendPointSchema = z.object({
  date: z.string(),
  total: z.number(),
  success: z.number(),
  error: z.number(),
});

export const ClaimTrendsSchema = z.object({
  data: z.array(TrendPointSchema),
});

export const HealthResponseSchema = z.object({
  status: z.string(),
  last_processed_at: z.string().nullable(),
  recent_error_rate: z.number().nullable(),
  poll_interval: z.number(),
});

export const PollerProcessStatusSchema = z.object({
  running: z.boolean(),
  pid: z.number().nullable(),
});

export type PollerProcessStatus = z.infer<typeof PollerProcessStatusSchema>;

// Inferred types
export type ClaimStats = z.infer<typeof ClaimStatsSchema>;
export type ClaimSummary = z.infer<typeof ClaimSummarySchema>;
export type ClaimListResponse = z.infer<typeof ClaimListResponseSchema>;
export type ClaimData = z.infer<typeof ClaimDataSchema>;
export type ClaimDetail = z.infer<typeof ClaimDetailSchema>;
export type TrendPoint = z.infer<typeof TrendPointSchema>;
export type ClaimTrends = z.infer<typeof ClaimTrendsSchema>;
export type HealthResponse = z.infer<typeof HealthResponseSchema>;
