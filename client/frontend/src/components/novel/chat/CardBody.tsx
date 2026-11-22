// CardBody——产物卡体（按 kind 渲染 payload；c-agent-chat-memory 批1 自 ChatDock
// 原样抽出：ChatDock 退役后卡面由 Aui2Dock 的 cardConfig 继续消费，视觉零变化）。
import type React from "react";

/** 已知键的中文标签（通用兜底渲染用；未收录键回退原键名）。 */
const GENERIC_LABELS: Record<string, string> = {
  directions: "剧情方向", versions: "剧情清单", plans: "本卷走法", branches: "支线候选",
  candidates: "候选", items: "清单", entry: "进场", exit: "退场", beat: "拍点",
  who: "谁", place: "地点", moves: "走向", spine: "主轴", conflict: "冲突",
  ending: "结局", focus: "侧重", focus_axis: "侧重轴", antagonist_type: "反派类型",
  axis: "轴", stage: "阶段", grade: "评级", note: "备注", summary: "概要",
  characters: "角色", name: "名", synopsis: "梗概", label: "标签", hints: "提示",
  rows: "逐段盘点", verdict: "判定", echo: "段落原文", role: "角色",
  persona: "人设", duty: "差事", entrance: "进场", exit_note: "退场",
  checks: "自检", warnings: "提醒", diff: "差异", one_liner: "一句话",
  constraints_used: "写法约束", value: "内容", theme: "题材", sub_genre: "子类",
  reason: "理由",
};

/** 设定字段 → 人话标签（设定卡主键是 stype/field，不能再露 value 裸键）。 */
const SETTINGS_FIELD_LABELS: Record<string, string> = {
  core_promise: "主要看什么",
  forbidden_list: "绝对禁止",
  cost_ratio: "吃苦指数",
  battlefield: "本小说斗什么",
  theme: "题材",
  sub_genre: "子类",
  synopsis: "简介",
  no_power: "现实向开关",
  stage: "世界舞台",
  power: "力量体系",
  cost: "力量的代价",
  history: "历史与旧账",
  factions: "势力",
  constraints: "世界铁律",
  extra: "更多世界细节",
};

function genericLabel(k: string): string {
  return GENERIC_LABELS[k] ?? k;
}

function genericValue(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v.trim();
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v).slice(0, 120);
  } catch {
    return String(v);
  }
}

/** 未知 payload 的结构化人话渲染：字符串字段逐行、对象字段展开一层、
 *  列表逐条编号。全部为空/噪音时返回 null（不渲染空卡）。 */
function renderGenericPayload(data: Record<string, unknown>): React.ReactNode | null {
  const NOISE = new Set(["ok", "act", "source", "pacing_fingerprint", "is_final", "why_not_old"]);
  const entries = Object.entries(data).filter(
    ([k, v]) => !NOISE.has(k) && !(k in GENERIC_LABELS && k === "diff") && v != null &&
      !(Array.isArray(v) && v.length === 0) &&
      (typeof v !== "object" || JSON.stringify(v) !== "{}"),
  );
  const out: React.ReactNode[] = [];
  let n = 0;
  for (const [k, v] of entries) {
    const label = genericLabel(k);
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      const t = genericValue(v);
      if (t) {
        n += 1;
        out.push(
          <div key={k} className="cd-draft-row">
            <b>{label}</b>
            <span>{_clip(t, 300)}</span>
          </div>,
        );
      }
    } else if (Array.isArray(v)) {
      const objs = v.filter((x) => x && typeof x === "object");
      if (objs.length) {
        n += 1;
        out.push(
          <div key={k} className="cd-generic-list">
            <b>{label}</b>
            {objs.map((item, i) => {
              const fields = Object.entries(item as Record<string, unknown>).filter(
                ([ik, iv]) => !NOISE.has(ik) && genericValue(iv),
              );
              return (
                <div key={i} className="cd-generic-item">
                  <b>
                    {label}
                    {String(i + 1)}
                  </b>
                  {fields.map(([ik, iv]) => (
                    <div key={ik} className="cd-draft-row">
                      <b>{genericLabel(ik)}</b>
                      <span>{_clip(genericValue(iv), 160)}</span>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>,
        );
      } else {
        const strs = v.map((x) => genericValue(x)).filter(Boolean);
        if (strs.length) {
          n += 1;
          out.push(
            <div key={k} className="cd-generic-list">
              <b>{label}</b>
              {strs.map((t, i) => (
                <div key={i}>
                  {_clip(t, 160)}
                </div>
              ))}
            </div>,
          );
        }
      }
    } else if (typeof v === "object") {
      const fields = Object.entries(v as Record<string, unknown>).filter(
        ([ik, iv]) => !NOISE.has(ik) && genericValue(iv),
      );
      if (fields.length) {
        n += 1;
        out.push(
          <div key={k} className="cd-generic-list">
            <b>{label}</b>
            {fields.map(([ik, iv]) => (
              <div key={ik} className="cd-draft-row">
                <b>{genericLabel(ik)}</b>
                <span>{_clip(genericValue(iv), 160)}</span>
              </div>
            ))}
          </div>,
        );
      }
    }
  }
  return n > 0 ? out : null;
}

export function _clip(text: string, budget: number): string {
  if (text.length <= budget) return text;
  return `${text.slice(0, budget - 1)}…`;
}

/** 产物卡体：按 cardKind 渲染 payload 摘要（struct/text/report/pick/gate）。 */
export function CardBody({ kind, payload }: { kind: string; payload: unknown }) {
  const data = (payload ?? {}) as Record<string, unknown>;
  if (kind === "report") {
    const groups = (data.report as { name: string; items: { status: string; text: string }[] }[] | undefined) ?? [];
    return (
      <div className="cd-report">
        {groups.map((g) => (
          <div key={g.name} className="cd-report-g">
            <b>{g.name}</b>
            <ul>
              {g.items.map((it, i) => (
                <li key={i} className={`cd-st-${it.status}`}>
                  {it.text}
                </li>
              ))}
            </ul>
          </div>
        ))}
        {groups.length === 0 && <p className="cd-dim">（报告为空）</p>}
      </div>
    );
  }
  if (kind === "pick") {
    const candidates = (data.candidates as { name: string; rationale: string }[] | undefined) ?? [];
    return (
      <ul className="cd-pick">
        {candidates.map((c) => (
          <li key={c.name}>
            <b>{c.name}</b>
            <span className="cd-dim"> — {c.rationale}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (kind === "struct" && Array.isArray(data.characters)) {
    const characters = data.characters as { name: string; role: string; persona: string; origin_note?: string; origin?: string }[];
    return (
      <div>
        {characters.map((c) => (
          <div key={c.name} className="cd-char">
            <b>
              {c.name}
              {c.origin === "divergent" && <span className="cd-badge">草案·发散</span>}
            </b>
            <span className="cd-dim">（{c.role}）</span>
            <p>{c.persona}</p>
            {c.origin_note && <p className="cd-anchor">锚点：{c.origin_note}</p>}
          </div>
        ))}
      </div>
    );
  }
  // 角色草案确认卡（draft_character）：字段化＋确认·建卡（作家点确认才调建卡）
  if (data.character_draft) {
    const d = data.character_draft as Record<string, string>;
    const rows: [string, string][] = [
      ["名字", d.name ?? ""],
      ["性别年龄", d.gender_age ?? ""],
      ["身份背景", d.identity ?? ""],
      ["与现有角色关系", d.relation ?? ""],
      ["剧情功能", d.function ?? ""],
      ["性格特质", d.personality ?? ""],
    ];
    return (
      <div className="cd-draft" data-testid="char-draft-card">
        {rows
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className="cd-draft-row">
              <b>{k}</b>
              <span>{v}</span>
            </div>
          ))}

      </div>
    );
  }
  // 章纲补全卡（settings_og_fill）：fills 逐项字段化
  if (data.fills && typeof data.fills === "object") {
    const fills = data.fills as Record<string, unknown>;
    const LABELS: Record<string, string> = {
      summary: "一句话概要", characters: "出场角色", changes: "必须完成的变化",
      prohibitions: "必须维持悬念", mood: "阶段",
    };
    return (
      <div className="cd-draft">
        {Object.entries(fills).map(([k, v]) => (
          <div key={k} className="cd-draft-row">
            <b>{LABELS[k] ?? k}</b>
            <span>{typeof v === "string" ? v : JSON.stringify(v)}</span>
          </div>
        ))}
        <p className="cd-dim">产物不落库——到章纲表单核对后采纳保存。</p>
      </div>
    );
  }
  // 设定字段卡（settings_genre_* / write_settings_field 产物）：按字段中文名渲染。
  // c-agent-genre-pick：01 题材目录卡单独走「题材/子类/理由」，其余字段也不再露裸 value。
  if (data.stype != null && data.field != null) {
    const field = String(data.field);
    if (field === "catalog") {
      const v = (data.value ?? {}) as Record<string, unknown>;
      const theme = String(v.theme ?? "").trim();
      const sub = String(v.sub_genre ?? "").trim();
      const note = String(v.note ?? "").trim();
      return (
        <div className="cd-draft" data-testid="genre-pick-card">
          <div className="cd-draft-row">
            <b>题材</b>
            <span>{theme || "（未定）"}</span>
          </div>
          {sub ? (
            <div className="cd-draft-row">
              <b>子类</b>
              <span>{sub}</span>
            </div>
          ) : null}
          {note ? (
            <div className="cd-draft-row">
              <b>理由</b>
              <span>{_clip(note, 300)}</span>
            </div>
          ) : null}
        </div>
      );
    }
    const label = SETTINGS_FIELD_LABELS[field] ?? field;
    const value = data.value;
    const rows: [string, string][] = [];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const v = value as Record<string, unknown>;
      const main = v.value ?? v.text ?? v.draft ?? "";
      const note = v.note ?? v.remark ?? "";
      if (main !== "") rows.push([label, String(main)]);
      if (note !== "") rows.push(["备注", String(note)]);
    } else if (Array.isArray(value)) {
      const texts = value
        .map((x) => {
          if (x && typeof x === "object") {
            const o = x as Record<string, unknown>;
            return String(o.text ?? o.tagId ?? "");
          }
          return String(x ?? "");
        })
        .filter(Boolean);
      if (texts.length) rows.push([label, texts.join("、")]);
    } else if (value != null) {
      rows.push([label, String(value)]);
    }
    if (rows.length) {
      return (
        <div className="cd-draft">
          {rows.map(([k, v]) => (
            <div key={k} className="cd-draft-row">
              <b>{k}</b>
              <span>{_clip(v, 300)}</span>
            </div>
          ))}
        </div>
      );
    }
  }
  // 设定字段 AI 卡（settings_* 工具）：字符串值直渲染；对象值走通用人话渲染
  // （禁 JSON.stringify 上对话框——boss 红线 2026-11-16，简介卡 result 曾整段裸 JSON）
  if (data.value != null || data.result != null) {
    const body = data.value != null ? data.value : data.result;
    if (typeof body === "string") {
      return <div className="cd-md cd-settings">{body}</div>;
    }
    const generic = renderGenericPayload(body as Record<string, unknown>);
    if (generic) {
      return <div className="cd-md cd-settings">{generic}</div>;
    }
    return null;
  }
  // 卷纲草稿（draft_volume_expand 卡）：字段化渲染，禁裸 JSON
  if (data.draft && typeof data.draft === "object") {
    const d = data.draft as Record<string, unknown>;
    const rows: [string, unknown][] = [
      ["卷名", d.name],
      ["主旨", d.summary],
      ["核心冲突", d.conflict],
      ["卷末", d.ending],
      ["对手线", d.antagonist_line],
      ["章节目标", d.chapter_target],
    ];
    return (
      <div className="cd-draft">
        {rows
          .filter(([, v]) => v != null && String(v).trim())
          .map(([k, v]) => (
            <div key={k} className="cd-draft-row">
              <b>{k}</b>
              <span>{String(v)}</span>
            </div>
          ))}
        {Array.isArray(d.plants) && d.plants.length > 0 && (
          <p className="cd-dim">埋设 {d.plants.length} 条 · 揭示 {Array.isArray(d.reveals) ? d.reveals.length : 0} 条</p>
        )}
      </div>
    );
  }
  // text/其余：分段正文
  const diff = data.diff as { one_liner?: string[] } | undefined;
  if (Array.isArray(diff?.one_liner)) {
    return (
      <ol className="cd-lines">
        {(diff?.one_liner ?? []).map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ol>
    );
  }
  // 人话 draft（收编工具产卡：推演/抽卡/盘点）——禁裸 JSON 上对话（boss 红线）
  if (typeof data.draft === "string" && data.draft.trim()) {
    return <p className="cd-pre">{_clip(data.draft, 1200)}</p>;
  }
  // 通用兜底：未知 payload 走结构化人话渲染（中文标签＋列表/条目展开），
  // 禁 JSON.stringify——程序文案不上对话框（boss 红线 2026-11-16）
  const generic = renderGenericPayload(data);
  if (generic) {
    return <div className="cd-generic">{generic}</div>;
  }
  const text = typeof payload === "string" ? payload : "";
  return text ? <p className="cd-pre">{_clip(text, 900)}</p> : null;
}
