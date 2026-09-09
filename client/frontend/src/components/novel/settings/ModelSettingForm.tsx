// AI 模型面板（book.html v2 设定视图·工具项；ADJUSTMENTS #10：parity 排除，
// 产品渲染真实状态/模型选择/变更历史/用量，信息密度高于原型静态演示）。
// 选择模型用原生 select + optgroup（按 API 配置分组），变更历史/用量统计为 cfg 折叠组。
import { useCallback, useState } from "react";
import { useModelStatus } from "@/hooks/useModelStatus";
import { Cfg } from "./FormField";
import { ChangeTimeline } from "./ChangeTimeline";
import { NovelUsagePanel } from "./NovelUsagePanel";

interface ModelSettingFormProps {
  projectId: string;
  settingKey: string;
}

const CHECK_PATH = "M5 13l4 4L19 7";

function BadgeIcon({ ok }: { ok: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      {ok ? <path d={CHECK_PATH} /> : <circle cx="12" cy="12" r="5" />}
    </svg>
  );
}

export default function ModelSettingForm({ projectId }: ModelSettingFormProps) {
  const {
    status,
    aiState,
    aiMessage,
    modelOptions,
    currentModel,
    currentConfigId,
    currentConfigName,
    hasKeys,
    loading,
    selectModel,
  } = useModelStatus(projectId);
  const [saving, setSaving] = useState(false);

  const handleSelect = useCallback(async (apiConfigId: string, model: string) => {
    setSaving(true);
    try {
      await selectModel(apiConfigId, model);
    } catch {
      // error handled by hook
    } finally {
      setSaving(false);
    }
  }, [selectModel]);

  if (!projectId) return null;
  if (loading) return <p className="opt">查询中…</p>;

  // 徽标/文案由后端 ai_state 投影（D13/D15），不再前端推导
  const badge =
    aiState === "ready"
      ? { cls: "ok", label: "可用", ok: true }
      : aiState === "invalid"
        ? { cls: "err", label: "配置失效", ok: false }
        : aiState === "missing_model"
          ? { cls: "empty", label: "未选择", ok: false }
          : aiState === "member_required"
            ? { cls: "empty", label: "需会员", ok: false }
            : { cls: "empty", label: "未配置", ok: false };
  const statusText =
    aiState === "ready"
      ? `${currentConfigName} · ${currentModel}`
      : aiMessage || "AI 暂不可用";
  // O-7 不死路：失效且没有任何可用配置 → 给「新建配置」入口
  const needNewConfig = aiState === "invalid" && !hasKeys;

  // 按 API 配置分组（optgroup 标签 = 配置名）；value 用 cid::model 复合编码
  const grouped: Record<string, typeof modelOptions> = {};
  for (const opt of modelOptions) {
    (grouped[opt.api_config_id] ||= []).push(opt);
  }
  const selectedValue =
    currentConfigId && currentModel ? `${currentConfigId}::${currentModel}` : "";

  return (
    <div data-setting-key="ai-model">
      <div className="field">
        <label>当前状态</label>
        <div className="cur-genre">
          <span className={`badge ${badge.cls}`}>
            <BadgeIcon ok={badge.ok} />
            {badge.label}
          </span>
          <span className="opt" style={{ fontWeight: 400 }}>{statusText}</span>
        </div>
        {(aiState === "no_key" || aiState === "member_required") && (
          <span className="opt" style={{ fontSize: 12, color: "var(--muted)" }}>
            {aiState === "member_required" ? "升级 PRO 后本书 AI 即可用" : "去「模型配置」添加 API Key"}
            <a href="#/config"> 去配置</a>
          </span>
        )}
        {needNewConfig && (
          <span className="opt" style={{ fontSize: 12, color: "var(--muted)" }}>
            当前绑定的 API 配置已删除，且没有其他可用配置——
            <a href="#/config">去「模型配置」新建配置</a>
          </span>
        )}
      </div>

      {hasKeys && (
        <div className="field">
          <label>
            选择模型
            {saving && <span className="opt">保存中…</span>}
          </label>
          <select
            className="input"
            value={selectedValue}
            onChange={(e) => {
              const [cid, ...rest] = e.target.value.split("::");
              void handleSelect(cid, rest.join("::"));
            }}
          >
            <option value="" disabled>
              选择模型
            </option>
            {Object.entries(grouped).map(([cid, opts]) => (
              <optgroup key={cid} label={opts[0].config_name}>
                {opts.map((o) => (
                  <option key={`${cid}::${o.model}`} value={`${cid}::${o.model}`}>
                    {o.model}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      )}

      <Cfg title="变更时间线" open>
        <ChangeTimeline projectId={projectId} />
      </Cfg>

      <Cfg title="本书用量面板" open>
        <NovelUsagePanel projectId={projectId} />
      </Cfg>
    </div>
  );
}
