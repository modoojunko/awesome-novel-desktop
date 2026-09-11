import { useEffect, useMemo, useSyncExternalStore } from "react";
import { api } from "@/lib/api";
import { recordLoreSuggestions } from "@/lib/loreSuggestions";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** 保存四态：自动保存中 / 已保存 / 未保存 / 失败（含重试） */
export type SaveState = "autosaving" | "saved" | "unsaved" | "failed";

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
  retry: () => void;
  /** 归档（aiSummary=归档 AI 摘要开关）；返回是否成功 */
  archive: (options?: { aiSummary?: boolean }) => Promise<boolean>;
  /** 恢复归档章为可编辑态（撤下归档全文 + 状态回退），完成后重拉章数据 */
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

export const DEFAULT_TARGET = 2500;

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
      targetWords: Number.isFinite(n) && n > 0 ? n : DEFAULT_TARGET,
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
    if (this.refCount === 1) void this.load();
  };

  /** 末位消费者卸载 → 脱离注册表 + 脏数据兜底 flush（防丢窗口）。 */
  release = () => {
    this.refCount -= 1;
    if (this.refCount > 0 || this.disposed) return;
    this.disposed = true;
    stores.delete(storeKey(this.projectId, this.ref));
    this.clearTimer();
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
    this.update({ prose: p });
    this.afterChange();
  };

  setStatus = (st: string) => {
    if (st === this.state.status) return;
    this.update({ status: st });
    this.afterChange();
  };

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
    } catch (e: any) {
      if (this.disposed) return;
      this.update({ loading: false, error: e.message || "加载章节失败" });
    }
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

  retry = () => {
    void this.doSave();
  };

  setTargetWords = (n: number) => {
    const safe = Number.isFinite(n) && n > 0 ? Math.round(n) : DEFAULT_TARGET;
    localStorage.setItem(targetKey(this.projectId, this.ref), String(safe));
    this.update({ targetWords: safe });
  };

  archive = async (options?: { aiSummary?: boolean }): Promise<boolean> => {
    const { prose: p } = this.state;
    if (!p.trim()) return false;
    this.update({ error: null });
    try {
      const resp = await api.post(`/novels/${this.projectId}/chapters/${this.ref}/archive`, {
        full_text: p,
        // ai_summary=false：设置里关掉归档 AI 摘要（后端降级为正文摘要）
        ai_summary: options?.aiSummary ?? true,
      });
      // lore-keeping（world-setting-v2）：归档识别的世界要素建议 → 暂存，世界页 06 确认
      if (resp && Array.isArray(resp.lore_suggestions) && resp.lore_suggestions.length) {
        recordLoreSuggestions(this.projectId, this.ref, resp.lore_suggestions);
      }
      this.update({
        status: "archived",
        initial: { prose: p, status: "archived" },
        saveState: "saved",
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
    retry: store.retry,
    archive: store.archive,
    unarchive: store.unarchive,
    reload: store.load,
    loading: state.loading,
    error: state.error,
    setError: store.setError,
  };
}

export default useChapterData;
