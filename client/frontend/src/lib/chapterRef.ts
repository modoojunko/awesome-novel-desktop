/**
 * 章 ref 语法单源（chapter-rewrite）：主线与旧稿支线双形制。
 *
 * - 主线：`vol-{N}-ch-{M}`
 * - 旧稿：`vol-{N}-ch-{M}-r{8hex}`（内容寻址快照；hash=源正文摘要前缀）
 *
 * 所有 ref 解析/取号 SHALL 经本模块（源码守卫测试会拒绝其它文件里的
 * 裸 `-ch-(\d+)` 正则）；返回判别联合，调用方必须显式处理 ghost 分支
 * （旧实现返回 null 导致点旧稿静默无响应）。
 */

export type ParsedRef =
  | { kind: "mainline"; vol: number; ch: number }
  | { kind: "ghost"; vol: number; ch: number; of: string; hash: string };

const MAINLINE_RE = /^vol-(\d+)-ch-(\d+)$/;
const GHOST_RE = /^vol-(\d+)-ch-(\d+)-r([0-9a-f]{8})$/;

export function parseChapterRef(ref: string): ParsedRef | null {
  const g = ref.match(GHOST_RE);
  if (g) {
    return {
      kind: "ghost",
      vol: parseInt(g[1], 10),
      ch: parseInt(g[2], 10),
      of: `vol-${g[1]}-ch-${g[2]}`,
      hash: g[3],
    };
  }
  const m = ref.match(MAINLINE_RE);
  if (m) {
    return { kind: "mainline", vol: parseInt(m[1], 10), ch: parseInt(m[2], 10) };
  }
  return null;
}

export function isGhostRef(ref: string): boolean {
  return GHOST_RE.test(ref);
}

/** 章号（旧稿返回其源章号）；不可解析返回 0。 */
export function chapterNoOf(ref: string): number {
  return parseChapterRef(ref)?.ch ?? 0;
}

/** 卷号；不可解析返回 0。 */
export function volNoOf(ref: string): number {
  return parseChapterRef(ref)?.vol ?? 0;
}
