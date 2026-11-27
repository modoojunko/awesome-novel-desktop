// 模型清单全局数据源（c-model-list-auto-refresh）：配置与模型清单的单一事实源。
//
// 背景：模型选择器遍布模型配置页 / 本书模型 / 助手底栏 / 拆书创建与详情，旧实现每个
// 组件各自持有一份 `GET /api-configs` 快照，打开选择器时读到的可能是上次保存时的旧
// 清单。这里把配置与清单收进模块级 store：任何一次后台保鲜（ensure）更新都会推给所有
// 订阅者，选择器不再各读各的。
//
// 保鲜策略在服务端（TTL 10 分钟 / 失败退避 / 单飞），前端只负责在「用户可能用到清单
// 之前」触发：应用启动、进含选择器的页面、定时、窗口回焦、选择器打开。触发本身有
// 30 秒客户端节流，避免页面切换连打本地接口。
import { useEffect, useSyncExternalStore } from "react";
import type { ApiConfig } from "../types/api-config";
import { request } from "./api";
import { isLoggedIn } from "./auth";
import { registerModelCatalogReset } from "./modelCatalogReset";

const V1 = "/api/v1";

/** 错误可读文案（与 lib/api.errMessage 同口径）：只有 4xx 的 message 才透出，
 * 其余一律兜底——部分测试 mock 了 lib/api，这里保持依赖面最小。 */
function catalogErrMessage(e: unknown, fallback: string): string {
  const err = e as { status?: number; message?: string } | null;
  const usable =
    typeof err?.status === "number" &&
    err.status >= 400 &&
    err.status < 500 &&
    typeof err.message === "string" &&
    !!err.message;
  return usable ? (err.message as string) : fallback;
}

/** 客户端触发节流：30 秒内的重复 ensure 直接复用结果（服务端还有 10 分钟 TTL）。 */
export const ENSURE_THROTTLE_MS = 30_000;
/** 前台定时保鲜间隔：5 分钟问一次本地接口，真正出网仍由服务端 TTL 决定。 */
export const CATALOG_POLL_MS = 5 * 60_000;

export interface EnsureModelsConfigResult {
  id: string;
  models: string[];
  models_updated_at: string | null;
  refreshed: boolean;
  ok: boolean;
  error?: string | null;
}

export interface EnsureModelsResult {
  configs: EnsureModelsConfigResult[];
}

export interface ModelCatalogState {
  configs: ApiConfig[];
  loading: boolean;
  error: string | null;
  /** 后台保鲜请求在途（选择器可据此显示「正在更新清单…」）。 */
  refreshing: boolean;
  /** 每个配置上次刷新失败的原因（成功即清）。 */
  lastErrors: Record<string, string>;
  /** 全局保鲜失败原因（请求本身失败，拿不到按配置的结果）。 */
  ensureError: string | null;
  /** 清单内容版本号：每次清单变化 +1，供非 React 数据流（拆书页）重取。 */
  version: number;
}

function initialState(): ModelCatalogState {
  return {
    configs: [],
    loading: true,
    error: null,
    refreshing: false,
    lastErrors: {},
    ensureError: null,
    version: 0,
  };
}

let state: ModelCatalogState = initialState();

const listeners = new Set<() => void>();

function emit(patch: Partial<ModelCatalogState>) {
  state = { ...state, ...patch };
  for (const l of listeners) l();
}

export function subscribeModelCatalog(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getModelCatalog(): ModelCatalogState {
  return state;
}

let loadPromise: Promise<void> | null = null;
/** 保鲜结果先于配置列表到达时的暂存（启动竞态）：load 完成后合并进来。 */
let pendingModels: Record<string, { models: string[]; models_updated_at: string | null }> = {};
/** 代际号：登出清空后 +1，旧账号在途响应据此丢弃（防跨账号串台）。 */
let epoch = 0;

/** 取配置列表（多实例共用单飞）。每次调用都重新取——与旧 useApiConfigs 挂载取数同口径。 */
export function loadModelCatalog(): Promise<void> {
  if (loadPromise) return loadPromise;
  const ep = epoch;
  emit({ loading: true, error: null });
  loadPromise = (async () => {
    try {
      const data = await request<ApiConfig[]>("/api-configs", { apiBase: V1 });
      if (ep !== epoch) return; // 登出/换号：旧账号的响应作废
      let changed = false;
      const configs = data.map((c) => {
        const pending = pendingModels[c.id];
        if (!pending) return c;
        if (pending.models.join("|") !== (c.models ?? []).join("|")) changed = true;
        return {
          ...c,
          models: pending.models,
          models_updated_at: pending.models_updated_at ?? c.models_updated_at,
        };
      });
      pendingModels = {}; // 已并入本次列表，之后以 DB 读面为准
      emit({
        configs,
        loading: false,
        version: changed ? state.version + 1 : state.version,
      });
    } catch (e) {
      if (ep !== epoch) return;
      // 本页就是 /config：503 只会是云托管冷启动，就地报错不强跳
      const msg =
        (e as { status?: number })?.status === 503
          ? "云端服务唤醒中，请稍后重试"
          : catalogErrMessage(e, "加载配置失败");
      emit({ loading: false, error: msg });
    } finally {
      if (ep === epoch) loadPromise = null;
    }
  })();
  return loadPromise;
}

/** CRUD 后局部更新（不重取整表）。 */
export function upsertModelCatalogConfig(config: ApiConfig) {
  const exists = state.configs.some((c) => c.id === config.id);
  const configs = exists
    ? state.configs.map((c) => (c.id === config.id ? config : c))
    : [config, ...state.configs];
  emit({ configs });
}

export function removeModelCatalogConfig(id: string) {
  emit({ configs: state.configs.filter((c) => c.id !== id) });
}

export function patchModelCatalogStatus(
  entries: Array<Partial<ApiConfig> & { id: string }>,
) {
  const configs = state.configs.map((c) => {
    const entry = entries.find((e) => e.id === c.id);
    if (!entry) return c;
    // undefined 不覆盖已有值（调用方用 undefined 表达「这次没带回该字段」）
    const patch = Object.fromEntries(
      Object.entries(entry).filter(([, v]) => v !== undefined),
    );
    return { ...c, ...patch };
  });
  emit({ configs });
}

function applyEnsureResult(result: EnsureModelsResult) {
  if (!Array.isArray(result.configs)) return;
  const known = new Set(state.configs.map((c) => c.id));
  for (const row of result.configs) {
    // 配置列表还没到（启动竞态）：暂存，load 完成后并入
    if (!known.has(row.id)) {
      pendingModels[row.id] = {
        models: Array.isArray(row.models) ? row.models : [],
        models_updated_at: row.models_updated_at ?? null,
      };
    }
  }
  const byId = new Map(result.configs.map((r) => [r.id, r]));
  let changed = false;
  const configs = state.configs.map((c) => {
    const row = byId.get(c.id);
    if (!row) return c;
    const nextModels = Array.isArray(row.models) ? row.models : c.models;
    if ((nextModels ?? []).join("|") !== (c.models ?? []).join("|")) changed = true;
    return {
      ...c,
      models: nextModels ?? [],
      models_updated_at: row.models_updated_at ?? c.models_updated_at,
    };
  });
  const lastErrors: Record<string, string> = {};
  for (const row of result.configs) {
    if (!row.ok && row.error) lastErrors[row.id] = row.error;
  }
  emit({
    configs,
    lastErrors,
    ensureError: null,
    version: changed ? state.version + 1 : state.version,
  });
}

let ensurePromise: Promise<EnsureModelsResult | null> | null = null;
let lastEnsureAt = 0;

/**
 * 后台保鲜：服务端按 TTL 决定是否真出网；这里只做客户端节流与在途复用。
 * 失败静默（选择器用缓存继续可选），错误进 state 供轻提示。
 */
export function ensureModelsFresh(opts?: {
  force?: boolean;
  configIds?: string[];
}): Promise<EnsureModelsResult | null> {
  if (!isLoggedIn()) return Promise.resolve(null); // 未登录不触网（登录页/落地页）
  if (ensurePromise && !opts?.force) return ensurePromise;
  const now = Date.now();
  if (!opts?.force && now - lastEnsureAt < ENSURE_THROTTLE_MS) {
    return Promise.resolve(null);
  }
  lastEnsureAt = now;
  const ep = epoch;
  emit({ refreshing: true });
  ensurePromise = (async () => {
    try {
      const body: Record<string, unknown> = {};
      if (opts?.force) body.force = true;
      if (opts?.configIds?.length) body.config_ids = opts.configIds;
      const result = await request<EnsureModelsResult>("/api-configs/ensure-models-fresh", {
        apiBase: V1,
        method: "POST",
        body: JSON.stringify(body),
      });
      if (ep !== epoch) return null; // 登出/换号：旧账号的清单不落地
      applyEnsureResult(result);
      return result;
    } catch (e) {
      if (ep === epoch) emit({ ensureError: catalogErrMessage(e, "模型清单更新失败") });
      return null;
    } finally {
      if (ep === epoch) {
        ensurePromise = null;
        emit({ refreshing: false });
      }
    }
  })();
  return ensurePromise;
}

/** 清空模型清单 store（登出/换号用：旧账号配置与清单不得留给下一位）。 */
export function clearModelCatalog() {
  epoch += 1;
  state = initialState();
  loadPromise = null;
  ensurePromise = null;
  pendingModels = {};
  lastEnsureAt = 0;
  for (const l of listeners) l();
}

/** 测试隔离：清空进程内状态与节流计时（须在渲染前调用）。 */
export function resetModelCatalogForTest() {
  clearModelCatalog();
}

export function useModelCatalog(): ModelCatalogState {
  return useSyncExternalStore(subscribeModelCatalog, getModelCatalog);
}

/** 清单内容版本（拆书等非 store 消费方据此重取选项）。 */
export function useModelCatalogVersion(): number {
  return useSyncExternalStore(subscribeModelCatalog, () => state.version);
}

/** 进入含模型选择的页面/面板时调用：服务端 TTL 内不会真出网。 */
export function useEnsureModelsFresh(enabled = true) {
  useEffect(() => {
    if (enabled) void ensureModelsFresh();
  }, [enabled]);
}

/** 应用级调度：启动、定时、窗口回焦/可见时保鲜（登录后才触发）。 */
export function useModelCatalogScheduler() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    let disposed = false;
    const tick = () => {
      if (disposed || !isLoggedIn()) return;
      void ensureModelsFresh();
    };
    tick(); // 启动即保鲜（用户走到选择器之前就完成）
    const timer = window.setInterval(tick, CATALOG_POLL_MS);
    const onVisible = () => {
      if (!document.hidden) tick();
    };
    window.addEventListener("focus", tick);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", tick);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
}

// 测试隔离桥：test-setup 通过它重置本模块状态（不直接 import 本模块，避免在
// mock lib/api 的用例里提前绑定真实 request）
registerModelCatalogReset(resetModelCatalogForTest);
