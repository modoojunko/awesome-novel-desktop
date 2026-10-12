// 拆书任务轮询（c-deconstruct-book 5.2）：有活动任务时 1.5s 轮询，全终态停表；
// quiet/stall 守卫沿用 ManuscriptDownloadModal 惯例（连续失败 3 次才报错）。
// React Query 关了窗口聚焦刷新（queryClient），此处手写轮询与既有长任务一致。
import { useCallback, useEffect, useState } from "react";
import { queryClient } from "@/lib/queryClient";
import { queryKeys } from "@/lib/queryKeys";
import {
  listDeconstructTasks,
  type DeconstructTaskListResp,
} from "../lib/deconstructApi";

const ACTIVE = new Set(["queued", "running"]);
const POLL_MS = 1500;

export function useDeconstructTasks(enabled = true) {
  const [data, setData] = useState<DeconstructTaskListResp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.deconstructTasks });
    setReloadTick((t) => t + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer: number | null = null;
    let quietFailures = 0;

    const tick = async () => {
      console.log('[hook] tick start');
      try {
        const resp = await listDeconstructTasks();
        console.log('[hook] tick resolved alive=', alive);
        if (!alive) return;
        console.log('[hook] tick resp badge=', resp.badge, 'tasks=', resp.tasks.length);
        setData(resp);
        setError(null);
        quietFailures = 0;
        const hasActive = resp.tasks.some((t) => ACTIVE.has(t.status));
        if (!hasActive && timer !== null) {
          window.clearInterval(timer); // 全终态停表
          timer = null;
        }
      } catch (e) {
        quietFailures += 1;
        if (alive && quietFailures >= 3) {
          setError(e instanceof Error ? e.message : "加载失败");
          if (timer !== null) {
            window.clearInterval(timer); // 连续失败守卫：停止敲库（进页/失效重新拉起）
            timer = null;
          }
        }
      }
    };

    void tick().catch(() => undefined); // 双保险：tick 自身已兜底，防边界态游离 rejection
    timer = window.setInterval(() => void tick().catch(() => undefined), POLL_MS);
    return () => {
      alive = false;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [enabled, reloadTick]);

  return { data, error, refresh };
}
