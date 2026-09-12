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
  saving: boolean;
  patch: (p: Partial<ArcData>) => void;
  save: () => Promise<boolean>;
}

export function useStoryArc(
  projectId: string,
  enabled = true,
  onDirtyChange?: (dirty: boolean) => void,
): ArcCtl {
  const [arc, setArc] = useState<ArcData>(EMPTY_ARC);
  const [loading, setLoading] = useState(enabled);
  const [saving, setSaving] = useState(false);
  // P3-4：晚到的挂载 fetch 不得覆盖用户输入
  const editedRef = useRef(false);
  const { snapshotLoaded, markSaved } = useDirtyState(arc, onDirtyChange);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
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
      .catch(() => !cancelled && snapshotLoaded(EMPTY_ARC))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
    // snapshotLoaded 引用稳定；仅项目/启用态变化重拉
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, enabled]);

  const patch = useCallback((p: Partial<ArcData>) => {
    editedRef.current = true;
    setArc((prev) => ({ ...prev, ...p }));
  }, []);

  const save = useCallback(async (): Promise<boolean> => {
    if (saving) return false;
    setSaving(true);
    try {
      await api.updateStoryArc(projectId, arc);
      markSaved();
      return true;
    } catch {
      toast.error("主线保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  }, [projectId, arc, saving, markSaved]);

  return { projectId, arc, loading, saving, patch, save };
}
