/** 右栏「AI 辅助」面板（storyline.html col-ai 复刻，workbench-storyline-ai-panel）：
 *  随中栏页签切换——每页签一条引导语＋统计卡＋动作清单。
 *  动作分两种：已实现=真实按钮；未实现=「规划中」占位（禁用，后续逐个补）。
 *  已在中栏页签内提供的动作不在此重复（文风调参/收尾确认等）。 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { chapterNoOf } from "@/lib/chapterRef";

export interface OgStats {
  reqOk: number; // 归档门槛已满足项（六项）
  planWords: number | null;
  keyCount: number;
  castCount: number;
}

interface ChapterLite {
  id: string;
  ref: string;
  chapter: number;
}

interface Act {
  label: string;
  /** 已实现动作的点击；缺省＝规划中占位 */
  onClick?: () => void;
  disabled?: boolean;
  busy?: boolean;
}

const PLACEHOLDER_TITLE = "规划中 · 后续版本提供";

function raStats(pairs: Array<[string, string]>) {
  return (
    <ul className="rail-stats">
      {pairs.map(([k, v]) => (
        <li key={k}>
          <span className="k">{k}</span>
          <span className="v num">{v}</span>
        </li>
      ))}
    </ul>
  );
}

function raActs(acts: Act[], locked: boolean) {
  return (
    <div className={`rail-acts${locked ? " rail-locked" : ""}`}>
      {acts.map((a) =>
        a.onClick ? (
          <button
            key={a.label}
            className="btn btn-secondary btn-sm"
            disabled={locked || a.disabled}
            onClick={a.onClick}
          >
            {a.busy ? `${a.label}…` : a.label}
          </button>
        ) : (
          <button
            key={a.label}
            className="btn btn-secondary btn-sm"
            disabled
            title={PLACEHOLDER_TITLE}
          >
            {a.label}
            <span className="tag-plan">规划中</span>
          </button>
        ),
      )}
    </div>
  );
}

export function AiAssistPanel({
  projectId,
  chapterRef,
  tab,
  isPro,
  ogStats,
  wordCount,
  planWords,
  archived,
  canAiDraft,
  aiDrafting,
  onAiDraft,
  onSimulate,
  staleDownstream,
}: {
  projectId: string;
  chapterRef: string;
  tab: string;
  isPro: boolean;
  ogStats: OgStats;
  wordCount: number;
  planWords: number | null;
  archived: boolean;
  canAiDraft: boolean;
  aiDrafting: boolean;
  onAiDraft: () => void;
  onSimulate: () => void;
  /** chapter-rewrite：下游「基于旧设定」章计数（无数据时显示「—」） */
  staleDownstream?: number;
}) {
  // 页签内轻量数据（与中栏页签同端点；只在对应页签激活时取）
  const [promptSrc, setPromptSrc] = useState<{ total: number; cast: number } | null>(null);
  const [styleStats, setStyleStats] = useState<{ rows: number; shadow: number } | null>(null);
  const [graphStats, setGraphStats] = useState<{ nodes: number; edges: number; here: number } | null>(null);
  const [hookStats, setHookStats] = useState<{
    total: number;
    open: number;
    plantHere: number;
    resolveHere: number;
  } | null>(null);
  const [loreStats, setLoreStats] = useState<{ here: number; until: number } | null>(null);

  const chapterNo = useMemo(() => {
    return chapterNoOf(chapterRef);
  }, [chapterRef]);

  useEffect(() => {
    let cancelled = false;
    if (tab === "prompt") {
      api
        .get(`/novels/${projectId}/chapters/${chapterRef}/prompt-sources`)
        .then((d: { total_chars?: number; cast_count?: number }) => {
          if (!cancelled) setPromptSrc({ total: d.total_chars ?? 0, cast: d.cast_count ?? 0 });
        })
        .catch(() => {
          /* 统计失败静默 */
        });
    }
    if (tab === "style") {
      api
        .get(`/novels/${projectId}/chapters/${chapterRef}/style-shadow/baseline`)
        .then(
          (d: {
            baseline?: Array<{ value?: string }>;
            shadow?: Record<string, unknown>;
          }) => {
            if (!cancelled)
              setStyleStats({
                rows: (d.baseline ?? []).filter((b) => (b.value ?? "").trim()).length,
                shadow: Object.keys(d.shadow ?? {}).length,
              });
          },
        )
        .catch(() => {
          /* 静默 */
        });
    }
    if (tab === "relations") {
      api
        .get(`/novels/${projectId}/characters/graph`)
        .then(
          (d: {
            nodes?: Array<{ id?: string }>;
            edges?: Array<{ origin_chapter?: string | null }>;
          }) => {
            const edges = d.edges ?? [];
            if (!cancelled)
              setGraphStats({
                nodes: (d.nodes ?? []).length,
                edges: edges.length,
                here: edges.filter((e) => e.origin_chapter === chapterRef).length,
              });
          },
        )
        .catch(() => {
          /* 静默 */
        });
    }
    if (tab === "hooks") {
      Promise.all([
        api.get(`/novels/${projectId}/hooks`),
        api.get(`/novels/${projectId}/volumes`),
      ])
        .then(([hd, tree]) => {
          const items = (hd?.data?.items ?? []) as Array<{
            status?: string;
            introduced_chapter_id?: string | null;
            resolved_chapter_id?: string | null;
          }>;
          const lite: ChapterLite[] = [];
          for (const v of (tree ?? []) as Array<{
            name?: string;
            ref?: string;
            chapters?: Array<{ id?: string; chapter: number; ref?: string }>;
          }>) {
            for (const c of v.chapters ?? []) {
              lite.push({
                id: c.id ?? c.ref ?? "",
                ref: c.ref ?? `${v.name ?? v.ref}-ch-${c.chapter}`,
                chapter: c.chapter,
              });
            }
          }
          const cur = lite.find((c) => c.ref === chapterRef)?.id ?? null;
          if (!cancelled)
            setHookStats({
              total: items.length,
              open: items.filter((h) => h.status === "active").length,
              plantHere: items.filter((h) => h.introduced_chapter_id === cur).length,
              resolveHere: items.filter((h) => h.resolved_chapter_id === cur).length,
            });
        })
        .catch(() => {
          /* 静默 */
        });
    }
    if (tab === "settings") {
      Promise.all([
        api.get(`/novels/${projectId}/chapters/${chapterRef}`),
        api.get(`/novels/${projectId}/settings/world`),
      ])
        .then(([ch, world]) => {
          const cast = (ch?.outline?.characters ?? []) as Array<{ state_change?: string }>;
          const here = cast.filter((c) => (c.state_change ?? "").trim()).length;
          const entries = [
            ...((world?.factions ?? []) as Array<{ origin?: string }>),
            ...((world?.history ?? []) as Array<{ origin?: string }>),
            ...((world?.extra ?? []) as Array<{ origin?: string }>),
          ];
          const until = entries.filter((e) => {
            if (!e.origin) return true;
            const n = chapterNoOf(e.origin);
            return n ? n <= chapterNo : true;
          }).length;
          if (!cancelled) setLoreStats({ here, until });
        })
        .catch(() => {
          /* 静默 */
        });
    }
    return () => {
      cancelled = true;
    };
  }, [tab, projectId, chapterRef, chapterNo]);

  const locked = !isPro;

  if (tab === "og") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 章纲</p>
        <p className="rail-lead">按本卷卷纲检查、补全第 {chapterNo} 章的章纲；必填项决定这一章能否归档。</p>
        {raStats([
          ["归档门槛", `${ogStats.reqOk}/6`],
          ["计划字数", ogStats.planWords ? `${ogStats.planWords.toLocaleString("zh-CN")} 字` : "未定"],
          ["关键事件", `${ogStats.keyCount} 条`],
          ["出场角色", `${ogStats.castCount} 人`],
        ])}
        {raActs(
          [
            { label: "剧情推演 · 按回合走一遍", onClick: onSimulate, disabled: archived },
            {
              label: aiDrafting ? "AI 起草中" : "AI 起草",
              onClick: onAiDraft,
              disabled: !canAiDraft || aiDrafting || archived,
              busy: aiDrafting,
            },
            { label: "补全缺失字段" },
            { label: "与卷纲冲突检测" },
          ],
          locked,
        )}
      </div>
    );
  }

  if (tab === "prose") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 正文</p>
        <p className="rail-lead">贴着本章章纲与全书文风，续写、扩写或改写已有的正文。</p>
        {raStats([
          ["正文字数", `${wordCount.toLocaleString("zh-CN")} 字`],
          ["计划字数", planWords ? `${planWords.toLocaleString("zh-CN")} 字` : "未定"],
          [
            "完成度",
            planWords ? `${Math.min(100, Math.round((wordCount / planWords) * 100))}%` : "—",
          ],
          ["状态", archived ? "已归档" : wordCount > 0 ? "草稿" : "待写"],
        ])}
        {raActs([{ label: "压缩啰嗦段落" }], locked)}
      </div>
    );
  }

  if (tab === "prompt") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 提示词</p>
        <p className="rail-lead">
          提示词由六处来源自动组装：全书设定、卷纲、本章章纲、全书文风（含本章调整）、截至上一章的伏笔进展、本章涉及的角色设定。
        </p>
        {raStats([
          ["组装来源", "6 处"],
          ["来源字数", promptSrc ? `${promptSrc.total.toLocaleString("zh-CN")} 字` : "—"],
          ["涉及角色", promptSrc ? `${promptSrc.cast} 人` : "—"],
        ])}
        {raActs(
          [
            { label: "重新组装提示词" },
            { label: "补全负向约束" },
            { label: "精简提示词" },
          ],
          locked,
        )}
      </div>
    );
  }

  if (tab === "settings") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 设定</p>
        <p className="rail-lead">
          从本章正文里提取本章变化，归档时并进全书那一套；回退后自动重算。
        </p>
        {raStats([
          ["本章变化", loreStats ? `${loreStats.here} 条` : "—"],
          ["截至本章条目", loreStats ? `${loreStats.until} 条` : "—"],
          ["基于旧设定", "—"],
        ])}
        {raActs([{ label: "提取本章变化" }], locked)}
      </div>
    );
  }

  if (tab === "style") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 文风</p>
        <p className="rail-lead">
          全书文风基线只读；本章只改这一章的差异项，不写回全书文风。AI 调参在本页签内逐项确认。
        </p>
        {raStats([
          ["全书基线", styleStats ? `${styleStats.rows} 行` : "—"],
          ["本章调整", styleStats ? (styleStats.shadow ? `${styleStats.shadow} 项` : "未调整") : "—"],
          ["硬约束", "见基线"],
        ])}
        {raActs([{ label: "文风一致性检查" }, { label: "标记偏离段落" }], locked)}
      </div>
    );
  }

  if (tab === "relations") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 角色关系</p>
        <p className="rail-lead">关系图是全书统一的一套；这一章可以在图上加新的关系。</p>
        {raStats([
          ["人物与势力", graphStats ? `${graphStats.nodes} 个` : "—"],
          ["关系边", graphStats ? `${graphStats.edges} 条` : "—"],
          ["本章变化的关系", graphStats ? `${graphStats.here} 条` : "—"],
        ])}
        {raActs(
          [
            { label: "识别角色与物品变化" },
            { label: "本章关系变化检测" },
            { label: "关系冲突检测" },
            { label: "建议补边" },
          ],
          locked,
        )}
      </div>
    );
  }

  if (tab === "hooks") {
    return (
      <div className="rail-assist" data-testid="rail-assist">
        <p className="ai-sec">AI 辅助 · 伏笔</p>
        <p className="rail-lead">
          伏笔台账展示到第 {chapterNo} 章为止：本章埋下与回收的条目会被标出，跨章悬置的继续挂着。
        </p>
        {raStats([
          ["悬置", hookStats ? `${hookStats.open} 条` : "—"],
          ["本章埋下", hookStats ? `${hookStats.plantHere} 条` : "—"],
          ["本章回收", hookStats ? `${hookStats.resolveHere} 条` : "—"],
          ["台账总数", hookStats ? `${hookStats.total} 条` : "—"],
        ])}
        {raActs(
          [
            { label: "建议本章回收" },
            { label: "伏笔冲突检测" },
            { label: "登记新伏笔" },
          ],
          locked,
        )}
      </div>
    );
  }

  return (
    <div className="rail-assist" data-testid="rail-assist">
      <p className="ai-sec">AI 辅助 · 操作</p>
      <p className="rail-lead">
        重写、回退、归档都会改动主线与全书设定；归档后的写回提案在「操作」里逐条确认。
      </p>
      {raStats([
        ["归档门槛", `${ogStats.reqOk}/6`],
        ["当前状态", archived ? "已归档" : wordCount > 0 ? "草稿" : "待写"],
        [
          "下游挂着旧设定",
          staleDownstream === undefined ? "—" : `${staleDownstream} 章`,
        ],
        ["正文", `${wordCount.toLocaleString("zh-CN")} 字`],
      ])}
      {raActs([{ label: "生成本章变更摘要" }, { label: "生成下一章建议" }], locked)}
    </div>
  );
}
