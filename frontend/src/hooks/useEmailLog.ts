import { useQuery, keepPreviousData } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import {
  EmailLogDetailSchema,
  EmailLogResponseSchema,
} from "@/schemas/email";

export interface EmailLogParams {
  page?: number;
  page_size?: number;
  status?: string | null;
  triage_status?: string | null;
  search?: string | null;
  from?: string | null;
  to?: string | null;
}

export function useEmailLog(params: EmailLogParams) {
  return useQuery({
    queryKey: ["email-log", params],
    queryFn: async ({ signal }) => {
      const cleanParams = Object.fromEntries(
        Object.entries(params).filter(([, v]) => v != null && v !== "")
      );
      const { data } = await apiClient.get("/email-log", { params: cleanParams, signal });
      return EmailLogResponseSchema.parse(data);
    },
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });
}

export function useEmailLogDetail(id: number | null) {
  return useQuery({
    queryKey: ["email-log", id],
    queryFn: async ({ signal }) => {
      const { data } = await apiClient.get(`/email-log/${id}`, { signal });
      return EmailLogDetailSchema.parse(data);
    },
    enabled: !!id,
    // NOTE: do NOT use staleTime: Infinity — action timeline changes after triage.
    // Invalidate ["email-log", id] in useTriageAction.onSettled instead.
  });
}
