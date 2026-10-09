import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useApiConfigs } from "../hooks/useApiConfigs";
import { useUsageStats } from "../hooks/useUsageStats";
import type { ApiConfig, UsageSummary } from "../types/api-config";
import { MigrationBanner } from "../components/api-config/MigrationBanner";
import { UsageStatsCard } from "../components/api-config/UsageStatsCard";
import { ApiConfigCard } from "../components/api-config/ApiConfigCard";
import { ApiConfigForm } from "../components/api-config/ApiConfigForm";
import type { ApiConfigFormData } from "../components/api-config/ApiConfigForm";
import { DeleteConfirmDialog } from "../components/api-config/DeleteConfirmDialog";
import { UndoToast } from "../components/api-config/UndoToast";
import { Ico, P } from "../components/icons";
import { isLoggedIn } from "../lib/auth";
import { request } from "../lib/api";
import { relTime } from "../lib/reltime";
import { toast } from "../lib/toast";
import ZhuquePanel from "../components/api-config/ZhuquePanel";

/** 模型配置屏（model-config.html parity：notice + 用量面板 + cfg-cards + 弹窗群） */
export default function ApiKeyConfigPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // c-zhuque-ai-detect：双页签；?tab=zhuque 深链；?add 组合强制大模型页签（添加弹窗只属于大模型域）
  const [cfgTab, setCfgTab] = useState<"llm" | "zhuque">(() =>
    searchParams.get("tab") === "zhuque" && !searchParams.has("add") ? "zhuque" : "llm",
  );

  useEffect(() => {
    if (!isLoggedIn()) {
      navigate("/login", { replace: true });
    }
  }, [navigate]);
  const { configs, loading, error, refresh, addConfig, updateConfig, deleteConfig, restoreConfig, refreshStatus, testConfig, testRawConfig, fetchRawModels } = useApiConfigs();
  const { data: usageData, loading: usageLoading, refresh: refreshUsage } = useUsageStats({});
  const [showForm, setShowForm] = useState(false);
  const [editConfig, setEditConfig] = useState<ApiConfig | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ApiConfig | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [undoToast, setUndoToast] = useState<ApiConfig | null>(null);
  const [migrationStatus, setMigrationStatus] = useState<{ completed: boolean; configName?: string } | undefined>(undefined);

  // Check #add anchor
  useEffect(() => {
    if (searchParams.get("add") === "" || window.location.hash === "#add") {
      setCfgTab("llm");
      setShowForm(true);
    }
  }, [searchParams]);

  // Fetch migration status（c-fetch-unify：迁中心栈；探测类静默失败，
  // 原实现连 r.ok 都不查——非 2xx 的 HTML/空体在这里会抛解析错，同样被静默兜住）
  useEffect(() => {
    request("/user/profile", { apiBase: "/api/v1", quiet: true })
      .then((data: any) => {
        if (data.migration_completed !== undefined) {
          setMigrationStatus({ completed: data.migration_completed, configName: data.migration_config_name });
        }
      })
      .catch(() => {});
  }, []);

  const handleFormSubmit = useCallback(async (data: ApiConfigFormData) => {
    // model 是表单的模型选择位：创建时落 models 首项；编辑时选中值置首（保留其余已存项，
    // 截 100 对齐后端手动路径上限），留空沿用已存值（与密钥同语义）
    const { model, ...rest } = data;
    if (editConfig) {
      // 「留空则保留当前密钥」：编辑态空 Key **必须省略字段**——原样发 "" 会被后端
      // 当作更新值（encrypt("") == ""）把已存密钥清空（2026-09-18 覆盖率专项实锤，
      // 后端同时收紧为「空串=未提供」，两侧各一道）
      const { api_key, ...fields } = rest;
      const picked = model.trim();
      const models = picked
        ? [picked, ...editConfig.models.filter((m) => m !== picked)].slice(0, 100)
        : null;
      await updateConfig(editConfig.id, {
        ...(api_key.trim() ? rest : fields),
        ...(models ? { models } : {}),
      });
      setEditConfig(null);
      toast.success(`已保存「${data.name}」`);
    } else {
      const newConfig = await addConfig({ ...rest, models: model ? [model] : [] });
      // 创建后自动测试，让卡片带上真实状态（原型同款行为）
      let ok = false;
      try {
        const r = await testConfig(newConfig.id);
        ok = r.ok;
      } catch { /* non-blocking */ }
      setShowForm(false);
      toast.success(`已添加「${data.name}」${ok ? " · 连接正常" : " · 请检查 Key"}`);
    }
  }, [editConfig, updateConfig, addConfig, testConfig]);

  const handleDelete = useCallback(async () => {
    /* v8 ignore start -- 防御分支：确认对话框只在 deleteTarget 非空时渲染，按钮无法在空态触发 */
    if (!deleteTarget) return;
    /* v8 ignore stop */
    setDeleting(true);
    try {
      await deleteConfig(deleteTarget.id);
      setDeleteTarget(null);
      setUndoToast(deleteTarget);
    } catch {
      // Keep dialog open on error
    } finally {
      setDeleting(false);
    }
  }, [deleteTarget, deleteConfig]);

  const handleUndoDelete = useCallback(async () => {
    /* v8 ignore start -- 防御分支：撤销按钮只在 undoToast 非空时渲染 */
    if (!undoToast) return;
    /* v8 ignore stop */
    try {
      // 撤销 = 后端软删 restore，恢复同一 id（配置名/key/base_url 原样回来）
      await restoreConfig(undoToast.id);
      toast.success(`已恢复「${undoToast.name}」`);
    } catch {
      // undo failed silently（配置已不存在等）
    }
  }, [undoToast, restoreConfig]);

  const closeForm = useCallback(() => {
    setShowForm(false);
    setEditConfig(null);
  }, []);

  // Refresh status when configs change
  useEffect(() => {
    if (configs.length > 0) {
      refreshStatus();
    }
    refreshUsage();
  }, [configs.length, refreshStatus, refreshUsage]);

  const usage = usageData as UsageSummary | null;

  return (
    <main className="main pg-config">
      <div className="page-head">
        <div>
          <h1>模型配置</h1>
          <p className="sub">管理你的 AI 服务 API Key，为不同小说选择不同模型</p>
        </div>
        {cfgTab === "llm" && (
          <button
            className="btn btn-primary"
            onClick={() => { setShowForm(true); setEditConfig(null); }}
          >
            <Ico d={P.plus} />
            添加 API Key
          </button>
        )}
      </div>

      {/* c-zhuque-ai-detect：配置分类页签（写作大模型 / 朱雀 AI 检测） */}
      <div className="cfg-tabs" role="tablist" aria-label="配置分类" data-od-id="cfg-tabs">
        <button
          className={`cfg-tab${cfgTab === "llm" ? " on" : ""}`}
          role="tab"
          aria-selected={cfgTab === "llm"}
          data-od-id="cfg-tab-llm"
          onClick={() => setCfgTab("llm")}
        >
          写作大模型
        </button>
        <button
          className={`cfg-tab${cfgTab === "zhuque" ? " on" : ""}`}
          role="tab"
          aria-selected={cfgTab === "zhuque"}
          data-od-id="cfg-tab-zhuque"
          onClick={() => setCfgTab("zhuque")}
        >
          朱雀 AI 检测
        </button>
      </div>

      <div hidden={cfgTab !== "llm"}>
      {/* 新手提示：不配置也能先开始手工创作 */}
      <div className="notice">
        <Ico d={P.info} sw={1.8} />
        <span>
          不配置也能先开始<b>手动创作</b>，随时可以回来添加。本地模型（如
          Ollama）<b>不需要</b> API Key；云端模型请选择对应供应商并填入 Base URL 与 Key。
        </span>
      </div>

      {/* Migration Banner（应用侧扩展：仅老用户未迁移时出现） */}
      <MigrationBanner migrationCompleted={migrationStatus?.completed} />

      {/* 用量统计 */}
      <UsageStatsCard
        data={usage}
        loading={usageLoading}
        updatedLabel={usage?.queried_at ? relTime(usage.queried_at) : undefined}
      />

      {/* Config List */}
      <div id="api-config-list">
        {loading ? (
          <div className="cards">
            {[1, 2, 3].map((i) => (
              <div key={i} className="card-skeleton">
                <div className="sk bar w40" />
                <div className="sk bar w90" />
                <div className="sk bar w70" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="empty">
            <div className="serif">配置加载失败</div>
            <p>{error}</p>
            <div style={{ marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => void refresh()}>
                重新加载
              </button>
            </div>
          </div>
        ) : configs.length === 0 ? (
          /* 原型口径：empty 是 .cards 网格里的单个网格项 */
          <div className="cards">
            <div className="empty">
              <div className="serif">还没有模型配置</div>
              <p>添加你的第一个 API Key 来开始使用 AI 写作。</p>
              <p style={{ marginTop: 14 }}>
                <Link className="btn btn-secondary btn-sm" to="/novels">
                  先开始手动创作
                </Link>
              </p>
            </div>
          </div>
        ) : (
          <div className="cards">
            {configs.map((c) => (
              <ApiConfigCard
                key={c.id}
                config={c}
                onEdit={() => { setEditConfig(c); setShowForm(false); }}
                onDelete={() => setDeleteTarget(c)}
                onTest={async (cfg) => testConfig(cfg.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* 添加 / 编辑弹窗（常挂载保 Modal 退场动画；表单随目标在渲染期重置） */}
      <ApiConfigForm
        open={showForm || !!editConfig}
        config={editConfig}
        onSubmit={handleFormSubmit}
        onCancel={closeForm}
        onTest={async (data) =>
          editConfig && !data.api_key.trim()
            ? testConfig(editConfig.id, data.model.trim() || undefined) // 未重敲 Key：用已存密钥测；表单改选模型作探针覆盖
            : testRawConfig({
                vendor_id: data.vendor_id,
                base_url: data.base_url,
                api_key: data.api_key,
                api_format: data.api_format,
                model: data.model || null,
                thinking_enabled: data.thinking_enabled,
                thinking_effort: data.thinking_effort,
              })
        }
        onFetchModels={async (data) => fetchRawModels(data)}
      />

      {/* 删除确认 */}
      {deleteTarget && (
        <DeleteConfirmDialog
          config={deleteTarget}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          deleting={deleting}
        />
      )}

      </div>{/* /pane-llm */}

      <div hidden={cfgTab !== "zhuque"}>
        <ZhuquePanel />
      </div>{/* /pane-zhuque */}

      {/* 撤销 toast（8 秒窗口） */}
      {undoToast && (
        <UndoToast
          configName={undoToast.name}
          onUndo={handleUndoDelete}
          onExpire={() => setUndoToast(null)}
        />
      )}
    </main>
  );
}
