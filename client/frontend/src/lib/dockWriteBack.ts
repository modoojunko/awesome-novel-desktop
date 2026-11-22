// dockWriteBack——产物卡「采纳 · 写入」按卡种写回器（c-agent-panel-consolidate）。
// 从 Aui2Dock 抽出为纯函数（lib 层可单测）；写回走各面既有 PUT/建卡链，
// 写完由调用方（ArtifactCard）上抛 refreshDomain 走宿主 dirty 守卫刷新面板。

// 世界观文本格 sink（factions/constraints 是条目数组——文本草稿不直写，回执引导手动贴）
const WORLD_TEXT_SINKS = new Set(["stage", "power", "cost"]);

export function worldTopicWritable(topic: string): boolean {
  return WORLD_TEXT_SINKS.has(topic);
}

export async function writeBackVolume(
  projectId: string,
  payload: Record<string, unknown>,
): Promise<string> {
  const draft = payload.draft as Record<string, unknown>;
  const volNo = payload.vol_no as number;
  const { api } = await import("@/lib/api");
  await api.put(`/novels/${projectId}/volumes/vol-${volNo}`, {
    title: draft.name,
    summary: draft.summary,
    core_conflict: draft.conflict,
    ending: draft.ending,
    chapter_target: draft.chapter_target,
    antagonist_type: draft.antagonist_type,
    antagonist_line: draft.antagonist_line,
  });
  return `已写入第 ${volNo} 卷的卷纲要点，可继续改。`;
}

export async function writeBackSettingsField(
  projectId: string,
  payload: Record<string, unknown>,
): Promise<string> {
  const stype = String(payload.stype ?? "");
  const field = String(payload.field ?? "");
  if (!stype || !field || payload.value == null) {
    throw new Error("这张卡没带写入位置（stype/field 缺失）——回面板手动贴一下。");
  }
  const { api } = await import("@/lib/api");
  const cur = (await api.get(`/novels/${projectId}/settings/${stype}`)) as Record<string, unknown> | null;
  const data = { ...(cur ?? {}) };
  // 01 题材目录卡（c-agent-genre-pick）：theme/sub_genre 成对写，其余字段保持。
  if (field === "catalog") {
    const one = (payload.value ?? {}) as Record<string, unknown>;
    const theme = String(one.theme ?? "").trim();
    const sub = String(one.sub_genre ?? "").trim();
    if (!theme) throw new Error("这张卡没带题材——回题材面板手动选一下。");
    data.theme = theme;
    data.sub_genre = sub;
    await api.put(`/novels/${projectId}/settings/${stype}`, data);
    return `已写进 01 题材：${theme}${sub ? ` / ${sub}` : ""}。`;
  }
  // core_promise 特例（review P2）：生成核出 {value, note}——value→短标签字段、
  // note→promise_note（面板同款映射，GenreSettingForm 250 行同构）；其余字段原样直写
  // （forbidden_list/battlefield 为归一化数组、cost_ratio 为数值——形状即契约）。
  // 多看点数组（复测 P2 补刀）：镜像面板多选语义——core_promise 置空、note 拼接各条，
  // 不把数组塞进字符串字段（toString＝[object Object] 污染）。
  let merged: Record<string, unknown> = { [field]: payload.value };
  if (field === "core_promise" && payload.value != null) {
    const v = payload.value;
    if (Array.isArray(v)) {
      const notes = v
        .map((item) => {
          const it = item as Record<string, unknown>;
          return String(it.note || it.value || "").trim();
        })
        .filter(Boolean);
      merged = { core_promise: "", promise_note: notes.join("\n") };
    } else if (typeof v === "object") {
      const one = v as Record<string, unknown>;
      const note = String(one.note ?? "").trim();
      merged = { core_promise: String(one.value ?? "") };
      if (note) merged.promise_note = note; // 空 note 不洗掉既有 promise_note
    }
  }
  for (const [k, v] of Object.entries(merged)) {
    data[k] = v;
  }
  await api.put(`/novels/${projectId}/settings/${stype}`, data);
  return "已写进设定并保存——切回面板就能看到（面板有未保存修改时保持你的版本）。";
}

export async function writeBackWorld(
  projectId: string,
  payload: Record<string, unknown>,
): Promise<string> {
  const topic = String(payload.topic ?? "");
  const draft = String(payload.draft ?? "").trim();
  if (!topic || !draft) {
    throw new Error("这张卡没带写入位置（topic/draft 缺失）——回面板手动贴一下。");
  }
  if (!worldTopicWritable(topic)) {
    throw new Error(`「${topic}」是条目格，草稿是散文形态——照着卡在面板上贴成条目更稳。`);
  }
  const { api } = await import("@/lib/api");
  const cur = (await api.get(`/novels/${projectId}/settings/world`)) as Record<string, unknown> | null;
  const data = { ...(cur ?? {}) };
  // 生成端偶发双层 JSON 串（后端已剥一层，这里再兜一次）——存纯文本
  let text = draft;
  try {
    const inner = JSON.parse(draft);
    if (inner && typeof inner === "object" && typeof (inner as { value?: unknown }).value === "string") {
      text = String((inner as { value: unknown }).value);
    }
  } catch {
    /* 非 JSON 串原样写 */
  }
  data[topic] = text;
  await api.put(`/novels/${projectId}/settings/world`, data);
  return "已写进世界设定并保存——切回面板就能看到。";
}

export async function writeBackCharacter(
  projectId: string,
  payload: Record<string, unknown>,
): Promise<string> {
  const d = payload.character_draft as Record<string, unknown> | undefined;
  if (!d || typeof d !== "object") {
    throw new Error("这张卡没带角色草案。");
  }
  const { charactersApi } = await import("@/lib/charactersApi");
  const name = String(d.name ?? "");
  // 空书第一张卡＝主角（与 CharacterManager 手动建卡同判据；review P3 对齐）
  const list = await charactersApi.list(projectId);
  const role = list.items.length === 0 ? "主角" : "配角";
  const created = await charactersApi.create(projectId, name, { role });
  const personality = String(d.personality ?? "").trim();
  if (personality) {
    await charactersApi.patch(projectId, created.id, "persona", personality, 0);
  }
  const rest = [d.gender_age, d.identity, d.relation, d.function].filter((x) => String(x ?? "").trim());
  return rest.length
    ? `新角色「${name || created.id}」已建卡（${role}）：名字和人设写进去了；性别年龄/身份/关系/功能这几格在卡上照着补。`
    : `新角色「${name || created.id}」已建卡（${role}）。`;
}
