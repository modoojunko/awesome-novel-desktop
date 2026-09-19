// 卷纲表单态 ↔ PUT /volumes/{ref} payload（c-volume-view-storyline 换代）
// 语义：字符串标量随整包提交（后端 fields_set 判定，显式 null/[] 即清空）；
// chapter_target 留空 → payload null（清空通道）；plants/reveals textarea 一行一条
// ↔ list[str]；行集提交即整族替换。

import type {
  VolumeCastMember,
  VolumeDetail,
  VolumePlotNode,
} from "./types";

export interface VolumeFormData {
  title: string;
  summary: string;
  template_name: string;
  core_conflict: string;
  goal: string;
  ending: string;
  /** 输入框字符串；"" = 不设（payload 置 null 清空） */
  chapter_target: string;
  /** textarea 一行一条原文本 */
  plantsText: string;
  revealsText: string;
  cast_members: VolumeCastMember[];
  plot_nodes: VolumePlotNode[];
}

/** textarea 一行一条 → list[str]（与后端 normalize_line_list 同语义） */
export function splitLines(text: string): string[] {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function toVolumeFormData(d: VolumeDetail): VolumeFormData {
  return {
    title: d.title || "",
    summary: d.summary || "",
    template_name: d.template_name || "",
    core_conflict: d.core_conflict || "",
    goal: d.goal || "",
    ending: d.ending || "",
    chapter_target: d.chapter_target != null ? String(d.chapter_target) : "",
    plantsText: (d.plants || []).join("\n"),
    revealsText: (d.reveals || []).join("\n"),
    cast_members: (d.cast_members || []).map((m) => ({ ...m })),
    plot_nodes: (d.plot_nodes || []).map((n) => ({ ...n })),
  };
}

export function volumeFormToPayload(f: VolumeFormData): Record<string, unknown> {
  const target = f.chapter_target.trim();
  return {
    title: f.title.trim(),
    summary: f.summary,
    template_name: f.template_name,
    core_conflict: f.core_conflict,
    goal: f.goal,
    ending: f.ending,
    // 留空 = 显式 null 清空（后端 fields_set 通道）
    chapter_target: target === "" ? null : Number(target),
    plants: splitLines(f.plantsText),
    reveals: splitLines(f.revealsText),
    cast_members: f.cast_members.map((m) => ({
      who: m.who.trim(),
      target: m.target.trim(),
      change: m.change.trim(),
    })),
    plot_nodes: f.plot_nodes.map((n) => ({
      stage: n.stage,
      text: n.text.trim(),
    })),
  };
}
