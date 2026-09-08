/**
 * 图标注册表（Open Design v2）—— 路径照抄原型内联 SVG，禁 lucide/emoji。
 * 尺寸不写死：由上下文 CSS 控制（.btn svg 15px、.genre svg 12px…），
 * 与原型的 svg 用法完全一致；独立使用时传 size。
 */
import type { CSSProperties } from "react";

export const P = {
  // 通用
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chevronRight: '<path d="M9 6l6 6-6 6"/>',
  chevronDown: '<path d="M6 9l6 6 6-6"/>',
  check: '<path d="M5 13l4 4L19 7"/>',
  pencil: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  upload: '<path d="M12 15V4M7 8l5-5 5 5M5 20h14"/>',
  dots: '<circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none"/>',
  // 题材（list.html GENRE_ICON 原样）
  scifi: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 12l9 5 9-5"/><path d="M3 17l9 5 9-5"/>',
  mystery: '<path d="M9.5 11a2.5 2.5 0 110-5 2.5 2.5 0 010 5z"/><path d="M9.5 11v6M7 7L4.5 3.5M12 7l2.5-3.5M9.5 14H8M9.5 17H8"/>',
  city: '<path d="M3 21h18M5 21V8l7-5 7 5v13M9 21v-6h4v6"/><path d="M9 10h.01M13 10h.01M11 7h.01"/>',
  fantasy: '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6z"/>',
  wuxia: '<path d="M4 20c6-2 12-8 15-15M13 7l4 4M6 14l4 4"/>',
  history: '<path d="M12 8a4 4 0 100 8 4 4 0 000-8z"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
  other: '<path d="M12 3v18M3 12h18"/>',
  // 模型配置（model-config.html）
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  spinner: '<path d="M21 12a9 9 0 11-6.2-8.56"/>',
  // 书工作台（book.html）
  back: '<path d="M15 6l-6 6 6 6"/>',
  list: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/>',
  focus: '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>',
  lock: '<rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/>',
  star: '<path d="M12 2l2.4 6.2L21 9l-5 4.4 1.6 6.6L12 16.6 6.4 20 8 13.4 3 9l6.6-.8z"/>',
  up: '<path d="M6 15l6-6 6 6"/>',
  tune: '<path d="M4 7h13M10 12h10M4 17h7"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  dot: '<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>',
  // book.html SPARK_SVG 原样（设定表单「AI 帮我填」）
  spark:
    '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>',
  // 提示词管理页（PR 5 轻重皮）：复制 / 恢复(rotate-ccw) / 文档
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 012-2h9"/>',
  refresh: '<path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  doc: '<path d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9z"/><path d="M14 3v6h6M9 13h6M9 17h4"/>',
  // 收尾 PR（退役 lucide/emoji 的迁移面）
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5H5V6h5"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16.5h.01"/>',
  moon: '<path d="M20.5 14.5A8.5 8.5 0 019.5 3.5a8.5 8.5 0 1011 11z"/>',
  chat: '<path d="M4 5h16v11H8l-4 4z"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M3 20h18"/>',
  // 控制中心面板（c-account-control-center）：用户名取不到时的头像退化
  person: '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  backup: '<path d="M12 15V4M7 8l5-5 5 5M5 20h14"/>',
  restore: '<path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  logout: '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>',
} as const;

/** 供应商图标（model-config.html VENDORS 原样；原型唯一用圆头线帽的图标组） */
export const VENDOR_ICON: Record<string, string> = {
  openai: '<path d="M12 4.5l2.1 5.4 5.4 2.1-5.4 2.1-2.1 5.4-2.1-5.4-5.4-2.1 5.4-2.1z"/>',
  anthropic: '<path d="M12 5v14M5 12h14M7.5 7.5l9 9M16.5 7.5l-9 9"/>',
  deepseek: '<path d="M11 5a6 6 0 100 12 6 6 0 000-12zM18.5 18.5l-3.4-3.4"/>',
  glm: '<path d="M5 20V10M12 20V5M19 20v-6"/>',
  kimi: '<path d="M20 15a8 8 0 01-10.8-5.2A8 8 0 1020 15z"/>',
  qwen: '<path d="M12 5a7 7 0 110 14 7 7 0 010-14zM12 9a3 3 0 110 6 3 3 0 010-6z"/>',
  ollama: '<path d="M6 6h12v12H6zM10 6V4M14 6V4M10 20v-2M14 20v-2"/>',
  "openai-compat": '<path d="M9 15l6-6M11 7l1.6-1.6a3 3 0 014.2 4.2L15 11M13 17l-1.6 1.6a3 3 0 01-4.2-4.2L9 13"/>',
};

/** 题材名 → 图标：含 8 题材库全名（悬疑刑侦/都市言情…）到原型 7 图标的归类 */
export function genreIconPath(genre?: string | null): string {
  const g = genre || "";
  if (/科幻/.test(g)) return P.scifi;
  if (/悬疑|刑侦|推理/.test(g)) return P.mystery;
  if (/都市|言情|日常/.test(g)) return P.city;
  if (/玄幻|仙侠|奇幻/.test(g)) return P.fantasy;
  if (/武侠/.test(g)) return P.wuxia;
  if (/历史|古风/.test(g)) return P.history;
  return P.other;
}

interface IcoProps {
  d: string;
  /** 线宽：原型惯例 2（通用）/ 2.2-2.4（强调）；默认 2 */
  sw?: number;
  /** 圆头线帽（供应商图标组专用：stroke-linecap/join round） */
  round?: boolean;
  /** 填充图标（star 等原型 fill=currentColor 的用法） */
  fill?: boolean;
  size?: number;
  style?: CSSProperties;
  className?: string;
}

/** 原型内联 SVG 的 React 等价物：viewBox 24、stroke currentColor、fill none */
export function Ico({ d, sw = 2, round, fill, size, style, className }: IcoProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={fill ? "currentColor" : "none"}
      stroke={fill ? undefined : "currentColor"}
      strokeWidth={fill ? undefined : sw}
      strokeLinecap={round ? "round" : undefined}
      strokeLinejoin={round ? "round" : undefined}
      width={size}
      height={size}
      style={style}
      className={className}
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: d }}
    />
  );
}
