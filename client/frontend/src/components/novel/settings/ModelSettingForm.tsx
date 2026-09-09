// AI 模型面板（book.html v2 设定视图·工具项；ADJUSTMENTS #10：parity 排除，
// 产品渲染真实状态/模型选择/变更历史/用量，信息密度高于原型静态演示）。
//
// 模型选择＝按 API 配置分组的卡片列表（tasks 7.1 / D12）：
//   组头＝配置名 + 供应商 + 连接状态徽标（last_test_status → 已连接/未测试/失败）；
//   组内模型行＝radiogroup/radio + roving tabindex + 方向键/Home/End（选中不可取消）；
//   **选择与生效分离**——点行只标亮（draft），点「设为本书模型」才落库（整对 PUT）；
//   400 保留 draft + 行内报错；draft 未确认时切面板走全局 dirty 提示。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useModelStatus } from "@/hooks/useModelStatus";
import { Cfg } from "./FormField";
import { ChangeTimeline } from "./ChangeTimeline";
import { NovelUsagePanel } from "./NovelUsagePanel";

interface ModelSettingFormProps {
  projectId: string;
  settingKey: string;
  onDirtyChange?: (dirty: boolean) => void;
}

const CHECK_PATH = "M5 13l4 4L19 7";

function BadgeIcon({ ok }: { ok: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      {ok ? <path d={CHECK_PATH} /> : <circle cx="12" cy="12" r="5" />}
    </svg>
  );
}

/** 连接状态 → 徽标（last_test_status 六值收敛为三档）。 */
function connBadge(status: string | null | undefined) {
  if (status === "ok") return { cls: "ok", label: "已连接" };
  if (!status || status === "unknown" || status === "untested")
    return { cls: "empty", label: "未测试" };
  return { cls: "err", label: "连接失败" };
}

export default function ModelSettingForm({
  projectId,
  onDirtyChange,
}: ModelSettingFormProps) {
  const {
    status,
    aiState,
    aiMessage,
    configs,
    modelOptions,
    currentModel,
    currentConfigId,
    currentConfigName,
    hasKeys,
    loading,
    selectModel,
  } = useModelStatus(projectId);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  /** draft＝已标亮未生效的 (config_id, model) 整对。 */
  const [draft, setDraft] = useState<{ cid: string; model: string } | null>(null);
  const rowRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  // draft 变化 → 上抛脏状态（切面板/离开设定视图走全局提示，O-10）
  useEffect(() => {
    onDirtyChange?.(draft !== null);
  }, [draft, onDirtyChange]);

  const handleSelect = useCallback((cid: string, model: string) => {
    setError("");
    setDraft({ cid, model });
  }, []);

  // 分组（按 api_config_id；组头取配置元数据）
  const grouped = useMemo(() => {
    const map = new Map<string, typeof modelOptions>();
    for (const opt of modelOptions) {
      const list = map.get(opt.api_config_id) ?? [];
      list.push(opt);
      map.set(opt.api_config_id, list);
    }
    return [...map.entries()];
  }, [modelOptions]);

  const configOf = useCallback(
    (cid: string) => configs.find((c) => c.id === cid),
    [configs],
  );

  /** 键盘导航（roving tabindex + 方向键环绕 + Home/End；选中不可 toggle-off）。 */
  const onRowKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>, flatIndex: number) => {
      const flat = grouped.flatMap(([cid, opts]) =>
        opts.map((o) => ({ cid, model: o.model })),
      );
      const go = (idx: number) => {
        const next = flat[(idx + flat.length) % flat.length];
        rowRefs.current[`${next.cid}::${next.model}`]?.focus();
      };
      if (e.key === "ArrowDown" || e.key === "ArrowRight") {
        e.preventDefault();
        go(flatIndex + 1);
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
        e.preventDefault();
        go(flatIndex - 1);
      } else if (e.key === "Home") {
        e.preventDefault();
        go(0);
      } else if (e.key === "End") {
        e.preventDefault();
        go(flat.length - 1);
      }
    },
    [grouped],
  );

  const handleApply = useCallback(async () => {
    if (!draft || saving) return;
    setSaving(true);
    setError("");
    try {
      await selectModel(draft.cid, draft.model);
      setDraft(null);
    } catch (e) {
      // 400 等：保留 draft + 行内报错（不清空、不禁用）
      setError((e as Error).message || "保存失败");
    } finally {
      setSaving(false);
    }
  }, [draft, saving, selectModel]);

  if (!projectId) return null;
  if (loading) return <p className="opt">查询中…</p>;

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
  const needNewConfig = aiState === "invalid" && !hasKeys;
  // 空态：有 Key 但没有任何可选模型（配置里 models 为空）
  const noModels = hasKeys && modelOptions.length === 0;

  let flatIndex = -1;

  return (
    <div data-setting-key="ai-model">
      <div className="field">
        <label>当前状态</label>
        <div className="cur-genre">
          <span className={`badge ${badge.cls}`}>
            <BadgeIcon ok={badge.ok} />
            {badge.label}
          </span>
          <span className="opt" style={{ fontWeight: 400 }}>
            {statusText}
          </span>
        </div>
        {aiState === "member_required" && (
          <span className="opt" style={{ fontSize: 12, color: "var(--muted)" }}>
            模型已配好 · 升级 PRO 后本书 AI 即可用
          </span>
        )}
        {(aiState === "no_key" || aiState === "missing_model") && (
          <span className="opt" style={{ fontSize: 12, color: "var(--muted)" }}>
            {aiState === "no_key"
              ? "去「模型配置」添加 API Key"
              : "选一个模型并点「设为本书模型」"}
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

      {noModels && (
        <div className="field">
          <span className="opt" style={{ fontSize: 12, color: "var(--muted)" }}>
            配置里还没有模型——<a href="#/config">去「模型配置」测试连接补模型</a>
          </span>
        </div>
      )}

      {modelOptions.length > 0 && (
        <div className="field">
          <label>
            选择模型
            <span className="opt" style={{ fontWeight: 400 }}>
              选好点「设为本书模型」生效
            </span>
          </label>
          <div role="radiogroup" aria-label="本书模型" className="model-groups">
            {grouped.map(([cid, opts]) => {
              const cfg = configOf(cid);
              const conn = connBadge(cfg?.last_test_status);
              return (
                <div className="model-group" key={cid}>
                  <div className="mg-head">
                    <span className="mg-name">{opts[0].config_name}</span>
                    <span className="mg-vendor">{opts[0].vendor}</span>
                    <span className={`badge ${conn.cls}`}>
                      <BadgeIcon ok={conn.cls === "ok"} />
                      {conn.label}
                    </span>
                  </div>
                  {opts.map((o) => {
                    flatIndex += 1;
                    const idx = flatIndex;
                    const active =
                      (draft && draft.cid === cid && draft.model === o.model) ||
                      (!draft && currentConfigId === cid && currentModel === o.model);
                    const key = `${cid}::${o.model}`;
                    return (
                      <button
                        key={key}
                        ref={(el) => {
                          rowRefs.current[key] = el;
                        }}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        tabIndex={active ? 0 : -1}
                        className={`model-row${active ? " on" : ""}`}
                        data-model={`${cid}::${o.model}`}
                        onClick={() => handleSelect(cid, o.model)}
                        onKeyDown={(e) => onRowKeyDown(e, idx)}
                      >
                        <span className="mr-dot" aria-hidden="true" />
                        <span className="mr-name">{o.model}</span>
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
          <div className="model-apply">
            <button
              className="btn btn-primary btn-sm"
              type="button"
              disabled={!draft || saving}
              onClick={() => void handleApply()}
            >
              {saving ? "保存中…" : "设为本书模型"}
            </button>
            {draft && !saving && (
              <span className="opt" style={{ fontSize: 12 }}>
                已选：{draft.model}
              </span>
            )}
            {error && (
              <span className="opt" style={{ color: "var(--err)", fontSize: 12 }}>
                {error}
              </span>
            )}
          </div>
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
