/** useZhuqueCheck（c-zhuque-ai-detect）：朱雀检测编排单源。
 *
 * - 状态仓挂**路由边界之上**（模块级单例 store）：跨 /config 路由切换存活、
 *   跨页签/视图存活；应用重启即弃（不进 localStorage/DB，spec 不落库边界）。
 * - 三消费点（右栏行、标题区结果条、正文 Decorations）经 useSyncExternalStore
 *   订阅同一状态；显示开关（prefs）由消费点各自读取，不在这里。
 * - run()：AbortController 防重复点击；切章卸载时 abort（effect cleanup）；
 *   flush 由调用方注入（ChapterWorkspace 传 store.flush——落盘由前端保证，
 *   后端只读盘上文本）。
 * - stale：正文编辑后由 ProsePane 以实时指纹调 markStale()（live ≠ 送检指纹
 *   → 标注与结果条整体转「可能过期」，重检恢复）。
 */
import { useSyncExternalStore, useEffect, useCallback } from "react";
import { api } from "@/lib/api";

export interface ZhuqueSegment {
  paragraph_index: number;
  label: 0 | 1 | 2; // 0=人工 1=AI 2=疑似
  confidence: number;
}

export interface ZhuqueResult {
  ok: true;
  prose_hash: string;
  checked_at?: string;
  summary: {
    human_ratio: number;
    suspect_ratio: number;
    ai_ratio: number;
    softmax_confidence: number;
  };
  segments: ZhuqueSegment[];
  usage_tokens: number;
}

export interface ZhuqueError {
  status?: number;
  reason?: string;
  message: string;
}

export interface ZhuqueState {
  status: "idle" | "running" | "ok" | "error";
  result?: ZhuqueResult;
  proseHash?: string;
  stale: boolean;
  error?: ZhuqueError;
  /** 服务端落库时间（ISO，c-zhuque-persist）：结果条「MM-DD 检测」事实源 */
  checkedAt?: string;
}

const IDLE: ZhuqueState = { status: "idle", stale: false };

/** 会话键＝书+章复合（c-zhuque-clear-keyscope）：裸 chapterRef 每本书都有 vol-1-ch-1，
 *  跨书同 ref 会串缓存/水位；ref 书内唯一，复合即全局唯一（DB 层仍按章 UUID 主键）。 */
const keyOf = (projectId: string, chapterRef: string) => `${projectId}:${chapterRef}`;

const stateByRef = new Map<string, ZhuqueState>();
/** inflight 记录带 prev（重检前的上一份 ok 结果）：abort（切章/卸载）时不丢会话内缓存 */
const inflight = new Map<string, { ac: AbortController; prev: ZhuqueState | undefined }>();
const listeners = new Set<() => void>();

/** 落盘 provider：ChapterWorkspace 注册本章 store.flush（落盘由前端保证），
 *  检测行（NovelWorkspace 层 Rail）跨层调用——不走 props/railData（渲染死循环纪律）。 */
let flushProvider: (() => Promise<void>) | null = null;
export function registerZhuqueFlush(fn: (() => Promise<void>) | null) {
  flushProvider = fn;
}

function notify() {
  listeners.forEach((l) => l());
}

function setState(ref: string, patch: Partial<ZhuqueState> | null) {
  if (patch === null) {
    stateByRef.delete(ref);
  } else {
    const prev = stateByRef.get(ref) ?? IDLE;
    stateByRef.set(ref, { ...prev, ...patch });
  }
  notify();
}

export function abortZhuque(projectId: string, chapterRef: string) {
  const key = keyOf(projectId, chapterRef);
  const entry = inflight.get(key);
  if (!entry) return;
  entry.ac.abort();
  inflight.delete(key);
  const st = stateByRef.get(key);
  if (st?.status !== "running") return;
  // 重检被中断：恢复重检前的上一份 ok 结果（会话内缓存保留）；无旧结果才落 idle
  if (entry.prev && entry.prev.status === "ok") setState(key, entry.prev);
  else setState(key, { status: "idle", stale: false });
}

/** 测试/调试：直读仓状态（绕过渲染订阅）。 */
export function zhuqueStoreGetState(projectId: string, chapterRef: string): ZhuqueState {
  return stateByRef.get(keyOf(projectId, chapterRef)) ?? IDLE;
}

/** 测试复位（清全部会话内状态）。 */
export function zhuqueStoreReset() {
  inflight.forEach((e) => e.ac.abort());
  inflight.clear();
  stateByRef.clear();
  hydrated.clear(); // 水位同清（c-zhuque-persist）：复位后同章可重新水合
  hydrating.clear();
  notify();
}

/** 模块级 run：检测行（右栏）直接调用；hook 消费点经订阅取状态。 */
export async function runZhuqueCheck(projectId: string, chapterRef: string) {
  const key = keyOf(projectId, chapterRef);
  if (inflight.has(key)) return; // 在途防抖
  const ac = new AbortController();
  const prev = stateByRef.get(key);
  inflight.set(key, { ac, prev });
  setState(key, { status: "running", stale: false });
  try {
    try {
      await flushProvider?.(); // 落盘由前端保证（后端只读盘上文本）
    } catch {
      setState(key, {
        status: "error",
        error: { message: "正文保存未完成，请重试" },
      });
      return;
    }
    const result = (await api.post(
      `/novels/${projectId}/chapters/${chapterRef}/zhuque-check`,
      undefined,
      { signal: ac.signal, quiet: true },
    )) as ZhuqueResult;
    setState(key, {
      status: "ok",
      result,
      proseHash: result.prose_hash,
      stale: false,
      checkedAt: result.checked_at,
    });
  } catch (e) {
    const err = e as Error & { status?: number; reason?: string };
    if (err.name === "AbortError") {
      // 中断（切章/卸载）：恢复重检前的上一份结果，无则 idle（与 abortZhuque 同语义）
      const p = stateByRef.get(key);
      if (p?.status === "running") {
        if (prev && prev.status === "ok") setState(key, prev);
        else setState(key, { status: "idle", stale: false });
      }
      return;
    }
    setState(key, {
      status: "error",
      error: { status: err.status, reason: err.reason, message: err.message || "检测失败，请重试" },
    });
  } finally {
    inflight.delete(key);
  }
}

/** 存档水合单飞（c-zhuque-persist）：仓内无该章状态时读库回填一次；跨消费点/重挂载防抖。 */
const hydrated = new Set<string>();
const hydrating = new Set<string>();

function hydrateFromStore(projectId: string, chapterRef: string) {
  const key = keyOf(projectId, chapterRef);
  if (hydrated.has(key) || hydrating.has(key)) return;
  if ((stateByRef.get(key) ?? IDLE).status !== "idle") return; // 仓已有状态（running/ok/error）不覆盖
  hydrating.add(key);
  // Promise 链包住：api 桩同步抛错/返回非 Promise 时静默降级，不炸挂载
  void Promise.resolve()
    .then(() => api.get(`/novels/${projectId}/chapters/${chapterRef}/zhuque-result`, { quiet: true }))
    .then((d) => {
      hydrated.add(key);
      const r = d as {
        stored: boolean;
        prose_hash?: string;
        result?: ZhuqueResult;
        checked_at?: string;
      };
      if (!r?.stored || !r.result) return;
      // 水合只填空：在途/已有会话状态时丢弃（保持单源不被旧档顶掉）——必须查复合键，
      // 裸键在复合键世界恒空查，守卫失效会让在途检测被旧档顶掉
      const cur = stateByRef.get(key) ?? IDLE;
      if (cur.status !== "idle" || inflight.has(key)) return;
      setState(key, {
        status: "ok",
        result: r.result,
        proseHash: r.prose_hash,
        stale: false, // 陈旧判定交载入方按实时指纹评估（ProsePane 载入评估）
        checkedAt: r.checked_at,
      });
    })
    .catch(() => {
      hydrated.add(key); // 失败静默降级为无存档，不反复打
    })
    .finally(() => hydrating.delete(key));
}

export function useZhuqueCheck(projectId: string, chapterRef: string) {
  const state = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => stateByRef.get(keyOf(projectId, chapterRef)) ?? IDLE,
    () => IDLE,
  );

  // 水合（c-zhuque-persist）：进章时仓内无状态则读库存档恢复
  useEffect(() => {
    hydrateFromStore(projectId, chapterRef);
  }, [projectId, chapterRef]);

  // 切章：中断旧章在途请求（spec：切章挂 abort）
  useEffect(() => {
    return () => abortZhuque(projectId, chapterRef);
  }, [projectId, chapterRef]);

  const run = useCallback(
    async (opts?: { flush?: () => Promise<void> }) => {
      if (opts?.flush) registerZhuqueFlush(opts.flush);
      await runZhuqueCheck(projectId, chapterRef);
    },
    [projectId, chapterRef],
  );

  /** 清除＝连存档一起删（c-zhuque-clear-keyscope 拍板 B）：DELETE 成功/404 才清会话态，
   *  失败保态（避免「屏上清了、重启复活」割裂）。 */
  const clear = useCallback(async () => {
    try {
      await Promise.resolve()
        .then(() => api.delete(`/novels/${projectId}/chapters/${chapterRef}/zhuque-result`, { quiet: true }));
    } catch (e) {
      const err = e as { status?: number };
      if (err?.status !== 404) return; // 删除失败：保持现状，不走清态
    }
    setState(keyOf(projectId, chapterRef), null);
  }, [projectId, chapterRef]);

  /** 失效判定（c-zhuque-stale-symmetric 双向）：stale ≡ 当前正文指纹 ≠ 送检指纹。
   *  不一致 → 标注/结果条转「可能过期」；一致（撤销回到送检态/切页往返两段式
   *  选章恢复收敛）→ 自动解除过期态恢复彩色。只在状态翻转时写，避免无谓 notify。 */
  const evaluateStale = useCallback(
    (liveHash: string) => {
      const key = keyOf(projectId, chapterRef);
      const st = stateByRef.get(key);
      if (st?.status !== "ok" || !st.proseHash) return;
      const mismatch = st.proseHash !== liveHash;
      if (mismatch !== st.stale) setState(key, { stale: mismatch });
    },
    [projectId, chapterRef],
  );

  return { state, run, clear, evaluateStale };
}
