// 卷纲表单态 ↔ PUT /volumes/{ref} payload（c-volume-antagonist 终版）
// 语义：字符串标量随整包提交（后端 fields_set 判定，显式 null/[] 即清空）；
// chapter_target 留空 → payload null（清空通道）；剧情节点行集提交即整族替换。
// 退役键（template_name/goal/plants/reveals）不在此层出现——后端 PUT 会 422 拒收。

import type { VolumeDetail } from "./types";

export interface VolumeFormData {
  title: string;
  summary: string;
  core_conflict: string;
  ending: string;
  /** 本卷的坎（c-volume-antagonist）：类型闭集＋一句话 */
  antagonist_type: string;
  antagonist_line: string;
  /** 输入框字符串；"" = 不设（payload 置 null 清空） */
  chapter_target: string;
}

export function toVolumeFormData(d: VolumeDetail): VolumeFormData {
  return {
    title: d.title || "",
    summary: d.summary || "",
    core_conflict: d.core_conflict || "",
    ending: d.ending || "",
    antagonist_type: d.antagonist_type || "",
    antagonist_line: d.antagonist_line || "",
    chapter_target: d.chapter_target != null ? String(d.chapter_target) : "",
  };
}

export function volumeFormToPayload(f: VolumeFormData): Record<string, unknown> {
  const target = f.chapter_target.trim();
  return {
    title: f.title.trim(),
    summary: f.summary,
    core_conflict: f.core_conflict,
    ending: f.ending,
    antagonist_type: f.antagonist_type || null,
    antagonist_line: f.antagonist_line,
    chapter_target: target === "" ? null : Number(target),
  };
}
