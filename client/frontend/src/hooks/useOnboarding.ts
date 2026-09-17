import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

// 完成判定 7 项（PRD 3.4 + story-arc-planning；banned-words-into-style：anti-ai
// 检查项退役，禁用词归文风面板）：与后端 READINESS_KEYS 一致。
// ai-model 不参与判定（模型配置不是创作设定），派生时恒绿。
const SETTINGS_TYPES = ["synopsis", "story-arc", "genre", "world", "style", "hooks", "characters"];

export function useOnboarding(projectId: string | undefined, volumes: any[]) {
  const [settingsStatus, setSettingsStatus] = useState<Record<string, boolean> | null>(null);
  // 已确认标记（PUT /settings/status/{type} 的持久源；与 /readiness 的「内容已填」区分，
  // 对齐 design-language §5.1：已填＝进行中(warn)、已确认＝ok）
  const [confirmedStatus, setConfirmedStatus] = useState<Record<string, boolean> | null>(null);
  const [loading, setLoading] = useState(true);

  // 数据源 = 内容就绪判定（/readiness）：completed 项即「已设定」；
  // 确认标记（PUT /settings/status/{type}）仍由 confirmSetting 维护。
  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    api
      .get(`/novels/${projectId}/readiness`)
      .then((data: any) => {
        const missing = new Set((data.missing ?? []).map((m: any) => m.key));
        setSettingsStatus(
          Object.fromEntries([
            ...SETTINGS_TYPES.map((t) => [t, !missing.has(t)]),
            ["ai-model", true],
          ]),
        );
      })
      .catch(() => setSettingsStatus(null));
    api
      .get(`/novels/${projectId}/settings/status`)
      .then((data: any) => setConfirmedStatus(data ?? null))
      .catch(() => setConfirmedStatus(null))
      .finally(() => setLoading(false));
  }, [projectId]);

  const hasVolumes = volumes.length > 0;
  const allConfirmed =
    settingsStatus !== null && SETTINGS_TYPES.every((t) => settingsStatus[t] === true);
  // settingsStatus 拉取失败（null）时不能当作「全新项目」——避免把已有数据的项目误拉回设定引导
  const isNew = settingsStatus !== null && !hasVolumes && !allConfirmed;

  // modnav「设定 N/7」口径（用户 2026-09-16 拍板数「已确认」；banned-words-into-style
  // 起共 7 项）：内容齐了但没点确认不算完成；ai-model 是恒绿派生项，不参与计数
  const settingsDone = confirmedStatus
    ? SETTINGS_TYPES.filter((t) => confirmedStatus[t] === true).length
    : 0;

  const confirmSetting = useCallback(
    async (type: string): Promise<boolean> => {
      if (!projectId) return false;
      try {
        await api.put(`/novels/${projectId}/settings/status/${type}`);
        setSettingsStatus((prev) => ({ ...prev, [type]: true }));
        setConfirmedStatus((prev) => ({ ...prev, [type]: true }));
        return true;
      } catch (e) {
        // 后端判定该项内容为空时返回 400（产品决策：点完成设定需内容非空）
        toast.error((e as Error).message || "该项还未填写内容");
        return false;
      }
    },
    [projectId],
  );

  // 角色第三态（character-settings-v2）：确认存档 vs 当前内容指纹
  const [charStaleState, setCharStaleState] = useState(false);
  useEffect(() => {
    if (!projectId) return; // 书未加载完不打空 id 请求（/novels//characters/... 404 污染控制台）
    let alive = true;
    void (async () => {
      try {
        const res = await api.get(`/novels/${projectId}/characters/gate/status`) as {
          data?: { confirmed?: boolean; stale?: boolean } | null;
        };
        if (alive && res?.data?.confirmed && res.data.stale) setCharStaleState(true);
        if (alive && !res?.data?.confirmed) setCharStaleState(false);
      } catch {
        /* 无确认存档 = 未确认，无需 stale */
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, confirmedStatus]);

  return { settingsStatus, confirmedStatus, settingsDone, allConfirmed, isNew, confirmSetting, loading, charStale: charStaleState };
}
