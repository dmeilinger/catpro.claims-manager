import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import {
  EmailLogDetailSchema,
  InboxCountSchema,
  InboxResponseSchema,
  type InboxResponse,
  type TriageAction,
} from "@/schemas/email";

export function useInboxCount() {
  return useQuery({
    queryKey: ["inbox-count"],
    queryFn: async ({ signal }) => {
      const { data } = await apiClient.get("/inbox/count", { signal });
      return InboxCountSchema.parse(data);
    },
    refetchInterval: 30_000,
  });
}

export function useInbox(params: { page?: number; page_size?: number } = {}) {
  return useQuery({
    queryKey: ["inbox", params],
    queryFn: async ({ signal }) => {
      const { data } = await apiClient.get("/inbox", { params, signal });
      return InboxResponseSchema.parse(data);
    },
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });
}

// Optimistic triage action with concurrent-dismiss safety
export function useTriageAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["triage"],
    mutationFn: async ({ id, action }: { id: number; action: TriageAction }) => {
      const { data } = await apiClient.patch(`/email-log/${id}/triage`, { action });
      return EmailLogDetailSchema.parse(data);
    },
    onMutate: async ({ id }) => {
      // Cancel in-flight refetches to avoid race conditions
      await queryClient.cancelQueries({ queryKey: ["inbox"] });
      const previousInbox = queryClient.getQueryData(["inbox"]);
      // Optimistically remove the row and decrement total so pagination math stays correct
      queryClient.setQueryData<InboxResponse>(["inbox"], (old) =>
        old
          ? {
              ...old,
              items: old.items.filter((item) => item.id !== id),
              total: Math.max(0, old.total - 1),
            }
          : old
      );
      return { previousInbox };
    },
    onError: (_err, _vars, context) => {
      // Roll back to previous list on failure
      queryClient.setQueryData(["inbox"], context?.previousInbox);
    },
    onSettled: () => {
      // Guard: only invalidate when no other mutations are running
      // (prevents list flicker when dismissing multiple rows rapidly)
      if (queryClient.isMutating({ mutationKey: ["triage"] }) === 1) {
        queryClient.invalidateQueries({ queryKey: ["inbox"] });
      }
      queryClient.invalidateQueries({ queryKey: ["inbox-count"] });
      queryClient.invalidateQueries({ queryKey: ["email-log"] });
    },
  });
}
