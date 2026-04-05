import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { HealthResponseSchema, type HealthResponse } from "@/schemas/claim";

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: async () => {
      const { data } = await apiClient.get("/health");
      return HealthResponseSchema.parse(data);
    },
    refetchInterval: 60_000,
  });
}
