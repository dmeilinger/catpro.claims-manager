import { useQuery, keepPreviousData } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import {
  ClaimListResponseSchema,
  ClaimDetailSchema,
  ClaimTrendsSchema,
  type ClaimListResponse,
  type ClaimDetail,
  type ClaimTrends,
} from "@/schemas/claim";

export interface ClaimFilters {
  page?: number;
  page_size?: number;
  status?: string | null;
  from?: string | null;
  to?: string | null;
  search?: string | null;
  sort_by?: string;
  sort_order?: string;
}

export function useClaims(filters: ClaimFilters) {
  return useQuery<ClaimListResponse>({
    queryKey: ["claims", filters],
    queryFn: async ({ signal }) => {
      const params: Record<string, string | number> = {};
      if (filters.page) params.page = filters.page;
      if (filters.page_size) params.page_size = filters.page_size;
      if (filters.status) params.status = filters.status;
      if (filters.from) params.from = filters.from;
      if (filters.to) params.to = filters.to;
      if (filters.search) params.search = filters.search;
      if (filters.sort_by) params.sort_by = filters.sort_by;
      if (filters.sort_order) params.sort_order = filters.sort_order;
      const { data } = await apiClient.get("/claims", { params, signal });
      return ClaimListResponseSchema.parse(data);
    },
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });
}

export function useClaimDetail(id: number | null) {
  return useQuery<ClaimDetail>({
    queryKey: ["claims", id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/claims/${id}`);
      return ClaimDetailSchema.parse(data);
    },
    enabled: !!id,
    staleTime: Infinity,
  });
}

export function useClaimTrends(from?: string, to?: string) {
  return useQuery<ClaimTrends>({
    queryKey: ["claims", "trends", { from, to }],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (from) params.from = from;
      if (to) params.to = to;
      const { data } = await apiClient.get("/claims/trends", { params });
      return ClaimTrendsSchema.parse(data);
    },
    refetchInterval: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
}
