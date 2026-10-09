/**
 * 章节默认字数（c-chapter-default-words，内测反馈#10）：**作品偏好** per-book 设置。
 *
 * 权威在后端（project_settings KV「book-prefs」，写正文生成链按它取章纲未填章的字数
 * 默认）；前端 localStorage 只作**展示缓存**——章纲表单「留空默认 XXX」文案与进度目标
 * 需要同步读，不能等异步请求。写入路径＝`saveChapterWordTarget`（PUT 后端成功后才更新
 * 缓存，前后端不打架）；读取路径＝缓存同步读（`getCachedChapterWordTarget`）＋
 * 项目切换时 `loadChapterWordTarget` 从后端回灌（换设备/清缓存后仍显示真值）。
 *
 * 区间与缺省与后端 settings/book_prefs_model.py 单源对拍
 * （client/backend/tests/test_shared_constants_parity.py）：表单放行值与生成侧夹取
 * 必须同一组数值。
 */

import { api } from "@/lib/api";

export const CHAPTER_WORD_TARGET_MIN = 500;
export const CHAPTER_WORD_TARGET_MAX = 6000;
export const CHAPTER_WORD_TARGET_DEFAULT = 2500;

const EVENT = "chapter-word-target-changed";

function cacheKey(projectId: string): string {
  return `pref.book.${projectId}.chapter_words`;
}

/** 归一：空/非数/越界 → 缺省 2500（与逐章 word_target 的夹取口径同族）。 */
export function normalizeChapterWordTarget(value: unknown): number {
  const n = typeof value === "string" ? parseInt(value, 10) : value;
  if (typeof n !== "number" || !Number.isFinite(n)) return CHAPTER_WORD_TARGET_DEFAULT;
  const rounded = Math.round(n);
  if (rounded < CHAPTER_WORD_TARGET_MIN || rounded > CHAPTER_WORD_TARGET_MAX) {
    return CHAPTER_WORD_TARGET_DEFAULT;
  }
  return rounded;
}

/** 展示缓存同步读：未缓存/损坏 → 缺省 2500（存量行为不变）。 */
export function getCachedChapterWordTarget(projectId: string): number {
  try {
    const raw = localStorage.getItem(cacheKey(projectId));
    return raw === null ? CHAPTER_WORD_TARGET_DEFAULT : normalizeChapterWordTarget(raw);
  } catch {
    return CHAPTER_WORD_TARGET_DEFAULT;
  }
}

/** 缓存写（含缺省值回写）：派发变更事件，工作台文案/目标立即跟随（prefs 同款约定）。 */
export function cacheChapterWordTarget(projectId: string, value: unknown): number {
  const safe = normalizeChapterWordTarget(value);
  try {
    localStorage.setItem(cacheKey(projectId), String(safe));
    window.dispatchEvent(new CustomEvent(EVENT));
  } catch {
    // localStorage 不可用（隐私模式等）：本次仅内存态生效
  }
  return safe;
}

/** 订阅变更（同页自定义事件＋跨页签 storage 事件）。 */
export function subscribeChapterWordTarget(cb: () => void): () => void {
  const on = () => cb();
  window.addEventListener(EVENT, on);
  window.addEventListener("storage", on);
  return () => {
    window.removeEventListener(EVENT, on);
    window.removeEventListener("storage", on);
  };
}

/** 后端读（GET book-prefs）→ 回灌缓存 → 返回值；失败抛给调用方（调用方回落缓存）。 */
export async function loadChapterWordTarget(projectId: string): Promise<number> {
  const doc = await api.get(
    `/novels/${projectId}/settings/book-prefs`,
  ) as { chapter_word_target?: unknown } | null;
  return cacheChapterWordTarget(projectId, doc?.chapter_word_target ?? null);
}

/** 后端写（PUT book-prefs）→ 成功后才更新缓存；失败抛出（表单保持打开可重试）。 */
export async function saveChapterWordTarget(
  projectId: string,
  value: unknown,
): Promise<number> {
  const safe = normalizeChapterWordTarget(value);
  const doc = await api.put(`/novels/${projectId}/settings/book-prefs`, {
    chapter_word_target: safe,
  }) as { chapter_word_target?: unknown } | null;
  return cacheChapterWordTarget(projectId, doc?.chapter_word_target ?? safe);
}
