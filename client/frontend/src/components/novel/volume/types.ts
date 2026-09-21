// GET /novels/{pid}/volumes/{ref} 详情契约（client/backend/volumes/service.get_volume）
// 标量字段 DB 可空，缺失时后端省略键 → 这里标 optional；
// c-volume-antagonist：template_name/goal/plants/reveals 已退役（GET 不回、PUT 422 拒收），
// 卷角色＝各章章纲聚合只读；剧情节点行集沿用。

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
  core_conflict?: string | null;
  ending?: string | null;
  chapter_target?: number | null;
  /** 进场（resolve_prev_ending 单源：事实优先） */
  prev_ending?: { text: string; source: string } | null;
  /** 本卷的坎（c-volume-antagonist） */
  antagonist_type?: string | null;
  antagonist_line?: string | null;
  /** 角色聚合视图（只读）：{name, role}——role 为「反派」或空 */
  cast_members: Array<{ name: string; role: string }>;
  plot_nodes: VolumePlotNode[];
  /** 本卷旧稿支线章数（不混入台账/计数，仅汇总提示） */
  ghost_count: number;
  /** 主线章列表（ghost 已滤除，按章序） */
  chapters: VolumeChapterMeta[];
}
