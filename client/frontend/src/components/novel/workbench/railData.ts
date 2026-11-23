/** 工作台右栏章语境数据（c-rail-ai-only 起右栏只剩 AI 域）。
 *  c-retire-prose-aimodal：Rail/AiAssistPanel 渲染面退役，类型从 Rail.tsx 迁此
 *  ——NovelWorkspace 消费、ChapterWorkspace 上抛；只保留活字段（写法块/存稿信号
 *  随渲染面一并退役）。 */
import type { AiCheckKind } from "@/lib/aiCheck";

export interface OgStats {
  /** 归档门槛已满足项（分母＝必填项数，见 REQ_FIELDS）；操作页签统计卡在用 */
  reqOk: number;
  /** 正文页签统计卡在用 */
  planWords: number | null;
  /** 展示位已上移中栏头部 meta 行（2026-09-27）；随数据通道保留 */
  plotCount: number;
  castCount: number;
  /** 还缺的必填项标签（原型 aiList('还缺'…)；「补全缺失字段」以它为输入） */
  missingLabels?: string[];
}


export interface RailChapterData {
  /** 未保存标记（c-agent-page-ops）：随 railData 上行进助手提示词 */
  dirty?: string[];
  wordCount: number;
  targetWords: number;
  setTargetWords: (n: number) => void;
  archived: boolean;
  bookWords: number;
  /** 中栏当前页签（storyline col-ai 口径：右栏 AI 辅助随页签切换） */
  tab?: string;
  /** 章纲页签统计（归档门槛/计划字数/关键事件/出场角色） */
  ogStats?: OgStats;
  /** 剧情推演（章纲页签动作） */
  onSimulate?: () => void;
  /** 剧情抽卡（章纲页签动作；三版选一弹层，生成类归 PRO） */
  onPlotDraw?: () => void;
  /** 盘点出场人物（章纲页签动作；免费只读盘点＋PRO 抽卡，c-character-intro） */
  onCastReview?: () => void;
  /** 空章（留存格与剧情条目全空）：盘点行禁用 hint「先写剧情再盘点」 */
  castEmpty?: boolean;
  /** 盘点/抽卡在途（行「生成中…」） */
  castBusy?: boolean;
  /** 当前章 ref（右栏辅助面板按章取数） */
  chapterRef?: string;
  /** chapter-rewrite：下游「基于旧设定」章计数（NovelWorkspace 由树计算注入） */
  staleDownstream?: number;
  /** 章纲缺项补全（AI 产物回填章纲表单） */
  onFillGaps?: () => void;
  gapsLoading?: boolean;
  /** 六类案头检查（就地弹窗） */
  onAiCheck?: (kind: AiCheckKind) => void;
  /** 文风「AI 建议本章调整」触发（StyleShadowPane 信号拉取；2026-09-20 入口收口右栏） */
  onStyleSuggest?: () => void;
}
