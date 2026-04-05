import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { AppConfigSchema, type AppConfig } from "@/schemas/claim";

export function useAppConfig(options?: { refetchInterval?: number }) {
  return useQuery<AppConfig>({
    queryKey: ["config"],
    queryFn: async () => {
      const { data } = await apiClient.get("/config");
      return AppConfigSchema.parse(data);
    },
    staleTime: 30_000,
    refetchInterval: options?.refetchInterval,
  });
}

export function useUpdateAppConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (updates: Partial<AppConfig>) => {
      const { data } = await apiClient.put("/config", updates);
      return AppConfigSchema.parse(data);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["config"], updated);
    },
  });
}
