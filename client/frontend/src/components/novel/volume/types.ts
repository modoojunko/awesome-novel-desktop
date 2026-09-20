// GET /novels/{pid}/volumes/{ref} 详情契约（client/backend/volumes/service.get_volume）
// 标量字段 DB 可空，缺失时后端省略键 → 这里标 optional；
// plants/reveals 契约 = list[str]（一行一条），行集 = 登场人物/剧情节点（c-volume-view-storyline 换代）

export interface VolumeCastMember {
  who: string;
  target: string;
  change: string;
}

export interface VolumePlotNode {
  stage: string;
  text: string;
}

/** 剧情节点阶段（固定六档，与后端 schemas.PLOT_STAGES 同源字面） */
export const PLOT_STAGES = [
  "开局铺垫",
  "冲突初现",
  "矛盾升级",
  "重要转折",
  "高潮爆发",
  "卷末收束",
] as const;

/** 结构模板（产品单源字面；ADJUSTMENTS ④ 登记不改「起承転結」） */
export const TEMPLATE_OPTIONS = [
  "三幕式",
  "起承転結",
  "悬疑递进",
  "人物弧线",
] as const;

export interface VolumeChapterMeta {
  ref: string;
  volume: number;
  chapter: number;
  title: string;
  status: string;
  word_count: number;
  has_prose: boolean;
  outline_status: string;
  archived: boolean;
  /** 本卷章节台账「章纲一句话」（Chapter.summary；可缺省） */
  outline_summary?: string;
}

export interface VolumeDetail {
  ref: string;
  volume: number;
  title: string;
  summary: string;
  template_name?: string | null;
  core_conflict?: string | null;
  goal?: string | null;
  ending?: string | null;
  chapter_target?: number | null;
  /** 展开依据（作者那一句/选中走法；卷纲表单只读行回看） */
  plan_line?: string | null;
  /** 进场（resolve_prev_ending 单源：事实优先） */
  prev_ending?: { text: string; source: string } | null;
  plants: string[];
  reveals: string[];
  cast_members: VolumeCastMember[];
  plot_nodes: VolumePlotNode[];
  /** 本卷旧稿支线章数（不混入台账/计数，仅汇总提示） */
  ghost_count: number;
  /** 主线章列表（ghost 已滤除，按章序） */
  chapters: VolumeChapterMeta[];
}
