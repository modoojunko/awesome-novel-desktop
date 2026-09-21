// 度量埋点（PRD §7，c-volume-antagonist）：只落 C端 本机 events 表，不外发、不上报。
//
// 可关：`localStorage["pref.metrics.off"]==="1"`（用户级）或 `VITE_METRICS=off`
// （构建级）任一生效即整体静默——埋点永不影响主流程：fire-and-forget、失败吞掉。
//
// 只收 PRD §7 事件表里「前端意图」那部分；服务端自己知道的两条（hooks_registered /
// check_run）在各自端点内落，不走这里（后端白名单同样只认这批名字）。
import { api } from "./api";

export type MetricEvent =
  | "plan_entry_open"
  | "pick_drawn"
  | "pick_redraw"
  | "pick_select"
  | "pick_confirm_ok"
  | "pick_confirm_fail"
  | "desk_manual_create"
  | "desk_expand"
  | "volume_saved"
  | "first_chapter_in_vol";

export function metricsOff(): boolean {
  if (import.meta.env.VITE_METRICS === "off") return true;
  try {
    return localStorage.getItem("pref.metrics.off") === "1";
  } catch {
    return false; // 隐私模式下 localStorage 不可用：按「不关」处理
  }
}

/** 记一条事件（best-effort）：不 await、不抛、不弹提示。
 *  quiet：埋点失败不触发全局副作用（401 踢出 / 503 弹条）——它不是用户动作。
 *  防御式可选链：埋点在任何实现下都不得抛（含 api 被替换/打桩的场景）。 */
export function track(event: MetricEvent, payload: Record<string, unknown> = {}) {
  if (metricsOff()) return;
  try {
    const sent = api.post("/events", { event_type: event, payload }, { quiet: true }) as
      | Promise<unknown>
      | undefined;
    void sent?.catch(() => {});
  } catch {
    /* 埋点永不影响主流程 */
  }
}
