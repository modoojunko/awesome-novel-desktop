// 知识提炼任务轮询 hook（与 useDeconstructTasks 同策略：3s 心跳，有进行中才快轮）
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { kbApi, type RefineTaskRow } from "../lib/kbApi";

export function isActiveRefine(status: RefineTaskRow["status"]): boolean {
  return status === "queued" || status === "running";
}

export function useRefineTasks() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["refine-tasks"],
    queryFn: () => kbApi.refineTasks.list(),
    refetchInterval: (q) => {
      const rows = q.state.data?.tasks ?? [];
      return rows.some((t) => isActiveRefine(t.status)) ? 3000 : 15000;
    },
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["refine-tasks"] });
  return { data: query.data, error: query.error as string | null, refresh };
}
