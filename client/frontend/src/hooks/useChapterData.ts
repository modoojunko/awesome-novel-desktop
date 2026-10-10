import {
  CHAPTER_WORD_TARGET_DEFAULT,
  getCachedChapterWordTarget,
} from "@/lib/chapterTarget";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** 保存四态：自动保存中 / 已保存 / 未保存 / 失败（含重试） */
export type SaveState = "autosaving" | "saved" | "unsaved" | "failed";

/**
 * 归档任务态（c-chapter-dossier 受理制）：点归档 → 后台 AI 提取四域 →
 * 成功才置 archived。extracting 期间本章锁定（编辑/归档/取消归档禁用）。
 */
export interface ArchiveJobState {
  state: "extracting" | "failed" | "done";
  error?: string | null;
  startedAt: number;
}

export interface ChapterPayload {
  volume: number;
  chapter: number;
  title: string;
  status: string;
  outline?: {
    summary?: string;
    [key: string]: any;
  };
  prose?: string;
  [key: string]: any;
}

export interface UseChapterDataReturn {
  chapter: ChapterPayload | null;
  prose: string;
  status: string;
  setProse: (v: string) => void;
  setStatus: (v: string) => void;
  isDirty: boolean;
  saveState: SaveState;
  wordCount: number;
  targetWords: number;
  setTargetWords: (n: number) => void;
  save: () => void;
  /** 落盘并等待完成（重写快照前置） */
  flush: () => Promise<void>;
  retry: () => void;
  /** 归档受理（aiSummary=归档 AI 摘要开关）：模型就绪→后台提取（archiveJob 跟踪，
   *  提取成功才置 archived）；模型未就绪→服务端同步归档。返回是否受理成功 */
  archive: (options?: { aiSummary?: boolean }) => Promise<boolean>;
  /** 逃生阀：跳过提取仍归档（提取失败后出现；确认由调用方 UI 承担） */
  skipArchive: () => Promise<boolean>;
  /** 重试/补提取（未归档章＝完整归档提取；已归档章＝只重写本章变化行）。
   *  返回 null＝已受理；返回错误文案＝调用方应就地 toast（store.error 无渲染面）。 */
  retryExtraction: () => Promise<string | null>;
  /** 归档任务态（受理制）；null＝无任务（从未受理或已终态清除） */
  archiveJob: ArchiveJobState | null;
  /** 恢复归档章为可编辑态（撤下归档全文 + 状态回退），完成后重拉章数据。
   *  c-archived-readonly 小改路径：横幅「恢复编辑」出口（整体重写走 /rewrite）。 */
  unarchive: () => Promise<void>;
  reload: () => Promise<void>;
  loading: boolean;
  error: string | null;
  setError: (msg: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** 去空白中文字符数（与后端 /tree 同口径 B5）。 */
export function countChars(text: string): number {
  if (!text) return 0;
  return text.replace(/\s/g, "").length;
}

/** targetWords 持久化 key（localStorage）。 */
function targetKey(projectId: string, ref: string): string {
  return `target-words-${projectId}-${ref}`;
}

/** 本章目标字数的兜底默认＝作品偏好「章节默认字数」（c-chapter-default-words，缓存读；
 *  逐章未单独设定时生效）；常量缺省 2500 与后端 book_prefs_model 同源。 */
export const DEFAULT_TARGET = CHAPTER_WORD_TARGET_DEFAULT;

/** 自动保存防抖窗口（N8）。 */
const AUTOSAVE_DEBOUNCE_MS = 1500;

// ---------------------------------------------------------------------------
// ChapterStore —— 每章一份的模块级单例（useChapterData 多实例共享）
//
// 修复前：ChapterEditor 与 ChapterStatusBar 各自持有一份 hook 状态和防抖
// timer，状态栏实例的 prose 停留在旧值，点「保存」会把旧正文 PUT 回去，
// 覆盖编辑器里未落盘的新输入（丢失更新）。修复后：同一章的所有消费者
// 订阅同一 store，全章唯一防抖 timer / 唯一 in-flight 保存。
// ---------------------------------------------------------------------------

interface ChapterStoreState {
  loading: boolean;
  error: string | null;
  chapter: ChapterPayload | null;
  prose: string;
  status: string;
  initial: { prose: string; status: string };
  saveState: SaveState;
  targetWords: number;
  archiveJob: ArchiveJobState | null;
}

type Listener = () => void;

class ChapterStore {
  readonly projectId: string;
  readonly ref: string;

  private listeners = new Set<Listener>();
  private saving = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private refCount = 0;
  private disposed = false;

  state: ChapterStoreState;

  constructor(projectId: string, ref: string) {
    this.projectId = projectId;
    this.ref = ref;
    const raw = localStorage.getItem(targetKey(projectId, ref));
    const n = raw ? parseInt(raw, 10) : NaN;
    this.state = {
      loading: true,
      error: null,
      chapter: null,
      prose: "",
      status: "outline",
      initial: { prose: "", status: "outline" },
      saveState: "saved",
      targetWords: Number.isFinite(n) && n > 0 ? n : getCachedChapterWordTarget(projectId),
      archiveJob: null,
    };
  }

  subscribe = (fn: Listener): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getSnapshot = (): ChapterStoreState => this.state;

  /** 首个消费者挂载 → 拉取章节数据。 */
  acquire = () => {
    this.refCount += 1;
    if (this.disposed) {
      // React 19 StrictMode（仅开发态）挂载即「卸载→重挂」：release() 把本实例置
      // disposed 并逐出注册表，而持有它的 useMemo 不会重算——再次 acquire 若不复活，
      // load() 的 `if (this.disposed) return` 会把章数据永远丢弃（实测 dev 下章节
      // 恒 0 字、接口数据正常）。复活并重新收编注册表，让后续 getStore 仍取本实例。
      this.disposed = false;
      stores.set(storeKey(this.projectId, this.ref), this);
    }
    if (this.refCount === 1) void this.load();
  };

  /** 末位消费者卸载 → 脱离注册表 + 脏数据兜底 flush（防丢窗口）。 */
  release = () => {
    this.refCount -= 1;
    if (this.refCount > 0 || this.disposed) return;
    this.disposed = true;
    stores.delete(storeKey(this.projectId, this.ref));
    this.clearTimer();
    this.clearPollTimer();
    if (this.isDirty() && !this.saving) void this.doSave();
  };

  private update(patch: Partial<ChapterStoreState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((l) => l());
  }

  isDirty = () =>
    this.state.prose !== this.state.initial.prose ||
    this.state.status !== this.state.initial.status;

  setProse = (p: string) => {
    if (p === this.state.prose) return;
    if (this.extracting()) return; // 归档提取中本章锁定（受理制全程软锁）
    this.update({ prose: p });
    this.afterChange();
  };

  setStatus = (st: string) => {
    if (st === this.state.status) return;
    if (this.extracting()) return;
    this.update({ status: st });
    this.afterChange();
  };

  extracting = (): boolean => this.state.archiveJob?.state === "extracting";

  setError = (msg: string) => this.update({ error: msg });

  private afterChange() {
    if (this.isDirty() && this.state.saveState === "saved") {
      this.update({ saveState: "unsaved" });
    }
    this.clearTimer();
    if (this.isDirty()) {
      this.timer = setTimeout(() => {
        this.timer = null;
        void this.doSave();
      }, AUTOSAVE_DEBOUNCE_MS);
    }
  }

  private clearTimer() {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  load = async (): Promise<void> => {
    this.update({ loading: true, error: null });
    try {
      const data: ChapterPayload = await api.get(
        `/novels/${this.projectId}/chapters/${this.ref}`,
      );
      if (this.disposed) return;
      const p = data.prose || "";
      const st = data.status || "outline";
      this.update({
        chapter: data,
        prose: p,
        status: st,
        initial: { prose: p, status: st },
        saveState: "saved",
        loading: false,
        error: null,
      });
      // 受理制恢复：服务端仍在提取（作者切章返回）→ 恢复任务态＋续轮询
      if (st !== "archived") void this.checkArchiveJob();
    } catch (e: any) {
      if (this.disposed) return;
      this.update({ loading: false, error: e.message || "加载章节失败" });
    }
  };

  private pollTimer: ReturnType<typeof setTimeout> | null = null;

  private clearPollTimer() {
    if (this.pollTimer !== null) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  }

  /** 查一次服务端提取任务态：在跑→恢复 extracting＋轮询；已终态且章归档→对齐。 */
  private checkArchiveJob = async (): Promise<void> => {
    if (this.disposed) return;
    try {
      const d = await api.get(
        `/novels/${this.projectId}/chapters/${this.ref}/dossier`,
      );
      if (this.disposed) return;
      const st = d?.extraction?.state;
      if (st === "extracting") {
        if (!this.extracting()) {
          this.update({
            archiveJob: { state: "extracting", startedAt: Date.now() },
          });
          this.schedulePoll();
        }
      } else if (st === "failed") {
        this.update({
          archiveJob: {
            state: "failed",
            error: d?.extraction?.error || "提取失败",
            startedAt: Date.now(),
          },
        });
      } else if (this.state.archiveJob?.state === "extracting") {
        // 终态但本地还以为在提取（如切走期间完成）→ 对齐
        await this.onArchiveSettled();
      }
    } catch {
      /* 变化端点不可用（旧后端）→ 忽略，保持无任务态 */
    }
  };

  private schedulePoll() {
    this.clearPollTimer();
    this.pollTimer = setTimeout(() => {
      void this.pollArchive();
    }, 3000);
  }

  private pollArchive = async (): Promise<void> => {
    if (this.disposed || !this.extracting()) return;
    try {
      const d = await api.get(
        `/novels/${this.projectId}/chapters/${this.ref}/dossier`,
      );
      if (this.disposed) return;
      const st = d?.extraction?.state;
      if (st === "failed") {
        this.update({
          archiveJob: {
            state: "failed",
            error: d?.extraction?.error || "提取失败",
            startedAt: Date.now(),
          },
        });
        return; // 终态停轮询；重试/逃生阀由用户驱动
      }
      if (st === "extracting" && !d?.archived) {
        this.schedulePoll();
        return;
      }
      await this.onArchiveSettled();
    } catch {
      this.schedulePoll(); // 网络抖动继续轮询
    }
  };

  /** 提取终态且服务端已归档：重拉章数据＋派发事件＋任务置 done。 */
  private onArchiveSettled = async (): Promise<void> => {
    this.clearPollTimer();
    await this.load();
    this.update({
      status: "archived",
      initial: { prose: this.state.prose, status: "archived" },
      saveState: "saved",
      archiveJob: { state: "done", startedAt: Date.now() },
    });
    window.dispatchEvent(
      new CustomEvent("chapter:archived", {
        detail: { projectId: this.projectId, ref: this.ref },
      }),
    );
  };

  doSave = async (): Promise<void> => {
    if (this.saving) return;
    const { prose: p, status: st, chapter: ch } = this.state;
    if (!ch) return;
    // 与后端 save_chapter 派生同口径：首次落非空正文 outline → writing。
    // 前端同步派生，否则 status 停留 outline（徽章错）且与 initial 恒不等
    // → isDirty 恒真 → 防抖保存死循环。
    const nextStatus = p.trim() && st === "outline" ? "writing" : st;
    this.saving = true;
    this.update({ saveState: "autosaving" });
    try {
      // 优先 PUT .../prose（后端 #12）。仅当端点结构性缺失（404/405）才降级
      // 全量 PUT；网络错误/5xx/403 直接 failed —— 降级前会重取最新章再合并，
      // 避免用陈旧全量 payload 覆盖其他入口（AI 设定等）刚写入的 outline。
      try {
        await api.put(`/novels/${this.projectId}/chapters/${this.ref}/prose`, {
          prose: p,
        });
      } catch (e: any) {
        if (e?.status !== 404 && e?.status !== 405) throw e;
        const latest: ChapterPayload = await api.get(
          `/novels/${this.projectId}/chapters/${this.ref}`,
        );
        const updated: ChapterPayload = { ...latest, prose: p, status: nextStatus };
        await api.put(`/novels/${this.projectId}/chapters/${this.ref}`, updated);
        this.update({ chapter: updated });
      }
      // 以此刻 store 内 chapter 为底（降级路径刚写入含最新 outline 的 updated）
      const base = this.state.chapter ?? ch;
      this.update({
        chapter: { ...base, status: nextStatus },
        status: nextStatus,
        initial: { prose: p, status: nextStatus },
        saveState: "saved",
      });
    } catch (e: any) {
      this.update({ saveState: "failed", error: e.message || "保存失败" });
    } finally {
      this.saving = false;
    }
  };

  save = () => {
    void this.doSave();
  };

  /** 落盘并等待完成（chapter-rewrite：重写快照必须先于旧稿留存）。
   *  已有在飞保存时轮询等待其收尾；脏则再存一次。 */
  flush = async (): Promise<void> => {
    for (let i = 0; i < 40 && this.saving; i++) {
      await new Promise((r) => setTimeout(r, 50));
    }
    if (this.isDirty()) await this.doSave();
  };

  retry = () => {
    void this.doSave();
  };

  setTargetWords = (n: number) => {
    const safe =
      Number.isFinite(n) && n > 0 ? Math.round(n) : getCachedChapterWordTarget(this.projectId);
    localStorage.setItem(targetKey(this.projectId, this.ref), String(safe));
    this.update({ targetWords: safe });
  };

  archive = async (options?: { aiSummary?: boolean }): Promise<boolean> => {
    const { prose: p } = this.state;
    if (!p.trim()) return false;
    if (this.extracting()) return true; // 受理幂等：在跑不重复受理
    // 受理制以 DB 正文为单一事实源（提取/归档/哈希全按 DB 值）——防抖窗口内
    // 未落盘的末段必须先 flush，否则按旧稿归档、且随后落盘必触发 prose_changed
    await this.flush();
    this.update({ error: null });
    try {
      const resp = await api.post(`/novels/${this.projectId}/chapters/${this.ref}/archive`, {
        full_text: p,
        // ai_summary=false：设置里关掉归档 AI 摘要（后端降级为正文摘要）
        ai_summary: options?.aiSummary ?? true,
      });
      if (resp?.state === "extracting") {
        // 受理制（c-chapter-dossier）：后台提取中——status 不动，任务态跟踪＋轮询；
        // 服务端真置 archived 后才派发事件（不乐观置位）
        this.update({
          archiveJob: { state: "extracting", startedAt: Date.now() },
        });
        this.schedulePoll();
        return true;
      }
      // 模型未就绪：服务端同步归档（无变化记录）——保持旧行为
      this.update({
        status: "archived",
        initial: { prose: p, status: "archived" },
        saveState: "saved",
        archiveJob: { state: "done", startedAt: Date.now() },
      });
      // 通知工作台树刷新 → 卷章列表 status 已置 archived → 📦 即时同步
      window.dispatchEvent(
        new CustomEvent("chapter:archived", {
          detail: { projectId: this.projectId, ref: this.ref },
        }),
      );
      return true;
    } catch (e: any) {
      this.update({ error: e.message || "归档失败", saveState: "failed" });
      return false;
    }
  };

  skipArchive = async (): Promise<boolean> => {
    try {
      await this.flush(); // skip 同样以 DB 正文收口——先落盘防抖窗口
      await api.post(`/novels/${this.projectId}/chapters/${this.ref}/dossier/skip`);
      await this.load();
      this.update({
        status: "archived",
        initial: { prose: this.state.prose, status: "archived" },
        saveState: "saved",
        archiveJob: { state: "done", startedAt: Date.now() },
      });
      window.dispatchEvent(
        new CustomEvent("chapter:archived", {
          detail: { projectId: this.projectId, ref: this.ref },
        }),
      );
      return true;
    } catch (e: any) {
      this.update({ error: e.message || "跳过提取失败" });
      return false;
    }
  };

  retryExtraction = async (): Promise<string | null> => {
    if (this.extracting()) return null;
    try {
      await this.flush(); // 未归档章的完整归档重试：先落盘（rows_only 补提无需，但 flush 无害）
      await api.post(`/novels/${this.projectId}/chapters/${this.ref}/dossier/extract`, {});
      this.update({
        archiveJob: { state: "extracting", startedAt: Date.now() },
      });
      this.schedulePoll();
      return null;
    } catch (e: any) {
      const msg = e.message || "重试提取失败";
      this.update({ error: msg });
      return msg;
    }
  };

  unarchive = async (): Promise<void> => {
    this.update({ error: null });
    try {
      await api.post(`/novels/${this.projectId}/chapters/${this.ref}/unarchive`);
      // 服务端状态已回退（draft）→ 重拉章数据，store 与 initial 一并对齐
      await this.load();
      // 复用归档事件通道 → 工作台树 📦 同步撤下
      window.dispatchEvent(
        new CustomEvent("chapter:archived", {
          detail: { projectId: this.projectId, ref: this.ref },
        }),
      );
    } catch (e: any) {
      this.update({ error: e.message || "恢复失败" });
    }
  };
}

const stores = new Map<string, ChapterStore>();

function storeKey(projectId: string, ref: string): string {
  return `${projectId}::${ref}`;
}

function getStore(projectId: string, ref: string): ChapterStore {
  const key = storeKey(projectId, ref);
  let s = stores.get(key);
  if (!s) {
    s = new ChapterStore(projectId, ref);
    stores.set(key, s);
  }
  return s;
}

/** 仅测试用：清空模块级 store 注册表，避免跨用例状态串扰。 */
export function resetChapterStoresForTest() {
  stores.clear();
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChapterData(
  projectId: string,
  ref: string,
): UseChapterDataReturn {
  const store = useMemo(() => getStore(projectId, ref), [projectId, ref]);

  useEffect(() => {
    store.acquire();
    return () => store.release();
  }, [store]);

  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);

  const isDirty =
    state.prose !== state.initial.prose || state.status !== state.initial.status;

  const wordCount = useMemo(() => countChars(state.prose), [state.prose]);

  return {
    chapter: state.chapter,
    prose: state.prose,
    status: state.status,
    setProse: store.setProse,
    setStatus: store.setStatus,
    isDirty,
    saveState: state.saveState,
    wordCount,
    targetWords: state.targetWords,
    setTargetWords: store.setTargetWords,
    save: store.save,
    flush: store.flush,
    retry: store.retry,
    archive: store.archive,
    skipArchive: store.skipArchive,
    retryExtraction: store.retryExtraction,
    archiveJob: state.archiveJob,
    unarchive: store.unarchive,
    reload: store.load,
    loading: state.loading,
    error: state.error,
    setError: store.setError,
  };
}

export default useChapterData;
