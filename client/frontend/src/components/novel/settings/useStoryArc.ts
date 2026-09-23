// 主线共享状态（storyline-settings-v2）：SettingsView 持有，主线表单与右栏
// AI 三行共用同一份 arc —— AI 产出落卡不覆盖表单未保存的编辑。
// 契约：{fullstory, ending{scene,hero,tone}}；legacy premise 由后端 GET 归一进 fullstory。
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { useDirtyState } from "@/hooks/useDirtyState";

export interface ArcData {
  fullstory: string;
  ending: { scene: string; hero: string; tone: string };
}

export const EMPTY_ARC: ArcData = {
  fullstory: "",
  ending: { scene: "", hero: "", tone: "" },
};

/** 旧数据里的占位基调（待定/？）按空处理；其余任意自定义文本合法 */
export function normTone(t: unknown): string {
  const s = typeof t === "string" ? t : "";
  return s === "待定" || s === "？" || s === "?" ? "" : s;
}

export interface ArcCtl {
  projectId: string;
  arc: ArcData;
  loading: boolean;
  /** 加载失败——失败后 SHALL NOT 以空卡作可保存基线（保存入口禁用，重试成功后恢复） */
  loadError: boolean;
  saving: boolean;
  patch: (p: Partial<ArcData>) => void;
  save: () => Promise<boolean>;
  reload: () => void;
}

export function useStoryArc(
  projectId: string,
  enabled = true,
  onDirtyChange?: (dirty: boolean) => void,
): ArcCtl {
  const [arc, setArc] = useState<ArcData>(EMPTY_ARC);
  const [loading, setLoading] = useState(enabled);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadTick, setLoadTick] = useState(0);
  // P3-4：晚到的挂载 fetch 不得覆盖用户输入
  const editedRef = useRef(false);
  const { snapshotLoaded, markSaved } = useDirtyState(arc, onDirtyChange);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    editedRef.current = false;
    api
      .fetchStoryArc(projectId)
      .then((d: any) => {
        if (cancelled || editedRef.current) return;
        const next: ArcData = {
          // 后端已归一（fullstory ?? premise）；此处兜底防直连旧后端
          fullstory: d.fullstory ?? d.premise ?? "",
          ending: {
            scene: d.ending?.scene ?? "",
            hero: d.ending?.hero ?? "",
            tone: normTone(d.ending?.tone),
          },
        };
        setArc(next);
        snapshotLoaded(next);
      })
      // 加载失败不再落 EMPTY_ARC 干净基线（c-silent-data-guards）：
      // 那会把「没加载到」伪装成「内容为空」，保存即整卡覆盖库里已有内容
      .catch(() => !cancelled && setLoadError(true))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
    // snapshotLoaded 引用稳定；仅项目/启用态/手动重载变化重拉
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, enabled, loadTick]);

  const reload = useCallback(() => setLoadTick((t) => t + 1), []);

  const patch = useCallback((p: Partial<ArcData>) => {
    editedRef.current = true;
    setArc((prev) => ({ ...prev, ...p }));
  }, []);

  const save = useCallback(async (): Promise<boolean> => {
    if (loadError) {
      toast.error("主线卡还没加载成功——先重新加载再保存");
      return false;
    }
    if (saving) return false;
    setSaving(true);
    try {
      await api.updateStoryArc(projectId, arc);
      markSaved();
      return true;
    } catch (e) {
      // 后端 400 带可行动原因（如「主线全文过长（2100/2000 字）——建议 600 字以内」），
      // 透出原文别泛化；但网络层失败（fetch 抛 TypeError「Failed to fetch」）与 401 无
      // 中文 detail——只凭 status（确有后端响应）判断，否则回落中文兜底
      // （P2/P3，2026-09-13 检视）
      const err = e as Error & { status?: number };
      toast.error(err.status && err.message ? err.message : "主线保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  }, [projectId, arc, saving, loadError, markSaved]);

  return { projectId, arc, loading, loadError, saving, patch, save, reload };
}
