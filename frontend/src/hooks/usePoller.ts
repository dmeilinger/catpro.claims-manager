import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { PollerProcessStatusSchema, type PollerProcessStatus } from "@/schemas/claim";
import { z } from "zod";

const PollerLogsSchema = z.object({ lines: z.array(z.string()) });

export function usePollerStatus() {
  return useQuery<PollerProcessStatus>({
    queryKey: ["poller-status"],
    queryFn: async () => {
      const { data } = await apiClient.get("/poller/status");
      return PollerProcessStatusSchema.parse(data);
    },
    refetchInterval: 10_000,
  });
}

export function useStartPoller() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post("/poller/start");
      return PollerProcessStatusSchema.parse(data);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["poller-status"], data);
    },
  });
}

export function useStopPoller() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post("/poller/stop");
      return PollerProcessStatusSchema.parse(data);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["poller-status"], data);
      queryClient.invalidateQueries({ queryKey: ["config"] });
    },
  });
}

export function usePollerLogs(enabled: boolean) {
  return useQuery({
    queryKey: ["poller-logs"],
    queryFn: async () => {
      const { data } = await apiClient.get("/poller/logs");
      return PollerLogsSchema.parse(data).lines;
    },
    refetchInterval: enabled ? 5_000 : false,
    enabled,
  });
}
