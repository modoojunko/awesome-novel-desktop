// 拆书任务轮询（c-deconstruct-book 5.2）：React Query refetchInterval 驱动——
// 有活动任务时 1.5s 轮询；全终态停表；连续 3 次失败守卫停表。
// 失败计数用 useRef 自持（RQ fetchFailureCount 每次 interval 轮询会重置，不合守卫语义）。
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { queryKeys } from "@/lib/queryKeys";
import {
  listDeconstructTasks,
  type DeconstructTaskListResp,
} from "../lib/deconstructApi";

const POLL_MS = 1500;
const FAIL_GUARD = 3;
const ACTIVE = new Set(["queued", "running"]);

/** 轮询间隔决策（纯函数，单测全分支）：failures≥3 停表；无数据先轮；全终态停表。 */
export function deconstructRefetchInterval(
  data: DeconstructTaskListResp | undefined,
  failures: number,
): number | false {
  if (failures >= FAIL_GUARD) return false; // 连续失败守卫：停表（进页重新拉起）
  if (!data) return POLL_MS;
  const hasActive = data.tasks.some((t) => ACTIVE.has(t.status));
  return hasActive ? POLL_MS : false; // 全终态停表
}

export function useDeconstructTasks(enabled = true) {
  const failRef = useRef(0);
  const query = useQuery({
    queryKey: queryKeys.deconstructTasks,
    queryFn: async () => {
      try {
        const resp = await listDeconstructTasks();
        failRef.current = 0; // 成功即清零连续失败计数
        return resp;
      } catch (e) {
        failRef.current += 1;
        if (failRef.current >= FAIL_GUARD) {
          // 连续失败守卫：停表（进页重新拉起）；抛错保持错误态可见
          failRef.current = FAIL_GUARD;
          throw e instanceof Error ? e : new Error("加载失败");
        }
        throw e;
      }
    },
    enabled,
    retry: false,
    refetchIntervalInBackground: true,
    refetchInterval: (query) => {
      if (failRef.current >= FAIL_GUARD) return false;
      const data = query.state.data as DeconstructTaskListResp | undefined;
      return deconstructRefetchInterval(
        data,
        failRef.current, // 失败态时 data 维持旧值，由 ref 决定停表
      );
    },
  });
  return {
    data: query.data,
    error: query.error instanceof Error ? query.error.message : null,
    /** 重试：清守卫计数重新拉起（进页等效） */
    refresh: () => {
      failRef.current = 0;
      void query.refetch();
    },
  };
}
