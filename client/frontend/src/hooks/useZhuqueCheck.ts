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
}

const IDLE: ZhuqueState = { status: "idle", stale: false };

const stateByRef = new Map<string, ZhuqueState>();
const inflight = new Map<string, AbortController>();
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

export function abortZhuque(ref: string) {
  inflight.get(ref)?.abort();
  inflight.delete(ref);
  const st = stateByRef.get(ref);
  if (st?.status === "running") setState(ref, { status: "idle" });
}

/** 测试/调试：直读仓状态（绕过渲染订阅）。 */
export function zhuqueStoreGetState(ref: string): ZhuqueState {
  return stateByRef.get(ref) ?? IDLE;
}

/** 测试复位（清全部会话内状态）。 */
export function zhuqueStoreReset() {
  inflight.forEach((ac) => ac.abort());
  inflight.clear();
  stateByRef.clear();
  notify();
}

/** 模块级 run：检测行（右栏）直接调用；hook 消费点经订阅取状态。 */
export async function runZhuqueCheck(projectId: string, chapterRef: string) {
  if (inflight.has(chapterRef)) return; // 在途防抖
  const ac = new AbortController();
  inflight.set(chapterRef, ac);
  setState(chapterRef, { status: "running", stale: false });
  try {
    try {
      await flushProvider?.(); // 落盘由前端保证（后端只读盘上文本）
    } catch {
      setState(chapterRef, {
        status: "error",
        error: { message: "正文保存未完成，请重试" },
      });
      return;
    }
    const result = (await api.post(
      `/api/novels/${projectId}/chapters/${chapterRef}/zhuque-check`,
      undefined,
      { signal: ac.signal, quiet: true },
    )) as ZhuqueResult;
    setState(chapterRef, {
      status: "ok",
      result,
      proseHash: result.prose_hash,
      stale: false,
    });
  } catch (e) {
    const err = e as Error & { status?: number; reason?: string };
    if (err.name === "AbortError") {
      setState(chapterRef, { status: "idle" });
      return;
    }
    setState(chapterRef, {
      status: "error",
      error: { status: err.status, reason: err.reason, message: err.message || "检测失败，请重试" },
    });
  } finally {
    inflight.delete(chapterRef);
  }
}

export function useZhuqueCheck(projectId: string, chapterRef: string) {
  const state = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => stateByRef.get(chapterRef) ?? IDLE,
    () => IDLE,
  );

  // 切章：中断旧章在途请求（spec：切章挂 abort）
  useEffect(() => {
    return () => abortZhuque(chapterRef);
  }, [chapterRef]);

  const run = useCallback(
    async (opts?: { flush?: () => Promise<void> }) => {
      if (opts?.flush) registerZhuqueFlush(opts.flush);
      await runZhuqueCheck(projectId, chapterRef);
    },
    [projectId, chapterRef],
  );

  const clear = useCallback(() => {
    setState(chapterRef, null);
  }, [chapterRef]);

  /** 正文编辑后由 ProsePane 调用：live 指纹 ≠ 送检指纹 → 标注/结果条转「可能过期」。 */
  const evaluateStale = useCallback(
    (liveHash: string) => {
      const st = stateByRef.get(chapterRef);
      if (st?.status === "ok" && st.proseHash && !st.stale && st.proseHash !== liveHash) {
        setState(chapterRef, { stale: true });
      }
    },
    [chapterRef],
  );

  return { state, run, clear, evaluateStale };
}
